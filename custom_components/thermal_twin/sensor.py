"""Sensors for ThermalTwin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import ThermalTwinConfigEntry
from .const import STATUS_OPTIONS
from .coordinator import ThermalTwinCoordinator, ThermalTwinData
from .entity import ThermalTwinEntity

RATE_UNIT = "°C/h"
EFFICIENCY_UNIT = "°C/kWh"
ABS_HUMIDITY_UNIT = "g/m³"


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _eta(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _has_hvac(c: ThermalTwinCoordinator) -> bool:
    return bool(c.hvac_entity or c.power_sensor)


def _has_humidity(c: ThermalTwinCoordinator) -> bool:
    return c.indoor_humidity is not None


def _precondition_start(d: ThermalTwinData) -> datetime | None:
    plan = d.precondition
    if plan is None or plan.start_ts is None:
        return None
    return dt_util.utc_from_timestamp(plan.start_ts)


def _precondition_attrs(d: ThermalTwinData) -> dict[str, Any]:
    plan = d.precondition
    return {
        "ready_at": _eta(d.ready_at),
        "ready_temperature": d.ready_temperature,
        "plan": None if plan is None else plan.status,
        "hvac_minutes": None if plan is None else _round(plan.hvac_minutes, 0),
        "temperature_without_hvac": None if plan is None else _round(plan.without_hvac, 1),
        "temperature_with_hvac": None if plan is None else _round(plan.with_hvac, 1),
        "uses_weather_forecast": d.uses_weather_forecast,
    }


@dataclass(frozen=True, kw_only=True)
class ThermalTwinSensorDescription(SensorEntityDescription):
    """Describe a ThermalTwin sensor."""

    value_fn: Callable[[ThermalTwinData], Any]
    attrs_fn: Callable[[ThermalTwinData], dict[str, Any]] | None = None
    exists_fn: Callable[[ThermalTwinCoordinator], bool] = lambda _c: True


SENSORS: tuple[ThermalTwinSensorDescription, ...] = (
    ThermalTwinSensorDescription(
        key="time_to_target",
        translation_key="time_to_target",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.time_to_target_min,
        attrs_fn=lambda d: {"target": d.target, "eta": _eta(d.target_eta)},
    ),
    ThermalTwinSensorDescription(
        key="time_to_target_hvac",
        translation_key="time_to_target_hvac",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.time_to_target_hvac_min,
        attrs_fn=lambda d: {"target": d.target, "eta": _eta(d.target_eta_hvac)},
        exists_fn=_has_hvac,
    ),
    ThermalTwinSensorDescription(
        key="equilibrium_temperature",
        translation_key="equilibrium_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: _round(d.equilibrium, 2),
    ),
    ThermalTwinSensorDescription(
        key="predicted_temperature_1h",
        translation_key="predicted_temperature_1h",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: _round(d.predicted_1h, 2),
    ),
    ThermalTwinSensorDescription(
        key="precondition_start",
        translation_key="precondition_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_precondition_start,
        attrs_fn=_precondition_attrs,
        exists_fn=lambda c: c.ready_by is not None and _has_hvac(c),
    ),
    ThermalTwinSensorDescription(
        key="dew_point",
        translation_key="dew_point",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: _round(d.dew_point, 2),
        exists_fn=_has_humidity,
    ),
    ThermalTwinSensorDescription(
        key="absolute_humidity",
        translation_key="absolute_humidity",
        native_unit_of_measurement=ABS_HUMIDITY_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: _round(d.abs_in, 2),
        attrs_fn=lambda d: {"outdoor": _round(d.abs_out, 2)},
        exists_fn=_has_humidity,
    ),
    ThermalTwinSensorDescription(
        key="apparent_temperature",
        translation_key="apparent_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: _round(d.apparent, 2),
        exists_fn=_has_humidity,
    ),
    ThermalTwinSensorDescription(
        key="hvac_runtime_today",
        translation_key="hvac_runtime_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.runtime_today_min,
        exists_fn=_has_hvac,
    ),
    ThermalTwinSensorDescription(
        key="hvac_energy_today",
        translation_key="hvac_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: d.energy_today_kwh,
        exists_fn=lambda c: c.power_sensor is not None,
    ),
    ThermalTwinSensorDescription(
        key="hvac_efficiency",
        translation_key="hvac_efficiency",
        native_unit_of_measurement=EFFICIENCY_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _round(d.efficiency, 3),
        exists_fn=lambda c: c.power_sensor is not None,
    ),
    ThermalTwinSensorDescription(
        key="time_constant",
        translation_key="time_constant",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _round(d.params.time_constant_h, 2),
    ),
    ThermalTwinSensorDescription(
        key="model_quality",
        translation_key="model_quality",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            None if d.params.r2 is None else round(max(0.0, d.params.r2) * 100, 0)
        ),
        attrs_fn=lambda d: {
            "passive_pairs": d.params.passive_pairs,
            "heating_pairs": d.params.heating_pairs,
            "cooling_pairs": d.params.cooling_pairs,
            "samples": d.sample_count,
            "uses_solar": d.use_solar,
            "solar_source": d.solar_source,
            "internal_gain_c_per_h": _round(d.params.offset, 3),
            "solar_gain": _round(d.params.solar_gain, 5),
        },
    ),
    ThermalTwinSensorDescription(
        key="heating_rate",
        translation_key="heating_rate",
        native_unit_of_measurement=RATE_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _round(d.params.heating_rate, 3),
        exists_fn=_has_hvac,
    ),
    ThermalTwinSensorDescription(
        key="cooling_rate",
        translation_key="cooling_rate",
        native_unit_of_measurement=RATE_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _round(d.params.cooling_rate, 3),
        exists_fn=_has_hvac,
    ),
)

STATUS_DESCRIPTION = ThermalTwinSensorDescription(
    key="status",
    translation_key="status",
    device_class=SensorDeviceClass.ENUM,
    options=STATUS_OPTIONS,
    value_fn=lambda d: d.status,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThermalTwinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ThermalTwin sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [ThermalTwinStatusSensor(coordinator, STATUS_DESCRIPTION)]
    entities.extend(
        ThermalTwinSensor(coordinator, description)
        for description in SENSORS
        if description.exists_fn(coordinator)
    )
    async_add_entities(entities)


class ThermalTwinSensor(ThermalTwinEntity, SensorEntity):
    """A ThermalTwin sensor."""

    entity_description: ThermalTwinSensorDescription

    def __init__(
        self,
        coordinator: ThermalTwinCoordinator,
        description: ThermalTwinSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class ThermalTwinStatusSensor(ThermalTwinSensor):
    """Overall room state - also the data source for the ThermalTwin card."""

    _unrecorded_attributes = frozenset({"forecast", "room"})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Everything the card needs in one place."""
        c = self.coordinator
        d = c.data
        plan = d.precondition
        return {
            "room": {
                "indoor_sensor": c.indoor_sensor,
                "outdoor_entity": c.outdoor_entity,
                "hvac_entity": c.hvac_entity,
                "hvac_type": c.hvac_type,
                "indoor_humidity": c.indoor_humidity,
                "weather_entity": c.weather_entity,
                "power_sensor": c.power_sensor,
            },
            "indoor_temperature": _round(d.t_in, 2),
            "outdoor_temperature": _round(d.t_out, 2),
            "indoor_humidity": _round(d.rh_in, 1),
            "outdoor_humidity": _round(d.rh_out, 1),
            "target": d.target,
            "comfort_min": c.comfort_min,
            "comfort_max": c.comfort_max,
            "humidity_max": c.humidity_max,
            "hvac_on": d.hvac_on,
            "power": _round(d.power, 1),
            "ventilation_blocked_by_humidity": d.ventilation_blocked_by_humidity,
            "precondition": None if plan is None else plan.status,
            "precondition_start": _eta(_precondition_start(d)),
            "ready_at": _eta(d.ready_at),
            "ready_temperature": d.ready_temperature,
            "uses_weather_forecast": d.uses_weather_forecast,
            "solar_source": d.solar_source if d.use_solar else None,
            "forecast": d.forecast,
        }
