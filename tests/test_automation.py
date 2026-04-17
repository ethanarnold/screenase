"""Tests for Echo 525 + OT-2 protocol exporters."""

from __future__ import annotations

import pandas as pd

from screenase.automation import build_echo_transfer_csv, build_ot2_protocol
from screenase.design import build_design
from screenase.plate import assign_plate
from screenase.volumes import compute_volumes


def test_echo_csv_has_per_reagent_rows(cfg) -> None:
    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    plate_df = assign_plate(design, plate="96", layout="column-major")
    csv_text = build_echo_transfer_csv(vol_df, plate_df)
    df = pd.read_csv(pd.io.common.StringIO(csv_text))
    # 19 runs × ~6 reagents (NTPs, MgCl2, T7, PEG8000, Buffer, DNA, Water — skip 0 vols)
    # Some runs may skip PEG8000 (vol=0 at low=0).
    assert len(df) > 0
    # Transfer volumes should be positive nL
    assert (df["Transfer Volume"] > 0).all()
    # All destination wells come from the 96-plate column-major fill (A1, B1, C1,…).
    assert df["Destination Well"].str.match(r"^[A-H][0-9]+$").all()


def test_ot2_protocol_contains_transfers(cfg) -> None:
    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    plate_df = assign_plate(design, plate="96", layout="column-major")
    code = build_ot2_protocol(vol_df, plate_df, cfg, run_id="test-run", plate_size=96)
    assert "from opentrons import protocol_api" in code
    assert "def run(ctx" in code
    assert "pipette.transfer" in code
    assert "test-run" in code
