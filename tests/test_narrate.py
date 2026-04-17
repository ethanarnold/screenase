"""Tests for `screenase.narrate.narrate_analysis`."""

from __future__ import annotations

from screenase.analyze import EffectRow
from screenase.narrate import narrate_analysis


def _effect(term: str, *, coef: float, t: float, p: float) -> EffectRow:
    return EffectRow(term=term, coef=coef, std_err=abs(coef / (t or 1)),
                     t=t, p=p, abs_std_effect=abs(t) / 10.0)


def test_narrate_significant_effect_mentions_driver() -> None:
    effects = [
        _effect("NTPs_mM_each_coded", coef=3.2, t=5.0, p=0.001),
        _effect("MgCl2_mM_coded", coef=-1.5, t=-2.0, p=0.08),
    ]
    out = narrate_analysis(effects, r_squared=0.92)
    assert "NTPs_mM_each" in out
    assert "R²" in out
    # Strongest is positive → "positive"
    assert "positive" in out


def test_narrate_no_significant_effect() -> None:
    effects = [
        _effect("X", coef=0.3, t=1.1, p=0.30),
        _effect("Y", coef=-0.1, t=-0.2, p=0.83),
    ]
    out = narrate_analysis(effects, r_squared=0.20)
    assert "within noise" in out


def test_narrate_flags_curvature_significance() -> None:
    effects = [_effect("X_coded", coef=2.0, t=4.0, p=0.01)]
    out = narrate_analysis(
        effects, r_squared=0.9,
        curvature={"p": 0.01, "mean_center": 15, "mean_corner": 10, "t": 3.2},
    )
    assert "central-composite" in out.lower() or "curvature" in out.lower()


def test_narrate_empty_effects() -> None:
    out = narrate_analysis([], r_squared=0.0)
    assert "No effects" in out


def test_narrate_clean_term_strips_coded() -> None:
    effects = [_effect("A_coded:B_coded", coef=1.0, t=3.0, p=0.01)]
    out = narrate_analysis(effects, r_squared=0.9)
    # Interaction should appear as `A × B` (unicode ×)
    assert "×" in out
    # And the raw `_coded` suffix should be stripped
    assert "A_coded" not in out
