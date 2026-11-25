"""Pure-Python thermal model for ThermalTwin.

This module deliberately has no Home Assistant imports so it can be unit
tested standalone.

Physics (lumped single-zone model, Newton's law of cooling):

    dT/dt = k * (T_out - T_in) + g * S + c + h

    k  heat exchange coefficient with outside [1/h]   (time constant = 1/k)
    g  solar gain per unit of the solar sensor [°C/h per unit]
    c  constant internal gains [°C/h]
    h  HVAC effect [°C/h] (> 0 heating, < 0 cooling, 0 when passive)

k, g and c are learned by least squares from passive periods (HVAC off,
windows closed). h is learned as the median residual of the passive model
during active heating / cooling periods.
"""

from __future__ import annotations

from collections.abc import Callable
import math
import statistics
from dataclasses import asdict, dataclass

MODE_PASSIVE = 0
MODE_HEATING = 1
MODE_COOLING = -1

# Learning horizons: passive drift is slow, so a longer window averages out
# sensor quantisation (typically 0.1 °C). HVAC runs are often short cycles.
PASSIVE_HORIZON_S = 3600
ACTIVE_HORIZON_S = 1200

MIN_PASSIVE_PAIRS = 36
MIN_ACTIVE_PAIRS = 6
MIN_DELTA_SPREAD = 0.8  # °C standard deviation of (T_out - T_in) needed
K_MIN = 0.005  # time constant max 200 h
K_MAX = 2.0  # time constant min 0.5 h
MAX_PREDICTION_H = 72.0


@dataclass(slots=True)
class Sample:
    """One snapshot of the room."""

    ts: float
    t_in: float
    t_out: float
    solar: float | None
    mode: int | None  # None = excluded (window open, unknown HVAC state)
    power: float | None = None  # HVAC power draw in W when a meter is set

    def to_list(self) -> list:
        """Serialise compactly for storage."""
        return [
            round(self.ts, 1),
            round(self.t_in, 3),
            round(self.t_out, 3),
            None if self.solar is None else round(self.solar, 2),
            self.mode,
            None if self.power is None else round(self.power, 1),
        ]

    @classmethod
    def from_list(cls, raw: list) -> Sample:
        """Deserialise from storage."""
        return cls(
            ts=float(raw[0]),
            t_in=float(raw[1]),
            t_out=float(raw[2]),
            solar=None if raw[3] is None else float(raw[3]),
            mode=None if raw[4] is None else int(raw[4]),
            power=None if len(raw) < 6 or raw[5] is None else float(raw[5]),
        )


@dataclass(slots=True)
class ModelParams:
    """Learned model parameters."""

    k: float | None = None
    solar_gain: float | None = None
    offset: float | None = None
    r2: float | None = None
    passive_pairs: int = 0
    heating_rate: float | None = None
    heating_pairs: int = 0
    cooling_rate: float | None = None
    cooling_pairs: int = 0

    @property
    def is_trained(self) -> bool:
        """Return True when the passive model is usable."""
        return self.k is not None

    @property
    def time_constant_h(self) -> float | None:
        """Return the thermal time constant in hours."""
        if self.k is None or self.k <= 0:
            return None
        return 1.0 / self.k

    def as_dict(self) -> dict:
        """Return a dict for diagnostics."""
        data = asdict(self)
        data["time_constant_h"] = self.time_constant_h
        return data


@dataclass(slots=True)
class _Pair:
    mode: int
    rate: float  # observed dT/dt [°C/h]
    delta: float  # mean (T_out - T_in) [°C]
    solar: float | None  # mean solar value


def _segments(samples: list[Sample], max_gap_s: float) -> list[list[Sample]]:
    """Split samples into runs with constant mode, no gaps, no exclusions."""
    runs: list[list[Sample]] = []
    current: list[Sample] = []
    for sample in samples:
        if sample.mode is None:
            if current:
                runs.append(current)
            current = []
            continue
        if current and (
            sample.mode != current[-1].mode
            or sample.ts - current[-1].ts > max_gap_s
            or sample.ts <= current[-1].ts
        ):
            runs.append(current)
            current = []
        current.append(sample)
    if current:
        runs.append(current)
    return runs


