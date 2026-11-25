"""Data coordinator for ThermalTwin: sampling, persistence and learning."""

from __future__ import annotations

from bisect import bisect_left
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from functools import partial
import math
from typing import TYPE_CHECKING, Any

from astral import Observer
from astral.sun import elevation as solar_elevation

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import PowerConverter, TemperatureConverter

from .const import (
    BOOTSTRAP_DAYS,
    CONF_COMFORT_MAX,
    CONF_COMFORT_MIN,
    CONF_HUMIDITY_MAX,
    CONF_HVAC_ENTITY,
    CONF_HVAC_TYPE,
    CONF_INDOOR_HUMIDITY,
    CONF_INDOOR_SENSOR,
    CONF_OUTDOOR_ENTITY,
    CONF_OUTDOOR_HUMIDITY,
    CONF_POWER_SENSOR,
    CONF_POWER_THRESHOLD,
    CONF_READY_BY,
    CONF_READY_TEMPERATURE,
    CONF_SOLAR_SENSOR,
    CONF_TARGET_TEMPERATURE,
    CONF_USE_SUN,
    CONF_WEATHER_ENTITY,
    CONF_WINDOW_SENSORS,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_POWER_THRESHOLD,
    DEFAULT_TARGET_TEMPERATURE,
    DOMAIN,
    DRY_MODE_TEMP_MARGIN,
    FORECAST_BIAS_DECAY_H,
    FORECAST_HORIZON_H,
    FORECAST_POINT_STEP_H,
    HVAC_TYPE_COOL,
    LOGGER,
    MAX_GAP_S,
    MAX_SAMPLES,
    PRECONDITION_MAX_LEAD_H,
    PREDICTION_HORIZON_H,
    SAMPLE_INTERVAL_S,
    SETPOINT_BAND,
    SOLAR_MIN_COVERAGE,
    SOLAR_MIN_GAIN,
    STORAGE_SAVE_DELAY_S,
    STORAGE_VERSION,
    TARGET_SEARCH_H,
    VENTILATION_HYSTERESIS,
    VENTILATION_MAX_EXTRA_HUMIDITY,
    VENTILATION_MIN_GAIN,
    WEATHER_REFRESH_S,
)
from .model import (
    MODE_COOLING,
    MODE_HEATING,
    MODE_PASSIVE,
    ModelParams,
    Precondition,
    Sample,
    absolute_humidity,
    dew_point,
    equilibrium,
    first_crossing,
    fit_model,
    heat_index,
    plan_precondition,
    simulate,
    sun_factor,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_INVALID_STATES = {STATE_UNKNOWN, STATE_UNAVAILABLE, "", None}
_HEATING_ACTIONS = {"heating", "preheating"}
_COOLING_ACTIONS = {"cooling", "drying"}
_PASSIVE_ACTIONS = {"idle", "off", "fan"}
_TEMP_UNITS = {
    UnitOfTemperature.CELSIUS,
    UnitOfTemperature.FAHRENHEIT,
    UnitOfTemperature.KELVIN,
}
_POWER_UNITS = {UnitOfPower.WATT, UnitOfPower.KILO_WATT, UnitOfPower.MILLIWATT}


@dataclass(slots=True)
class ThermalTwinData:
    """Snapshot exposed to entities."""

    params: ModelParams = field(default_factory=ModelParams)
    t_in: float | None = None
    t_out: float | None = None
    solar: float | None = None
    mode: int | None = None
    hvac_on: bool | None = None
    power: float | None = None
    target: float = DEFAULT_TARGET_TEMPERATURE
    time_to_target_min: float | None = None
    target_eta: datetime | None = None
    time_to_target_hvac_min: float | None = None
    target_eta_hvac: datetime | None = None
    equilibrium: float | None = None
    predicted_1h: float | None = None
    ventilation_recommended: bool | None = None
    ventilation_blocked_by_humidity: bool = False
    sample_count: int = 0
    use_solar: bool = False
    solar_source: str | None = None
    # humidity
    rh_in: float | None = None
    rh_out: float | None = None
    abs_in: float | None = None
    abs_out: float | None = None
    dew_point: float | None = None
    apparent: float | None = None
    dry_recommended: bool | None = None
    # planning
    precondition: Precondition | None = None
    ready_at: datetime | None = None
    ready_temperature: float | None = None
    forecast: list[list[float | None]] = field(default_factory=list)
    uses_weather_forecast: bool = False
    # usage
    runtime_today_min: float | None = None
    energy_today_kwh: float | None = None
    efficiency: float | None = None
    status: str = "learning"


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


def read_humidity(state: State | None) -> float | None:
    """Read relative humidity in % from a sensor or weather state."""
    if state is None or state.state in _INVALID_STATES:
        return None
    if _domain(state) == "weather":
        value = _to_float(state.attributes.get("humidity"))
    else:
        value = _to_float(state.state)
    if value is None or not 0 < value <= 100:
        return None
    return value


def read_power(state: State | None) -> float | None:
    """Read a power value in W."""
    if state is None:
        return None
    value = _to_float(state.state)
    if value is None:
        return None
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, UnitOfPower.WATT)
    if unit in _POWER_UNITS and unit != UnitOfPower.WATT:
        value = PowerConverter.convert(value, unit, UnitOfPower.WATT)
    return value


