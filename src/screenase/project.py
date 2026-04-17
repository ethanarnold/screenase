"""Project-level organization — a home for multi-screen campaigns.

Layout:
    <project>/
        project.yaml           # metadata (name, owner, created)
        screens/
            <run-id-1>/
                config.yaml
                ivt_screen.csv
                analysis_report.md   (after analyze)
                ...
            <run-id-2>/
                ...

`init_project` creates the skeleton; `project_status` scans `screens/` and
returns an at-a-glance summary table for the CLI / Streamlit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml

PROJECT_META = "project.yaml"
SCREENS_SUBDIR = "screens"


@dataclass
class ScreenStatus:
    run_id: str
    has_config: bool
    has_screen_csv: bool
    has_bench_sheet: bool
    has_analysis: bool
    top_term: str | None
    r_squared: float | None


def init_project(root: Path | str, *, name: str, owner: str = "") -> Path:
    """Create the project scaffolding at `root`. Fails if already initialized."""
    root = Path(root)
    meta_path = root / PROJECT_META
    if meta_path.exists():
        raise FileExistsError(f"{meta_path} already exists")
    (root / SCREENS_SUBDIR).mkdir(parents=True, exist_ok=True)
    meta = {
        "name": name,
        "owner": owner,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    meta_path.write_text(yaml.safe_dump(meta, sort_keys=False))
    return root


def _parse_analysis(md_path: Path) -> tuple[str | None, float | None]:
    """Extract (top_term, r_squared) from an analysis_report.md, best-effort."""
    if not md_path.exists():
        return None, None
    text = md_path.read_text()
    r2 = None
    m = re.search(r"R².*?:\s*([0-9.]+)", text)
    if m:
        try:
            r2 = float(m.group(1))
        except ValueError:
            r2 = None
    top = None
    # First row of the ranked-effects table looks like: | `term` | coef | ...
    tm = re.search(r"## Ranked effects[\s\S]+?\|\s*`([^`]+)`", text)
    if tm:
        top = tm.group(1)
    return top, r2


def project_status(root: Path | str) -> pd.DataFrame:
    """Scan `<root>/screens/` and return a status DataFrame."""
    root = Path(root)
    rows: list[dict] = []
    screens_dir = root / SCREENS_SUBDIR
    if not screens_dir.exists():
        return pd.DataFrame(columns=[
            "run_id", "has_config", "has_screen_csv", "has_bench_sheet",
            "has_analysis", "top_term", "r_squared",
        ])
    for d in sorted(screens_dir.iterdir()):
        if not d.is_dir():
            continue
        top_term, r2 = _parse_analysis(d / "analysis_report.md")
        rows.append({
            "run_id": d.name,
            "has_config": (d / "config.yaml").exists() or (d / "ivt_screen.csv").exists(),
            "has_screen_csv": (d / "ivt_screen.csv").exists(),
            "has_bench_sheet": (d / "ivt_bench_sheet.html").exists(),
            "has_analysis": (d / "analysis_report.md").exists(),
            "top_term": top_term,
            "r_squared": r2,
        })
    return pd.DataFrame(rows)
