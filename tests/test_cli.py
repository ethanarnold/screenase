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
