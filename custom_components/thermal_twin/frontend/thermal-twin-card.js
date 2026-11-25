/*
 * ThermalTwin card - bundled with the ThermalTwin integration.
 * Finds every ThermalTwin room on its own. Minimal config:
 *
 *   type: custom:thermal-twin-card
 *
 * Options: title, rooms (list of ThermalTwin status sensors to show, in order),
 *          glow (default true), hours (forecast hours, 3-12, default 12).
 */
const TT_VERSION = "0.2.0";

const STATUS = {
  learning: { c: "#FF9800", t: "LEARNING", i: "mdi:school-outline" },
  comfortable: { c: "#4CAF50", t: "COMFORTABLE", i: "mdi:emoticon-happy-outline" },
  too_warm: { c: "#FF7043", t: "TOO WARM", i: "mdi:thermometer-high" },
  too_cold: { c: "#64B5F6", t: "TOO COLD", i: "mdi:thermometer-low" },
  ventilate: { c: "#4CAF50", t: "VENTILATE", i: "mdi:window-open-variant" },
  dry: { c: "#B388FF", t: "DRY MODE", i: "mdi:water-percent" },
  precondition: { c: "#22d3ee", t: "START AC", i: "mdi:clock-alert-outline" },
  cooling: { c: "#22d3ee", t: "COOLING", i: "mdi:snowflake" },
  heating: { c: "#FF7043", t: "HEATING", i: "mdi:fire" },
};

const KEYS = [
  "status", "time_to_target", "time_to_target_hvac", "equilibrium_temperature",
  "predicted_temperature_1h", "precondition_start", "dew_point", "absolute_humidity",
  "apparent_temperature", "hvac_runtime_today", "hvac_energy_today", "hvac_efficiency",
  "time_constant", "model_quality", "cooling_rate", "heating_rate", "model_trained",
  "ventilation_recommended", "precondition_now", "dry_mode_recommended",
];

const ROOM_ICONS = [
  [/bed|schlaf|sleep|master/i, "mdi:bed-outline"],
  [/guest|gast/i, "mdi:bed-double-outline"],
  [/living|wohn|lounge/i, "mdi:sofa-outline"],
  [/kitchen|küche|kueche/i, "mdi:fridge-outline"],
  [/office|büro|buero|study|arbeit/i, "mdi:desk"],
  [/kid|kinder|child|nursery/i, "mdi:teddy-bear"],
  [/bath|bad/i, "mdi:shower"],
];

