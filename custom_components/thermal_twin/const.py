"""Constants for ThermalTwin."""

from __future__ import annotations

import logging

DOMAIN = "thermal_twin"
LOGGER = logging.getLogger(__package__)

CONF_INDOOR_SENSOR = "indoor_sensor"
CONF_OUTDOOR_ENTITY = "outdoor_entity"
CONF_TARGET_TEMPERATURE = "target_temperature"
CONF_HVAC_ENTITY = "hvac_entity"
CONF_HVAC_TYPE = "hvac_type"
CONF_WINDOW_SENSORS = "window_sensors"
CONF_SOLAR_SENSOR = "solar_sensor"
CONF_COMFORT_MAX = "comfort_max"
# v0.2
CONF_COMFORT_MIN = "comfort_min"
CONF_INDOOR_HUMIDITY = "indoor_humidity"
CONF_OUTDOOR_HUMIDITY = "outdoor_humidity"
CONF_HUMIDITY_MAX = "humidity_max"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_POWER_SENSOR = "power_sensor"
CONF_POWER_THRESHOLD = "power_threshold"
CONF_READY_BY = "ready_by"
CONF_READY_TEMPERATURE = "ready_temperature"
CONF_USE_SUN = "use_sun"

HVAC_TYPE_HEAT = "heat"
HVAC_TYPE_COOL = "cool"

DEFAULT_TARGET_TEMPERATURE = 20.0
DEFAULT_HUMIDITY_MAX = 65.0
DEFAULT_POWER_THRESHOLD = 100.0

SAMPLE_INTERVAL_S = 300
MAX_GAP_S = SAMPLE_INTERVAL_S * 2.5
RETENTION_DAYS = 14
MAX_SAMPLES = RETENTION_DAYS * 86400 // SAMPLE_INTERVAL_S
BOOTSTRAP_DAYS = 7
SOLAR_MIN_COVERAGE = 0.8
SOLAR_MIN_GAIN = 0.02  # R² improvement needed to keep the solar term

STORAGE_VERSION = 1
STORAGE_SAVE_DELAY_S = 900

PREDICTION_HORIZON_H = 1.0
FORECAST_HORIZON_H = 12.0
FORECAST_POINT_STEP_H = 0.5
TARGET_SEARCH_H = 24.0
WEATHER_REFRESH_S = 1800
FORECAST_BIAS_DECAY_H = 6.0
PRECONDITION_MAX_LEAD_H = 6.0
SETPOINT_BAND = 0.5  # °C - an IR unit within this band of its setpoint is only holding

VENTILATION_MIN_GAIN = 1.0  # °C outdoor advantage before recommending
VENTILATION_HYSTERESIS = 0.5  # °C above comfort max before recommending
VENTILATION_MAX_EXTRA_HUMIDITY = 2.0  # g/m³ more water outside blocks the advice
DRY_MODE_TEMP_MARGIN = 1.0  # °C above comfort max where dry mode still makes sense

STATUS_OPTIONS = [
    "learning",
    "comfortable",
    "too_warm",
    "too_cold",
    "ventilate",
    "dry",
    "precondition",
    "cooling",
    "heating",
]
