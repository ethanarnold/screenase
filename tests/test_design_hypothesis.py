"""Generative property tests for `build_design`.

Proves invariants across many randomly-sampled configurations rather than
a single hand-written example: row counts, corner coverage, center-point
midpoint equality, seed determinism, and coded ±1 structure.
"""

from __future__ import annotations

import itertools

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from screenase.config import Factor, ReactionConfig, Stock
from screenase.design import build_design

SETTINGS = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@st.composite
def reaction_configs(draw, k_range=(2, 5), cp_range=(0, 6)) -> ReactionConfig:
    """Generate a valid ReactionConfig with k factors and N center points."""
    k = draw(st.integers(min_value=k_range[0], max_value=k_range[1]))
    center_points = draw(st.integers(min_value=cp_range[0], max_value=cp_range[1]))
    seed = draw(st.integers(min_value=0, max_value=10_000))

    factors: list[Factor] = []
    stocks: dict[str, Stock] = {}
    for i in range(k):
        reagent = f"R{i}"
        low = draw(st.floats(min_value=0.0, max_value=50.0,
                             allow_nan=False, allow_infinity=False))
        span = draw(st.floats(min_value=0.1, max_value=50.0,
                              allow_nan=False, allow_infinity=False))
        high = low + span
        stock_conc = high + draw(st.floats(min_value=1.0, max_value=100.0,
                                           allow_nan=False, allow_infinity=False))
        factors.append(Factor(
            name=f"f{i}", low=low, high=high, unit="mM", reagent=reagent,
            dosing="concentration",
        ))
        stocks[reagent] = Stock(name=reagent, concentration=stock_conc, unit="mM")

    return ReactionConfig(
        reaction_volume_uL=20.0,
        dna_template_uL=1.0,
        center_points=center_points,
        seed=seed,
        factors=factors,
        stocks=stocks,
    )


@SETTINGS
@given(cfg=reaction_configs())
def test_row_count(cfg: ReactionConfig) -> None:
    df = build_design(cfg)
    assert len(df) == 2 ** len(cfg.factors) + cfg.center_points


@SETTINGS
@given(cfg=reaction_configs())
def test_index_is_run_numbered_from_one(cfg: ReactionConfig) -> None:
    df = build_design(cfg)
    assert df.index.name == "Run"
    assert list(df.index) == list(range(1, len(df) + 1))


@SETTINGS
@given(cfg=reaction_configs())
def test_every_corner_present_exactly_once(cfg: ReactionConfig) -> None:
    df = build_design(cfg)
    factor_names = [f.name for f in cfg.factors]
    non_center = df.loc[~df["is_center"], factor_names]
    expected = {
        tuple(f.low if c == -1 else f.high for f, c in zip(cfg.factors, combo, strict=True))
        for combo in itertools.product([-1, 1], repeat=len(cfg.factors))
    }
    actual = {tuple(row) for row in non_center.to_numpy()}
    assert actual == expected
    assert len(non_center) == 2 ** len(cfg.factors)


@SETTINGS
@given(cfg=reaction_configs())
def test_center_rows_are_midpoints(cfg: ReactionConfig) -> None:
    df = build_design(cfg)
    centers = df.loc[df["is_center"]]
    assert len(centers) == cfg.center_points
    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        if len(centers):
            assert np.allclose(centers[f.name].to_numpy(), mid)


@SETTINGS
@given(cfg=reaction_configs())
def test_coded_columns_pm_one_at_corners_zero_at_centers(cfg: ReactionConfig) -> None:
    df = build_design(cfg)
    for f in cfg.factors:
        col = f"{f.name}_coded"
        corners = df.loc[~df["is_center"], col].to_numpy()
        assert np.allclose(np.abs(corners), 1.0)
        centers = df.loc[df["is_center"], col].to_numpy()
        if len(centers):
            assert np.allclose(centers, 0.0)


@SETTINGS
@given(cfg=reaction_configs())
def test_same_seed_identical_frame(cfg: ReactionConfig) -> None:
    a = build_design(cfg)
    b = build_design(cfg)
    factor_cols = [f.name for f in cfg.factors]
    assert a[factor_cols].equals(b[factor_cols])


@SETTINGS
@given(cfg=reaction_configs())
def test_different_seed_permutes_rows(cfg: ReactionConfig) -> None:
    # k=2 + 0 center points is 4 rows — seed bump can occasionally hash to the
    # same order, so we only assert when the design is large enough that
    # collisions are astronomically unlikely.
    if 2 ** len(cfg.factors) + cfg.center_points < 6:
        return
    a = build_design(cfg)
    other = cfg.model_copy(update={"seed": cfg.seed + 1})
    b = build_design(other)
    factor_cols = [f.name for f in cfg.factors]
    assert not a[factor_cols].reset_index(drop=True).equals(
        b[factor_cols].reset_index(drop=True)
    )


@SETTINGS
@given(cfg=reaction_configs())
def test_is_center_count_matches_center_points(cfg: ReactionConfig) -> None:
    df = build_design(cfg)
    assert int(df["is_center"].sum()) == cfg.center_points
