"""Tests for diagnostic plots, lack-of-fit, bootstrap CIs, model selection."""

from __future__ import annotations

import numpy as np

from screenase.analyze import fit_model, rank_effects
from screenase.design import build_ccd, build_design
from screenase.diagnostics import (
    bootstrap_coefficient_ci,
    compare_models,
    flag_outliers,
    half_normal_plot,
    heteroscedasticity_tests,
    lack_of_fit_test,
    render_residual_diagnostics,
)


def _seeded_results(cfg, seed: int = 0):
    design = build_design(cfg)
    coded_cols = [f"{f.name}_coded" for f in cfg.factors]
    rng = np.random.default_rng(seed)
    results = design.copy()
    results["y"] = (
        3 * results["NTPs_mM_each_coded"]
        - 2 * results["MgCl2_mM_coded"]
        + rng.normal(0, 0.1, len(design))
    )
    return results, coded_cols


def test_render_residual_diagnostics(cfg, tmp_path) -> None:
    results, coded_cols = _seeded_results(cfg)
    fit = fit_model(results, "y", coded_cols)
    out = render_residual_diagnostics(fit, tmp_path / "resid.png")
    assert out.exists() and out.stat().st_size > 0


def test_flag_outliers_clean_data(cfg) -> None:
    results, coded_cols = _seeded_results(cfg)
    fit = fit_model(results, "y", coded_cols)
    # Low-noise synthetic should have no |studentized| > 3
    out = flag_outliers(fit, threshold=3.0)
    assert isinstance(out, list)


def test_half_normal_plot(cfg, tmp_path) -> None:
    results, coded_cols = _seeded_results(cfg)
    fit = fit_model(results, "y", coded_cols)
    effects = rank_effects(fit)
    out = half_normal_plot(effects, tmp_path / "hn.png")
    assert out.exists() and out.stat().st_size > 0


def test_lack_of_fit_requires_centers(cfg) -> None:
    results, coded_cols = _seeded_results(cfg)
    fit = fit_model(results, "y", coded_cols)
    lof = lack_of_fit_test(fit, results, "y", results["is_center"].astype(bool))
    assert lof is not None
    assert lof.df_pe >= 1


def test_bootstrap_coefficient_ci(cfg) -> None:
    results, coded_cols = _seeded_results(cfg)
    ci_df = bootstrap_coefficient_ci(results, "y", coded_cols, n_boot=200, seed=0)
    assert set(ci_df.columns) >= {"coef", "lo", "hi", "p_boot"}
    # Large-effect NTPs coefficient should have a CI that excludes zero
    ntps_ci = ci_df.loc["NTPs_mM_each_coded"]
    assert ntps_ci["lo"] > 0 or ntps_ci["hi"] < 0


def test_heteroscedasticity_tests(cfg) -> None:
    results, coded_cols = _seeded_results(cfg)
    fit = fit_model(results, "y", coded_cols)
    out = heteroscedasticity_tests(fit)
    assert 0 <= out["breusch_pagan_p"] <= 1


def test_compare_models_includes_quadratic_on_ccd(cfg) -> None:
    design = build_ccd(cfg, alpha="face")
    coded_cols = [f"{f.name}_coded" for f in cfg.factors]
    rng = np.random.default_rng(0)
    # Curved response — quadratic should win on AICc
    results = design.copy()
    x1 = results["NTPs_mM_each_coded"].to_numpy()
    x2 = results["MgCl2_mM_coded"].to_numpy()
    results["y"] = 3 * x1 - 2 * x2 - 1.5 * x1**2 + rng.normal(0, 0.1, len(design))
    comps = compare_models(results, "y", coded_cols)
    names = [c.name for c in comps]
    assert "quadratic" in names
    assert names[0] == "quadratic"  # best by AICc


def test_compare_models_ranks_linear_best_on_linear_truth(cfg) -> None:
    results, coded_cols = _seeded_results(cfg)
    comps = compare_models(results, "y", coded_cols)
    # Linear truth → main-only or main+2FI should beat quadratic on AICc
    assert comps[0].name != "quadratic"
