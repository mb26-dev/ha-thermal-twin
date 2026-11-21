"""ThermalTwin - learns the thermal behaviour of a room and predicts it."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import ThermalTwinCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

type ThermalTwinConfigEntry = ConfigEntry[ThermalTwinCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ThermalTwinConfigEntry) -> bool:
    """Set up a ThermalTwin room from a config entry."""
    coordinator = ThermalTwinCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ThermalTwinConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown_store()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ThermalTwinConfigEntry) -> None:
    """Delete stored samples when the room is removed."""
    # Imported here to avoid a module-level dependency cycle.
    from homeassistant.helpers.storage import Store  # noqa: PLC0415

    from .const import DOMAIN, STORAGE_VERSION  # noqa: PLC0415

    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_update_listener(hass: HomeAssistant, entry: ThermalTwinConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
