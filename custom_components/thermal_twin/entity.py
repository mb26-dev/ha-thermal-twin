"""Base entity for ThermalTwin."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ThermalTwinCoordinator


class ThermalTwinEntity(CoordinatorEntity[ThermalTwinCoordinator]):
    """Common device and naming for all ThermalTwin entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ThermalTwinCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ThermalTwin",
            model="Room thermal model",
            entry_type=DeviceEntryType.SERVICE,
        )
