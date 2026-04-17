"""Plackett-Burman design tests."""

from __future__ import annotations

import numpy as np
import pytest

from screenase.design import build_pb, plackett_burman


@pytest.mark.parametrize("runs", [8, 12, 16, 20, 24])
def test_plackett_burman_is_hadamard(runs: int) -> None:
    m = plackett_burman(runs)
    assert m.shape == (runs, runs - 1)
    # Every column has zero column sum (balanced main effects)
    assert (m.sum(axis=0) == 0).all(), f"unbalanced columns at runs={runs}"
    # Any pair of columns is orthogonal
    gram = m.T @ m
    off_diag = gram - np.diag(np.diag(gram))
    assert (off_diag == 0).all(), f"non-orthogonal columns at runs={runs}"


def test_plackett_burman_unsupported_runs_raises() -> None:
    with pytest.raises(ValueError, match="not supported"):
        plackett_burman(9)


def test_build_pb_default_config(cfg) -> None:
    design = build_pb(cfg, runs=12)
    # 12 PB rows + 3 center points
    assert len(design) == 15
    factor_cols = [f.name for f in cfg.factors]
    for c in factor_cols:
        assert c in design.columns
        assert f"{c}_coded" in design.columns
    assert "is_center" in design.columns
    assert design["is_center"].sum() == cfg.center_points


def test_build_pb_k_exceeds_runs_raises(cfg) -> None:
    # cfg has k=4; PB-8 supports up to 7 factors, so this should be fine.
    # Artificially shrink PB capacity: runs=8 and inject an oversized k.
    # Easiest: monkey-build a fake cfg-like object.
    class _Cfg:
        seed = 42
        center_points = 0
        factors = cfg.factors * 3  # 12 factors > 7 PB-8 capacity

    with pytest.raises(ValueError, match="exceeds PB runs"):
        build_pb(_Cfg(), runs=8)  # type: ignore[arg-type]
