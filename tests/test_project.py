"""Tests for `screenase.project` init/status."""

from __future__ import annotations

from pathlib import Path

import pytest

from screenase.project import init_project, project_status


def test_init_project_creates_skeleton(tmp_path: Path) -> None:
    root = init_project(tmp_path, name="IVT Optimization", owner="ethan")
    assert (root / "project.yaml").exists()
    assert (root / "screens").is_dir()


def test_init_project_fails_on_existing(tmp_path: Path) -> None:
    init_project(tmp_path, name="X")
    with pytest.raises(FileExistsError):
        init_project(tmp_path, name="X")


def test_project_status_empty(tmp_path: Path) -> None:
    init_project(tmp_path, name="X")
    df = project_status(tmp_path)
    assert df.empty


def test_project_status_finds_screens(tmp_path: Path) -> None:
    init_project(tmp_path, name="X")
    # Create a fake screen
    s = tmp_path / "screens" / "run-001"
    s.mkdir()
    (s / "ivt_screen.csv").write_text("Run,NTPs\n1,5\n")
    (s / "ivt_bench_sheet.html").write_text("<html></html>")
    (s / "analysis_report.md").write_text(
        "# Analysis\n- R²: 0.987\n\n## Ranked effects\n\n"
        "| Term | Coef |\n|---|---:|\n| `NTPs_coded` | 2.0 |\n"
    )
    df = project_status(tmp_path)
    assert len(df) == 1
    assert df.iloc[0]["run_id"] == "run-001"
    assert df.iloc[0]["top_term"] == "NTPs_coded"
    assert df.iloc[0]["r_squared"] == pytest.approx(0.987)
