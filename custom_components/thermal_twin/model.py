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

    def to_list(self) -> list:
        """Serialise compactly for storage."""
        return [
            round(self.ts, 1),
            round(self.t_in, 3),
            round(self.t_out, 3),
            None if self.solar is None else round(self.solar, 2),
            self.mode,
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
