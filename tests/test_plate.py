from __future__ import annotations

import pytest

from screenase.config import ReactionConfig
from screenase.design import build_design
from screenase.plate import (
    assign_plate,
    plate_dims,
    render_plate_map_html,
    render_plate_map_png,
)


def test_plate_dims_roundtrip():
    assert plate_dims("96") == (8, 12)
    assert plate_dims("384") == (16, 24)


def test_plate_dims_rejects_unknown():
    with pytest.raises(ValueError, match="unknown plate type"):
        plate_dims("1536")  # type: ignore[arg-type]


def test_assign_plate_single_plate_column_major(cfg: ReactionConfig):
    df = build_design(cfg)
    assigned = assign_plate(df, plate="96", layout="column-major")
    assert list(assigned["plate"].unique()) == [1]
    assert set(assigned.columns) >= {"plate", "well", "row_letter", "col_number"}
    # First 8 runs land in column 1 (A1..H1), then column 2
    assert list(assigned["well"].head(8)) == [f"{ch}1" for ch in "ABCDEFGH"]
    assert list(assigned["col_number"].head(8)) == [1] * 8
    assert assigned["well"].is_unique


def test_assign_plate_row_major(cfg: ReactionConfig):
    df = build_design(cfg)
    assigned = assign_plate(df, plate="96", layout="row-major")
    # First 12 runs fill row A: A1..A12
    heads = list(assigned["well"].head(12))
    assert heads[0] == "A1"
    assert heads[-1] == "A12"


def test_assign_plate_randomized_reproducible(cfg: ReactionConfig):
    df = build_design(cfg)
    a = assign_plate(df, plate="96", layout="randomized", seed=7)
    b = assign_plate(df, plate="96", layout="randomized", seed=7)
    assert list(a["well"]) == list(b["well"])
    c = assign_plate(df, plate="96", layout="randomized", seed=8)
    assert list(a["well"]) != list(c["well"])


def test_assign_plate_requires_seed_for_randomized(cfg: ReactionConfig):
    df = build_design(cfg)
    with pytest.raises(ValueError, match="randomized layout requires a seed"):
        assign_plate(df, plate="96", layout="randomized")


def test_assign_plate_spills_across_plates():
    # Fake 120 runs → 2 plates (1..96 on plate 1, 97..120 on plate 2)
    import pandas as pd

    df = pd.DataFrame({"x": range(120)}, index=pd.Index(range(1, 121), name="Run"))
    assigned = assign_plate(df, plate="96", layout="column-major")
    assert sorted(assigned["plate"].unique().tolist()) == [1, 2]
    assert int((assigned["plate"] == 1).sum()) == 96
    assert int((assigned["plate"] == 2).sum()) == 24


def test_assign_plate_empty_rejected():
    import pandas as pd

    with pytest.raises(ValueError, match="empty design"):
        assign_plate(pd.DataFrame(), plate="96")


def test_render_plate_map_html_contains_every_run(cfg: ReactionConfig):
    df = build_design(cfg)
    assigned = assign_plate(df, plate="96")
    html = render_plate_map_html(assigned, plate="96")
    for run in assigned.index:
        assert f">{run}<" in html
    assert "Plate 1" in html


def test_render_plate_map_html_marks_centers(cfg: ReactionConfig):
    df = build_design(cfg)
    assigned = assign_plate(df, plate="96")
    html = render_plate_map_html(assigned, plate="96")
    n_centers = int(assigned["is_center"].sum())
    assert html.count('class="center"') == n_centers


def test_render_plate_map_png_single_file(cfg: ReactionConfig, tmp_path):
    df = build_design(cfg)
    assigned = assign_plate(df, plate="96")
    out = tmp_path / "plate.png"
    files = render_plate_map_png(assigned, out, plate="96")
    assert files == [out]
    assert out.exists() and out.stat().st_size > 0


def test_render_plate_map_png_multi_plate(tmp_path):
    import pandas as pd

    df = pd.DataFrame({"x": range(120), "is_center": [False] * 120},
                      index=pd.Index(range(1, 121), name="Run"))
    assigned = assign_plate(df, plate="96")
    out = tmp_path / "plate.png"
    files = render_plate_map_png(assigned, out, plate="96")
    assert len(files) == 2
    for f in files:
        assert f.exists() and f.stat().st_size > 0


def test_assign_plate_384_has_full_capacity():
    import pandas as pd

    df = pd.DataFrame({"x": range(384)}, index=pd.Index(range(1, 385), name="Run"))
    assigned = assign_plate(df, plate="384", layout="column-major")
    assert list(assigned["plate"].unique()) == [1]
    assert assigned["well"].nunique() == 384
    # Row letters span A..P (16 rows)
    assert set(assigned["row_letter"].unique()) == set("ABCDEFGHIJKLMNOP")
