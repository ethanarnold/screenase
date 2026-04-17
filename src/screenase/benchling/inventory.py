"""Compute reagent consumption for a Screenase run and shape an inventory
decrement payload for Benchling.

No live API calls. `compute_reagent_consumption` sums per-reagent pipetting
volumes (with an excess factor for dead volume / pipetting loss);
`build_inventory_decrement_payload` wraps those sums in a payload a caller
could POST to Benchling's containers API to decrement stock lot volumes.

Mapping rationale:
- Each Screenase stock reagent → one Benchling Container (or Lot)
- Each run consumes `sum(<reagent>_pipet_uL) * excess` µL from the container
- Emitting the payload without calling the API lets us demonstrate the mapping
  end-to-end without enterprise Developer Platform access.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from screenase.config import ReactionConfig
from screenase.volumes import PIPET_SUFFIX, TOTAL_COL, WATER_COL, stock_totals


def compute_reagent_consumption(
    vol_df: pd.DataFrame,
    cfg: ReactionConfig,
    *,
    excess: float = 1.2,
    include_water: bool = False,
    include_dna: bool = False,
) -> dict[str, float]:
    """Per-reagent total µL consumed by this screen, scaled by `excess`.

    By default, water and DNA template are excluded — they're typically
    tracked separately from reagent inventory. Flip `include_water` /
    `include_dna` to include them.
    """
    raw = stock_totals(vol_df, excess=excess)
    out: dict[str, float] = {}
    for reagent, total in raw.items():
        if reagent == "Water":
            if not include_water:
                continue
        elif reagent == "DNA":
            if not include_dna:
                continue
        elif reagent not in cfg.stocks and reagent not in cfg.fixed_reagents:
            # Drop unknown reagents so the payload stays aligned with the config
            continue
        out[reagent] = round(float(total), 4)
    return out


def build_inventory_decrement_payload(
    consumption: dict[str, float],
    lot_refs: dict[str, dict[str, str]],
    *,
    run_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Shape an inventory-decrement payload for Benchling's containers API.

    `lot_refs` maps reagent key → `{"containerId": ..., "lotId": ...}`.
    Unknown reagents (in `consumption` but not in `lot_refs`) are emitted as
    `"unresolved"` entries so a caller can surface a "link these lots" UI
    rather than silently swallowing the miss.
    """
    decrements: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for reagent, vol_uL in consumption.items():
        ref = lot_refs.get(reagent)
        if not ref:
            unresolved.append({"reagent": reagent, "volumeUL": vol_uL})
            continue
        decrements.append({
            "reagent": reagent,
            "containerId": ref.get("containerId"),
            "lotId": ref.get("lotId"),
            "volumeUL": vol_uL,
            "units": "uL",
        })
    return {
        "operation": "inventoryDecrement",
        "runId": run_id,
        "dryRun": dry_run,
        "decrements": decrements,
        "unresolved": unresolved,
    }


def post_run_inventory_summary(
    vol_df: pd.DataFrame,
    cfg: ReactionConfig,
    lot_refs: dict[str, dict[str, str]],
    *,
    run_id: str,
    excess: float = 1.2,
    dry_run: bool = True,
) -> dict[str, Any]:
    """One-shot: consumption + payload + human-readable summary."""
    consumption = compute_reagent_consumption(vol_df, cfg, excess=excess)
    payload = build_inventory_decrement_payload(
        consumption, lot_refs, run_id=run_id, dry_run=dry_run,
    )
    pipet_cols = [
        c for c in vol_df.columns
        if c.endswith(PIPET_SUFFIX) and c not in (TOTAL_COL, WATER_COL)
    ]
    total_pipetted_uL = float(vol_df[pipet_cols].sum().sum())
    return {
        "runId": run_id,
        "excess": excess,
        "totalPipettedUL": round(total_pipetted_uL, 4),
        "consumptionUL": consumption,
        "payload": payload,
    }
