"""Context assembler + Jinja2 renderer for the IVT bench sheet."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, PackageLoader

from screenase.config import ReactionConfig
from screenase.volumes import (
    DNA_COL,
    PIPET_SUFFIX,
    TOTAL_COL,
    WATER_COL,
    VolumeWarning,
    stock_totals,
)

DEFAULT_TIPS = [
    "Prepare reactions on ice",
    "Add T7 polymerase last",
    "Mix gently by pipetting (do not vortex)",
]


def _fmt(value: Any, n: int = 2) -> str:
    try:
        return f"{float(value):.{n}f}"
    except (TypeError, ValueError):
        return str(value)


_env = Environment(
    loader=PackageLoader("screenase", "templates"),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["fmt"] = _fmt


def _stock_display(unit: str, concentration: float) -> str:
    if unit in ("X", "x"):
        return f"{concentration:g}X"
    if unit == "%":
        return f"{concentration:g}%"
    return f"{concentration:g} {unit}"


def build_context(
    vol_df: pd.DataFrame,
    is_center: pd.Series,
    cfg: ReactionConfig,
    *,
    run_id: str,
    generated_at: str,
    lib_version: str,
    config_hash: str,
    warnings: list[VolumeWarning] | None = None,
    operator: str = "",
    signoff_date: str = "",
    tips: list[str] | None = None,
    plate_map_html: str | None = None,
    reagent_cost_per_uL: dict[str, float] | None = None,
) -> dict[str, Any]:
    totals = stock_totals(vol_df)

    stocks_ctx: list[dict[str, Any]] = []
    seen: set[str] = set()
    ordered_reagents = [f.reagent for f in cfg.factors] + list(cfg.fixed_reagents.keys())
    for reagent in ordered_reagents:
        if reagent in seen or reagent not in cfg.stocks:
            continue
        seen.add(reagent)
        stock = cfg.stocks[reagent]
        stocks_ctx.append({
            "name": stock.name,
            "stock_display": _stock_display(stock.unit, stock.concentration),
            "min_volume_uL": totals.get(reagent, 0.0),
        })
    dna_total = totals.get("DNA", cfg.dna_template_uL * len(vol_df) * 1.2)
    stocks_ctx.append({
        "name": "DNA Template",
        "stock_display": "PCR product",
        "min_volume_uL": dna_total,
    })
    water_total = totals.get("Water", 0.0)
    stocks_ctx.append({
        "name": "Nuclease-free H₂O",
        "stock_display": "—",
        "min_volume_uL": water_total,
    })

    columns: list[dict[str, str]] = []
    for factor in cfg.factors:
        fstock = cfg.stocks.get(factor.reagent)
        sub = _stock_display(fstock.unit, fstock.concentration) if fstock else ""
        columns.append({
            "key": f"{factor.reagent}{PIPET_SUFFIX}",
            "label": factor.display or factor.reagent,
            "sublabel": sub,
        })
    for reagent in cfg.fixed_reagents:
        rstock = cfg.stocks.get(reagent)
        sub = _stock_display(rstock.unit, rstock.concentration) if rstock else ""
        columns.append({
            "key": f"{reagent}{PIPET_SUFFIX}",
            "label": reagent,
            "sublabel": sub,
        })
    columns.append({"key": DNA_COL, "label": "DNA", "sublabel": "PCR"})
    columns.append({"key": WATER_COL, "label": "H₂O", "sublabel": ""})

    runs_ctx: list[dict[str, Any]] = []
    for run_idx, row in vol_df.iterrows():
        r: dict[str, Any] = {
            "run": int(run_idx),
            "is_center": bool(is_center.loc[run_idx]),
            "total_uL": float(row[TOTAL_COL]),
        }
        for col in columns:
            r[col["key"]] = float(row[col["key"]])
        runs_ctx.append(r)

    n_factors = len(cfg.factors)
    design_label = (
        f"2^{n_factors} Full Factorial + {cfg.center_points} Center Points "
        f"({len(vol_df)} runs)"
    )

    cost_ctx: dict[str, Any] | None = None
    if reagent_cost_per_uL:
        from screenase.multiresponse import compute_run_cost
        cost = compute_run_cost(vol_df, reagent_cost_per_uL)
        cost_ctx = {
            "screen_total": cost["screen_total"],
            "avg_per_run": cost["avg_per_run"],
            "per_reagent": [
                {"reagent": r, "total": v}
                for r, v in sorted(cost["per_reagent_total"].items(),
                                   key=lambda kv: -kv[1]) if v > 0
            ],
        }

    return {
        "meta": {
            "generated_at": generated_at,
            "reaction_volume_uL": cfg.reaction_volume_uL,
            "design_label": design_label,
            "run_id": run_id,
            "config_hash": config_hash,
            "lib_version": lib_version,
            "seed": cfg.seed,
        },
        "stocks": stocks_ctx,
        "columns": columns,
        "runs": runs_ctx,
        "warnings": warnings or [],
        "signoff": {"operator": operator, "date": signoff_date},
        "tips": tips if tips is not None else DEFAULT_TIPS,
        "plate_map_html": plate_map_html,
        "cost": cost_ctx,
    }


def render_bench_sheet(context: dict[str, Any]) -> str:
    template = _env.get_template("bench_sheet.html.j2")
    return template.render(**context)


def write_bench_sheet(
    vol_df: pd.DataFrame,
    is_center: pd.Series,
    cfg: ReactionConfig,
    out_path: Path | str,
    *,
    run_id: str,
    generated_at: str,
    lib_version: str,
    config_hash: str,
    warnings: list[VolumeWarning] | None = None,
    operator: str = "",
    signoff_date: str = "",
    tips: list[str] | None = None,
    plate_map_html: str | None = None,
    reagent_cost_per_uL: dict[str, float] | None = None,
) -> Path:
    ctx = build_context(
        vol_df, is_center, cfg,
        run_id=run_id,
        generated_at=generated_at,
        lib_version=lib_version,
        config_hash=config_hash,
        warnings=warnings,
        operator=operator,
        signoff_date=signoff_date,
        tips=tips,
        plate_map_html=plate_map_html,
        reagent_cost_per_uL=reagent_cost_per_uL,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_bench_sheet(ctx))
    return out
