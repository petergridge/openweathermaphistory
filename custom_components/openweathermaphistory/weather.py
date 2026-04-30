"""Support for the OpenWeatherMap History weather entity."""

from __future__ import annotations

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
    ATTR_CONDITION_WINDY_VARIANT,
    ATTR_FORECAST_CLOUD_COVERAGE,
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_HUMIDITY,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_PRESSURE,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTRIBUTION, DOMAIN
from .weatherhistory import WeatherCoordinator

CONDITION_MAP: dict[str, str] = {
    "clear": ATTR_CONDITION_SUNNY,
    "cloud": ATTR_CONDITION_CLOUDY,
    "partly": ATTR_CONDITION_PARTLYCLOUDY,
    "rain": ATTR_CONDITION_RAINY,
    "drizzle": ATTR_CONDITION_POURING,
    "thunderstorm": ATTR_CONDITION_LIGHTNING_RAINY,
    "thunder": ATTR_CONDITION_LIGHTNING,
    "snow": ATTR_CONDITION_SNOWY,
    "sleet": ATTR_CONDITION_SNOWY_RAINY,
    "fog": ATTR_CONDITION_FOG,
    "mist": ATTR_CONDITION_FOG,
    "haze": ATTR_CONDITION_FOG,
    "wind": ATTR_CONDITION_WINDY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the OpenWeatherMap History weather entity."""

    shared = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = shared["coordinator"]

    async_add_entities(
        [OpenWeatherHistoryWeather(config_entry.entry_id, coordinator)], False
    )


def _map_condition(description: str | None) -> str | None:
    if not description:
        return None

    text = description.lower()
    for keyword, condition in CONDITION_MAP.items():
        if keyword in text:
            return condition

    return ATTR_CONDITION_EXCEPTIONAL


class OpenWeatherHistoryWeather(SingleCoordinatorWeatherEntity[WeatherCoordinator]):
    """Representation of the OpenWeatherMap History weather entity."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_visibility_unit = UnitOfLength.METERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY

    def __init__(self, unique_id: str, coordinator: WeatherCoordinator) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, unique_id)},
            manufacturer="OpenWeatherMap",
        )

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        return _map_condition(
            self.coordinator.data.processed_value("current", "description")
        )

    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.coordinator.data.processed_value("current", "temp")

    @property
    def native_pressure(self) -> float | None:
        """Return the current pressure."""
        return self.coordinator.data.processed_value("current", "pressure")

    @property
    def humidity(self) -> float | None:
        """Return the current humidity."""
        return self.coordinator.data.processed_value("current", "humidity")

    @property
    def native_wind_speed(self) -> float | None:
        """Return the current wind speed."""
        return self.coordinator.data.processed_value("current", "wind_speed")

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the current wind bearing."""
        return self.coordinator.data.processed_value("current", "wind_deg")

    @property
    def cloud_coverage(self) -> float | None:
        """Return the current cloud coverage."""
        return self.coordinator.data.processed_value("current", "clouds")

    @property
    def native_precipitation(self) -> float | None:
        """Return the current precipitation."""
        return self.coordinator.data.processed_value(
            "current", "rain"
        ) + self.coordinator.data.processed_value("current", "snow")

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return additional state attributes."""
        weather = self.coordinator.data
        if weather is None:
            return None
        return {
            "daily_count": weather.daily_count(),
            "remaining_backlog": weather.remaining_backlog(),
            "current_description": weather.processed_value("current", "description"),
        }

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        forecasts: list[Forecast] = []
        weather = self.coordinator.data
        if weather is None:
            return None

        for i in range(7):
            forecast_time = weather.processed_value(f"f{i}", "datetime")
            if not forecast_time:
                continue

            forecasts.append(
                Forecast(
                    {
                        ATTR_FORECAST_TIME: forecast_time,
                        ATTR_FORECAST_NATIVE_TEMP: weather.processed_value(
                            f"f{i}", "max_temp"
                        ),
                        ATTR_FORECAST_NATIVE_TEMP_LOW: weather.processed_value(
                            f"f{i}", "min_temp"
                        ),
                        ATTR_FORECAST_NATIVE_PRECIPITATION: (
                            weather.processed_value(f"f{i}", "rain")
                            + weather.processed_value(f"f{i}", "snow")
                        ),
                        ATTR_FORECAST_CONDITION: _map_condition(
                            weather.processed_value(f"f{i}", "description")
                        ),
                        ATTR_FORECAST_NATIVE_PRESSURE: weather.processed_value(
                            f"f{i}", "pressure"
                        ),
                        ATTR_FORECAST_NATIVE_WIND_SPEED: weather.processed_value(
                            f"f{i}", "wind_speed"
                        ),
                        ATTR_FORECAST_WIND_BEARING: weather.processed_value(
                            f"f{i}", "wind_deg"
                        ),
                        ATTR_FORECAST_HUMIDITY: weather.processed_value(
                            f"f{i}", "humidity"
                        ),
                        ATTR_FORECAST_CLOUD_COVERAGE: weather.processed_value(
                            f"f{i}", "clouds"
                        ),
                    }
                )
            )

        return forecasts if forecasts else None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry for weather platform."""
    shared = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = shared["coordinator"]

    entity = OpenWeatherHistoryWeather(config_entry.entry_id, coordinator)
    async_add_entities([entity], False)
