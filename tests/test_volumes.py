from __future__ import annotations

import pytest

from screenase.config import ReactionConfig
from screenase.design import build_design
from screenase.volumes import (
    PIPET_SUFFIX,
    TOTAL_COL,
    WATER_COL,
    VolumeWarning,
    compute_volumes,
    stock_totals,
    validate_volumes,
)


def test_row_sum_equals_reaction_volume(cfg: ReactionConfig):
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    pipet_cols = [c for c in v.columns if c.endswith(PIPET_SUFFIX) and c != TOTAL_COL]
    row_sums = v[pipet_cols].sum(axis=1)
    assert (row_sums - cfg.reaction_volume_uL).abs().max() < 1e-9


def test_validate_raises_when_high_exceeds_stock(cfg: ReactionConfig):
    # Shove NTPs high above its 100 mM stock
    bad = cfg.model_copy(deep=True)
    bad.factors[0].high = 500.0  # NTPs_mM_each, stock=100 mM
    d = build_design(bad)
    v = compute_volumes(d, bad)
    with pytest.raises(ValueError, match="exceeds stock"):
        validate_volumes(v, bad)


def test_sub_min_pipet_volume_warns(cfg: ReactionConfig):
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    ws = validate_volumes(v, cfg, min_pipet_uL=0.5)
    # T7 low setpoint is 0.2 µL (volume-dosed) — every non-center run with T7 low triggers
    t7_warnings = [w for w in ws if w.reagent == "T7"]
    assert len(t7_warnings) == 8
    assert all(w.volume_uL == pytest.approx(0.2) for w in t7_warnings)


def test_stock_totals_approx_sum_times_excess(cfg: ReactionConfig):
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    totals = stock_totals(v, excess=1.2)
    for reagent, expected in totals.items():
        col = f"{reagent}{PIPET_SUFFIX}"
        assert col in v.columns
        assert expected == pytest.approx(float(v[col].sum()) * 1.2)


def test_negative_water_triggers_warning(cfg: ReactionConfig):
    # Push reagents past reaction volume by cranking DNA template way up
    bad = cfg.model_copy(update={"dna_template_uL": 30.0})
    d = build_design(bad)
    v = compute_volumes(d, bad)
    assert (v[WATER_COL] < 0).any()
    ws = validate_volumes(v, bad)
    neg_water = [w for w in ws if w.reagent == "Water"]
    assert len(neg_water) > 0
    assert all(isinstance(w, VolumeWarning) for w in neg_water)
