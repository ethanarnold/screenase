"""Tests for wall-clock scheduling + lot-expiry warnings."""

from __future__ import annotations

import pandas as pd

from screenase.design import build_design
from screenase.plate import assign_plate
from screenase.scheduling import (
    check_lot_expiry,
    plan_schedule,
    render_gantt_png,
)


def test_plan_schedule_single_plate(cfg) -> None:
    design = build_design(cfg)
    plate_df = assign_plate(design, plate="96", layout="column-major")
    stages = plan_schedule(plate_df, incubate_min=60, read_min=10, pipet_min_per_run=1)
    assert len(stages) == 3  # pipet, incubate, read for 1 plate
    n = len(plate_df)
    assert stages[0].stage == "pipet"
    assert stages[0].end_min == n * 1
    assert stages[1].stage == "incubate"
    assert stages[1].end_min == n * 1 + 60
    assert stages[2].stage == "read"
    assert stages[2].end_min == n * 1 + 60 + 10


def test_plan_schedule_multi_plate_stagger(cfg) -> None:
    # Force a 2-plate situation by using a 384-plate with minimal fills
    # Actually the default k=4 design is 19 runs, fits one plate. Build a
    # synthetic 2-plate frame.
    plate_df = pd.DataFrame({
        "plate": [1] * 10 + [2] * 10,
        "well": [f"A{i}" for i in range(1, 11)] * 2,
    })
    stages = plan_schedule(plate_df, plate_stagger_min=5, pipet_min_per_run=1,
                           incubate_min=60, read_min=10)
    assert len(stages) == 6  # 3 stages × 2 plates
    # Plate 2 starts 5 min after plate 1
    plate2_pipet = next(s for s in stages if s.plate == 2 and s.stage == "pipet")
    assert plate2_pipet.start_min == 5


def test_render_gantt_png(cfg, tmp_path) -> None:
    design = build_design(cfg)
    plate_df = assign_plate(design, plate="96", layout="column-major")
    stages = plan_schedule(plate_df)
    out = render_gantt_png(stages, tmp_path / "gantt.png")
    assert out.exists() and out.stat().st_size > 0


def test_check_lot_expiry_flags_soon_and_expired() -> None:
    refs = {
        "NTPs": {"containerId": "con_1", "lotId": "lot_a", "expiryDate": "2026-05-01"},
        "MgCl2": {"containerId": "con_2", "lotId": "lot_b", "expiryDate": "2026-04-01"},
        "T7": {"containerId": "con_3", "lotId": "lot_c", "expiryDate": "2027-06-01"},
        "PEG8000": {"containerId": "con_4", "lotId": "lot_d"},  # no expiry
    }
    today = "2026-04-17"
    warns = check_lot_expiry(refs, today=today, warn_threshold_days=30)
    # NTPs expires in 14 days → warn; MgCl2 expired 16 days ago → warn;
    # T7 expires far future → no warn; PEG8000 lacks expiry → no warn.
    flagged = {w.reagent for w in warns}
    assert flagged == {"NTPs", "MgCl2"}
    mgcl2 = next(w for w in warns if w.reagent == "MgCl2")
    assert mgcl2.days_until_expiry < 0
    ntps = next(w for w in warns if w.reagent == "NTPs")
    assert 0 <= ntps.days_until_expiry <= 30
