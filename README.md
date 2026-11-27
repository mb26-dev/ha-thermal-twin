<p align="center">
  <img src="images/logo.png" alt="ThermalTwin" width="220">
</p>

<h1 align="center">🌡️ ThermalTwin</h1>

<p align="center">
  <b>The thermal digital twin for every room – built for air conditioners, made in the tropics.</b><br>
  Learns how fast your rooms heat up and cool down, plans when the AC has to start, and tells you what happens next.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white" alt="HACS"></a>
  <a href="https://github.com/mb26-dev/ha-thermal-twin/releases"><img src=".github/badge-release.svg" alt="Release v0.1.1"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.3%2B-18BCF2?logo=homeassistant&logoColor=white" alt="Home Assistant">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT"></a>
  <a href="https://ko-fi.com/mb26dev"><img src="https://img.shields.io/badge/Ko--fi-support-FF5E5B?logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
</p>

---

## 🤔 Why

Thermostats know the temperature **now**. They do not know how long your bedroom takes to cool down, where the living room will settle this afternoon, when the AC has to start so the room is cool at bedtime – or whether humidity, not heat, is the real problem.

ThermalTwin learns exactly that from the sensors you already have and turns it into entities for automations – plus a ready-made card that shows it all.

**Made for split air conditioners, one per room** – the setup of most homes in warm climates:

- ❄️ **Cooling-only units are first class.** No heat-and-cool thermostat required.
- 📡 **IR units without feedback** (Broadlink, SmartIR, ESPHome IR) are understood: Home Assistant only knows what it sent, so ThermalTwin skips the periods where the room already sits at the setpoint and learns the real pull-down capacity. Add a power plug or CT clamp and it knows exactly when the compressor runs.
- 💧 **Humidity matters as much as heat.** Dew point, absolute humidity, feels-like temperature, a dry-mode advice and ventilation advice that refuses to let humid air in.
- 🧭 **Advisor, not controller.** ThermalTwin creates sensors and leaves control to your automations, night profiles and thermostats. No sidebar panel, no cloud, no AI key.

## 🖼️ The card

The **ThermalTwin card** ships with the integration – no extra download, no resource to register:

```yaml
type: custom:thermal-twin-card
```

It finds all your ThermalTwin rooms on its own and shows them as tabs (swipe or tap). Per room: inside vs. outside with an animated heat flow, the current advice, a **12-hour forecast** with and without AC against your comfort band, the planned AC start, and the learned AC capacity.

| Option | Default | |
|---|---|---|
| `title` | `THERMALTWIN` | Card title |
| `rooms` | all | List of status sensors or room names, in the order you want |
| `hours` | `12` | Forecast range, 3–12 hours |
| `glow` | `true` | Gold border glow |

## ✨ What you get per room

| Entity | Meaning |
|---|---|
| `sensor.<room>_status` | 🧭 One state for the room: `comfortable`, `too_warm`, `ventilate`, `dry`, `precondition`, `cooling`, … – ideal for automations |
| `sensor.<room>_predicted_temperature_in_1_h` | 🔮 Forecast for the next hour (follows the weather forecast when configured) |
| `sensor.<room>_equilibrium_temperature` | ⚖️ Temperature the room settles at without AC |
| `sensor.<room>_time_to_target` | ⏱️ Minutes until the room drifts to the target on its own (attribute `eta`) |
| `sensor.<room>_time_to_target_with_hvac` | ❄️ Minutes to reach the target with the AC running |
| `sensor.<room>_start_for_ready_time` | ⏰ **When the AC has to start** so the room is at the ready temperature at your ready time |
| `binary_sensor.<room>_start_now_for_ready_time` | ▶️ Turns on at that moment – trigger your AC with it (blueprint included) |
| `sensor.<room>_feels_like` | 🥵 Heat index from temperature and humidity |
| `sensor.<room>_dew_point` / `_absolute_humidity` | 💧 Humidity in numbers that can be compared inside vs. outside |
| `binary_sensor.<room>_dry_mode_recommended` | 💨 Humidity, not heat, is the problem – dry mode beats cooling |
| `binary_sensor.<room>_ventilation_recommended` | 🪟 Outside is cooler **and** not more humid – open the windows |
| `sensor.<room>_runtime_today` | ⏳ How long the AC ran today |
| `sensor.<room>_energy_today` / `_efficiency` | ⚡ kWh today and °C of cooling per kWh (with a power meter) |
| `sensor.<room>_cooling_rate` / `_heating_rate` | 📊 Diagnostic: the learned capacity of your unit in °C/h |
| `sensor.<room>_model_quality` / `_thermal_time_constant` | 📊 Diagnostic: how well the model fits, how well the room holds its temperature |
| `binary_sensor.<room>_model_trained` · `button.<room>_reset_model` | ✅ Training state · 🔁 relearn from history |

