from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from screenase.config import ReactionConfig
from screenase.design import build_design, full_factorial, is_center_point


def test_full_factorial_shape():
    corners = full_factorial(4)
    assert corners.shape == (16, 4)
    assert set(np.unique(corners)) == {-1, 1}


def test_design_has_expected_row_count(cfg: ReactionConfig):
    df = build_design(cfg)
    assert len(df) == 2 ** len(cfg.factors) + cfg.center_points == 19
    assert df.index.name == "Run"
    assert list(df.index) == list(range(1, 20))


def test_every_corner_present_exactly_once(cfg: ReactionConfig):
    df = build_design(cfg)
    non_center = df.loc[~df["is_center"]]
    factor_names = [f.name for f in cfg.factors]
    expected = {
        tuple(f.low if c == -1 else f.high for f, c in zip(cfg.factors, combo, strict=True))
        for combo in itertools.product([-1, 1], repeat=len(cfg.factors))
    }
    actual = {tuple(row) for row in non_center[factor_names].to_numpy()}
    assert actual == expected


def test_center_rows_are_midpoints(cfg: ReactionConfig):
    df = build_design(cfg)
    centers = df.loc[df["is_center"]]
    assert len(centers) == cfg.center_points
    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        assert np.allclose(centers[f.name], mid)


def test_coded_columns_are_pm1_at_corners(cfg: ReactionConfig):
    df = build_design(cfg)
    non_center = df.loc[~df["is_center"]]
    for f in cfg.factors:
        col = f"{f.name}_coded"
        values = non_center[col].to_numpy()
        assert set(np.unique(np.round(values))) == {-1, 1}
    centers = df.loc[df["is_center"]]
    for f in cfg.factors:
        col = f"{f.name}_coded"
        assert np.allclose(centers[col], 0.0)


def test_same_seed_identical_order(cfg: ReactionConfig):
    a = build_design(cfg)
    b = build_design(cfg)
    pd.testing.assert_frame_equal(a, b)


def test_different_seed_different_order(cfg: ReactionConfig):
    a = build_design(cfg)
    other = cfg.model_copy(update={"seed": cfg.seed + 1})
    b = build_design(other)
    assert len(a) == len(b)
    # Run order must differ somewhere (factor columns row-wise)
    factor_cols = [f.name for f in cfg.factors]
    assert not a[factor_cols].reset_index(drop=True).equals(b[factor_cols].reset_index(drop=True))


def test_is_center_point_helper(cfg: ReactionConfig):
    df = build_design(cfg)
    mask = is_center_point(df, cfg)
    assert int(mask.sum()) == cfg.center_points
    pd.testing.assert_series_equal(mask.rename("is_center"), df["is_center"].rename("is_center"))


def test_byte_identical_csv_contract(cfg: ReactionConfig, tmp_path):
    """CSV output of the default config must match the legacy 2.10 script byte-for-byte."""
    df = build_design(cfg)
    factor_cols = [f.name for f in cfg.factors]
    out = tmp_path / "ivt_screen.csv"
    df[factor_cols].to_csv(out)
    from pathlib import Path
    legacy = Path(__file__).resolve().parent.parent / "ivt_doe_screen.csv"
    if legacy.exists():
        assert out.read_text() == legacy.read_text()