def build_pairs(samples: list[Sample], max_gap_s: float) -> list[_Pair]:
    """Build (rate, delta, solar) observations from consecutive samples."""
    pairs: list[_Pair] = []
    for run in _segments(samples, max_gap_s):
        mode = run[0].mode
        horizon = PASSIVE_HORIZON_S if mode == MODE_PASSIVE else ACTIVE_HORIZON_S
        j = 0
        for i, start in enumerate(run):
            if j < i:
                j = i
            while j < len(run) and run[j].ts - start.ts < horizon:
                j += 1
            if j >= len(run):
                break
            end = run[j]
            span_h = (end.ts - start.ts) / 3600.0
            if span_h <= 0:
                continue
            window = run[i : j + 1]
            delta = statistics.fmean(s.t_out - s.t_in for s in window)
            solar_values = [s.solar for s in window]
            solar = (
                None
                if any(v is None for v in solar_values)
                else statistics.fmean(solar_values)  # type: ignore[arg-type]
            )
            pairs.append(
                _Pair(
                    mode=mode,  # type: ignore[arg-type]
                    rate=(end.t_in - start.t_in) / span_h,
                    delta=delta,
                    solar=solar,
                )
            )
    return pairs


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Solve a small linear system by Gaussian elimination with pivoting."""
    size = len(vector)
    aug = [row[:] + [vector[idx]] for idx, row in enumerate(matrix)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for row in range(size):
            if row == col:
                continue
            factor = aug[row][col] / aug[col][col]
            for c in range(col, size + 1):
                aug[row][c] -= factor * aug[col][c]
    return [aug[r][size] / aug[r][r] for r in range(size)]


def _least_squares(rows: list[list[float]], targets: list[float]) -> list[float] | None:
    """Ordinary least squares via normal equations."""
    n_feat = len(rows[0])
    xtx = [[0.0] * n_feat for _ in range(n_feat)]
    xty = [0.0] * n_feat
    for row, y in zip(rows, targets, strict=True):
        for a in range(n_feat):
            xty[a] += row[a] * y
            for b in range(n_feat):
                xtx[a][b] += row[a] * row[b]
    return _solve(xtx, xty)


def fit_model(
    samples: list[Sample], use_solar: bool, max_gap_s: float
) -> ModelParams:
    """Learn model parameters from samples."""
    params = ModelParams()
    pairs = build_pairs(samples, max_gap_s)
    passive = [
        p
        for p in pairs
        if p.mode == MODE_PASSIVE and (not use_solar or p.solar is not None)
    ]
    params.passive_pairs = len(passive)
    if len(passive) < MIN_PASSIVE_PAIRS:
        return params
    if statistics.pstdev(p.delta for p in passive) < MIN_DELTA_SPREAD:
        return params

    if use_solar:
        rows = [[p.delta, p.solar, 1.0] for p in passive]  # type: ignore[list-item]
    else:
        rows = [[p.delta, 1.0] for p in passive]
    targets = [p.rate for p in passive]
    coef = _least_squares(rows, targets)
    if coef is None:
        return params

    k = coef[0]
    if not K_MIN <= k <= K_MAX:
        return params
    solar_gain = coef[1] if use_solar else None
    offset = coef[-1]

    mean_y = statistics.fmean(targets)
    ss_tot = sum((y - mean_y) ** 2 for y in targets)
    ss_res = sum(
        (y - sum(c * x for c, x in zip(coef, row, strict=True))) ** 2
        for row, y in zip(rows, targets, strict=True)
    )
    params.k = k
    params.solar_gain = solar_gain
    params.offset = offset
    params.r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None

    def passive_rate(pair: _Pair) -> float:
        value = k * pair.delta + offset
        if use_solar and solar_gain is not None and pair.solar is not None:
            value += solar_gain * pair.solar
        return value

    heating = [
        p.rate - passive_rate(p)
        for p in pairs
        if p.mode == MODE_HEATING and (not use_solar or p.solar is not None)
    ]
    cooling = [
        p.rate - passive_rate(p)
        for p in pairs
        if p.mode == MODE_COOLING and (not use_solar or p.solar is not None)
    ]
    params.heating_pairs = len(heating)
    params.cooling_pairs = len(cooling)
    if len(heating) >= MIN_ACTIVE_PAIRS:
        rate = statistics.median(heating)
        params.heating_rate = rate if rate > 0 else None
    if len(cooling) >= MIN_ACTIVE_PAIRS:
        rate = statistics.median(cooling)
        params.cooling_rate = rate if rate < 0 else None
    return params


def equilibrium(
    params: ModelParams, t_out: float, solar: float | None, hvac_rate: float = 0.0
) -> float | None:
    """Temperature the room converges to under current conditions."""
    if params.k is None or params.offset is None:
        return None
    gains = params.offset + hvac_rate
    if params.solar_gain is not None and solar is not None:
        gains += params.solar_gain * solar
    return t_out + gains / params.k


def predict(
    params: ModelParams,
    t_in: float,
    t_out: float,
    solar: float | None,
    hours: float,
    hvac_rate: float = 0.0,
) -> float | None:
    """Predict indoor temperature after `hours` with constant conditions."""
    teq = equilibrium(params, t_out, solar, hvac_rate)
    if teq is None or params.k is None:
        return None
    return teq + (t_in - teq) * math.exp(-params.k * hours)


def time_to_target(
    params: ModelParams,
    t_in: float,
    t_out: float,
    solar: float | None,
    target: float,
    hvac_rate: float = 0.0,
) -> float | None:
    """Hours until the room reaches `target`, None if it never will."""
    teq = equilibrium(params, t_out, solar, hvac_rate)
    if teq is None or params.k is None:
        return None
    if abs(target - t_in) < 0.05:
        return 0.0
    # Target must lie between the current temperature and the equilibrium.
    if (target - t_in) * (teq - t_in) <= 0:
        return None
    if abs(teq - t_in) <= abs(target - t_in):
        return None
    ratio = (target - teq) / (t_in - teq)
    if ratio <= 0 or ratio >= 1:
        return None
    hours = -math.log(ratio) / params.k
    return hours if hours <= MAX_PREDICTION_H else None


# --------------------------------------------------------------------------
# Trajectories with time-varying conditions (weather forecast, sun position)
# --------------------------------------------------------------------------

SIM_STEP_H = 1.0 / 12.0  # 5 minutes


def simulate(
    params: ModelParams,
    t_in: float,
    start_ts: float,
    hours: float,
    t_out_at: Callable[[float], float],
    solar_at: Callable[[float], float | None] | None = None,
    hvac_rate: float = 0.0,
    hvac_from_ts: float | None = None,
    step_h: float = SIM_STEP_H,
) -> list[tuple[float, float]]:
    """Integrate the room temperature step by step.

    Each step uses the exact exponential solution with the conditions held
    constant over the step, so the result equals `predict` when the
    conditions never change. HVAC is applied from `hvac_from_ts` on (or from
    the start when None and `hvac_rate` is set).
    """
    if params.k is None or params.offset is None:
        return []
    k = params.k
    steps = max(1, round(hours / step_h))
    decay = math.exp(-k * step_h)
    temp = t_in
    out = [(start_ts, temp)]
    for idx in range(steps):
        ts = start_ts + idx * step_h * 3600.0
        mid = ts + step_h * 1800.0
        gains = params.offset
        if params.solar_gain is not None and solar_at is not None:
            solar = solar_at(mid)
            if solar is not None:
                gains += params.solar_gain * solar
        if hvac_rate and (hvac_from_ts is None or mid >= hvac_from_ts):
            gains += hvac_rate
        teq = t_out_at(mid) + gains / k
        temp = teq + (temp - teq) * decay
        out.append((ts + step_h * 3600.0, temp))
    return out


def first_crossing(
    trajectory: list[tuple[float, float]], target: float
) -> float | None:
    """Return the timestamp where the trajectory first reaches `target`."""
    if not trajectory:
        return None
    start = trajectory[0][1]
    if abs(start - target) < 0.05:
        return trajectory[0][0]
    rising = target > start
    prev_ts, prev_t = trajectory[0]
    for ts, temp in trajectory[1:]:
        if (rising and temp >= target) or (not rising and temp <= target):
            span = temp - prev_t
            frac = 0.0 if span == 0 else (target - prev_t) / span
            return prev_ts + (ts - prev_ts) * min(1.0, max(0.0, frac))
        prev_ts, prev_t = ts, temp
    return None


@dataclass(slots=True)
class Precondition:
    """Result of the pre-cool / pre-heat planner."""

    status: str  # scheduled, now, not_needed, late
    start_ts: float | None
    hvac_minutes: float | None
    without_hvac: float | None  # predicted temperature at ready time
    with_hvac: float | None


def plan_precondition(
    params: ModelParams,
    t_in: float,
    now_ts: float,
    ready_ts: float,
    target: float,
    hvac_rate: float,
    t_out_at: Callable[[float], float],
    solar_at: Callable[[float], float | None] | None = None,
    max_lead_h: float = 6.0,
    step_h: float = SIM_STEP_H,
) -> Precondition | None:
    """Find the latest HVAC start so the room is at `target` by `ready_ts`.

    Cooling when `hvac_rate` < 0 (room must be at or below target), heating
    when > 0 (room must be at or above target).
    """
    if params.k is None or not hvac_rate or ready_ts <= now_ts:
        return None
    cooling = hvac_rate < 0
    hours = (ready_ts - now_ts) / 3600.0

    def ok(temp: float) -> bool:
        return temp <= target + 0.05 if cooling else temp >= target - 0.05

    passive = simulate(params, t_in, now_ts, hours, t_out_at, solar_at, step_h=step_h)
    if not passive:
        return None
    without = passive[-1][1]
    if ok(without):
        return Precondition("not_needed", None, 0.0, without, without)

    earliest = max(now_ts, ready_ts - max_lead_h * 3600.0)
    # Walk the passive trajectory backwards from the ready time.
    candidates = [p for p in passive if p[0] >= earliest - 1]
    best: tuple[float, float] | None = None
    for ts, temp in reversed(candidates):
        rest = (ready_ts - ts) / 3600.0
        run = simulate(
            params, temp, ts, rest, t_out_at, solar_at, hvac_rate=hvac_rate, step_h=step_h
        )
        end = run[-1][1] if run else temp
        if ok(end):
            best = (ts, end)
            break
    if best is None:
        run = simulate(
            params, t_in, now_ts, hours, t_out_at, solar_at, hvac_rate=hvac_rate, step_h=step_h
        )
        return Precondition(
            "late", now_ts, hours * 60.0, without, run[-1][1] if run else None
        )
    start_ts, end = best
    status = "now" if start_ts <= now_ts + step_h * 3600.0 else "scheduled"
    return Precondition(status, start_ts, (ready_ts - start_ts) / 60.0, without, end)


# --------------------------------------------------------------------------
# Psychrometrics - humidity matters as much as temperature in the tropics
# --------------------------------------------------------------------------


def _vapour_pressure_sat(temp: float) -> float:
    """Saturation vapour pressure over water in hPa (Magnus, Sonntag 1990)."""
    return 6.112 * math.exp(17.62 * temp / (243.12 + temp))


def absolute_humidity(temp: float, rh: float) -> float | None:
    """Water vapour content in g/m³."""
    if rh <= 0:
        return None
    vapour = rh / 100.0 * _vapour_pressure_sat(temp)
    return 216.7 * vapour / (273.15 + temp)


def dew_point(temp: float, rh: float) -> float | None:
    """Dew point in °C."""
    if rh <= 0:
        return None
    gamma = math.log(min(rh, 100.0) / 100.0) + 17.62 * temp / (243.12 + temp)
    return 243.12 * gamma / (17.62 - gamma)


def heat_index(temp: float, rh: float) -> float:
    """Apparent temperature in °C (NOAA heat index, Rothfusz with adjustments)."""
    t_f = temp * 9.0 / 5.0 + 32.0
    simple = 0.5 * (t_f + 61.0 + (t_f - 68.0) * 1.2 + rh * 0.094)
    if (simple + t_f) / 2.0 < 80.0:
        hi = simple
    else:
        hi = (
            -42.379
            + 2.04901523 * t_f
            + 10.14333127 * rh
            - 0.22475541 * t_f * rh
            - 0.00683783 * t_f * t_f
            - 0.05481717 * rh * rh
            + 0.00122874 * t_f * t_f * rh
            + 0.00085282 * t_f * rh * rh
            - 0.00000199 * t_f * t_f * rh * rh
        )
        if rh < 13 and 80 <= t_f <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t_f - 95.0)) / 17)
        elif rh > 85 and 80 <= t_f <= 87:
            hi += ((rh - 85) / 10) * ((87 - t_f) / 5)
    return (hi - 32.0) * 5.0 / 9.0


def sun_factor(elevation_deg: float) -> float:
    """Direct-sun proxy from the solar elevation: sin(elevation), 0 at night."""
    return max(0.0, math.sin(math.radians(elevation_deg)))
