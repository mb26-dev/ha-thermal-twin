"""Data coordinator for ThermalTwin: sampling, persistence and learning."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
import math
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    BOOTSTRAP_DAYS,
    CONF_COMFORT_MAX,
    CONF_HVAC_ENTITY,
    CONF_HVAC_TYPE,
    CONF_INDOOR_SENSOR,
    CONF_OUTDOOR_ENTITY,
    CONF_SOLAR_SENSOR,
    CONF_TARGET_TEMPERATURE,
    CONF_WINDOW_SENSORS,
    DEFAULT_TARGET_TEMPERATURE,
    DOMAIN,
    HVAC_TYPE_COOL,
    LOGGER,
    MAX_GAP_S,
    MAX_SAMPLES,
    PREDICTION_HORIZON_H,
    SAMPLE_INTERVAL_S,
    SOLAR_MIN_COVERAGE,
    STORAGE_SAVE_DELAY_S,
    STORAGE_VERSION,
    VENTILATION_HYSTERESIS,
    VENTILATION_MIN_GAIN,
)
from .model import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_PASSIVE,
    ModelParams,
    Sample,
    equilibrium,
    fit_model,
    predict,
    time_to_target,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_INVALID_STATES = {STATE_UNKNOWN, STATE_UNAVAILABLE, "", None}
_HEATING_ACTIONS = {"heating", "preheating"}
_COOLING_ACTIONS = {"cooling"}
_PASSIVE_ACTIONS = {"idle", "off", "fan"}
_TEMP_UNITS = {
    UnitOfTemperature.CELSIUS,
    UnitOfTemperature.FAHRENHEIT,
    UnitOfTemperature.KELVIN,
}


@dataclass(slots=True)
class ThermalTwinData:
    """Snapshot exposed to entities."""

    params: ModelParams = field(default_factory=ModelParams)
    t_in: float | None = None
    t_out: float | None = None
    solar: float | None = None
    mode: int | None = None
    target: float = DEFAULT_TARGET_TEMPERATURE
    time_to_target_min: float | None = None
    target_eta: datetime | None = None
    time_to_target_hvac_min: float | None = None
    target_eta_hvac: datetime | None = None
    equilibrium: float | None = None
    predicted_1h: float | None = None
    ventilation_recommended: bool | None = None
    sample_count: int = 0
    use_solar: bool = False


def _to_float(value: Any) -> float | None:
    if value in _INVALID_STATES:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _domain(state: State) -> str:
    """Return the domain; recorder LazyState objects have no domain attribute."""
    return state.entity_id.split(".", 1)[0]


def read_temperature(state: State | None, default_unit: str) -> float | None:
    """Read a temperature in °C from a sensor or weather state."""
    if state is None or state.state in _INVALID_STATES:
        return None
    if _domain(state) == "weather":
        value = _to_float(state.attributes.get("temperature"))
        unit = state.attributes.get("temperature_unit", default_unit)
    else:
        value = _to_float(state.state)
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, default_unit)
    if value is None:
        return None
    if unit in _TEMP_UNITS and unit != UnitOfTemperature.CELSIUS:
        value = TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS)
    return value


def read_number(state: State | None) -> float | None:
    """Read a plain numeric state."""
    if state is None:
        return None
    return _to_float(state.state)


def determine_mode(
    hvac_state: State | None,
    hvac_configured: bool,
    hvac_type: str,
    window_states: list[State | None],
) -> int | None:
    """Classify a snapshot as passive, heating, cooling or excluded (None)."""
    for window in window_states:
        if window is None or window.state in _INVALID_STATES:
            return None
        if window.state == STATE_ON:
            return None
    if not hvac_configured:
        return MODE_PASSIVE
    if hvac_state is None or hvac_state.state in _INVALID_STATES:
        return None

    if _domain(hvac_state) == "climate":
        action = hvac_state.attributes.get("hvac_action")
        if action is not None:
            if action in _HEATING_ACTIONS:
                return MODE_HEATING
            if action in _COOLING_ACTIONS:
                return MODE_COOLING
            if action in _PASSIVE_ACTIONS:
                return MODE_PASSIVE
            return None
        # No hvac_action reported (e.g. IR controlled units): use hvac mode.
        if hvac_state.state == "heat":
            return MODE_HEATING
        if hvac_state.state == "cool":
            return MODE_COOLING
        if hvac_state.state == "off":
            return MODE_PASSIVE
        return None

    if hvac_state.state == STATE_ON:
        return MODE_COOLING if hvac_type == HVAC_TYPE_COOL else MODE_HEATING
    return MODE_PASSIVE


class ThermalTwinCoordinator(DataUpdateCoordinator[ThermalTwinData]):
    """Collect samples, learn the room model and compute predictions."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.title}",
            update_interval=timedelta(seconds=SAMPLE_INTERVAL_S),
        )
        opts = entry.options
        self.indoor_sensor: str = opts[CONF_INDOOR_SENSOR]
        self.outdoor_entity: str = opts[CONF_OUTDOOR_ENTITY]
        self.target: float = float(
            opts.get(CONF_TARGET_TEMPERATURE, DEFAULT_TARGET_TEMPERATURE)
        )
        self.hvac_entity: str | None = opts.get(CONF_HVAC_ENTITY) or None
        self.hvac_type: str = opts.get(CONF_HVAC_TYPE, "heat")
        self.window_sensors: list[str] = list(opts.get(CONF_WINDOW_SENSORS) or [])
        self.solar_sensor: str | None = opts.get(CONF_SOLAR_SENSOR) or None
        comfort_max = opts.get(CONF_COMFORT_MAX)
        self.comfort_max: float | None = (
            float(comfort_max) if comfort_max not in (None, "") else None
        )

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._samples: deque[Sample] = deque(maxlen=MAX_SAMPLES)
        self._params = ModelParams()
        self._use_solar = False
        self._ventilation_on = False

    # ------------------------------------------------------------------ setup

    @property
    def fingerprint(self) -> str:
        """Identify the sensor set; stored samples are invalid if it changes."""
        return "|".join(
            [
                self.indoor_sensor,
                self.outdoor_entity,
                self.hvac_entity or "",
                self.hvac_type,
                ",".join(sorted(self.window_sensors)),
                self.solar_sensor or "",
            ]
        )

    @property
    def samples(self) -> list[Sample]:
        """Return a copy of the stored samples."""
        return list(self._samples)

    @property
    def params(self) -> ModelParams:
        """Return the current model parameters."""
        return self._params

    async def async_initialize(self) -> None:
        """Load persisted samples or bootstrap from recorder history."""
        stored = await self._store.async_load()
        if stored and stored.get("fingerprint") == self.fingerprint:
            for raw in stored.get("samples", []):
                try:
                    self._samples.append(Sample.from_list(raw))
                except (TypeError, ValueError, IndexError):
                    continue
            LOGGER.debug(
                "%s: loaded %s stored samples", self.config_entry.title, len(self._samples)
            )
        else:
            await self._async_bootstrap_from_history()
            await self._async_save_now()
        await self._async_refit()

    async def async_reset(self) -> None:
        """Forget everything and relearn from recorder history."""
        self._samples.clear()
        self._params = ModelParams()
        await self._async_bootstrap_from_history()
        await self._async_save_now()
        await self._async_refit()
        self.async_set_updated_data(self._build_data())

    async def async_shutdown_store(self) -> None:
        """Persist samples on unload."""
        await self._async_save_now()

    # ------------------------------------------------------------ persistence

    def _serialize(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "samples": [s.to_list() for s in self._samples],
        }

    async def _async_save_now(self) -> None:
        await self._store.async_save(self._serialize())

    # -------------------------------------------------------------- bootstrap

    def _tracked_entities(self) -> list[str]:
        entities = [self.indoor_sensor, self.outdoor_entity, *self.window_sensors]
        if self.hvac_entity:
            entities.append(self.hvac_entity)
        if self.solar_sensor:
            entities.append(self.solar_sensor)
        return entities

    async def _async_bootstrap_from_history(self) -> None:
        """Seed samples from the recorder so the model is useful immediately."""
        if "recorder" not in self.hass.config.components:
            return
        # Imported lazily: recorder is an optional after_dependency.
        from homeassistant.components.recorder import get_instance, history  # noqa: PLC0415

        end = dt_util.utcnow()
        start = end - timedelta(days=BOOTSTRAP_DAYS)
        entity_ids = self._tracked_entities()
        try:
            history_states: dict[str, list[State]] = await get_instance(
                self.hass
            ).async_add_executor_job(
                partial(
                    history.get_significant_states,
                    self.hass,
                    start,
                    end,
                    entity_ids,
                    None,
                    include_start_time_state=True,
                    significant_changes_only=False,
                    minimal_response=False,
                    no_attributes=False,
                )
            )
        except Exception:  # noqa: BLE001 - history is best effort
            LOGGER.warning(
                "%s: could not read recorder history, learning from scratch",
                self.config_entry.title,
                exc_info=True,
            )
            return

        try:
            samples = await self.hass.async_add_executor_job(
                self._resample_history,
                history_states,
                start.timestamp(),
                end.timestamp(),
            )
        except Exception:  # noqa: BLE001 - history is best effort
            LOGGER.warning(
                "%s: could not process recorder history, learning from scratch",
                self.config_entry.title,
                exc_info=True,
            )
            return
        self._samples.extend(samples)
        LOGGER.info(
            "%s: bootstrapped %s samples from %s days of history",
            self.config_entry.title,
            len(samples),
            BOOTSTRAP_DAYS,
        )

    def _resample_history(
        self, history_states: dict[str, list[State]], start_ts: float, end_ts: float
    ) -> list[Sample]:
        """Turn irregular state history into a regular sample grid."""
        series = {
            entity_id: sorted(states, key=lambda s: s.last_updated)
            for entity_id, states in history_states.items()
        }
        pointers = dict.fromkeys(series, -1)

        def state_at(entity_id: str, ts: float) -> State | None:
            states = series.get(entity_id)
            if not states:
                return None
            idx = pointers[entity_id]
            while idx + 1 < len(states) and states[idx + 1].last_updated.timestamp() <= ts:
                idx += 1
            pointers[entity_id] = idx
            return states[idx] if idx >= 0 else None

        default_unit = self.hass.config.units.temperature_unit
        samples: list[Sample] = []
        ts = start_ts - (start_ts % SAMPLE_INTERVAL_S) + SAMPLE_INTERVAL_S
        while ts <= end_ts:
            sample = self._make_sample(ts, state_at, default_unit)
            if sample is not None:
                samples.append(sample)
            ts += SAMPLE_INTERVAL_S
        return samples

    # --------------------------------------------------------------- sampling

    def _make_sample(self, ts: float, state_of, default_unit: str) -> Sample | None:
        t_in = read_temperature(state_of(self.indoor_sensor, ts), default_unit)
        t_out = read_temperature(state_of(self.outdoor_entity, ts), default_unit)
        if t_in is None or t_out is None:
            return None
        solar = read_number(state_of(self.solar_sensor, ts)) if self.solar_sensor else None
        mode = determine_mode(
            state_of(self.hvac_entity, ts) if self.hvac_entity else None,
            self.hvac_entity is not None,
            self.hvac_type,
            [state_of(w, ts) for w in self.window_sensors],
        )
        return Sample(ts=ts, t_in=t_in, t_out=t_out, solar=solar, mode=mode)

    def _live_state(self, entity_id: str, _ts: float) -> State | None:
        return self.hass.states.get(entity_id)

    async def _async_refit(self) -> None:
        samples = list(self._samples)
        if self.solar_sensor:
            usable = [s for s in samples if s.mode is not None]
            with_solar = sum(1 for s in usable if s.solar is not None)
            self._use_solar = bool(usable) and with_solar / len(usable) >= SOLAR_MIN_COVERAGE
        else:
            self._use_solar = False
        self._params = await self.hass.async_add_executor_job(
            fit_model, samples, self._use_solar, MAX_GAP_S
        )

    async def _async_update_data(self) -> ThermalTwinData:
        """Take a sample, relearn and compute predictions."""
        now_ts = dt_util.utcnow().timestamp()
        sample = self._make_sample(
            now_ts, self._live_state, self.hass.config.units.temperature_unit
        )
        if sample is not None:
            self._samples.append(sample)
            self._store.async_delay_save(self._serialize, STORAGE_SAVE_DELAY_S)
        await self._async_refit()
        return self._build_data()

    # ------------------------------------------------------------ predictions

    def _build_data(self) -> ThermalTwinData:
        default_unit = self.hass.config.units.temperature_unit
        t_in = read_temperature(self.hass.states.get(self.indoor_sensor), default_unit)
        t_out = read_temperature(self.hass.states.get(self.outdoor_entity), default_unit)
        solar = (
            read_number(self.hass.states.get(self.solar_sensor))
            if self.solar_sensor and self._use_solar
            else None
        )
        if self._use_solar and solar is None:
            solar = 0.0
        mode = determine_mode(
            self.hass.states.get(self.hvac_entity) if self.hvac_entity else None,
            self.hvac_entity is not None,
            self.hvac_type,
            [self.hass.states.get(w) for w in self.window_sensors],
        )
        params = self._params
        data = ThermalTwinData(
            params=params,
            t_in=t_in,
            t_out=t_out,
            solar=solar,
            mode=mode,
            target=self.target,
            sample_count=len(self._samples),
            use_solar=self._use_solar,
        )
        if t_in is None or t_out is None:
            return data

        # Ventilation advice is pure physics and works before training.
        # Hysteresis: switch on above comfort_max + 0.5 °C with outdoor at
        # least 1 °C cooler; stay on until the room is back at comfort_max or
        # outdoor is no longer cooler at all.
        if self.comfort_max is not None:
            if self._ventilation_on:
                self._ventilation_on = t_in > self.comfort_max and t_out < t_in
            else:
                self._ventilation_on = (
                    t_in >= self.comfort_max + VENTILATION_HYSTERESIS
                    and t_out <= t_in - VENTILATION_MIN_GAIN
                )
            data.ventilation_recommended = self._ventilation_on

        if not params.is_trained:
            return data

        now = dt_util.utcnow()
        data.equilibrium = equilibrium(params, t_out, solar)
        data.predicted_1h = predict(params, t_in, t_out, solar, PREDICTION_HORIZON_H)

        hours = time_to_target(params, t_in, t_out, solar, self.target)
        if hours is not None:
            data.time_to_target_min = round(hours * 60, 0)
            data.target_eta = now + timedelta(hours=hours)

        if self.hvac_entity:
            rate = params.heating_rate if self.target > t_in else params.cooling_rate
            if rate is not None:
                hours = time_to_target(params, t_in, t_out, solar, self.target, rate)
                if hours is not None:
                    data.time_to_target_hvac_min = round(hours * 60, 0)
                    data.target_eta_hvac = now + timedelta(hours=hours)
        return data