Entities only appear when the sensors they need are configured.

## 🧠 How it works

A lumped single-zone model (Newton's law of cooling):

```
dT/dt = k·(T_out − T_in) + g·Sun + c + AC
```

* `k`, `g`, `c` are fitted by least squares on **passive** periods (AC off, windows closed). The sun term comes from a solar sensor or – new – simply from the **sun position**; it is only kept when it really improves the fit.
* The AC effect is learned separately for cooling and heating from active periods.
* Predictions are **simulated step by step** along the hourly **weather forecast** (bias-corrected to your own outdoor sensor), not with a frozen outdoor temperature.
* The **pre-cool planner** searches the latest start time that still reaches the ready temperature in time – no AC running longer than needed.
* ⚡ **Instant start:** on first setup the last 7 days of recorder history are used. Samples every 5 minutes, kept for 14 days.
* 🔒 100 % local, Python standard library only.

---

## 📦 Installation

### HACS (recommended)
1. HACS → ⋮ → **Custom repositories** → add `https://github.com/mb26-dev/ha-thermal-twin` as **Integration**
2. Install **ThermalTwin** and restart Home Assistant
3. **Settings → Devices & services → Add integration → ThermalTwin** – add one entry per room
4. Add the card: `type: custom:thermal-twin-card`

### Manual
Copy `custom_components/thermal_twin` into your `config/custom_components` folder and restart.

Requires Home Assistant **2026.3** or newer.

---

## ⚙️ Configuration

| Field | Description |
|---|---|
| **Indoor temperature sensor** | Any temperature sensor in the room |
| **Outdoor temperature** | A temperature sensor or a weather entity |
| **Target temperature** | Time-to-target refers to it, e.g. 28 °C as upper limit in the tropics |
| **Heating / cooling entity** | Optional. A `climate` entity (also IR / SmartIR) or a switch |
| **What the unit does** | Cooling or heating |
| **Window / door sensors** | Optional. Open periods are ignored for learning |
| **Solar sensor** | Optional. Without one, the sun position is used |
| **Comfort minimum / maximum** | Optional. Comfort band, ventilation advice |
| **Indoor / outdoor humidity** | Optional. Dew point, feels-like, dry-mode and humidity-aware ventilation |
| **Humidity limit** | Above it dry mode is recommended (default 65 %) |
| **Weather entity** | Optional. Hourly forecast for the predictions |
| **Power meter + threshold** | Optional. Exact compressor detection, energy and efficiency |
| **Ready by + ready temperature** | Optional. Daily time the room should be ready, e.g. bedtime – enables the pre-cool planner |

Everything can be changed later under **Configure**. Changing a sensor discards the learned data and relearns from recorder history.

---

## 💡 Automation ideas

**Cool the bedroom exactly in time for bedtime** – import the blueprint:

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmb26-dev%2Fha-thermal-twin%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fthermal_twin%2Fprecondition.yaml)

Switch to dry mode when humidity is the problem:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.bedroom_dry_mode_recommended
    to: "on"
    for: "00:15:00"
conditions:
  - condition: state
    entity_id: climate.bedroom_ac
    state: cool
actions:
  - action: climate.set_hvac_mode
    target: { entity_id: climate.bedroom_ac }
    data: { hvac_mode: dry }
```

Tell me when free cooling is possible:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.living_room_status
    to: ventilate
actions:
  - action: notify.notify
    data:
      message: "Open the living room windows – it's cooler and drier outside."
```

---

## 🆚 ThermalTwin or Climate Advisor?

[Climate Advisor](https://github.com/gunkl/ClimateAdvisor) is an excellent, mature integration that **takes over** a central heat-and-cool thermostat and schedules it for you. Pick it if that is your setup.

Pick **ThermalTwin** if you have **one air conditioner per room**, cooling only or IR controlled, care about humidity as much as temperature, and want predictions and advice while keeping control in your own automations.

## ℹ️ Good to know

- 🌴 **The AC must be known to the twin.** If an AC cools the room but Home Assistant does not see it, the room does not follow the outdoor temperature and the fit stays weak. Add it as heating/cooling entity – an IR blaster like a Broadlink RM4 Mini is enough.
- 📉 Watch **Model quality**: a low value means the room barely follows the outdoor temperature – treat predictions as rough.
- One air temperature per room; very large open-plan spaces are approximated.

## 🙏 Support

If ThermalTwin keeps your rooms comfortable, a coffee keeps the next project going: [ko-fi.com/mb26dev](https://ko-fi.com/mb26dev)

## 📄 License

MIT
