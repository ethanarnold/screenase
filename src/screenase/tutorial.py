"""OFAT-vs-DoE simulator used by the tutorial (Streamlit tab + notebook + docs).

Exposes a *ground-truth* IVT response surface and two planning strategies —
one-factor-at-a-time (OFAT) and 2ᵏ full-factorial DoE — so a reader can see,
numerically, what OFAT's blind spot costs them when factors interact.

The ground truth mirrors a realistic IVT: large positive NTPs main effect,
negative MgCl2 main effect, and a *strong* NTPs × MgCl2 interaction that flips
the direction of the MgCl2 preference depending on NTPs. OFAT's independence
assumption misses the interaction entirely, so its predicted optimum is the
wrong corner of the hypercube — we quantify exactly how much yield that costs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from screenase.analyze import fit_model, optimize_response
from screenase.config import ReactionConfig

# Ground-truth coefficients in *coded* space (each factor in [-1, +1]).
# Centered around a 10 µg/µL intercept so all corners are plausible yields.
# The NTPs×MgCl2 interaction is the "trap" — it's large enough to flip the
# main-effect-only prediction of the optimum, which is the whole point.
TRUTH_COEFFICIENTS: dict[str, float] = {
    "intercept": 10.0,
    "NTPs_mM_each": 2.5,
    "MgCl2_mM": -1.5,
    "T7_uL": 0.5,
    "PEG8000_pct": 0.3,
    "NTPs_mM_each:MgCl2_mM": 2.5,
    "NTPs_mM_each:T7_uL": 0.2,
}
TRUTH_NOISE_SIGMA = 0.35


def truth_response(
    coded: pd.DataFrame,
    *,
    coeffs: dict[str, float] | None = None,
    sigma: float | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Evaluate the ground-truth response at coded factor settings.

    `coded` columns must be named exactly as factor names (no `_coded` suffix).
    Missing factors default to 0. Additive Gaussian noise is applied if `sigma`
    is non-zero. Pass `sigma=0` for the noise-free truth surface.
    """
    c = {**TRUTH_COEFFICIENTS, **(coeffs or {})}
    s = TRUTH_NOISE_SIGMA if sigma is None else sigma
    rng = rng if rng is not None else np.random.default_rng(0)

    y = np.full(len(coded), c["intercept"], dtype=float)
    for term, beta in c.items():
        if term == "intercept":
            continue
        if ":" in term:
            a, b = term.split(":")
            if a in coded.columns and b in coded.columns:
                y += beta * coded[a].to_numpy() * coded[b].to_numpy()
        elif term in coded.columns:
            y += beta * coded[term].to_numpy()

    if s > 0:
        y += rng.normal(0.0, s, size=len(coded))
    return y


def ofat_plan(cfg: ReactionConfig, *, center_replicates: int = 3) -> pd.DataFrame:
    """Classic one-factor-at-a-time plan: one center + ±1 spokes per factor.

    Returns a `Run`-indexed DataFrame with real factor columns, `_coded`
    columns, and `is_center`. Total runs = `center_replicates` + 2k.
    """
    factor_names = [f.name for f in cfg.factors]
    k = len(factor_names)

    rows: list[np.ndarray] = [np.zeros(k)] * center_replicates
    for i in range(k):
        low = np.zeros(k)
        low[i] = -1.0
        high = np.zeros(k)
        high[i] = 1.0
        rows.append(low)
        rows.append(high)

    coded = np.vstack(rows)
    df = pd.DataFrame(coded, columns=factor_names)

    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        half = (f.high - f.low) / 2.0
        df[f.name] = mid + df[f.name] * half
        df[f"{f.name}_coded"] = (df[f.name] - mid) / half if half else 0.0

    df["is_center"] = df[factor_names].eq(
        {f.name: (f.low + f.high) / 2.0 for f in cfg.factors},
    ).all(axis=1)
    df.index = pd.Index(range(1, len(df) + 1), name="Run")
    return df


def ofat_pick_optimum(
    results: pd.DataFrame,
    *,
    response_col: str,
    factor_names: list[str],
) -> dict[str, float]:
    """OFAT's naive rule: for each factor, pick the coded level (-1, 0, +1) whose
    mean response is highest while the *other* factors sat at 0. Returns a dict
    mapping factor name → chosen coded setpoint.

    This is the crux of OFAT's blindness: levels are chosen independently, with
    no knowledge of what happens at combinations the plan never tested.
    """
    picks: dict[str, float] = {}
    for name in factor_names:
        coded_col = f"{name}_coded"
        others = [f"{n}_coded" for n in factor_names if n != name]
        at_origin = (results[others].abs().sum(axis=1) < 1e-9)
        subset = results.loc[at_origin]
        means = subset.groupby(coded_col)[response_col].mean()
        picks[name] = float(means.idxmax())
    return picks


