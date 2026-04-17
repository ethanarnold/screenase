"""Plate-layout generator: assign design runs to 96/384-well plate wells.

`assign_plate` attaches `plate`, `well`, `row_letter`, and `col_number` columns
to a design DataFrame. Wells are traversed in column-major, row-major, or
seeded-random order; when the number of runs exceeds a single plate, extra
plates are spilled into (plate index 1, 2, ...).

`render_plate_map_html` and `render_plate_map_png` visualize the placement so
scientists can dry-run a physical plate layout before pipetting.
"""

from __future__ import annotations

from pathlib import Path
from string import ascii_uppercase
from typing import Literal

import numpy as np
import pandas as pd

PlateType = Literal["96", "384"]
LayoutMode = Literal["column-major", "row-major", "randomized"]

PLATE_DIMS: dict[str, tuple[int, int]] = {
    "96": (8, 12),
    "384": (16, 24),
}


def plate_dims(plate: PlateType) -> tuple[int, int]:
    """Return `(rows, cols)` for the named plate type."""
    if plate not in PLATE_DIMS:
        raise ValueError(f"unknown plate type {plate!r}; expected one of {sorted(PLATE_DIMS)}")
    return PLATE_DIMS[plate]


def _row_letter(r: int) -> str:
    """0 → 'A', 15 → 'P'. Supports 96-well (8 rows) and 384-well (16 rows)."""
    if r < 0 or r >= len(ascii_uppercase):
        raise ValueError(f"row index {r} out of range")
    return ascii_uppercase[r]


def _well_label(r: int, c: int) -> str:
    return f"{_row_letter(r)}{c + 1}"


def _traversal(rows: int, cols: int, layout: LayoutMode, seed: int | None) -> list[tuple[int, int]]:
    if layout == "column-major":
        return [(r, c) for c in range(cols) for r in range(rows)]
    if layout == "row-major":
        return [(r, c) for r in range(rows) for c in range(cols)]
    if layout == "randomized":
        if seed is None:
            raise ValueError("randomized layout requires a seed")
        order = [(r, c) for r in range(rows) for c in range(cols)]
        rng = np.random.default_rng(seed)
        rng.shuffle(order)
        return order
    raise ValueError(f"unknown layout {layout!r}")


def assign_plate(
    design_df: pd.DataFrame,
    *,
    plate: PlateType = "96",
    layout: LayoutMode = "column-major",
    seed: int | None = None,
) -> pd.DataFrame:
    """Return a copy of `design_df` with `plate`, `well`, `row_letter`, `col_number` columns.

    Runs are placed in the order they appear in `design_df`. With more runs
    than one plate holds, plates are added as needed (plate 1, plate 2, ...),
    each with the same traversal layout and the same seed offset so
    randomized layouts stay reproducible.
    """
    if design_df.empty:
        raise ValueError("cannot assign plate to an empty design")
    rows, cols = plate_dims(plate)
    n_wells = rows * cols
    n_runs = len(design_df)
    n_plates = (n_runs + n_wells - 1) // n_wells

    assigned = design_df.copy()
    plates: list[int] = []
    wells: list[str] = []
    row_letters: list[str] = []
    col_numbers: list[int] = []
    for p in range(n_plates):
        # Bump the seed per plate so every plate gets a different random order
        plate_seed = None if seed is None else seed + p
        order = _traversal(rows, cols, layout, plate_seed)
        start = p * n_wells
        end = min(start + n_wells, n_runs)
        for r, c in order[: end - start]:
            plates.append(p + 1)
            wells.append(_well_label(r, c))
            row_letters.append(_row_letter(r))
            col_numbers.append(c + 1)

    assigned["plate"] = plates
    assigned["well"] = wells
    assigned["row_letter"] = row_letters
    assigned["col_number"] = col_numbers
    return assigned


