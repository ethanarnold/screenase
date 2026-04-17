from __future__ import annotations

import numpy as np
import pytest

from screenase.config import ReactionConfig
from screenase.design import build_ccd, ccd_alpha


def test_ccd_alpha_face():
    assert ccd_alpha(4, "face") == 1.0


def test_ccd_alpha_rotatable():
    assert ccd_alpha(4, "rotatable") == pytest.approx(2.0)
    assert ccd_alpha(3, "rotatable") == pytest.approx(2 ** 0.75)
    assert ccd_alpha(2, "rotatable") == pytest.approx(2 ** 0.5)


def test_ccd_alpha_numeric_passthrough():
    assert ccd_alpha(4, 1.5) == 1.5


def test_ccd_alpha_unknown_mode():
    with pytest.raises(ValueError, match="unknown alpha mode"):
        ccd_alpha(4, "orthogonal")  # type: ignore[arg-type]


def test_ccd_row_count_face(cfg: ReactionConfig):
    df = build_ccd(cfg, alpha="face")
    k = len(cfg.factors)
    assert len(df) == 2 ** k + 2 * k + cfg.center_points


def test_ccd_design_kind_counts(cfg: ReactionConfig):
    df = build_ccd(cfg, alpha="face")
    counts = df["design_kind"].value_counts().to_dict()
    k = len(cfg.factors)
    assert counts["factorial"] == 2 ** k
    assert counts["axial"] == 2 * k
    assert counts["center"] == cfg.center_points


def test_ccd_face_stays_within_low_high(cfg: ReactionConfig):
    df = build_ccd(cfg, alpha="face")
    for f in cfg.factors:
        assert df[f.name].min() >= f.low - 1e-9
        assert df[f.name].max() <= f.high + 1e-9


def test_ccd_rotatable_extends_range(cfg: ReactionConfig):
    df = build_ccd(cfg, alpha="rotatable")
    k = len(cfg.factors)
    alpha = ccd_alpha(k, "rotatable")
    assert alpha > 1.0
    # Axial points should reach coded ±alpha on exactly one factor each
    axial = df.loc[df["design_kind"] == "axial"]
    coded_cols = [f"{f.name}_coded" for f in cfg.factors]
    for _, row in axial.iterrows():
        active = [abs(row[c]) for c in coded_cols]
        assert max(active) == pytest.approx(alpha, abs=1e-6)
        # All other coded values must be zero
        close_to_zero = sum(1 for v in active if abs(v) < 1e-9)
        assert close_to_zero == len(coded_cols) - 1


def test_ccd_center_points_are_midpoints(cfg: ReactionConfig):
    df = build_ccd(cfg, alpha="face")
    centers = df.loc[df["design_kind"] == "center"]
    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        assert np.allclose(centers[f.name], mid)
    assert bool(df["is_center"].equals(df["design_kind"].eq("center")))


def test_ccd_seeded_deterministic(cfg: ReactionConfig):
    a = build_ccd(cfg, alpha="face")
    b = build_ccd(cfg, alpha="face")
    factor_cols = [f.name for f in cfg.factors]
    assert a[factor_cols].equals(b[factor_cols])


def test_ccd_custom_axial_center_points(cfg: ReactionConfig):
    df = build_ccd(cfg, alpha="face", axial_center_points=6)
    assert int((df["design_kind"] == "center").sum()) == 6


def test_ccd_coded_columns_match_real_values(cfg: ReactionConfig):
    df = build_ccd(cfg, alpha="face")
    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        half = (f.high - f.low) / 2.0
        reconstructed = mid + df[f"{f.name}_coded"] * half
        assert np.allclose(reconstructed, df[f.name])