@dataclass
class StrategyReport:
    """What one planning strategy produced on the simulated truth."""

    name: str
    n_runs: int
    predicted_optimum_coded: dict[str, float]
    predicted_yield_at_optimum: float
    true_yield_at_optimum: float
    caught_interactions: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ComparisonReport:
    """OFAT vs DoE, side by side, plus the unreachable truth."""

    ofat: StrategyReport
    doe: StrategyReport
    true_best_coded: dict[str, float]
    true_best_yield: float

    def yield_gap(self) -> float:
        """How many yield units OFAT leaves on the table vs DoE (positive = DoE wins)."""
        return self.doe.true_yield_at_optimum - self.ofat.true_yield_at_optimum


def _grid_search_truth(factor_names: list[str]) -> tuple[dict[str, float], float]:
    """Exhaustive search over the 2ᵏ corners to find the true best setpoint."""
    from itertools import product
    best_y = -np.inf
    best_pt: dict[str, float] = {}
    for combo in product([-1.0, 1.0], repeat=len(factor_names)):
        row = pd.DataFrame([dict(zip(factor_names, combo, strict=True))])
        y = float(truth_response(row, sigma=0.0)[0])
        if y > best_y:
            best_y = y
            best_pt = dict(zip(factor_names, combo, strict=True))
    return best_pt, best_y


def run_ofat_vs_doe(
    cfg: ReactionConfig,
    *,
    seed: int = 0,
    coeffs: dict[str, float] | None = None,
    sigma: float | None = None,
) -> ComparisonReport:
    """Simulate both strategies on the ground-truth IVT surface and score them.

    Returns a `ComparisonReport` with each strategy's predicted optimum, the
    *true* yield at that setpoint (computed from the noise-free truth), and
    the interactions DoE managed to flag at α=0.05 that OFAT couldn't see.
    """
    from screenase.design import build_design

    rng_ofat = np.random.default_rng(seed)
    rng_doe = np.random.default_rng(seed + 1)

    factor_names = [f.name for f in cfg.factors]
    factor_cols = [f"{n}_coded" for n in factor_names]

    # --- OFAT ---
    ofat_df = ofat_plan(cfg)
    coded_ofat = ofat_df[[f"{n}_coded" for n in factor_names]].copy()
    coded_ofat.columns = pd.Index(factor_names)
    ofat_df["yield_ug_per_uL"] = truth_response(
        coded_ofat, coeffs=coeffs, sigma=sigma, rng=rng_ofat,
    )
    ofat_pick = ofat_pick_optimum(
        ofat_df, response_col="yield_ug_per_uL", factor_names=factor_names,
    )
    ofat_pred = float(truth_response(
        pd.DataFrame([ofat_pick]), coeffs=coeffs, sigma=0.0,
    )[0])

    # --- DoE (full factorial + centers) ---
    doe_df = build_design(cfg)
    coded_doe = doe_df[[f"{n}_coded" for n in factor_names]].copy()
    coded_doe.columns = pd.Index(factor_names)
    doe_df["yield_ug_per_uL"] = truth_response(
        coded_doe, coeffs=coeffs, sigma=sigma, rng=rng_doe,
    )
    fit = fit_model(doe_df, "yield_ug_per_uL", factor_cols)
    opt = optimize_response(fit, factor_cols, direction="maximize")
    doe_pick = {
        n: float(opt["coded"][f"{n}_coded"]) for n in factor_names
    }
    doe_pred = float(truth_response(
        pd.DataFrame([doe_pick]), coeffs=coeffs, sigma=0.0,
    )[0])

    caught = [
        term.replace("_coded", "")
        for term in fit.pvalues.index
        if ":" in term and fit.pvalues[term] < 0.05
    ]

    true_best_pt, true_best_y = _grid_search_truth(factor_names)

    return ComparisonReport(
        ofat=StrategyReport(
            name="OFAT",
            n_runs=len(ofat_df),
            predicted_optimum_coded=ofat_pick,
            predicted_yield_at_optimum=ofat_pred,
            true_yield_at_optimum=ofat_pred,  # picks real levels, no model bias
            caught_interactions=[],
            notes=(
                "Picks each factor's best level independently; assumes they "
                "don't interact. Cannot estimate 2-factor interactions."
            ),
        ),
        doe=StrategyReport(
            name="DoE (2ᵏ + centers)",
            n_runs=len(doe_df),
            predicted_optimum_coded=doe_pick,
            predicted_yield_at_optimum=float(opt["predicted"]),
            true_yield_at_optimum=doe_pred,
            caught_interactions=caught,
            notes=(
                "Fits main effects + 2-factor interactions on the full "
                "2ᵏ + center-point design; searches the fitted surface for the "
                "optimum."
            ),
        ),
        true_best_coded=true_best_pt,
        true_best_yield=true_best_y,
    )
