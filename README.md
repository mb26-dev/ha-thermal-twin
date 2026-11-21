<p align="center"><img src="images/logo.png" width="320" alt="ThermalTwin"></p>

# ThermalTwin

**A thermal digital twin for every room – for heating *and* cooling climates.**

ThermalTwin learns how fast each room cools down and heats up from the sensors you
already have (indoor temperature + outdoor temperature or a weather entity) and turns
that into prediction entities you can use in automations.

It **does not control anything**. It works next to any thermostat, Better Thermostat,
Versatile Thermostat, SmartIR air conditioner – or no HVAC at all.

## What you get per room

| Entity | Meaning |
|---|---|
| `sensor.<room>_time_to_target` | Minutes until the room drifts to the target temperature on its own (attribute `eta`) |
| `sensor.<room>_time_to_target_with_hvac` | Minutes to reach the target with heating/cooling running – the pre-heat / pre-cool value |
| `sensor.<room>_equilibrium_temperature` | Temperature the room settles at under current conditions |
| `sensor.<room>_predicted_temperature_in_1_h` | Forecast for the next hour |
| `binary_sensor.<room>_ventilation_recommended` | Room above comfort max and outside cooler → open the window |
| `sensor.<room>_thermal_time_constant` | Diagnostic: how well the room holds temperature (hours) |
| `sensor.<room>_model_quality` | Diagnostic: R² of the learned model |
| `sensor.<room>_heating_rate` / `_cooling_rate` | Diagnostic: °C/h your HVAC adds or removes |

## How it works

A lumped single-zone model (Newton's law of cooling):

```
dT/dt = k·(T_out − T_in) + g·Solar + c + HVAC
```

* `k`, `g`, `c` are fitted by least squares on **passive** periods (HVAC off, windows closed).
* HVAC effect is learned separately for heating and cooling from active periods.
* On first setup the last **7 days of recorder history** are used, so most rooms are
  trained immediately. Samples are taken every 5 minutes and kept for 14 days.
* 100 % local, Python standard library only, no cloud, no extra dependencies.

## Installation

HACS → ⋮ → *Custom repositories* → `https://github.com/mb26-dev/ha-thermal-twin`
(category *Integration*) → install → restart → *Settings → Devices & services →
Add integration → ThermalTwin*. Add one entry per room.

Requires Home Assistant 2026.3 or newer.

## Automation examples

Start heating so the office is at 21 °C at 07:00:

```yaml
triggers:
  - trigger: template
    value_template: >
      {% set mins = states('sensor.office_time_to_target_with_hvac') | float(0) %}
      {{ now() + timedelta(minutes=mins) >= today_at('07:00') and now() < today_at('07:00') }}
actions:
  - action: climate.set_hvac_mode
    target: { entity_id: climate.office }
    data: { hvac_mode: heat }
```

Notify when ventilating would cool the bedroom:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.bedroom_ventilation_recommended
    to: "on"
actions:
  - action: notify.notify
    data:
      message: "Open the bedroom window – it's cooler outside."
```

## Limitations

* One air temperature per room; very large open-plan spaces are approximated.
* Ventilation advice uses temperature only (humidity is on the roadmap).
* Rooms whose HVAC never switches off can only learn the passive model when it does.

## License

MIT
