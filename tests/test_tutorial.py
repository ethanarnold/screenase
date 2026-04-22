"""Tests for the OFAT-vs-DoE simulator powering the tutorial surfaces."""

from __future__ import annotations

import numpy as np
import pandas as pd

from screenase.config import Factor, ReactionConfig, Stock
from screenase.tutorial import (
    TRUTH_COEFFICIENTS,
    ComparisonReport,
    ofat_pick_optimum,
    ofat_plan,
    run_ofat_vs_doe,
    truth_response,
)


def _default_cfg() -> ReactionConfig:
    return ReactionConfig(
        reaction_volume_uL=20.0,
        dna_template_uL=3.2,
        center_points=3,
        seed=42,
        factors=[
            Factor(name="NTPs_mM_each", low=5, high=10, unit="mM", reagent="NTPs"),
            Factor(name="MgCl2_mM", low=30, high=60, unit="mM", reagent="MgCl2"),
            Factor(name="T7_uL", low=0.2, high=1.2, unit="uL",
                   reagent="T7", dosing="volume"),
            Factor(name="PEG8000_pct", low=0, high=2, unit="%", reagent="PEG8000"),
        ],
        stocks={
            "NTPs": Stock(name="NTP Mix", concentration=100, unit="mM"),
            "MgCl2": Stock(name="MgCl2", concentration=1000, unit="mM"),
            "T7": Stock(name="T7 Polymerase", concentration=3, unit="mg/mL"),
            "PEG8000": Stock(name="PEG8000", concentration=50, unit="%"),
            "Buffer": Stock(name="Buffer", concentration=20, unit="X"),
        },
        fixed_reagents={"Buffer": 1.0},
    )


def test_truth_response_noise_free_is_deterministic() -> None:
    coded = pd.DataFrame({
        "NTPs_mM_each": [1.0, -1.0, 0.0],
        "MgCl2_mM": [1.0, -1.0, 0.0],
        "T7_uL": [0.0, 0.0, 0.0],
        "PEG8000_pct": [0.0, 0.0, 0.0],
    })
    y = truth_response(coded, sigma=0.0)
    # At (+,+) the NTPs×MgCl2 interaction boosts yield above main-effect sum
    expected_pp = (
        TRUTH_COEFFICIENTS["intercept"]
        + TRUTH_COEFFICIENTS["NTPs_mM_each"]
        + TRUTH_COEFFICIENTS["MgCl2_mM"]
        + TRUTH_COEFFICIENTS["NTPs_mM_each:MgCl2_mM"]
    )
    assert y[0] == expected_pp
    assert y[2] == TRUTH_COEFFICIENTS["intercept"]


def test_ofat_plan_shape() -> None:
    cfg = _default_cfg()
    plan = ofat_plan(cfg, center_replicates=3)
    # 3 centers + 2 spokes per factor × 4 factors = 11 runs
    assert len(plan) == 3 + 2 * 4
    assert int(plan["is_center"].sum()) == 3
    for f in cfg.factors:
        assert f"{f.name}_coded" in plan.columns


def test_ofat_pick_optimum_recovers_main_effect_direction() -> None:
    """With no interaction and pure main effects, OFAT picks correctly."""
    cfg = _default_cfg()
    plan = ofat_plan(cfg)
    # Noise-free, main-effects-only truth (no interaction)
    pure_main = {
        "intercept": 10.0,
        "NTPs_mM_each": 2.0,
        "MgCl2_mM": -2.0,
        "T7_uL": 1.0,
        "PEG8000_pct": 0.5,
    }
    coded_only = plan[[f"{f.name}_coded" for f in cfg.factors]].copy()
    coded_only.columns = pd.Index([f.name for f in cfg.factors])
    plan["y"] = truth_response(coded_only, coeffs=pure_main, sigma=0.0)
    picks = ofat_pick_optimum(
        plan, response_col="y",
        factor_names=[f.name for f in cfg.factors],
    )
    assert picks["NTPs_mM_each"] == 1.0
    assert picks["MgCl2_mM"] == -1.0
    assert picks["T7_uL"] == 1.0
    assert picks["PEG8000_pct"] == 1.0


def test_run_ofat_vs_doe_doe_beats_or_ties_ofat() -> None:
    """The headline claim: DoE's true yield ≥ OFAT's true yield on this surface."""
    cfg = _default_cfg()
    report = run_ofat_vs_doe(cfg, seed=0)
    assert isinstance(report, ComparisonReport)
    assert report.doe.n_runs == 19  # 2^4 + 3 centers
    assert report.ofat.n_runs == 11  # 3 centers + 2*4 spokes
    # The DoE strategy should reach strictly higher true yield because of the
    # baked-in NTPs×MgCl2 interaction that OFAT cannot see.
    assert report.doe.true_yield_at_optimum > report.ofat.true_yield_at_optimum
    # DoE should catch the NTPs:MgCl2 interaction at α=0.05 at this signal/noise
    assert any("NTPs_mM_each" in term and "MgCl2_mM" in term
               for term in report.doe.caught_interactions)


def test_run_ofat_vs_doe_reaches_true_optimum() -> None:
    cfg = _default_cfg()
    report = run_ofat_vs_doe(cfg, seed=7)
    # Truth's best corner on this surface is (+,+,+,+) because of the strong
    # positive NTPs:MgCl2 interaction even though MgCl2's main effect is neg.
    assert report.true_best_coded["NTPs_mM_each"] == 1.0
    assert report.true_best_coded["MgCl2_mM"] == 1.0
    # DoE's picked optimum should land at the same corner (within coded bounds)
    assert report.doe.predicted_optimum_coded["NTPs_mM_each"] > 0.5
    assert report.doe.predicted_optimum_coded["MgCl2_mM"] > 0.5


def test_run_ofat_vs_doe_reproducible() -> None:
    cfg = _default_cfg()
    a = run_ofat_vs_doe(cfg, seed=123)
    b = run_ofat_vs_doe(cfg, seed=123)
    assert a.ofat.true_yield_at_optimum == b.ofat.true_yield_at_optimum
    assert a.doe.true_yield_at_optimum == b.doe.true_yield_at_optimum


def test_truth_response_with_rng() -> None:
    coded = pd.DataFrame({
        "NTPs_mM_each": np.zeros(100),
        "MgCl2_mM": np.zeros(100),
        "T7_uL": np.zeros(100),
        "PEG8000_pct": np.zeros(100),
    })
    rng = np.random.default_rng(0)
    y = truth_response(coded, rng=rng)
    # At the center, mean should be ~intercept with small empirical spread
    assert abs(y.mean() - TRUTH_COEFFICIENTS["intercept"]) < 0.1
    assert 0.2 < y.std() < 0.6  # sigma ~0.35
