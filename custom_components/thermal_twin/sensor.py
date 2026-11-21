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
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThermalTwinConfigEntry
from .coordinator import ThermalTwinCoordinator, ThermalTwinData
from .entity import ThermalTwinEntity

RATE_UNIT = "°C/h"


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


@dataclass(frozen=True, kw_only=True)
class ThermalTwinSensorDescription(SensorEntityDescription):
    """Describe a ThermalTwin sensor."""

    value_fn: Callable[[ThermalTwinData], float | int | None]
    attrs_fn: Callable[[ThermalTwinData], dict[str, Any]] | None = None
    requires_hvac: bool = False


def _eta(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


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
        requires_hvac=True,
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
        requires_hvac=True,
    ),
    ThermalTwinSensorDescription(
        key="cooling_rate",
        translation_key="cooling_rate",
        native_unit_of_measurement=RATE_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _round(d.params.cooling_rate, 3),
        requires_hvac=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThermalTwinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ThermalTwin sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        ThermalTwinSensor(coordinator, description)
        for description in SENSORS
        if not description.requires_hvac or coordinator.hvac_entity
    )


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
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