const CSS = `
:host{display:block;}
ha-card{position:relative;overflow:hidden;padding:14px;border-radius:var(--tt-radius,18px);
  color:#e8e8e8;background:var(--tt-bg,linear-gradient(160deg,#1c1a14 0%,#121212 55%,#0d1214 100%));}
ha-card.glow{border:1px solid rgba(255,215,0,0.38);box-shadow:0 0 18px rgba(255,215,0,0.16),inset 0 0 22px rgba(255,215,0,0.04);}
*{box-sizing:border-box;}
.hd{display:flex;align-items:center;gap:10px;}
.logo{flex:0 0 38px;height:38px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#FFD70033,#22d3ee22);border:1px solid #FFD70055;}
.logo ha-icon{--mdc-icon-size:22px;color:#FFD700;}
.ttl{flex:1;min-width:0;}
.ttl b{display:block;font-size:15px;letter-spacing:2px;color:#FFD700;font-weight:800;}
.ttl span{display:block;font-size:11px;color:#9e9e9e;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.pill{flex:0 0 auto;display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:999px;font-size:10.5px;
  font-weight:800;letter-spacing:1px;color:var(--sc);border:1px solid var(--sc);background:color-mix(in srgb,var(--sc) 12%,transparent);}
.pill ha-icon{--mdc-icon-size:14px;}
.tabs{display:flex;gap:4px;margin:12px 0 12px;padding:4px;border-radius:999px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,215,0,0.2);}
.tab{flex:1 1 0;min-width:0;display:flex;align-items:center;justify-content:center;gap:5px;padding:7px 4px;border-radius:999px;
  font-size:11px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;color:#9e9e9e;cursor:pointer;white-space:nowrap;
  overflow:hidden;user-select:none;-webkit-tap-highlight-color:transparent;transition:all .25s ease;}
.tab span{overflow:hidden;text-overflow:ellipsis;}
.tab ha-icon{--mdc-icon-size:15px;flex:0 0 15px;}
.tab .snow{--mdc-icon-size:13px;flex:0 0 13px;color:#22d3ee;animation:spin 6s linear infinite;}
.tab.on{color:#111;background:linear-gradient(90deg,#B8860B,#FFD700);box-shadow:0 0 12px #FFD70055;}
.tab.on .snow{color:#00505e;}
.hero{display:grid;grid-template-columns:minmax(0,1.15fr) 52px minmax(0,1fr);gap:6px;align-items:stretch;}
.box{border-radius:14px;padding:10px 12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);min-width:0;}
.box small{display:block;font-size:10px;color:#9e9e9e;text-transform:uppercase;letter-spacing:0.6px;white-space:nowrap;}
.box .big{display:block;font-size:30px;font-weight:800;line-height:1.1;margin-top:2px;white-space:nowrap;}
.box .mid{display:block;font-size:24px;font-weight:700;line-height:1.15;margin-top:4px;white-space:nowrap;color:#22d3ee;}
.box em{display:block;font-style:normal;font-size:10.5px;color:#9a9a9a;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.flow{display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:0;}
.arrow{position:relative;width:100%;height:14px;overflow:hidden;border-radius:999px;background:rgba(255,255,255,0.04);}
.arrow i{position:absolute;top:4px;left:0;width:6px;height:6px;border-radius:50%;background:var(--fc);box-shadow:0 0 6px var(--fc);opacity:0;animation:flow 1.8s linear infinite;}
.arrow i:nth-child(2){animation-delay:.6s;}.arrow i:nth-child(3){animation-delay:1.2s;}
.arrow.rev i{animation-name:flowr;}
.arrow.none i{animation:none;opacity:.5;left:calc(50% - 3px);}
.arrow.none i:nth-child(2),.arrow.none i:nth-child(3){display:none;}
.dl{font-size:11px;font-weight:800;color:var(--fc);margin-top:4px;white-space:nowrap;}
.dc{font-size:8.5px;color:#8a8a8a;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap;}
.advice{display:flex;align-items:flex-start;gap:8px;margin-top:10px;padding:9px 11px;border-radius:12px;font-size:12px;line-height:1.35;
  border:1px solid color-mix(in srgb,var(--sc) 45%,transparent);background:color-mix(in srgb,var(--sc) 8%,transparent);color:#e8e8e8;}
.advice ha-icon{--mdc-icon-size:17px;flex:0 0 17px;color:var(--sc);margin-top:0;}
.advice b{color:var(--sc);}
.sec{display:flex;justify-content:space-between;align-items:baseline;font-size:10px;color:#9e9e9e;text-transform:uppercase;letter-spacing:1px;margin:14px 0 4px;}
.sec span:last-child{text-transform:none;letter-spacing:0;color:#777;}
.chart{position:relative;width:100%;touch-action:pan-y;}
.chart svg{display:block;width:100%;height:auto;overflow:visible;}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:10px;color:#9e9e9e;margin-top:4px;}
.legend span{display:inline-flex;align-items:center;gap:5px;}
.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:10px;}
.chip{background:rgba(255,215,0,0.05);border:1px solid rgba(255,215,0,0.2);border-radius:14px;padding:8px 10px;min-width:0;cursor:pointer;}
.chip small{display:block;font-size:10px;color:#9e9e9e;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.chip b{display:block;font-size:16px;font-weight:800;color:var(--v,#fff);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.chip em{display:block;font-style:normal;font-size:10px;color:#8a8a8a;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.ac{display:flex;align-items:center;gap:10px;margin-top:10px;padding:10px 12px;border-radius:14px;cursor:pointer;
  border:1px solid var(--ab,rgba(255,255,255,0.14));background:rgba(255,255,255,0.03);}
.ac ha-icon{--mdc-icon-size:24px;flex:0 0 24px;color:var(--ac,#9e9e9e);}
.ac .acx{flex:1;min-width:0;font-size:12px;line-height:1.3;}
.ac .acx b{color:var(--ac,#e0e0e0);letter-spacing:.5px;}
.ac .acx em{display:block;font-style:normal;font-size:10.5px;color:#8a8a8a;margin-top:2px;}
.ac .acr{flex:0 0 auto;text-align:right;font-size:10px;color:#8a8a8a;line-height:1.35;}
.ac .acr b{display:block;font-size:14px;color:#FFD700;}
.prog{position:relative;height:8px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,0.06);margin-top:6px;}
.fill{position:absolute;top:0;bottom:0;left:0;border-radius:999px;background:linear-gradient(90deg,#B8860B,#FFD700);overflow:hidden;}
.shim{position:absolute;top:0;bottom:0;width:40px;left:-40px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.35),transparent);animation:shim 2.8s ease-in-out infinite;}
.ft{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 10px;margin-top:12px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.08);
  font-size:10.5px;color:#8a8a8a;cursor:pointer;}
.ft b{color:#FFD700;font-weight:700;}
.empty{padding:18px 6px;text-align:center;color:#9e9e9e;font-size:13px;line-height:1.5;}
.empty b{color:#FFD700;}
.fade{animation:fade .35s ease;}
@keyframes flow{0%{left:0;opacity:0}15%{opacity:1}85%{opacity:1}100%{left:calc(100% - 6px);opacity:0}}
@keyframes flowr{0%{left:calc(100% - 6px);opacity:0}15%{opacity:1}85%{opacity:1}100%{left:0;opacity:0}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes shim{0%{left:-40px}100%{left:100%}}
@keyframes fade{from{opacity:.35;transform:translateX(var(--dx,0))}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}
`;

