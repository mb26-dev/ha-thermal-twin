"""Standalone tests for the ThermalTwin model (no Home Assistant needed)."""

from __future__ import annotations

import importlib.util
import math
import random
import sys
from pathlib import Path

MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "thermal_twin"
    / "model.py"
)
_spec = importlib.util.spec_from_file_location("thermal_twin_model", MODEL_PATH)
model = importlib.util.module_from_spec(_spec)
sys.modules["thermal_twin_model"] = model
_spec.loader.exec_module(model)

STEP_S = 300
TRUE_K = 0.08  # time constant 12.5 h
TRUE_OFFSET = 0.25  # °C/h internal gains
TRUE_HEAT = 1.6  # °C/h
TRUE_COOL = -1.2  # °C/h


def _simulate(days: int, seed: int = 1, with_hvac: bool = True) -> list:
    rng = random.Random(seed)
    samples = []
    t_in = 20.0
    for step in range(days * 86400 // STEP_S):
        ts = 1_700_000_000 + step * STEP_S
        hour = (step * STEP_S / 3600) % 24
        t_out = 8 + 7 * math.sin((hour - 9) / 24 * 2 * math.pi)
        mode = model.MODE_PASSIVE
        if with_hvac and 6 <= hour < 7.5:
            mode = model.MODE_HEATING
        elif with_hvac and 15 <= hour < 16:
            mode = model.MODE_COOLING
        hvac = {model.MODE_HEATING: TRUE_HEAT, model.MODE_COOLING: TRUE_COOL}.get(
            mode, 0.0
        )
        dt_h = STEP_S / 3600
        t_in += (TRUE_K * (t_out - t_in) + TRUE_OFFSET + hvac) * dt_h
        measured = round(t_in + rng.gauss(0, 0.03), 1)  # 0.1 °C sensor
        samples.append(model.Sample(ts, measured, round(t_out, 1), None, mode))
    return samples


def test_fit_recovers_parameters():
    params = model.fit_model(_simulate(7), use_solar=False, max_gap_s=750)
    assert params.is_trained
    assert abs(params.k - TRUE_K) / TRUE_K < 0.15
    assert abs(params.offset - TRUE_OFFSET) < 0.1
    assert params.heating_rate is not None
    assert abs(params.heating_rate - TRUE_HEAT) / TRUE_HEAT < 0.25
    assert params.cooling_rate is not None
    assert abs(params.cooling_rate - TRUE_COOL) / abs(TRUE_COOL) < 0.25
    assert params.r2 is not None and params.r2 > 0.5


def test_not_trained_with_too_little_data():
    params = model.fit_model(_simulate(1)[:20], use_solar=False, max_gap_s=750)
    assert not params.is_trained


def test_gap_breaks_pairs():
    samples = _simulate(1, with_hvac=False)
    for idx, sample in enumerate(samples):
        sample.ts += (idx // 2) * 3600  # every second sample a huge gap
    assert model.build_pairs(samples, max_gap_s=750) == []


def test_window_open_excluded():
    samples = _simulate(2, with_hvac=False)
    for sample in samples:
        sample.mode = None
    params = model.fit_model(samples, use_solar=False, max_gap_s=750)
    assert params.passive_pairs == 0


def test_time_to_target_analytic():
    params = model.ModelParams(k=0.1, offset=0.0)
    hours = model.time_to_target(params, 20.0, 10.0, None, 19.0)
    assert math.isclose(hours, -math.log(0.9) / 0.1, rel_tol=1e-9)
    # Wrong direction and unreachable targets
    assert model.time_to_target(params, 20.0, 10.0, None, 21.0) is None
    assert model.time_to_target(params, 20.0, 10.0, None, 9.0) is None
    # With heating the room can reach 22 °C
    hours_hvac = model.time_to_target(params, 20.0, 10.0, None, 22.0, hvac_rate=2.0)
    assert hours_hvac is not None and hours_hvac > 0


def test_predict_matches_equilibrium():
    params = model.ModelParams(k=0.2, offset=0.4)
    teq = model.equilibrium(params, 30.0, None)
    assert math.isclose(teq, 32.0)
    assert math.isclose(model.predict(params, 25.0, 30.0, None, 1000), teq, abs_tol=1e-6)


def test_sample_roundtrip():
    sample = model.Sample(1.0, 21.123, 5.5, None, 0)
    assert model.Sample.from_list(sample.to_list()) == model.Sample(
        1.0, 21.123, 5.5, None, 0
    )


def _params() -> "model.ModelParams":
    return model.ModelParams(k=TRUE_K, offset=TRUE_OFFSET, cooling_rate=TRUE_COOL)


def test_simulate_matches_analytic_prediction():
    params = _params()
    traj = model.simulate(params, 30.0, 0.0, 3.0, lambda _ts: 26.0)
    expected = model.predict(params, 30.0, 26.0, None, 3.0)
    assert abs(traj[-1][1] - expected) < 1e-6
    assert len(traj) == 37


def test_first_crossing_interpolates():
    traj = [(0.0, 30.0), (100.0, 29.0), (200.0, 28.0)]
    assert model.first_crossing(traj, 28.5) == 150.0
    assert model.first_crossing(traj, 27.0) is None


def test_precondition_schedules_latest_start():
    params = _params()
    plan = model.plan_precondition(
        params, 30.0, 0.0, 4 * 3600.0, 28.0, TRUE_COOL, lambda _ts: 30.0
    )
    assert plan is not None
    assert plan.status == "scheduled"
    assert plan.with_hvac <= 28.05
    # Starting one step later must miss the target.
    late_start = plan.start_ts + 300.0
    passive = model.simulate(params, 30.0, 0.0, late_start / 3600.0, lambda _ts: 30.0)
    run = model.simulate(
        params,
        passive[-1][1],
        late_start,
        (4 * 3600.0 - late_start) / 3600.0,
        lambda _ts: 30.0,
        hvac_rate=TRUE_COOL,
    )
    assert run[-1][1] > 28.05


def test_precondition_not_needed_when_room_cools_itself():
    plan = model.plan_precondition(
        _params(), 28.5, 0.0, 6 * 3600.0, 28.0, TRUE_COOL, lambda _ts: 20.0
    )
    assert plan is not None and plan.status == "not_needed"


def test_psychrometrics():
    assert abs(model.absolute_humidity(25.0, 50.0) - 11.5) < 0.2
    assert abs(model.dew_point(25.0, 50.0) - 13.9) < 0.2
    assert abs(model.heat_index(32.0, 70.0) - 40.5) < 1.0
    assert abs(model.heat_index(20.0, 50.0) - 19.6) < 1.0
    assert model.sun_factor(-10.0) == 0.0
    assert abs(model.sun_factor(90.0) - 1.0) < 1e-9


def test_precondition_unreachable_starts_at_max_lead():
    params = _params()
    ready = 12 * 3600.0
    plan = model.plan_precondition(
        params, 30.0, 0.0, ready, 20.0, TRUE_COOL, lambda _ts: 32.0, max_lead_h=4.0
    )
    assert plan is not None
    assert plan.reachable is False
    assert plan.status == "scheduled"
    assert plan.start_ts == ready - 4 * 3600.0