def read_number(state: State | None) -> float | None:
    """Read a plain numeric state."""
    if state is None:
        return None
    return _to_float(state.state)


def _direction(hvac_state: State | None, hvac_type: str) -> int:
    """Which way an active HVAC unit pushes the temperature."""
    if hvac_state is not None and _domain(hvac_state) == "climate":
        if hvac_state.state in ("heat",):
            return MODE_HEATING
        if hvac_state.state in ("cool", "dry"):
            return MODE_COOLING
    return MODE_COOLING if hvac_type == HVAC_TYPE_COOL else MODE_HEATING


def hvac_is_on(hvac_state: State | None, power: float | None, threshold: float) -> bool | None:
    """Return whether the unit is switched on / drawing power."""
    if power is not None:
        return power >= threshold
    if hvac_state is None or hvac_state.state in _INVALID_STATES:
        return None
    if _domain(hvac_state) == "climate":
        return hvac_state.state not in ("off", "fan_only")
    return hvac_state.state == STATE_ON


def determine_mode(
    hvac_state: State | None,
    hvac_configured: bool,
    hvac_type: str,
    window_states: list[State | None],
    t_in: float | None = None,
    power_state: State | None = None,
    power_configured: bool = False,
    power_threshold: float = DEFAULT_POWER_THRESHOLD,
) -> int | None:
    """Classify a snapshot as passive, heating, cooling or excluded (None)."""
    for window in window_states:
        if window is None or window.state in _INVALID_STATES:
            return None
        if window.state == STATE_ON:
            return None

    # A power meter is the ground truth: compressor running or not.
    if power_configured:
        power = read_power(power_state)
        if power is None:
            return None
        if power < power_threshold:
            return MODE_PASSIVE
        return _direction(hvac_state, hvac_type)

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
        # No hvac_action (IR units like SmartIR/Broadlink): HA only knows what
        # it sent. Use the mode, but ignore periods where the room is already
        # at the setpoint - the compressor is only cycling there, which would
        # hide the real pull-down capacity.
        state = hvac_state.state
        if state == "off":
            return MODE_PASSIVE
        if state not in ("heat", "cool"):
            return None
        setpoint = _to_float(hvac_state.attributes.get("temperature"))
        if setpoint is not None and t_in is not None:
            if state == "cool" and t_in <= setpoint + SETPOINT_BAND:
                return None
            if state == "heat" and t_in >= setpoint - SETPOINT_BAND:
                return None
        return MODE_HEATING if state == "heat" else MODE_COOLING

    if hvac_state.state == STATE_ON:
        return MODE_COOLING if hvac_type == HVAC_TYPE_COOL else MODE_HEATING
    return MODE_PASSIVE