def render_plate_map_html(assigned_df: pd.DataFrame, plate: PlateType = "96") -> str:
    """Render an HTML snippet: one table per plate, cells labelled by Run index."""
    rows, cols = plate_dims(plate)
    if "plate" not in assigned_df.columns or "well" not in assigned_df.columns:
        raise ValueError("call assign_plate() first; missing `plate`/`well` columns")
    parts: list[str] = []
    parts.append("<style>")
    parts.append(
        ".plate-map{border-collapse:collapse;font-family:system-ui,sans-serif;"
        "font-size:12px;margin:1em 0;}"
        ".plate-map th,.plate-map td{border:1px solid #ccc;padding:4px 6px;"
        "text-align:center;min-width:28px;}"
        ".plate-map th{background:#f4f4f4;}"
        ".plate-map td.empty{background:#fafafa;color:#bbb;}"
        ".plate-map td.center{background:#fff3cd;}"
        ".plate-map .caption{font-weight:600;margin:0.5em 0 0.2em;}"
    )
    parts.append("</style>")
    for plate_idx in sorted(assigned_df["plate"].unique()):
        sub = assigned_df[assigned_df["plate"] == plate_idx]
        by_well = {row.well: (int(idx), bool(row.get("is_center", False)))
                   for idx, row in sub.iterrows()}
        parts.append(f'<div class="caption">Plate {plate_idx}</div>')
        parts.append('<table class="plate-map">')
        parts.append("<tr><th></th>" + "".join(f"<th>{c + 1}</th>" for c in range(cols)) + "</tr>")
        for r in range(rows):
            cells = [f"<th>{_row_letter(r)}</th>"]
            for c in range(cols):
                well = _well_label(r, c)
                if well in by_well:
                    run, is_center = by_well[well]
                    klass = "center" if is_center else ""
                    cells.append(f'<td class="{klass}">{run}</td>')
                else:
                    cells.append('<td class="empty">·</td>')
            parts.append("<tr>" + "".join(cells) + "</tr>")
        parts.append("</table>")
    return "\n".join(parts)


def render_plate_map_png(
    assigned_df: pd.DataFrame,
    out_path: Path | str,
    *,
    plate: PlateType = "96",
) -> list[Path]:
    """Render one PNG per plate. Returns the list of files written."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows, cols = plate_dims(plate)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    plate_idxs = sorted(assigned_df["plate"].unique())
    for plate_idx in plate_idxs:
        sub = assigned_df[assigned_df["plate"] == plate_idx]
        by_well = {row.well: (int(idx), bool(row.get("is_center", False)))
                   for idx, row in sub.iterrows()}
        fig, ax = plt.subplots(figsize=(cols * 0.5 + 1.2, rows * 0.5 + 1.2))
        for r in range(rows):
            for c in range(cols):
                well = _well_label(r, c)
                if well in by_well:
                    run, is_center = by_well[well]
                    color = "#fff3cd" if is_center else "#eaf3fb"
                    edge = "#ba9a00" if is_center else "#4a6fa5"
                    ax.add_patch(plt.Circle((c, rows - 1 - r), 0.38, facecolor=color,
                                            edgecolor=edge, linewidth=1.2))
                    ax.text(c, rows - 1 - r, str(run), ha="center", va="center",
                            fontsize=8, color="#222")
                else:
                    ax.add_patch(plt.Circle((c, rows - 1 - r), 0.38, facecolor="white",
                                            edgecolor="#ccc", linewidth=0.8))
        ax.set_xlim(-0.8, cols - 0.2)
        ax.set_ylim(-0.8, rows - 0.2)
        ax.set_aspect("equal")
        ax.set_xticks(range(cols))
        ax.set_xticklabels([str(c + 1) for c in range(cols)])
        ax.set_yticks(range(rows))
        ax.set_yticklabels([_row_letter(rows - 1 - r) for r in range(rows)])
        ax.xaxis.tick_top()
        ax.xaxis.set_label_position("top")
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(length=0)
        ax.set_title(f"Plate {plate_idx} ({plate}-well)", pad=10)
        fig.tight_layout()
        if len(plate_idxs) == 1:
            target = out_path
        else:
            stem, suffix = out_path.stem, out_path.suffix or ".png"
            target = out_path.with_name(f"{stem}_plate{plate_idx}{suffix}")
        fig.savefig(target, dpi=140)
        plt.close(fig)
        written.append(target)
    return written
