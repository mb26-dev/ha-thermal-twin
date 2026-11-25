"""Binary sensors for ThermalTwin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThermalTwinConfigEntry
from .const import HVAC_TYPE_COOL
from .coordinator import ThermalTwinCoordinator
from .entity import ThermalTwinEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThermalTwinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ThermalTwin binary sensors."""
    c = entry.runtime_data
    entities: list[BinarySensorEntity] = [ThermalTwinTrainedSensor(c)]
    if c.comfort_max is not None:
        entities.append(ThermalTwinVentilationSensor(c))
    if c.ready_by is not None and (c.hvac_entity or c.power_sensor):
        entities.append(ThermalTwinPreconditionSensor(c))
    if c.indoor_humidity and c.hvac_type == HVAC_TYPE_COOL:
        entities.append(ThermalTwinDryModeSensor(c))
    async_add_entities(entities)


class ThermalTwinVentilationSensor(ThermalTwinEntity, BinarySensorEntity):
    """On when opening a window would cool the room towards comfort."""

    _attr_translation_key = "ventilation_recommended"

    def __init__(self, coordinator: ThermalTwinCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "ventilation_recommended")

    @property
    def is_on(self) -> bool | None:
        """Return True when ventilating is recommended."""
        return self.coordinator.data.ventilation_recommended

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the values the decision is based on."""
        data = self.coordinator.data
        return {
            "comfort_max": self.coordinator.comfort_max,
            "indoor_temperature": data.t_in,
            "outdoor_temperature": data.t_out,
            "blocked_by_humidity": data.ventilation_blocked_by_humidity,
        }


class ThermalTwinPreconditionSensor(ThermalTwinEntity, BinarySensorEntity):
    """On when the AC should run now to reach the ready temperature in time."""

    _attr_translation_key = "precondition_now"

    def __init__(self, coordinator: ThermalTwinCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "precondition_now")

    @property
    def is_on(self) -> bool | None:
        """Return True when it is time to start."""
        plan = self.coordinator.data.precondition
        if plan is None:
            return None if not self.coordinator.data.params.is_trained else False
        return plan.status in ("now", "late")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the plan."""
        data = self.coordinator.data
        plan = data.precondition
        return {
            "plan": None if plan is None else plan.status,
            "ready_at": None if data.ready_at is None else data.ready_at.isoformat(),
            "ready_temperature": data.ready_temperature,
        }


class ThermalTwinDryModeSensor(ThermalTwinEntity, BinarySensorEntity):
    """On when humidity, not heat, is the problem - dry mode beats cooling."""

    _attr_translation_key = "dry_mode_recommended"

    def __init__(self, coordinator: ThermalTwinCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "dry_mode_recommended")

    @property
    def is_on(self) -> bool | None:
        """Return True when dry mode is the better choice."""
        return self.coordinator.data.dry_recommended

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the values the decision is based on."""
        data = self.coordinator.data
        return {
            "indoor_humidity": data.rh_in,
            "humidity_max": self.coordinator.humidity_max,
            "dew_point": None if data.dew_point is None else round(data.dew_point, 1),
        }


class ThermalTwinTrainedSensor(ThermalTwinEntity, BinarySensorEntity):
    """On when the model has enough data to make predictions."""

    _attr_translation_key = "model_trained"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ThermalTwinCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "model_trained")

    @property
    def is_on(self) -> bool:
        """Return True when the passive model is trained."""
        return self.coordinator.data.params.is_trained