def _opt_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        self.comfort_max: float | None = _opt_float(opts.get(CONF_COMFORT_MAX))
        self.comfort_min: float | None = _opt_float(opts.get(CONF_COMFORT_MIN))
        self.indoor_humidity: str | None = opts.get(CONF_INDOOR_HUMIDITY) or None
        self.outdoor_humidity: str | None = opts.get(CONF_OUTDOOR_HUMIDITY) or None
        self.humidity_max: float = (
            _opt_float(opts.get(CONF_HUMIDITY_MAX)) or DEFAULT_HUMIDITY_MAX
        )
        weather = opts.get(CONF_WEATHER_ENTITY) or None
        if weather is None and self.outdoor_entity.startswith("weather."):
            weather = self.outdoor_entity
        self.weather_entity: str | None = weather
        self.power_sensor: str | None = opts.get(CONF_POWER_SENSOR) or None
        self.power_threshold: float = (
            _opt_float(opts.get(CONF_POWER_THRESHOLD)) or DEFAULT_POWER_THRESHOLD
        )
        self.ready_by: time | None = None
        if opts.get(CONF_READY_BY):
            self.ready_by = dt_util.parse_time(str(opts[CONF_READY_BY]))
        self.ready_temperature: float = (
            _opt_float(opts.get(CONF_READY_TEMPERATURE)) or self.target
        )
        self.use_sun: bool = bool(opts.get(CONF_USE_SUN, True)) and not self.solar_sensor

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._samples: deque[Sample] = deque(maxlen=MAX_SAMPLES)
        self._params = ModelParams()
        self._use_solar = False
        self._ventilation_on = False
        self._sun_cache: dict[int, float] = {}
        self._astral: Observer | None = None
        self._forecast_points: list[tuple[float, float]] = []
        self._forecast_fetched = 0.0
        self._usage: dict[str, Any] = {"day": None, "runtime_s": 0.0, "energy_wh": 0.0}
        self._usage_last_ts: float | None = None

    # ------------------------------------------------------------------ setup

    @property
    def fingerprint(self) -> str:
        """Identify the sensor set; stored samples are invalid if it changes."""
        parts = [
            self.indoor_sensor,
            self.outdoor_entity,
            self.hvac_entity or "",
            self.hvac_type,
            ",".join(sorted(self.window_sensors)),
            self.solar_sensor or "",
        ]
        if self.power_sensor:
            # Appended only when used so v0.1 rooms keep their learned data.
            parts += [self.power_sensor, f"{self.power_threshold:g}"]
        return "|".join(parts)

    @property
    def samples(self) -> list[Sample]:
        """Return a copy of the stored samples."""
        return list(self._samples)

    @property
    def params(self) -> ModelParams:
        """Return the current model parameters."""
        return self._params

    @property
    def hvac_rate(self) -> float | None:
        """The learned HVAC rate in the configured direction."""
        if self.hvac_type == HVAC_TYPE_COOL:
            return self._params.cooling_rate
        return self._params.heating_rate

    async def async_initialize(self) -> None:
        """Load persisted samples or bootstrap from recorder history."""
        if self.use_sun:
            try:
                cfg = self.hass.config
                self._astral = Observer(cfg.latitude, cfg.longitude, cfg.elevation or 0)
            except Exception:  # noqa: BLE001 - sun position is optional
                LOGGER.debug("Sun position unavailable", exc_info=True)
                self.use_sun = False
        stored = await self._store.async_load()
        if stored and isinstance(stored.get("usage"), dict):
            self._usage.update(stored["usage"])
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
            "usage": dict(self._usage),
        }

    async def _async_save_now(self) -> None:
        await self._store.async_save(self._serialize())

    # ------------------------------------------------------------------- sun

    def sun_at(self, ts: float) -> float | None:
        """Sun factor (sin of the solar elevation, 0 at night) at a timestamp."""
        if self._astral is None:
            return None
        key = int(ts // SAMPLE_INTERVAL_S)
        cached = self._sun_cache.get(key)
        if cached is not None:
            return cached
        when = datetime.fromtimestamp(key * SAMPLE_INTERVAL_S, UTC)
        try:
            value = sun_factor(solar_elevation(self._astral, when))
        except Exception:  # noqa: BLE001 - astral edge cases (polar regions)
            value = 0.0
        if len(self._sun_cache) > MAX_SAMPLES * 2:
            self._sun_cache.clear()
        self._sun_cache[key] = value
        return value

    # -------------------------------------------------------------- bootstrap

    def _tracked_entities(self) -> list[str]:
        entities = [self.indoor_sensor, self.outdoor_entity, *self.window_sensors]
        if self.hvac_entity:
            entities.append(self.hvac_entity)
        if self.solar_sensor:
            entities.append(self.solar_sensor)
        if self.power_sensor:
            entities.append(self.power_sensor)
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

    def _make_sample(
        self, ts: float, state_of: Callable[[str, float], State | None], default_unit: str
    ) -> Sample | None:
        t_in = read_temperature(state_of(self.indoor_sensor, ts), default_unit)
        t_out = read_temperature(state_of(self.outdoor_entity, ts), default_unit)
        if t_in is None or t_out is None:
            return None
        if self.solar_sensor:
            solar = read_number(state_of(self.solar_sensor, ts))
        elif self.use_sun:
            solar = self.sun_at(ts)
        else:
            solar = None
        power_state = state_of(self.power_sensor, ts) if self.power_sensor else None
        mode = determine_mode(
            state_of(self.hvac_entity, ts) if self.hvac_entity else None,
            self.hvac_entity is not None,
            self.hvac_type,
            [state_of(w, ts) for w in self.window_sensors],
            t_in=t_in,
            power_state=power_state,
            power_configured=self.power_sensor is not None,
            power_threshold=self.power_threshold,
        )
        return Sample(
            ts=ts,
            t_in=t_in,
            t_out=t_out,
            solar=solar,
            mode=mode,
            power=read_power(power_state) if power_state is not None else None,
        )

    def _live_state(self, entity_id: str, _ts: float) -> State | None:
        return self.hass.states.get(entity_id)

    async def _async_refit(self) -> None:
        self._params = await self.hass.async_add_executor_job(
            self._fit, list(self._samples)
        )

    def _fit(self, samples: list[Sample]) -> ModelParams:
        """Fit the model (runs in the executor)."""
        if self.use_sun:
            # v0.1 samples carry no solar value: derive it from the timestamp.
            for sample in samples:
                if sample.solar is None:
                    sample.solar = self.sun_at(sample.ts)
        if self.solar_sensor or self.use_sun:
            usable = [s for s in samples if s.mode is not None]
            with_solar = sum(1 for s in usable if s.solar is not None)
            self._use_solar = bool(usable) and with_solar / len(usable) >= SOLAR_MIN_COVERAGE
        else:
            self._use_solar = False
        plain = fit_model(samples, False, MAX_GAP_S)
        if not self._use_solar:
            return plain
        solar = fit_model(samples, True, MAX_GAP_S)
        # Only keep the sun term when it is physically sound and actually helps.
        if solar.is_trained and (
            not plain.is_trained
            or (solar.r2 or 0.0) >= (plain.r2 or 0.0) + SOLAR_MIN_GAIN
        ) and (solar.solar_gain or 0.0) >= 0:
            return solar
        self._use_solar = False
        return plain

    # ---------------------------------------------------------------- weather

    async def _async_refresh_forecast(self) -> None:
        """Fetch the hourly outdoor forecast (best effort, every 30 min)."""
        if not self.weather_entity:
            return
        now = dt_util.utcnow().timestamp()
        if now - self._forecast_fetched < WEATHER_REFRESH_S:
            return
        self._forecast_fetched = now
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"type": "hourly"},
                target={"entity_id": self.weather_entity},
                blocking=True,
                return_response=True,
            )
        except Exception:  # noqa: BLE001 - forecast is optional
            LOGGER.debug("%s: hourly forecast unavailable", self.weather_entity, exc_info=True)
            return
        state = self.hass.states.get(self.weather_entity)
        unit = (
            state.attributes.get("temperature_unit", UnitOfTemperature.CELSIUS)
            if state
            else UnitOfTemperature.CELSIUS
        )
        points: list[tuple[float, float]] = []
        items = ((response or {}).get(self.weather_entity) or {}).get("forecast") or []
        for item in items:
            when = dt_util.parse_datetime(str(item.get("datetime", "")))
            temp = _to_float(item.get("temperature"))
            if when is None or temp is None:
                continue
            if unit in _TEMP_UNITS and unit != UnitOfTemperature.CELSIUS:
                temp = TemperatureConverter.convert(temp, unit, UnitOfTemperature.CELSIUS)
            points.append((when.timestamp(), temp))
        points.sort()
        if points:
            self._forecast_points = points

    def _outdoor_function(self, now_ts: float, t_out_now: float) -> Callable[[float], float]:
        """Outdoor temperature over time: forecast, bias-corrected to the sensor."""
        points = [p for p in self._forecast_points if p[0] >= now_ts - 3 * 3600]
        if len(points) < 2:
            return lambda _ts: t_out_now
        stamps = [p[0] for p in points]

        def raw(ts: float) -> float:
            if ts <= stamps[0]:
                return points[0][1]
            if ts >= stamps[-1]:
                return points[-1][1]
            idx = bisect_left(stamps, ts)
            (t0, v0), (t1, v1) = points[idx - 1], points[idx]
            return v0 + (v1 - v0) * (ts - t0) / (t1 - t0)

        bias = t_out_now - raw(now_ts)
        decay_s = FORECAST_BIAS_DECAY_H * 3600.0

        def at(ts: float) -> float:
            weight = max(0.0, 1.0 - (ts - now_ts) / decay_s)
            return raw(ts) + bias * weight

        return at

    # ------------------------------------------------------------------ usage

    def _track_usage(self, now: datetime, hvac_on: bool | None, power: float | None) -> None:
        day = dt_util.as_local(now).date().isoformat()
        if self._usage.get("day") != day:
            self._usage = {"day": day, "runtime_s": 0.0, "energy_wh": 0.0}
        ts = now.timestamp()
        if self._usage_last_ts is not None:
            span = min(max(0.0, ts - self._usage_last_ts), MAX_GAP_S)
            if hvac_on:
                self._usage["runtime_s"] += span
            if power is not None:
                self._usage["energy_wh"] += power * span / 3600.0
        self._usage_last_ts = ts

    def _efficiency(self) -> float | None:
        """°C per kWh while the unit actively heats or cools."""
        rate = self.hvac_rate
        if rate is None or not self.power_sensor:
            return None
        active = MODE_COOLING if self.hvac_type == HVAC_TYPE_COOL else MODE_HEATING
        draws = [s.power for s in self._samples if s.mode == active and s.power]
        if len(draws) < 6:
            return None
        mean_kw = sum(draws) / len(draws) / 1000.0
        return abs(rate) / mean_kw if mean_kw > 0 else None

    # ----------------------------------------------------------------- update

    async def _async_update_data(self) -> ThermalTwinData:
        """Take a sample, relearn and compute predictions."""
        now = dt_util.utcnow()
        sample = self._make_sample(
            now.timestamp(), self._live_state, self.hass.config.units.temperature_unit
        )
        if sample is not None:
            self._samples.append(sample)
        await self._async_refit()
        await self._async_refresh_forecast()
        data = await self.hass.async_add_executor_job(self._build_data)
        self._track_usage(now, data.hvac_on, data.power)
        data.runtime_today_min = round(self._usage["runtime_s"] / 60.0, 0)
        if self.power_sensor:
            data.energy_today_kwh = round(self._usage["energy_wh"] / 1000.0, 3)
        self._store.async_delay_save(self._serialize, STORAGE_SAVE_DELAY_S)
        return data

    # ------------------------------------------------------------ predictions

    def _next_ready(self, now: datetime) -> datetime | None:
        if self.ready_by is None:
            return None
        local = dt_util.as_local(now)
        ready = local.replace(
            hour=self.ready_by.hour, minute=self.ready_by.minute, second=0, microsecond=0
        )
        if ready <= local:
            ready += timedelta(days=1)
        return ready

    def _build_data(self) -> ThermalTwinData:
        default_unit = self.hass.config.units.temperature_unit
        states = self.hass.states
        now = dt_util.utcnow()
        now_ts = now.timestamp()
        t_in = read_temperature(states.get(self.indoor_sensor), default_unit)
        outdoor_state = states.get(self.outdoor_entity)
        t_out = read_temperature(outdoor_state, default_unit)

        if self.solar_sensor and self._use_solar:
            solar = read_number(states.get(self.solar_sensor))
            if solar is None:
                solar = 0.0
        elif self.use_sun and self._use_solar:
            solar = self.sun_at(now_ts)
        else:
            solar = None

        hvac_state = states.get(self.hvac_entity) if self.hvac_entity else None
        power_state = states.get(self.power_sensor) if self.power_sensor else None
        power = read_power(power_state)
        mode = determine_mode(
            hvac_state,
            self.hvac_entity is not None,
            self.hvac_type,
            [states.get(w) for w in self.window_sensors],
            t_in=t_in,
            power_state=power_state,
            power_configured=self.power_sensor is not None,
            power_threshold=self.power_threshold,
        )
        hvac_on = (
            hvac_is_on(hvac_state, power, self.power_threshold)
            if (self.hvac_entity or self.power_sensor)
            else None
        )
        params = self._params
        data = ThermalTwinData(
            params=params,
            t_in=t_in,
            t_out=t_out,
            solar=solar,
            mode=mode,
            hvac_on=hvac_on,
            power=power,
            target=self.target,
            sample_count=len(self._samples),
            use_solar=self._use_solar,
            solar_source=(
                "sensor" if self.solar_sensor else ("sun" if self.use_sun else None)
            ),
            efficiency=self._efficiency(),
            ready_temperature=self.ready_temperature if self.ready_by else None,
        )

        # Humidity - works without training.
        data.rh_in = read_humidity(states.get(self.indoor_humidity)) if self.indoor_humidity else None
        if self.outdoor_humidity:
            data.rh_out = read_humidity(states.get(self.outdoor_humidity))
        elif outdoor_state is not None and _domain(outdoor_state) == "weather":
            data.rh_out = read_humidity(outdoor_state)
        if t_in is not None and data.rh_in is not None:
            data.abs_in = absolute_humidity(t_in, data.rh_in)
            data.dew_point = dew_point(t_in, data.rh_in)
            data.apparent = heat_index(t_in, data.rh_in)
        if t_out is not None and data.rh_out is not None:
            data.abs_out = absolute_humidity(t_out, data.rh_out)

        if t_in is None or t_out is None:
            if hvac_on:
                data.status = "cooling" if self.hvac_type == HVAC_TYPE_COOL else "heating"
            else:
                data.status = "learning" if not params.is_trained else "comfortable"
            return data

        upper = self.comfort_max if self.comfort_max is not None else self.target

        # Ventilation advice is pure physics and works before training.
        # Hysteresis: on above comfort_max + 0.5 °C with outside >= 1 °C
        # cooler; stays on until the room is back at comfort_max or outside is
        # no longer cooler. Blocked when outside air carries clearly more water.
        if self.comfort_max is not None:
            if self._ventilation_on:
                self._ventilation_on = t_in > self.comfort_max and t_out < t_in
            else:
                self._ventilation_on = (
                    t_in >= self.comfort_max + VENTILATION_HYSTERESIS
                    and t_out <= t_in - VENTILATION_MIN_GAIN
                )
            blocked = (
                data.abs_in is not None
                and data.abs_out is not None
                and data.abs_out > data.abs_in + VENTILATION_MAX_EXTRA_HUMIDITY
            )
            data.ventilation_blocked_by_humidity = bool(self._ventilation_on and blocked)
            data.ventilation_recommended = self._ventilation_on and not blocked

        if data.rh_in is not None and self.hvac_type == HVAC_TYPE_COOL:
            data.dry_recommended = (
                data.rh_in >= self.humidity_max and t_in <= upper + DRY_MODE_TEMP_MARGIN
            )

        if params.is_trained:
            self._predict(data, t_in, t_out, now, now_ts)

        data.status = self._status(data, t_in, upper)
        return data

    def _predict(
        self, data: ThermalTwinData, t_in: float, t_out: float, now: datetime, now_ts: float
    ) -> None:
        params = self._params
        t_out_at = self._outdoor_function(now_ts, t_out)
        data.uses_weather_forecast = len(self._forecast_points) >= 2
        solar_at: Callable[[float], float | None] | None = None
        if self._use_solar:
            if self.use_sun:
                solar_at = self.sun_at
            else:
                solar_now = data.solar
                solar_at = lambda _ts: solar_now  # noqa: E731

        data.equilibrium = equilibrium(params, t_out, data.solar)
        passive = simulate(params, t_in, now_ts, TARGET_SEARCH_H, t_out_at, solar_at)
        if passive:
            one_h = round(PREDICTION_HORIZON_H * 12)
            data.predicted_1h = passive[min(one_h, len(passive) - 1)][1]
            crossing = first_crossing(passive, self.target)
            if crossing is not None:
                data.time_to_target_min = round((crossing - now_ts) / 60.0, 0)
                data.target_eta = now + timedelta(seconds=crossing - now_ts)

        hvac_traj: list[tuple[float, float]] = []
        if self.hvac_entity or self.power_sensor:
            configured = self.hvac_rate
            if configured is not None:
                hvac_traj = simulate(
                    params, t_in, now_ts, TARGET_SEARCH_H, t_out_at, solar_at,
                    hvac_rate=configured,
                )
            rate = params.heating_rate if self.target > t_in else params.cooling_rate
            if rate is not None:
                traj = (
                    hvac_traj
                    if rate == configured
                    else simulate(
                        params, t_in, now_ts, TARGET_SEARCH_H, t_out_at, solar_at,
                        hvac_rate=rate,
                    )
                )
                crossing = first_crossing(traj, self.target)
                if crossing is not None:
                    data.time_to_target_hvac_min = round((crossing - now_ts) / 60.0, 0)
                    data.target_eta_hvac = now + timedelta(seconds=crossing - now_ts)

        # Compact curve for the card: [minutes, passive, with hvac, outdoor].
        step = round(FORECAST_POINT_STEP_H * 12)
        limit = round(FORECAST_HORIZON_H * 12)
        curve: list[list[float | None]] = []
        for idx in range(0, min(limit, len(passive) - 1) + 1, step):
            ts, temp = passive[idx]
            with_hvac = hvac_traj[idx][1] if idx < len(hvac_traj) else None
            curve.append(
                [
                    round((ts - now_ts) / 60.0),
                    round(temp, 2),
                    None if with_hvac is None else round(with_hvac, 2),
                    round(t_out_at(ts), 2),
                ]
            )
        data.forecast = curve

        ready = self._next_ready(now)
        direction_rate = self.hvac_rate
        if ready is not None and direction_rate is not None:
            data.ready_at = ready
            data.precondition = plan_precondition(
                params,
                t_in,
                now_ts,
                ready.timestamp(),
                self.ready_temperature,
                direction_rate,
                t_out_at,
                solar_at,
                max_lead_h=PRECONDITION_MAX_LEAD_H,
            )

    def _status(self, data: ThermalTwinData, t_in: float, upper: float) -> str:
        if data.mode == MODE_COOLING or (
            data.hvac_on and self.hvac_type == HVAC_TYPE_COOL
        ):
            return "cooling"
        if data.mode == MODE_HEATING or (data.hvac_on and self.hvac_type != HVAC_TYPE_COOL):
            return "heating"
        if not data.params.is_trained:
            return "learning"
        if data.precondition is not None and data.precondition.status in ("now", "late"):
            return "precondition"
        if data.ventilation_recommended:
            return "ventilate"
        if data.dry_recommended:
            return "dry"
        if self.hvac_type == HVAC_TYPE_COOL:
            if t_in > upper:
                return "too_warm"
            if self.comfort_min is not None and t_in < self.comfort_min:
                return "too_cold"
        else:
            if t_in < self.target:
                return "too_cold"
            if self.comfort_max is not None and t_in > self.comfort_max:
                return "too_warm"
        return "comfortable"
