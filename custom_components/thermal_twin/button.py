"""Button to reset the learned model."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up the reset button."""
    async_add_entities([ThermalTwinResetButton(entry.runtime_data)])


class ThermalTwinResetButton(ThermalTwinEntity, ButtonEntity):
    """Discard learned data and relearn from recorder history."""

    _attr_translation_key = "reset_model"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ThermalTwinCoordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, "reset_model")

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_reset()
