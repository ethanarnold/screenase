"""Wall-clock schedule for a run: prep → pipet → incubate → read.

`plan_schedule` lays out sequential stages per plate as (stage, start_min,
end_min). `render_gantt_png` draws a Gantt bar chart.

Timings are intentionally rough — a real deployment would read per-reagent
prep times from the config. The defaults (pipet 1 min/run, incubate 120 min,
read 15 min) cover the common IVT loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


@dataclass
class ScheduleStage:
    plate: int
    stage: str
    start_min: float
    end_min: float


def plan_schedule(
    plate_df: pd.DataFrame,
    *,
    pipet_min_per_run: float = 1.0,
    incubate_min: float = 120.0,
    read_min: float = 15.0,
    plate_stagger_min: float = 5.0,
) -> list[ScheduleStage]:
    """Sequential prep → pipet → incubate → read, with a small per-plate stagger."""
    if "plate" not in plate_df.columns:
        raise ValueError("plate_df must have a `plate` column (from assign_plate)")
    stages: list[ScheduleStage] = []
    plates = sorted(plate_df["plate"].unique())
    for i, p in enumerate(plates):
        n_runs = int((plate_df["plate"] == p).sum())
        t0 = i * plate_stagger_min
        pipet_end = t0 + n_runs * pipet_min_per_run
        incubate_end = pipet_end + incubate_min
        read_end = incubate_end + read_min
        stages.append(ScheduleStage(plate=int(p), stage="pipet", start_min=t0, end_min=pipet_end))
        stages.append(ScheduleStage(plate=int(p), stage="incubate",
                                    start_min=pipet_end, end_min=incubate_end))
        stages.append(ScheduleStage(plate=int(p), stage="read",
                                    start_min=incubate_end, end_min=read_end))
    return stages


_STAGE_COLORS = {
    "pipet": "#4a6fa5",
    "incubate": "#f2b84b",
    "read": "#4ca57a",
}


def render_gantt_png(stages: list[ScheduleStage], out_path: Path | str) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plates = sorted({s.plate for s in stages})
    fig, ax = plt.subplots(figsize=(8, max(2, 0.5 * len(plates) + 1)))
    for s in stages:
        y = plates.index(s.plate)
        ax.barh(y, s.end_min - s.start_min, left=s.start_min,
                color=_STAGE_COLORS.get(s.stage, "#888"),
                edgecolor="white", linewidth=0.5)
        mid = (s.start_min + s.end_min) / 2
        ax.text(mid, y, s.stage, ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")
    ax.set_yticks(range(len(plates)))
    ax.set_yticklabels([f"Plate {p}" for p in plates])
    ax.set_xlabel("Minutes from start")
    ax.set_title("Screenase run schedule")
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


# ---------- Lot expiry warnings ----------

@dataclass
class LotWarning:
    reagent: str
    lot_id: str
    days_until_expiry: int
    reason: str


def check_lot_expiry(
    lot_refs: dict[str, dict[str, str]],
    *,
    today: str,
    warn_threshold_days: int = 30,
) -> list[LotWarning]:
    """Warn when lot expiry is within `warn_threshold_days`.

    `lot_refs[reagent]` is expected to carry an `expiryDate` (YYYY-MM-DD). A
    missing date is silently skipped (matches the Benchling convention of
    nullable lot metadata).
    """
    from datetime import date

    t = date.fromisoformat(today)
    out: list[LotWarning] = []
    for reagent, ref in lot_refs.items():
        exp = ref.get("expiryDate")
        if not exp:
            continue
        days = (date.fromisoformat(exp) - t).days
        if days < 0:
            out.append(LotWarning(
                reagent=reagent, lot_id=ref.get("lotId", ""),
                days_until_expiry=days,
                reason=f"lot expired {-days} days ago",
            ))
        elif days <= warn_threshold_days:
            out.append(LotWarning(
                reagent=reagent, lot_id=ref.get("lotId", ""),
                days_until_expiry=days,
                reason=f"lot expires in {days} days (threshold: {warn_threshold_days})",
            ))
    return out
