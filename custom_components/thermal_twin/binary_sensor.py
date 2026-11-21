"""Binary sensors for ThermalTwin."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ThermalTwinConfigEntry
from .coordinator import ThermalTwinCoordinator
from .entity import ThermalTwinEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThermalTwinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ThermalTwin binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [ThermalTwinTrainedSensor(coordinator)]
    if coordinator.comfort_max is not None:
        entities.append(ThermalTwinVentilationSensor(coordinator))
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
    def extra_state_attributes(self) -> dict[str, float | None]:
        """Return the values the decision is based on."""
        data = self.coordinator.data
        return {
            "comfort_max": self.coordinator.comfort_max,
            "indoor_temperature": data.t_in,
            "outdoor_temperature": data.t_out,
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
