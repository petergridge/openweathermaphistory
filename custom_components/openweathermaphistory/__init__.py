"""The openweathermaphistory integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry (from UI config)"""
    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform.SENSOR]
    )
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options flow update (from UI reconfigure)."""
    await hass.config_entries.async_reload(entry.entry_id)
