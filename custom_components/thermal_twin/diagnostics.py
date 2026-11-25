"""Diagnostics for ThermalTwin."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import ThermalTwinConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ThermalTwinConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    samples = coordinator.samples
    data = coordinator.data
    return {
        "options": dict(entry.options),
        "model": coordinator.params.as_dict(),
        "sample_count": len(samples),
        "first_sample_ts": samples[0].ts if samples else None,
        "last_samples": [s.to_list() for s in samples[-12:]],
        "current": {
            "t_in": data.t_in,
            "t_out": data.t_out,
            "solar": data.solar,
            "mode": data.mode,
            "uses_solar": data.use_solar,
            "equilibrium": data.equilibrium,
            "time_to_target_min": data.time_to_target_min,
            "time_to_target_hvac_min": data.time_to_target_hvac_min,
            "status": data.status,
            "hvac_on": data.hvac_on,
            "rh_in": data.rh_in,
            "rh_out": data.rh_out,
            "precondition": None if data.precondition is None else {
                "status": data.precondition.status,
                "start_ts": data.precondition.start_ts,
                "hvac_minutes": data.precondition.hvac_minutes,
            },
            "uses_weather_forecast": data.uses_weather_forecast,
            "solar_source": data.solar_source,
        },
    }
