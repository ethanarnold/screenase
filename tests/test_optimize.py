"""Tests for `analyze.surface_plot` and `analyze.optimize_response`."""

from __future__ import annotations

import pytest

from screenase.analyze import fit_model, optimize_response, surface_plot
from screenase.design import build_design


def _synthetic(cfg, f):
    """y = f(coded row) — fit a known polynomial against the full factorial."""
    design = build_design(cfg)
    coded_cols = [f"{fc.name}_coded" for fc in cfg.factors]
    ys = []
    for _, row in design.iterrows():
        coded = {c: float(row[c]) for c in coded_cols}
        ys.append(f(coded))
    results = design.copy()
    results["y"] = ys
    return results, coded_cols


def test_surface_plot_emits_png(cfg, tmp_path) -> None:
    results, coded_cols = _synthetic(
        cfg, lambda r: 3 * r["NTPs_mM_each_coded"] - 2 * r["MgCl2_mM_coded"],
    )
    fit = fit_model(results, "y", coded_cols)
    out = surface_plot(fit, tmp_path / "surface.png")
    assert out.exists() and out.stat().st_size > 0


def test_optimize_response_finds_positive_gradient(cfg) -> None:
    # y increases monotonically in NTPs_coded and decreases in MgCl2_coded.
    results, coded_cols = _synthetic(
        cfg, lambda r: 3 * r["NTPs_mM_each_coded"] - 2 * r["MgCl2_mM_coded"],
    )
    fit = fit_model(results, "y", coded_cols)
    opt = optimize_response(fit, coded_cols, direction="maximize")
    assert opt["coded"]["NTPs_mM_each_coded"] == pytest.approx(1.0, abs=1e-3)
    assert opt["coded"]["MgCl2_mM_coded"] == pytest.approx(-1.0, abs=1e-3)
    # Minimize should flip signs
    opt_min = optimize_response(fit, coded_cols, direction="minimize")
    assert opt_min["coded"]["NTPs_mM_each_coded"] == pytest.approx(-1.0, abs=1e-3)
    assert opt_min["coded"]["MgCl2_mM_coded"] == pytest.approx(1.0, abs=1e-3)


def test_optimize_response_respects_bounds(cfg) -> None:
    # Monotonic increasing in all factors → optimum hits the upper corner
    results, coded_cols = _synthetic(
        cfg, lambda r: sum(r.values()),
    )
    fit = fit_model(results, "y", coded_cols)
    opt = optimize_response(fit, coded_cols)
    for v in opt["coded"].values():
        assert v == pytest.approx(1.0, abs=1e-3)
