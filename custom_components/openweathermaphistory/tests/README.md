# Tests for OpenWeatherMap History custom component

This directory contains unit tests for the OpenWeatherMap History custom component.

## Running Tests

From the component tests directory:
```bash
cd config/custom_components/openweathermaphistory/tests/
python -m pytest test_weather.py
```

From the core tests directory:
```bash
cd tests/components/openweathermaphistory/
python -m pytest test_weather.py
```

## Test Coverage

- `test_weather.py`: Tests for the weather platform including:
  - Weather entity properties
  - Daily forecast generation
  - Config entry setup