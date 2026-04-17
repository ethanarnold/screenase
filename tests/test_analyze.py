from __future__ import annotations

import numpy as np
import pytest

from screenase.analyze import analyze_cli, fit_model, pareto_plot, rank_effects
from screenase.design import build_design


@pytest.fixture
def results(cfg):
    """Synthetic response surface y = 3 x1 − 2 x2 + 1.5 x1·x2 + N(0, .1)."""
    rng = np.random.default_rng(0)
    d = build_design(cfg)
    x1 = d["NTPs_mM_each_coded"].to_numpy()
    x2 = d["MgCl2_mM_coded"].to_numpy()
    y = 3.0 * x1 - 2.0 * x2 + 1.5 * x1 * x2 + rng.normal(0, 0.1, size=len(d))
    d = d.copy()
    d["yield_ug_per_uL"] = y
    return d


def test_top_three_terms_are_x1_x2_x1x2(results):
    factor_cols = [c for c in results.columns if c.endswith("_coded")]
    fit = fit_model(results, "yield_ug_per_uL", factor_cols)
    effects = rank_effects(fit)
    top_three = [e.term for e in effects[:3]]
    # statsmodels renders interactions as "A:B"; either order is acceptable.
    assert "NTPs_mM_each_coded" in top_three[:2]
    assert "MgCl2_mM_coded" in top_three[:2]
    assert any("NTPs_mM_each_coded:MgCl2_mM_coded" == t
               or "MgCl2_mM_coded:NTPs_mM_each_coded" == t
               for t in top_three)


def test_negligible_term_has_high_p(results):
    factor_cols = [c for c in results.columns if c.endswith("_coded")]
    fit = fit_model(results, "yield_ug_per_uL", factor_cols)
    effects = rank_effects(fit)
    t7 = next(e for e in effects if e.term == "T7_uL_coded")
    assert t7.p > 0.2


def test_pareto_png_is_written(results, tmp_path):
    factor_cols = [c for c in results.columns if c.endswith("_coded")]
    fit = fit_model(results, "yield_ug_per_uL", factor_cols)
    effects = rank_effects(fit)
    out = tmp_path / "pareto.png"
    pareto_plot(effects, out, df_resid=int(fit.df_resid))
    assert out.exists()
    assert out.stat().st_size > 2_000  # non-trivial PNG


def test_fit_model_rejects_non_identifier_column(results):
    bad = results.rename(columns={"yield_ug_per_uL": "yield mg/mL"})
    with pytest.raises(ValueError, match="identifier"):
        fit_model(bad, "yield mg/mL", ["NTPs_mM_each_coded"])


def test_analyze_cli_writes_report_and_png(results, tmp_path):
    csv = tmp_path / "results.csv"
    results.to_csv(csv)
    out_dir = tmp_path / "out"
    summary = analyze_cli(csv, "yield_ug_per_uL", out_dir)
    assert (out_dir / "pareto.png").exists()
    report = out_dir / "analysis_report.md"
    assert report.exists()
    text = report.read_text()
    assert "yield_ug_per_uL" in text
    assert "|" in text  # markdown table
    assert summary["r2"] > 0.9
