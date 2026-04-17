"""Tests for multi-response desirability, power analysis, cost model."""

from __future__ import annotations

import numpy as np
import pytest

from screenase.analyze import fit_model
from screenase.design import build_design
from screenase.multiresponse import (
    ResponseGoal,
    composite_desirability,
    compute_run_cost,
    optimize_multi_response,
    recommend_sample_size,
)
from screenase.volumes import compute_volumes


def test_desirability_maximize_bounds() -> None:
    g = ResponseGoal(column="y", goal="maximize", lo=0, hi=10)
    assert composite_desirability({"y": -1}, [g]) == 0.0
    assert composite_desirability({"y": 11}, [g]) == 1.0
    # Linear midpoint
    d = composite_desirability({"y": 5}, [g])
    assert 0.4 < d < 0.6


def test_desirability_minimize() -> None:
    g = ResponseGoal(column="y", goal="minimize", lo=0, hi=10)
    # Low values → high desirability for minimize goals
    assert composite_desirability({"y": 0}, [g]) == 1.0
    assert composite_desirability({"y": 10}, [g]) == 0.0


def test_desirability_target() -> None:
    g = ResponseGoal(column="y", goal="target", lo=0, hi=10, target_value=5)
    # At target → 1.0
    assert composite_desirability({"y": 5}, [g]) == pytest.approx(1.0)
    # At edges → 0
    assert composite_desirability({"y": 0}, [g]) == 0.0


def test_optimize_multi_response_tradeoff(cfg) -> None:
    design = build_design(cfg)
    coded_cols = [f"{f.name}_coded" for f in cfg.factors]
    rng = np.random.default_rng(0)
    results = design.copy()
    x1 = results["NTPs_mM_each_coded"].to_numpy()
    x2 = results["MgCl2_mM_coded"].to_numpy()
    # yield: maximize y1; purity: minimize y2 (conflicting drivers)
    results["yield_val"] = 3 * x1 - 2 * x2 + rng.normal(0, 0.05, len(design))
    results["purity"] = -3 * x1 + 2 * x2 + rng.normal(0, 0.05, len(design))
    fit_yield = fit_model(results, "yield_val", coded_cols)
    fit_purity = fit_model(results, "purity", coded_cols)
    goals = [
        ResponseGoal(column="yield_val", goal="maximize", lo=-5, hi=5),
        ResponseGoal(column="purity", goal="maximize", lo=-5, hi=5),
    ]
    result = optimize_multi_response(
        {"yield_val": fit_yield, "purity": fit_purity},
        goals, coded_cols,
    )
    assert "coded" in result
    assert 0 <= result["D"] <= 1
    assert set(result["per_response"]) == {"yield_val", "purity"}


def test_recommend_sample_size() -> None:
    out = recommend_sample_size(k=4, effect_std=1.0, noise_std=0.5)
    assert out["factorial_runs"] == 16
    assert out["total_runs"] >= 16
    assert 0 < out["alpha"] < 1


def test_recommend_sample_size_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        recommend_sample_size(k=4, effect_std=0, noise_std=1)


def test_compute_run_cost(cfg) -> None:
    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    costs = {"NTPs": 0.5, "T7": 3.0, "MgCl2": 0.01}
    out = compute_run_cost(vol_df, costs)
    assert out["screen_total"] > 0
    assert "NTPs" in out["per_reagent_total"]
    # Per-run costs sum to screen_total
    assert sum(out["per_run"].values()) == pytest.approx(out["screen_total"])
