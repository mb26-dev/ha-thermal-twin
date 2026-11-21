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

HVAC_TYPE_HEAT = "heat"
HVAC_TYPE_COOL = "cool"

DEFAULT_TARGET_TEMPERATURE = 20.0

SAMPLE_INTERVAL_S = 300
MAX_GAP_S = SAMPLE_INTERVAL_S * 2.5
RETENTION_DAYS = 14
MAX_SAMPLES = RETENTION_DAYS * 86400 // SAMPLE_INTERVAL_S
BOOTSTRAP_DAYS = 7
SOLAR_MIN_COVERAGE = 0.8

STORAGE_VERSION = 1
STORAGE_SAVE_DELAY_S = 900

PREDICTION_HORIZON_H = 1.0
VENTILATION_MIN_GAIN = 1.0  # °C outdoor advantage before recommending
VENTILATION_HYSTERESIS = 0.5  # °C above comfort max before recommending
