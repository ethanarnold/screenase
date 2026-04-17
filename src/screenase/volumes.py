"""Stock → pipetting volume calculations + validation warnings."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from screenase.config import ReactionConfig

PIPET_SUFFIX = "_pipet_uL"
WATER_COL = "Water" + PIPET_SUFFIX
TOTAL_COL = "Total" + PIPET_SUFFIX
DNA_COL = "DNA" + PIPET_SUFFIX


@dataclass
class VolumeWarning:
    run: int
    reagent: str
    volume_uL: float
    reason: str


def _pipet_col(reagent: str) -> str:
    return f"{reagent}{PIPET_SUFFIX}"


def compute_volumes(design: pd.DataFrame, cfg: ReactionConfig) -> pd.DataFrame:
    """Add `<reagent>_pipet_uL` columns plus Water/Total. Sums to `cfg.reaction_volume_uL`."""
    vol_df = design.copy()
    v_rxn = cfg.reaction_volume_uL
    reagent_cols: list[str] = []

    for factor in cfg.factors:
        col = _pipet_col(factor.reagent)
        if factor.dosing == "volume":
            vol_df[col] = design[factor.name].astype(float)
        else:
            stock = cfg.stocks[factor.reagent]
            vol_df[col] = design[factor.name].astype(float) * v_rxn / stock.concentration
        reagent_cols.append(col)

    for reagent, vol in cfg.fixed_reagents.items():
        col = _pipet_col(reagent)
        vol_df[col] = float(vol)
        reagent_cols.append(col)

    vol_df[DNA_COL] = float(cfg.dna_template_uL)
    reagent_cols.append(DNA_COL)

    vol_df[WATER_COL] = v_rxn - vol_df[reagent_cols].sum(axis=1)
    vol_df[TOTAL_COL] = v_rxn
    return vol_df


def validate_volumes(
    vol_df: pd.DataFrame,
    cfg: ReactionConfig,
    min_pipet_uL: float = 0.5,
) -> list[VolumeWarning]:
    """Raise on impossible doses, warn on sub-min-pipet volumes and negative water."""
    for factor in cfg.factors:
        if factor.dosing != "concentration":
            continue
        stock = cfg.stocks.get(factor.reagent)
        if stock is None:
            raise ValueError(f"Factor {factor.name!r} references unknown stock {factor.reagent!r}")
        if factor.high > stock.concentration:
            raise ValueError(
                f"Factor {factor.name!r} high setpoint {factor.high} "
                f"exceeds stock {factor.reagent!r} concentration {stock.concentration}"
            )

    warnings: list[VolumeWarning] = []
    pipet_cols = [
        c for c in vol_df.columns
        if c.endswith(PIPET_SUFFIX) and c not in (TOTAL_COL,)
    ]
    for col in pipet_cols:
        reagent = col[: -len(PIPET_SUFFIX)]
        for run, vol in vol_df[col].items():
            vol_f = float(vol)
            if col == WATER_COL and vol_f < 0:
                warnings.append(VolumeWarning(
                    run=int(run), reagent=reagent, volume_uL=vol_f,
                    reason="reagents exceed reaction volume (water < 0)",
                ))
            elif 0 < vol_f < min_pipet_uL:
                warnings.append(VolumeWarning(
                    run=int(run), reagent=reagent, volume_uL=vol_f,
                    reason=f"< {min_pipet_uL} uL pipetting minimum",
                ))
    return warnings


def stock_totals(vol_df: pd.DataFrame, excess: float = 1.2) -> dict[str, float]:
    """Per-reagent sum across all runs, scaled by `excess` (1.2 ≈ +20%)."""
    totals: dict[str, float] = {}
    for c in vol_df.columns:
        if c.endswith(PIPET_SUFFIX) and c != TOTAL_COL:
            reagent = c[: -len(PIPET_SUFFIX)]
            totals[reagent] = float(vol_df[c].sum()) * excess
    return totals
