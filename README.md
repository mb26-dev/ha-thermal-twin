<p align="center">
  <img src="images/logo.png" alt="ThermalTwin" width="220">
</p>

<h1 align="center">🌡️ ThermalTwin</h1>

<p align="center">
  <b>A thermal digital twin for every room in Home Assistant – for heating <i>and</i> cooling climates.</b><br>
  Learns how fast your rooms heat up and cool down, and tells you what happens next.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white" alt="HACS"></a>
  <img src="https://img.shields.io/github/v/release/mb26-dev/ha-thermal-twin?include_prereleases&label=release" alt="Release">
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.3%2B-18BCF2?logo=homeassistant&logoColor=white" alt="Home Assistant">
  <a href="https://github.com/mb26-dev/ha-thermal-twin/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/mb26-dev/ha-thermal-twin/validate.yml?branch=main&label=validate" alt="Validate"></a>
  <a href="https://ko-fi.com/mb26dev"><img src="https://img.shields.io/badge/Ko--fi-support-FF5E5B?logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
</p>

---

## 🤔 Why

Thermostats know the temperature **now**. They do not know how long your bedroom takes to cool down, where the living room will settle this afternoon, or whether opening the window helps right now.

ThermalTwin learns exactly that from the sensors you already have – one indoor temperature sensor plus an outdoor temperature sensor or weather entity – and turns it into prediction entities you can use in automations and dashboards.

It **does not control anything**. It runs next to any thermostat, Better Thermostat, Versatile Thermostat, an IR air conditioner (Broadlink, SmartIR) – or no HVAC at all.

## ✨ What you get per room

| Entity | Meaning |
|---|---|
| `sensor.<room>_time_to_target` | ⏱️ Minutes until the room drifts to the target temperature on its own (attribute `eta`) |
| `sensor.<room>_time_to_target_with_hvac` | 🔥❄️ Minutes to reach the target with heating/cooling running – the pre-heat / pre-cool value |
| `sensor.<room>_equilibrium_temperature` | ⚖️ Temperature the room settles at under current conditions |
| `sensor.<room>_predicted_temperature_in_1_h` | 🔮 Forecast for the next hour |
| `binary_sensor.<room>_ventilation_recommended` | 🪟 Room above comfort max and outside cooler → open the window |
| `sensor.<room>_thermal_time_constant` | 📊 Diagnostic: how well the room holds its temperature (hours) |
| `sensor.<room>_model_quality` | 📊 Diagnostic: R² of the learned model |
| `sensor.<room>_heating_rate` / `_cooling_rate` | 📊 Diagnostic: °C/h your HVAC adds or removes |
| `binary_sensor.<room>_model_trained` | ✅ The twin has enough data to predict |
| `button.<room>_reset_model` | 🔁 Forget everything and relearn from recorder history |

The HVAC entities only appear when a heating/cooling entity is configured for the room.

## 🧠 How it works

A lumped single-zone model (Newton's law of cooling):

```
dT/dt = k·(T_out − T_in) + g·Solar + c + HVAC
```

* `k`, `g`, `c` are fitted by least squares on **passive** periods (HVAC off, windows closed).
* The HVAC effect is learned separately for heating and cooling from active periods.
* ⚡ **Instant start:** on first setup the last **7 days of recorder history** are used, so most rooms are trained right away. Samples are taken every 5 minutes and kept for 14 days.
* 🔒 100 % local, Python standard library only, no cloud, no extra dependencies.

---

## 📦 Installation

### HACS (recommended)
1. HACS → ⋮ → **Custom repositories** → add `https://github.com/mb26-dev/ha-thermal-twin` as **Integration**
2. Install **ThermalTwin** and restart Home Assistant
3. **Settings → Devices & services → Add integration → ThermalTwin** – add one entry per room

### Manual
Copy `custom_components/thermal_twin` into your `config/custom_components` folder and restart.

Requires Home Assistant **2026.3** or newer.

---

## ⚙️ Configuration

| Field | Description |
|---|---|
| **Room name** | Used for the device and the entity IDs |
| **Indoor temperature sensor** | Any temperature sensor in the room |
| **Outdoor temperature** | A temperature sensor or a weather entity |
| **Target temperature** | Time-to-target refers to this value, e.g. 19 °C as lower limit in winter or 28 °C as upper limit in the tropics |
| **Heating / cooling entity** | Optional. A `climate` entity reports heating/cooling itself; for a switch or plug choose the type |
| **Window / door sensors** | Optional. Periods with an open window are ignored for learning |
| **Solar sensor** | Optional. Irradiance (W/m²) or lux |
| **Comfort maximum** | Optional. Creates the ventilation sensor |

Everything can be changed later under **Configure**. Changing a sensor discards the learned data and relearns from recorder history.

---

## 💡 Automation ideas

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

---

## ℹ️ Good to know

- 🌴 **Air conditioning must be known to the twin.** If an AC cools the room but Home Assistant does not see it, the room does not follow the outdoor temperature and the twin refuses to predict. Add the AC as heating/cooling entity (e.g. an IR blaster like a Broadlink RM4 Mini) and the cooling periods are learned separately.
- 📉 Watch **Model quality**: a low value means the room barely follows the outdoor temperature – treat predictions as rough.
- One air temperature per room; very large open-plan spaces are approximated.
- Ventilation advice uses temperature only (humidity is on the roadmap).

## 🙏 Support

If ThermalTwin keeps your rooms comfortable, a coffee keeps the next project going: [ko-fi.com/mb26dev](https://ko-fi.com/mb26dev)

## 📄 License

MIT
