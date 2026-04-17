from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from screenase.cli import main

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "examples" / "config.yaml"


def test_help_exits_zero():
    r = subprocess.run(
        [sys.executable, "-m", "screenase", "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "screenase" in r.stdout


def test_generate_help_exits_zero():
    r = subprocess.run(
        [sys.executable, "-m", "screenase", "generate", "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0


def test_analyze_help_exits_zero():
    r = subprocess.run(
        [sys.executable, "-m", "screenase", "analyze", "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0


def test_generate_writes_csv_and_html(tmp_path):
    rc = main(["generate", "--config", str(CONFIG), "--out-dir", str(tmp_path)])
    assert rc == 0
    csv = tmp_path / "ivt_screen.csv"
    html = tmp_path / "ivt_bench_sheet.html"
    assert csv.exists() and csv.stat().st_size > 0
    assert html.exists() and html.stat().st_size > 0


def test_generate_with_export_benchling(tmp_path):
    rc = main(["generate", "--config", str(CONFIG), "--out-dir", str(tmp_path),
               "--export", "benchling"])
    assert rc == 0
    out = tmp_path / "benchling_request.json"
    assert out.exists()
    payload = json.loads(out.read_text())
    assert isinstance(payload, dict)
    for key in ("schemaId", "fields", "runs"):
        assert key in payload, f"missing {key}"


def test_generate_and_analyze_round_trip(tmp_path, cfg):
    # generate
    assert main(["generate", "--config", str(CONFIG), "--out-dir", str(tmp_path)]) == 0
    coded_csv = tmp_path / "ivt_screen_coded.csv"
    assert coded_csv.exists()

    # attach a synthetic response and analyze
    df = pd.read_csv(coded_csv, index_col="Run")
    rng_terms = (
        3.0 * df["NTPs_mM_each_coded"]
        - 2.0 * df["MgCl2_mM_coded"]
        + 1.5 * df["NTPs_mM_each_coded"] * df["MgCl2_mM_coded"]
    )
    df["yield_ug_per_uL"] = rng_terms + 0.1
    results_csv = tmp_path / "results.csv"
    df.to_csv(results_csv)

    out_ana = tmp_path / "ana"
    rc = main(["analyze", str(results_csv), "--response", "yield_ug_per_uL",
               "--out-dir", str(out_ana)])
    assert rc == 0
    assert (out_ana / "pareto.png").exists()
    assert (out_ana / "analysis_report.md").exists()


def test_generate_seed_override_changes_order(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    main(["generate", "--config", str(CONFIG), "--out-dir", str(a), "--seed", "42"])
    main(["generate", "--config", str(CONFIG), "--out-dir", str(b), "--seed", "7"])
    assert (a / "ivt_screen.csv").read_text() != (b / "ivt_screen.csv").read_text()


def test_generate_with_plate_writes_layout(tmp_path):
    rc = main(["generate", "--config", str(CONFIG), "--out-dir", str(tmp_path),
               "--plate", "96"])
    assert rc == 0
    assert (tmp_path / "plate_layout.csv").exists()
    assert (tmp_path / "plate_map.png").exists()
    df = pd.read_csv(tmp_path / "plate_layout.csv", index_col="Run")
    assert set(df.columns) >= {"plate", "well", "row_letter", "col_number", "is_center"}
    assert len(df) == 19
    # Plate map should be embedded in the bench sheet
    html = (tmp_path / "ivt_bench_sheet.html").read_text()
    assert "Plate layout" in html
    assert "plate-map" in html


def test_generate_ccd_design_emits_extra_runs(tmp_path):
    rc = main(["generate", "--config", str(CONFIG), "--out-dir", str(tmp_path),
               "--design", "ccd", "--alpha", "face"])
    assert rc == 0
    df = pd.read_csv(tmp_path / "ivt_screen_coded.csv", index_col="Run")
    # 2^4 factorial + 2*4 axial + 3 center
    assert len(df) == 16 + 8 + 3


def test_generate_export_benchling_inventory(tmp_path):
    lot_refs = {
        "NTPs": {"containerId": "con_ntp", "lotId": "lot_ntp"},
        "MgCl2": {"containerId": "con_mg", "lotId": "lot_mg"},
        "T7": {"containerId": "con_t7", "lotId": "lot_t7"},
        "PEG8000": {"containerId": "con_peg", "lotId": "lot_peg"},
        "Buffer": {"containerId": "con_buffer", "lotId": "lot_buffer"},
    }
    refs_path = tmp_path / "lot_refs.json"
    refs_path.write_text(json.dumps(lot_refs))
    rc = main(["generate", "--config", str(CONFIG), "--out-dir", str(tmp_path),
               "--export", "benchling-inventory", "--lot-refs", str(refs_path)])
    assert rc == 0
    out = tmp_path / "benchling_inventory.json"
    assert out.exists()
    summary = json.loads(out.read_text())
    assert summary["payload"]["operation"] == "inventoryDecrement"
    assert summary["payload"]["unresolved"] == []
    assert summary["consumptionUL"]


def test_generate_export_both_benchling_flavors(tmp_path):
    rc = main(["generate", "--config", str(CONFIG), "--out-dir", str(tmp_path),
               "--export", "benchling", "--export", "benchling-inventory"])
    assert rc == 0
    assert (tmp_path / "benchling_request.json").exists()
    assert (tmp_path / "benchling_inventory.json").exists()


def test_generate_ccd_rotatable_alpha(tmp_path):
    rc = main(["generate", "--config", str(CONFIG), "--out-dir", str(tmp_path),
               "--design", "ccd", "--alpha", "rotatable"])
    assert rc == 0
    assert (tmp_path / "ivt_bench_sheet.html").exists()


def test_generate_with_plate_randomized_is_reproducible(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    main(["generate", "--config", str(CONFIG), "--out-dir", str(a),
          "--plate", "96", "--plate-layout", "randomized"])
    main(["generate", "--config", str(CONFIG), "--out-dir", str(b),
          "--plate", "96", "--plate-layout", "randomized"])
    da = pd.read_csv(a / "plate_layout.csv", index_col="Run")
    db = pd.read_csv(b / "plate_layout.csv", index_col="Run")
    assert list(da["well"]) == list(db["well"])
