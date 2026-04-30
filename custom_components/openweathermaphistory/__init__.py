"""__init__."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, storage as store

from . import utils
from .const import CONST_INITIAL, DOMAIN
from .weatherhistory import Weather, WeatherCoordinator

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up irrigtest from a config entry."""
    config = entry.options or entry.data

    weather = Weather(hass, config)
    weather.set_processing_type(CONST_INITIAL)
    coordinator = WeatherCoordinator(hass, weather)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "weather": weather,
        "coordinator": coordinator,
        "config": config,
    }

    PLATFORMS: list[str] = ["sensor", "weather"]

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    def _set_processing_type(event):
        weather.set_processing_type("general")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _set_processing_type)

    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))
    return True


async def async_setup(hass: HomeAssistant, config):
    """Card setup."""

    # 1. Serve lovelace card
    path = Path(__file__).parent / "www"
    utils.register_static_path(
        hass.http.app,
        "/openweathermaphistory/www/openweathermaphistory.js",
        path / "openweathermaphistory.js",
    )

    # 2. Add card to resources
    version = getattr(hass.data["integrations"][DOMAIN], "version", 0)
    await utils.init_resource(
        hass, "/openweathermaphistory/www/openweathermaphistory.js", str(version)
    )

    async def list_vars(call: ServiceCall):
        """List all available variables."""
        for entry in hass.config_entries.async_entries("openweathermaphistory"):
            if call.data.get("entry_id") == entry.entry_id:
                event_data = {"action": "list_variables", "entry": entry.title}
                hass.bus.async_fire("owmh_event", event_data)

    hass.services.async_register(DOMAIN, "list_vars", list_vars)

    async def api_call(call: ServiceCall):
        """Test API call."""
        for entry in hass.config_entries.async_entries("openweathermaphistory"):
            if call.data.get("entry_id") == entry.entry_id:
                event_data = {
                    "action": "api_call",
                    "entry": entry.title,
                    "api": call.data.get("api"),
                }
                hass.bus.async_fire("owmh_event", event_data)

    hass.services.async_register(DOMAIN, "api_call", api_call)

    return True


async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, (Platform.SENSOR, Platform.WEATHER)
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.info("Migrating from version %s", config_entry.version)

    #     if config_entry.version == 1:
    #         new = {**config_entry.data}
    #         dname = config_entry.data.get(CONF_NAME,'unknown')
    # #        name = config_entry.options.get(CONF_NAME)
    #         name = config_entry.options.get(CONF_NAME,dname)
    #         try:
    #             file = os.path.join(hass.config.path(), cv.slugify(name)  + '.pickle')
    #             if exists(file):
    #                 os.remove(file)
    #         except FileNotFoundError:
    #             pass
    #         try:
    #             file = os.path.join(hass.config.path(), cv.slugify('owm_api_count')  + '.pickle')
    #             os.remove(file)
    #         except FileNotFoundError:
    #             pass
    #         hass.config_entries.async_update_entry(config_entry,data=new,minor_version=1,version=2)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Handle removal of entry."""
    name = "OWMH_" + entry.title
    x = store.Store[dict[any]](hass, 1, name)
    await x.async_remove()
