"""Property tests for `compute_volumes`: per-run reagent sum invariant."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from screenase.config import Factor, ReactionConfig, Stock
from screenase.design import build_design
from screenase.volumes import TOTAL_COL, compute_volumes


@st.composite
def _configs(draw) -> ReactionConfig:
    n_factors = draw(st.integers(min_value=2, max_value=4))
    reaction_v = draw(st.floats(min_value=10, max_value=100))
    dna_v = draw(st.floats(min_value=0.5, max_value=3.0))
    seed = draw(st.integers(min_value=0, max_value=1000))
    center_pts = draw(st.integers(min_value=0, max_value=5))
    # Concentration-based factors; avoid impossibly-small stock that would blow out the volume
    factors = []
    stocks = {}
    for i in range(n_factors):
        lo = draw(st.floats(min_value=0.0, max_value=5))
        hi = draw(st.floats(min_value=lo + 0.5, max_value=lo + 20))
        stock_conc = draw(st.floats(min_value=hi * 10, max_value=hi * 100))
        name = f"F{i}"
        reagent = f"Reagent{i}"
        factors.append(Factor(name=name, low=lo, high=hi, unit="mM",
                              reagent=reagent, dosing="concentration"))
        stocks[reagent] = Stock(name=reagent, concentration=stock_conc, unit="mM")
    return ReactionConfig(
        reaction_volume_uL=reaction_v,
        dna_template_uL=dna_v,
        center_points=center_pts,
        seed=seed,
        factors=factors,
        stocks=stocks,
    )


@given(cfg=_configs())
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_reagent_sum_equals_reaction_volume(cfg: ReactionConfig) -> None:
    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    # Per-run, all pipetted volumes should sum to the reaction volume
    pipet_cols = [c for c in vol_df.columns if c.endswith("_pipet_uL") and c != TOTAL_COL]
    per_run = vol_df[pipet_cols].sum(axis=1)
    for v in per_run:
        assert abs(v - cfg.reaction_volume_uL) < 1e-6, (
            f"per-run sum {v} ≠ reaction volume {cfg.reaction_volume_uL}"
        )


@given(cfg=_configs())
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_total_column_matches_reaction_volume(cfg: ReactionConfig) -> None:
    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    assert (vol_df[TOTAL_COL] == cfg.reaction_volume_uL).all()