function num(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}
const f1 = (v) => (v === null || v === undefined ? "–" : Number(v).toFixed(1));
function dur(min) {
  if (min === null || min === undefined) return null;
  const m = Math.round(min);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h}h ${String(r).padStart(2, "0")}m` : `${h}h`;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

class ThermalTwinCard extends HTMLElement {
  constructor() {
    super();
    this._idx = 0;
    this._sig = "";
    this.attachShadow({ mode: "open" });
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { glow: true, hours: 12, ...(config || {}) };
    this._sig = "";
    if (this._hass) this._render();
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  set hass(hass) {
    this._hass = hass;
    const rooms = this._rooms();
    const sig = this._signature(rooms);
    if (sig === this._sig) return;
    this._sig = sig;
    this._render(rooms);
  }

  /* ------------------------------------------------------------ discovery */

  _rooms() {
    const hass = this._hass;
    if (!hass || !hass.entities) return [];
    const byDevice = new Map();
    for (const e of Object.values(hass.entities)) {
      if (e.platform !== "thermal_twin" || !e.device_id) continue;
      if (!byDevice.has(e.device_id)) byDevice.set(e.device_id, []);
      byDevice.get(e.device_id).push(e);
    }
    let rooms = [];
    for (const [deviceId, ents] of byDevice) {
      const map = {};
      for (const key of KEYS) {
        const hit =
          ents.find((e) => e.translation_key === key) ||
          ents.find((e) => e.entity_id.endsWith("_" + key) && !(key === "time_to_target" && e.entity_id.endsWith("_hvac")));
        if (hit) map[key] = hit.entity_id;
      }
      if (!map.status) continue;
      const device = hass.devices ? hass.devices[deviceId] : null;
      const name = (device && (device.name_by_user || device.name)) || map.status;
      rooms.push({ id: deviceId, name, e: map });
    }
    const wanted = this._config && Array.isArray(this._config.rooms) ? this._config.rooms : null;
    if (wanted && wanted.length) {
      rooms = wanted
        .map((w) => rooms.find((r) => r.e.status === w || r.name.toLowerCase() === String(w).toLowerCase()))
        .filter(Boolean);
    }
    return rooms;
  }

  _signature(rooms) {
    const s = this._hass.states;
    const parts = [rooms.map((r) => r.id).join(","), this._idx];
    for (const r of rooms) {
      const st = s[r.e.status];
      parts.push(st ? st.last_updated : "-");
      const hvac = st && st.attributes.room ? st.attributes.room.hvac_entity : null;
      if (hvac && s[hvac]) parts.push(s[hvac].last_updated);
    }
    const cur = rooms[Math.min(this._idx, rooms.length - 1)];
    if (cur) {
      for (const id of Object.values(cur.e)) parts.push(s[id] ? s[id].last_updated : "-");
      const st = s[cur.e.status];
      const room = st && st.attributes.room;
      if (room) {
        for (const id of [room.indoor_sensor, room.outdoor_entity, room.indoor_humidity]) {
          if (id && s[id]) parts.push(s[id].last_updated);
        }
      }
    }
    return parts.join("|");
  }

  /* --------------------------------------------------------------- events */

  _moreInfo(entityId) {
    if (!entityId) return;
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId };
    this.dispatchEvent(ev);
  }

  _select(idx, dir) {
    const rooms = this._rooms();
    if (!rooms.length) return;
    this._idx = (idx + rooms.length) % rooms.length;
    this._dir = dir || 0;
    this._sig = "";
    this._render(rooms);
  }

  _bind(rooms) {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-tab]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const i = Number(el.dataset.tab);
        this._select(i, i > this._idx ? 1 : -1);
      })
    );
    root.querySelectorAll("[data-more]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._moreInfo(el.dataset.more);
      })
    );
    const swipe = root.querySelector(".swipe");
    if (swipe && rooms.length > 1) {
      let x0 = null;
      let y0 = null;
      swipe.addEventListener("touchstart", (e) => {
        x0 = e.touches[0].clientX;
        y0 = e.touches[0].clientY;
      }, { passive: true });
      swipe.addEventListener("touchend", (e) => {
        if (x0 === null) return;
        const dx = e.changedTouches[0].clientX - x0;
        const dy = e.changedTouches[0].clientY - y0;
        x0 = null;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) {
          this._select(this._idx + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1);
        }
      }, { passive: true });
    }
  }

  /* --------------------------------------------------------------- render */

  _fmtTime(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (isNaN(d)) return null;
    const hass = this._hass;
    try {
      return d.toLocaleTimeString((hass.locale && hass.locale.language) || hass.language || "en", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: hass.config && hass.config.time_zone ? hass.config.time_zone : undefined,
      });
    } catch (e) {
      return d.toTimeString().slice(0, 5);
    }
  }

  _icon(name) {
    for (const [re, icon] of ROOM_ICONS) if (re.test(name)) return icon;
    return "mdi:home-thermometer-outline";
  }

  _render(rooms) {
    if (!this._hass || !this._config) return;
    rooms = rooms || this._rooms();
    const glow = this._config.glow !== false ? "glow" : "";
    if (!rooms.length) {
      this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card class="${glow}">
        <div class="hd"><div class="logo"><ha-icon icon="mdi:home-thermometer"></ha-icon></div>
        <div class="ttl"><b>THERMALTWIN</b><span>Digital twin of your rooms</span></div></div>
        <div class="empty">No ThermalTwin room found.<br>Add one under <b>Settings → Devices &amp; services → ThermalTwin</b>.</div></ha-card>`;
      return;
    }
    if (this._idx >= rooms.length) this._idx = 0;
    const room = rooms[this._idx];
    const s = this._hass.states;
    const st = s[room.e.status];
    const a = st ? st.attributes : {};
    const cfg = a.room || {};
    const status = st ? st.state : "learning";
    const meta = STATUS[status] || STATUS.learning;
    const trainedState = s[room.e.model_trained];
    const trained = trainedState ? trainedState.state === "on" : false;

    const tin = num(a.indoor_temperature);
    const tout = num(a.outdoor_temperature);
    const rhIn = num(a.indoor_humidity);
    const rhOut = num(a.outdoor_humidity);
    const cmax = num(a.comfort_max);
    const cmin = num(a.comfort_min);
    const target = num(a.target);
    const val = (k) => (room.e[k] && s[room.e[k]] ? num(s[room.e[k]].state) : null);
    const attr = (k, n) => (room.e[k] && s[room.e[k]] ? s[room.e[k]].attributes[n] : null);

    const upper = cmax !== null ? cmax : target;
    const lower = cmin !== null ? cmin : null;
    const tc = tin === null ? "#9e9e9e" : upper !== null && tin > upper + 1.5 ? "#F44336" : upper !== null && tin > upper ? "#FF9800"
      : lower !== null && tin < lower ? "#64B5F6" : "#4CAF50";

    /* heat flow */
    const d = tin !== null && tout !== null ? tout - tin : null;
    let fc = "#9e9e9e", fcls = "none", fcap = "balanced";
    if (d !== null && d > 0.3) { fc = "#FF9800"; fcls = "rev"; fcap = "heat in"; }
    else if (d !== null && d < -0.3) { fc = "#22d3ee"; fcls = ""; fcap = "heat out"; }
    const dTxt = d === null ? "–" : (Math.abs(d) < 0.05 ? "±0.0" : (d > 0 ? "+" : "") + d.toFixed(1)) + "°";

    const feels = val("apparent_temperature");
    const dew = val("dew_point");
    const absIn = val("absolute_humidity");
    const absOut = num(attr("absolute_humidity", "outdoor"));
    const inSub = [rhIn !== null ? `${rhIn.toFixed(0)} %` : null, dew !== null ? `dew ${dew.toFixed(1)}°` : null].filter(Boolean).join(" · ");
    const outSub = [rhOut !== null ? `${rhOut.toFixed(0)} %` : null, absOut !== null ? `${absOut.toFixed(1)} g/m³` : null].filter(Boolean).join(" · ");

    /* hvac */
    const hvacId = cfg.hvac_entity;
    const hvac = hvacId ? s[hvacId] : null;
    const hvacOn = a.hvac_on === true;

    /* advice */
    const readyTime = this._fmtTime(a.ready_at);
    const startTime = this._fmtTime(a.precondition_start);
    const readyT = num(a.ready_temperature);
    let advice = "";
    switch (status) {
      case "learning": {
        const q = s[room.e.model_quality];
        const samples = q ? Number(q.attributes.samples || 0) : 0;
        advice = `<b>Learning this room.</b> ${samples.toLocaleString("en-US")} samples so far – predictions unlock once there are a few hours without AC and with windows closed.`;
        break;
      }
      case "cooling":
      case "heating": {
        const eta = this._fmtTime(attr("time_to_target_hvac", "eta"));
        advice = `<b>${status === "cooling" ? "Cooling" : "Heating"}.</b> ` + (eta && target !== null ? `Reaches ${target.toFixed(0)} °C around <b>${eta}</b>.` : "The twin is learning the unit's real capacity.");
        break;
      }
      case "precondition":
        advice = `<b>Start the AC now</b> to have ${readyT !== null ? readyT.toFixed(0) + " °C" : "the room ready"} by <b>${readyTime || "–"}</b>.`;
        break;
      case "ventilate":
        advice = `<b>Open the windows.</b> Outside is ${d !== null ? Math.abs(d).toFixed(1) : "–"}° cooler and not more humid – free cooling.`;
        break;
      case "dry":
        advice = `<b>Dry mode beats cooling.</b> ${rhIn !== null ? rhIn.toFixed(0) : "–"} % humidity is the problem, not the heat – drying feels cooler for less energy.`;
        break;
      case "too_warm":
        advice = a.ventilation_blocked_by_humidity
          ? `<b>Too warm – keep windows closed.</b> Outside is cooler but carries ${absOut !== null && absIn !== null ? (absOut - absIn).toFixed(1) : "much"} g/m³ more water.`
          : `<b>Above ${upper !== null ? upper.toFixed(0) : "–"} °C.</b> ` + (d !== null && d >= 0 ? `Outside is ${d.toFixed(1)}° warmer – windows closed, AC on.` : "Outside is not cool enough to help.");
        break;
      case "too_cold":
        advice = `<b>Below comfort.</b> ${lower !== null ? "Comfort starts at " + lower.toFixed(0) + " °C." : ""}`;
        break;
      default:
        advice = `<b>Comfortable.</b> ` + (startTime && a.precondition === "scheduled" ? `AC start planned at <b>${startTime}</b> for ${readyTime}.` : "Nothing to do right now.");
    }

    /* tabs */
    const tabs = rooms.length > 1
      ? `<div class="tabs">${rooms.map((r, i) => {
          const rs = s[r.e.status];
          const on = rs && rs.attributes.hvac_on === true;
          const label = r.name.replace(/\s*room$/i, "");
          return `<div class="tab${i === this._idx ? " on" : ""}" data-tab="${i}"><ha-icon icon="${this._icon(r.name)}"></ha-icon><span>${esc(label)}</span>${on ? '<ha-icon class="snow" icon="mdi:snowflake"></ha-icon>' : ""}</div>`;
        }).join("")}</div>`
      : "";

    /* chips */
    const p1 = val("predicted_temperature_1h");
    const eq = val("equilibrium_temperature");
    const ttt = val("time_to_target");
    const tttEta = this._fmtTime(attr("time_to_target", "eta"));
    const tttH = val("time_to_target_hvac");
    const tttHEta = this._fmtTime(attr("time_to_target_hvac", "eta"));
    const chips = [];
    if (trained) {
      chips.push(`<div class="chip" style="--v:#FFD700" data-more="${room.e.predicted_temperature_1h || ""}"><small>In 1 hour</small><b>${f1(p1)} °C</b><em>${p1 !== null && tin !== null ? (p1 - tin >= 0 ? "+" : "") + (p1 - tin).toFixed(1) + "° vs now" : "no forecast"}</em></div>`);
      chips.push(`<div class="chip" data-more="${room.e.equilibrium_temperature || ""}"><small>Settles at</small><b>${f1(eq)} °C</b><em>without AC, current weather</em></div>`);
      if (target !== null) {
        if (hvacId && tttH !== null && (hvacOn || ttt === null)) {
          chips.push(`<div class="chip" style="--v:#22d3ee" data-more="${room.e.time_to_target_hvac || ""}"><small>${target.toFixed(0)} °C with AC</small><b>${dur(tttH)}</b><em>${tttHEta ? "at " + tttHEta : ""}</em></div>`);
        } else {
          chips.push(`<div class="chip" style="--v:${ttt !== null ? "#22d3ee" : "#9e9e9e"}" data-more="${room.e.time_to_target || ""}"><small>Reaches ${target.toFixed(0)} °C</small><b>${ttt !== null ? dur(ttt) : "not today"}</b><em>${tttEta ? "at " + tttEta : "on its own"}</em></div>`);
        }
      }
      if (room.e.precondition_start) {
        const plan = a.precondition;
        const txt = plan === "not_needed" ? "not needed" : plan === "late" ? "now (late)" : plan === "now" ? "now" : startTime || "–";
        chips.push(`<div class="chip" style="--v:${plan === "now" || plan === "late" ? "#22d3ee" : "#FFD700"}" data-more="${room.e.precondition_start}"><small>AC start for ${readyTime || "–"}</small><b>${txt}</b><em>${readyT !== null ? readyT.toFixed(0) + " °C by " + (readyTime || "–") : ""}</em></div>`);
      } else if (feels !== null) {
        chips.push(`<div class="chip" style="--v:${feels > (upper || 99) + 3 ? "#FF7043" : "#fff"}" data-more="${room.e.apparent_temperature}"><small>Feels like</small><b>${f1(feels)} °C</b><em>heat index from humidity</em></div>`);
      } else {
        const tau = val("time_constant");
        chips.push(`<div class="chip" data-more="${room.e.time_constant || ""}"><small>Thermal inertia</small><b>${tau !== null ? tau.toFixed(1) + " h" : "–"}</b><em>time constant τ</em></div>`);
      }
    }

    /* AC block */
    let ac = "";
    if (hvacId) {
      const runtime = val("hvac_runtime_today");
      const energy = val("hvac_energy_today");
      const rate = val(cfg.hvac_type === "heat" ? "heating_rate" : "cooling_rate");
      const modeTxt = hvac ? (hvac.attributes.hvac_action || hvac.state) : "unavailable";
      const set = hvac && hvacOn && hvac.attributes.temperature !== undefined ? ` · set ${hvac.attributes.temperature} °C` : "";
      const fan = hvac && hvacOn && hvac.attributes.fan_mode ? ` · fan ${hvac.attributes.fan_mode}` : "";
      const learned = rate !== null ? `Learned ${cfg.hvac_type === "heat" ? "heating" : "cooling"} rate ${rate > 0 ? "+" : ""}${rate.toFixed(2)} °C/h` : "Learning the real capacity – needs a few AC cycles";
      const col = hvacOn ? (cfg.hvac_type === "heat" ? "#FF7043" : "#22d3ee") : "#9e9e9e";
      ac = `<div class="ac" style="--ac:${col};--ab:${hvacOn ? col + "66" : "rgba(255,255,255,0.14)"}" data-more="${hvacId}">
        <ha-icon icon="${hvacOn ? "mdi:air-conditioner" : "mdi:air-conditioner"}"></ha-icon>
        <div class="acx"><b>AC ${esc(String(modeTxt).toUpperCase())}</b>${esc(set)}${esc(fan)}<em>${learned}</em></div>
        <div class="acr">${runtime !== null ? `<b>${dur(runtime) || "0 min"}</b>today` : ""}${energy !== null ? `<br>${energy.toFixed(2)} kWh` : ""}</div></div>`;
    }

    /* learning progress or quality */
    const q = s[room.e.model_quality];
    const qv = q ? num(q.state) : null;
    const samples = q ? Number(q.attributes.samples || 0) : 0;
    let learn = "";
    if (!trained) {
      const frac = Math.min(1, samples / 4032);
      learn = `<div class="sec"><span>Learning</span><span>${samples.toLocaleString("en-US")} samples</span></div>
        <div class="prog"><div class="fill" style="width:${Math.max(2, frac * 100).toFixed(1)}%"><div class="shim"></div></div></div>`;
    }

    const chart = trained ? this._chart(a, tin, upper, lower, target) : "";
    const extras = [
      a.uses_weather_forecast ? "weather forecast" : "constant weather",
      a.solar_source === "sun" ? "sun position" : a.solar_source === "sensor" ? "solar sensor" : null,
    ].filter(Boolean).join(" · ");

    const dx = this._dir ? (this._dir > 0 ? "18px" : "-18px") : "0";
    this._dir = 0;
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <ha-card class="${glow}">
        <div class="hd">
          <div class="logo"><ha-icon icon="mdi:home-thermometer"></ha-icon></div>
          <div class="ttl"><b>${esc(this._config.title || "THERMALTWIN")}</b><span>${esc(room.name)} · digital twin</span></div>
          <div class="pill" style="--sc:${meta.c}"><ha-icon icon="${meta.i}"></ha-icon>${meta.t}</div>
        </div>
        ${tabs}
        <div class="swipe fade" style="--dx:${dx}">
          <div class="hero" style="--fc:${fc}">
            <div class="box" data-more="${cfg.indoor_sensor || ""}"><small>Inside</small><span class="big" style="color:${tc}">${f1(tin)}°</span><em>${feels !== null ? `feels ${feels.toFixed(1)}° · ` : ""}${inSub || "&nbsp;"}</em></div>
            <div class="flow"><div class="arrow ${fcls}"><i></i><i></i><i></i></div><div class="dl">${dTxt}</div><div class="dc">${fcap}</div></div>
            <div class="box" data-more="${cfg.outdoor_entity || ""}"><small>Outside</small><span class="mid">${f1(tout)}°</span><em>${outSub || "&nbsp;"}</em></div>
          </div>
          <div class="advice" style="--sc:${meta.c}"><ha-icon icon="${meta.i}"></ha-icon><span>${advice}</span></div>
          ${chart}
          ${chips.length ? `<div class="grid">${chips.join("")}</div>` : ""}
          ${ac}
          ${learn}
        </div>
        <div class="ft" data-more="${room.e.model_quality || ""}">
          <span>Fit <b>${qv !== null ? qv.toFixed(0) + " %" : "–"}</b> · ${extras}</span>
          <span>ThermalTwin v${TT_VERSION}</span>
        </div>
      </ha-card>`;
    this._bind(rooms);
  }

  _chart(a, tin, upper, lower, target) {
    const raw = Array.isArray(a.forecast) ? a.forecast : [];
    const hours = Math.max(3, Math.min(12, Number(this._config.hours) || 12));
    const pts = raw.filter((p) => Array.isArray(p) && p[0] <= hours * 60 + 1);
    if (pts.length < 2) return "";
    const W = 340, H = 150, L = 28, R = 8, T = 10, B = 22;
    const maxMin = pts[pts.length - 1][0] || hours * 60;
    const vals = [];
    for (const p of pts) for (const v of [p[1], p[2], p[3]]) if (v !== null && v !== undefined) vals.push(v);
    for (const v of [upper, lower, target, tin]) if (v !== null && v !== undefined) vals.push(v);
    let lo = Math.floor(Math.min(...vals) - 0.5), hi = Math.ceil(Math.max(...vals) + 0.5);
    if (hi - lo < 4) { const m = (hi + lo) / 2; lo = Math.floor(m - 2); hi = Math.ceil(m + 2); }
    const x = (m) => L + (m / maxMin) * (W - L - R);
    const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const path = (i) => {
      let dStr = "";
      let pen = false;
      for (const p of pts) {
        const v = p[i];
        if (v === null || v === undefined) { pen = false; continue; }
        dStr += `${pen ? "L" : "M"}${x(p[0]).toFixed(1)},${y(v).toFixed(1)} `;
        pen = true;
      }
      return dStr;
    };
    const passive = path(1);
    const withAc = path(2);
    const outdoor = path(3);
    const area = passive ? `${passive} L${x(pts[pts.length - 1][0]).toFixed(1)},${(H - B).toFixed(1)} L${x(0).toFixed(1)},${(H - B).toFixed(1)} Z` : "";

    let band = "";
    if (upper !== null) {
      const top = y(Math.min(hi, upper));
      const bot = y(Math.max(lo, lower !== null ? lower : lo));
      band = `<rect x="${L}" y="${top.toFixed(1)}" width="${W - L - R}" height="${Math.max(0, bot - top).toFixed(1)}" fill="rgba(76,175,80,0.10)" stroke="rgba(76,175,80,0.35)" stroke-width="0.6" stroke-dasharray="2 3"/>`;
    }
    const tgt = target !== null && target >= lo && target <= hi
      ? `<line x1="${L}" x2="${W - R}" y1="${y(target).toFixed(1)}" y2="${y(target).toFixed(1)}" stroke="#FFD700" stroke-opacity="0.55" stroke-width="0.8" stroke-dasharray="4 4"/>
         <text x="${W - R}" y="${(y(target) - 3).toFixed(1)}" text-anchor="end" font-size="8.5" fill="#FFD700" fill-opacity="0.8">target ${target.toFixed(0)}°</text>`
      : "";

    /* time grid */
    const now = Date.now();
    let grid = "";
    for (let m = 0; m <= maxMin; m += 180) {
      const xx = x(m).toFixed(1);
      const lbl = m === 0 ? "now" : this._fmtTime(new Date(now + m * 60000).toISOString());
      grid += `<line x1="${xx}" x2="${xx}" y1="${T}" y2="${H - B}" stroke="rgba(255,255,255,0.06)"/>
        <text x="${xx}" y="${H - 7}" text-anchor="${m === 0 ? "start" : "middle"}" font-size="9" fill="#8a8a8a">${lbl}</text>`;
    }
    let yl = "";
    const stepY = hi - lo > 8 ? 4 : 2;
    for (let v = Math.ceil(lo / stepY) * stepY; v <= hi; v += stepY) {
      yl += `<text x="${L - 5}" y="${(y(v) + 3).toFixed(1)}" text-anchor="end" font-size="9" fill="#777">${v}°</text>
        <line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="rgba(255,255,255,0.04)"/>`;
    }

    /* AC start / ready markers */
    let marks = "";
    const mk = (iso, color, label) => {
      if (!iso) return "";
      const m = (new Date(iso).getTime() - now) / 60000;
      if (!(m >= 0 && m <= maxMin)) return "";
      const xx = x(m).toFixed(1);
      return `<line x1="${xx}" x2="${xx}" y1="${T}" y2="${H - B}" stroke="${color}" stroke-width="1" stroke-dasharray="3 3"/>
        <text x="${xx}" y="${T + 8}" text-anchor="${m > maxMin * 0.8 ? "end" : "start"}" dx="${m > maxMin * 0.8 ? -3 : 3}" font-size="8.5" font-weight="700" fill="${color}">${label}</text>`;
    };
    if (a.precondition === "scheduled") marks += mk(a.precondition_start, "#22d3ee", "AC on");
    if (a.ready_at && a.precondition && a.precondition !== "not_needed") marks += mk(a.ready_at, "#FFD700", "ready");

    const nowDot = tin !== null ? `<circle cx="${x(0)}" cy="${y(tin).toFixed(1)}" r="4" fill="#fff" stroke="#FFD700" stroke-width="1.5"><animate attributeName="r" values="3.5;5;3.5" dur="2.4s" repeatCount="indefinite"/></circle>` : "";
    const hasAc = withAc.trim().length > 0;
    const legend = `<div class="legend"><span><i style="background:#FFD700"></i>without AC</span>${hasAc ? '<span><i style="background:#22d3ee"></i>with AC</span>' : ""}<span><i style="background:#777"></i>outside</span>${upper !== null ? '<span><i style="background:rgba(76,175,80,0.6)"></i>comfort</span>' : ""}</div>`;
    return `<div class="sec"><span>Next ${hours} hours</span><span>${a.uses_weather_forecast ? "with weather forecast" : "weather held constant"}</span></div>
      <div class="chart"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
        <defs><linearGradient id="ttg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#FFD700" stop-opacity="0.28"/><stop offset="1" stop-color="#FFD700" stop-opacity="0"/></linearGradient></defs>
        ${yl}${band}${grid}${tgt}
        <path d="${area}" fill="url(#ttg)"/>
        <path d="${outdoor}" fill="none" stroke="#8a8a8a" stroke-width="1.1" stroke-dasharray="1.5 3" stroke-linecap="round"/>
        ${hasAc ? `<path d="${withAc}" fill="none" stroke="#22d3ee" stroke-width="2" stroke-dasharray="5 3" stroke-linecap="round"/>` : ""}
        <path d="${passive}" fill="none" stroke="#FFD700" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="filter:drop-shadow(0 0 3px #FFD70088)"/>
        ${marks}${nowDot}
      </svg></div>${legend}`;
  }
}

if (!customElements.get("thermal-twin-card")) {
  customElements.define("thermal-twin-card", ThermalTwinCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "thermal-twin-card",
    name: "ThermalTwin",
    description: "Digital twin of your rooms - forecast, AC planning and comfort advice.",
    preview: true,
    documentationURL: "https://github.com/mb26-dev/ha-thermal-twin",
  });
  console.info(`%c THERMALTWIN %c card v${TT_VERSION} `, "color:#111;background:#FFD700;font-weight:700", "color:#FFD700;background:#111");
}
