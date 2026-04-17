"""Multi-response optimization via Derringer-Suich composite desirability.

Given multiple response columns, each with a target ("maximize", "minimize",
or "target" with a numeric target), transform each to a [0,1] desirability
`d_i`, then optimize the geometric mean `D = (prod d_i)^(1/n)` via scipy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.optimize import minimize

GoalType = Literal["maximize", "minimize", "target"]


@dataclass
class ResponseGoal:
    column: str
    goal: GoalType
    lo: float              # undesirable edge
    hi: float              # desirable edge (for target, see `target_value`)
    weight: float = 1.0
    target_value: float | None = None  # only used when goal="target"
    shape: float = 1.0  # Derringer shape exponent (s); 1 = linear


def _desirability(value: float, goal: ResponseGoal) -> float:
    lo, hi = goal.lo, goal.hi
    s = max(goal.shape, 1e-6)
    if goal.goal == "maximize":
        if value <= lo:
            return 0.0
        if value >= hi:
            return 1.0
        return float(((value - lo) / (hi - lo)) ** s)
    if goal.goal == "minimize":
        if value <= lo:
            return 1.0
        if value >= hi:
            return 0.0
        return float(((hi - value) / (hi - lo)) ** s)
    # target
    t = goal.target_value if goal.target_value is not None else (lo + hi) / 2
    if value <= lo or value >= hi:
        return 0.0
    if value <= t:
        if t == lo:
            return 1.0
        return float(((value - lo) / (t - lo)) ** s)
    if hi == t:
        return 1.0
    return float(((hi - value) / (hi - t)) ** s)


def composite_desirability(
    values: dict[str, float],
    goals: list[ResponseGoal],
    *,
    floor: float = 0.0,
) -> float:
    """Weighted geometric mean of per-response desirabilities; returns D ∈ [0, 1].

    `floor` replaces exact zeros with a tiny value so the optimizer can move
    uphill out of a 0-region. Defaults to 0 for hard-boundary behavior; set
    e.g. `1e-12` inside an optimizer's objective.
    """
    if not goals:
        return 0.0
    raw: list[float] = []
    weights: list[float] = []
    for g in goals:
        v = values.get(g.column)
        if v is None:
            continue
        raw.append(_desirability(float(v), g))
        weights.append(g.weight)
    if not raw:
        return 0.0
    total_w = sum(weights)
    if total_w <= 0:
        return 0.0
    if any(d == 0.0 for d in raw) and floor == 0.0:
        return 0.0
    ds = [max(d, floor) if floor > 0 else d for d in raw]
    log_d = sum(w * np.log(d) for w, d in zip(weights, ds, strict=True))
    return float(np.exp(log_d / total_w))


def optimize_multi_response(
    fits: dict[str, object],            # {response: fit object}
    goals: list[ResponseGoal],
    factor_cols: list[str],
    *,
    bounds_coded: tuple[float, float] = (-1.0, 1.0),
) -> dict:
    """Maximize composite desirability jointly across all response fits.

    `fits[goal.column]` must be a statsmodels OLS result over `factor_cols`.
    Returns `{coded, per_response, D, success}`.
    """
    from screenase.analyze import _eval_fit_at

    def objective(x: np.ndarray) -> float:
        row = {c: float(x[i]) for i, c in enumerate(factor_cols)}
        values: dict[str, float] = {}
        for g in goals:
            fit = fits.get(g.column)
            if fit is None:
                continue
            values[g.column] = _eval_fit_at(fit, row)
        return -composite_desirability(values, goals, floor=1e-12)  # minimize -D

    x0 = np.zeros(len(factor_cols))
    result = minimize(objective, x0, method="L-BFGS-B",
                      bounds=[bounds_coded] * len(factor_cols))
    coded = {c: float(result.x[i]) for i, c in enumerate(factor_cols)}
    per = {}
    for g in goals:
        fit = fits.get(g.column)
        if fit is None:
            continue
        pred = _eval_fit_at(fit, coded)
        per[g.column] = {
            "predicted": pred,
            "desirability": _desirability(pred, g),
        }
    return {
        "coded": coded,
        "per_response": per,
        "D": -float(result.fun),
        "success": bool(result.success),
    }


# ---------- Power analysis ----------

def recommend_sample_size(
    *,
    k: int,
    effect_std: float,
    noise_std: float,
    alpha: float = 0.05,
    power: float = 0.80,
    include_2fi: bool = True,
) -> dict:
    """Crude power analysis for a 2^k factorial.

    `effect_std` is the expected coefficient magnitude (coded ±1) and
    `noise_std` is the per-observation residual standard deviation. Returns
    recommended total runs + center-point count so that the smallest coef
    has power ≥ `power` at significance `alpha`.

    This is a quick sanity-check, not a full non-central-F calculation; for
    serious planning use statsmodels.stats.power.
    """
    from scipy.stats import norm

    if effect_std <= 0 or noise_std <= 0:
        raise ValueError("effect_std and noise_std must be > 0")
    z_alpha = float(norm.ppf(1 - alpha / 2))
    z_beta = float(norm.ppf(power))
    # Variance of a 2^k factorial coefficient on coded ±1 is sigma^2 / n.
    # Effect size d = |coef| / (sigma / sqrt(n)) ≥ z_alpha + z_beta.
    # → n ≥ ((z_alpha + z_beta) * sigma / coef)^2
    n_per_coef = ((z_alpha + z_beta) * noise_std / effect_std) ** 2
    # 2^k runs is typical floor; bump center points to hit `n_per_coef`.
    factorial_runs = 2 ** k
    needed_total = int(np.ceil(n_per_coef))
    center_points = max(0, needed_total - factorial_runs)
    dof = needed_total - (k + (k * (k - 1) // 2 if include_2fi else 0) + 1)
    return {
        "factorial_runs": factorial_runs,
        "recommended_center_points": center_points,
        "total_runs": max(needed_total, factorial_runs),
        "df_resid": max(dof, 0),
        "alpha": alpha,
        "power": power,
        "effect_std": effect_std,
        "noise_std": noise_std,
    }


# ---------- Cost model ----------

def compute_run_cost(
    vol_df: pd.DataFrame,
    reagent_cost_per_uL: dict[str, float],
) -> dict:
    """Per-run and per-screen $ cost given a `reagent → $/µL` map.

    Missing reagents are treated as $0 (typical for water / buffer).
    """
    from screenase.volumes import DNA_COL, PIPET_SUFFIX, TOTAL_COL, WATER_COL

    per_run = pd.Series(0.0, index=vol_df.index)
    per_reagent: dict[str, float] = {}
    for col in vol_df.columns:
        if not col.endswith(PIPET_SUFFIX) or col in (TOTAL_COL,):
            continue
        reagent = col[: -len(PIPET_SUFFIX)]
        if col in (WATER_COL, DNA_COL) and reagent not in reagent_cost_per_uL:
            continue
        rate = reagent_cost_per_uL.get(reagent, 0.0)
        cost_col = vol_df[col] * rate
        per_run += cost_col
        per_reagent[reagent] = float(cost_col.sum())
    return {
        "per_run": per_run.to_dict(),
        "per_reagent_total": per_reagent,
        "screen_total": float(per_run.sum()),
        "avg_per_run": float(per_run.mean()),
    }
