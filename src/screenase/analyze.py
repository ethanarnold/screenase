"""OLS main + 2FI model, effect ranking, Pareto plot."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # noqa: E402

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import t as student_t


@dataclass
class EffectRow:
    term: str
    coef: float
    std_err: float
    t: float
    p: float
    abs_std_effect: float


def fit_model(
    results: pd.DataFrame,
    response_col: str,
    factor_cols: list[str],
):
    """Fit `response ~ (f1 + ... + fk)**2` — main effects + 2-factor interactions."""
    for c in [response_col, *factor_cols]:
        if not c.isidentifier():
            raise ValueError(
                f"Column {c!r} is not a valid Python identifier; "
                "statsmodels formulas require identifier column names."
            )
    formula = f"{response_col} ~ (" + " + ".join(factor_cols) + ")**2"
    model = smf.ols(formula, data=results)
    return model.fit()


def rank_effects(fit) -> list[EffectRow]:
    """Return non-intercept terms sorted by |t| descending."""
    params = fit.params.drop("Intercept", errors="ignore")
    bse = fit.bse.drop("Intercept", errors="ignore")
    tv = fit.tvalues.drop("Intercept", errors="ignore")
    pv = fit.pvalues.drop("Intercept", errors="ignore")
    max_abs_t = float(tv.abs().max()) or 1.0
    rows = [
        EffectRow(
            term=term,
            coef=float(params[term]),
            std_err=float(bse[term]),
            t=float(tv[term]),
            p=float(pv[term]),
            abs_std_effect=float(abs(tv[term]) / max_abs_t),
        )
        for term in params.index
    ]
    rows.sort(key=lambda r: abs(r.t), reverse=True)
    return rows


def pareto_plot(
    effects: list[EffectRow],
    out_png: Path | str,
    alpha: float = 0.05,
    df_resid: int | None = None,
    half_normal: bool = False,
) -> Path:
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    terms = [e.term for e in effects]
    abs_t = [abs(e.t) for e in effects]
    fig, ax = plt.subplots(figsize=(7, max(3.0, 0.4 * len(terms) + 1)))
    y = np.arange(len(terms))
    ax.barh(y, abs_t, color="#4a6fa5")
    ax.set_yticks(y)
    ax.set_yticklabels(terms)
    ax.invert_yaxis()
    ax.set_xlabel("|t|")
    ax.set_title("Pareto of standardized effects")
    if df_resid and df_resid > 0:
        t_crit = float(student_t.ppf(1 - alpha / 2, df_resid))
        ax.axvline(t_crit, color="#c33", linestyle="--",
                   label=f"t_crit (α={alpha}, df={df_resid})")
        ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def surface_plot(
    fit,
    out_png: Path | str,
    *,
    x_term: str | None = None,
    y_term: str | None = None,
    resolution: int = 40,
    levels: int = 12,
) -> Path:
    """2D contour of the fitted response over the two most-significant factors.

    All other factors are held at their coded center (0). By default, picks the
    two main-effect terms with the largest |t| from `fit`; pass `x_term` /
    `y_term` to override.
    """
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)

    params = fit.params.drop("Intercept", errors="ignore")
    tvals = fit.tvalues.drop("Intercept", errors="ignore")
    mains = [t for t in params.index if ":" not in t]
    if len(mains) < 2:
        raise ValueError("surface_plot needs at least 2 main-effect terms in the fit")
    if x_term is None or y_term is None:
        ranked = sorted(mains, key=lambda m: abs(float(tvals.get(m, 0.0))), reverse=True)
        x_term = x_term or ranked[0]
        y_term = y_term or next(m for m in ranked if m != x_term)

    grid = np.linspace(-1.0, 1.0, resolution)
    X, Y = np.meshgrid(grid, grid)
    design_row = {m: 0.0 for m in mains}
    Z = np.zeros_like(X)
    for i in range(resolution):
        for j in range(resolution):
            row = dict(design_row)
            row[x_term] = float(X[i, j])
            row[y_term] = float(Y[i, j])
            Z[i, j] = _eval_fit_at(fit, row)

    fig, ax = plt.subplots(figsize=(6, 5))
    cs = ax.contourf(X, Y, Z, levels=levels, cmap="viridis")
    ax.contour(X, Y, Z, levels=levels, colors="white", linewidths=0.4, alpha=0.5)
    fig.colorbar(cs, ax=ax, label="predicted response")
    ax.set_xlabel(f"{x_term} (coded)")
    ax.set_ylabel(f"{y_term} (coded)")
    ax.set_title(f"Response surface: {x_term} × {y_term}")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def _eval_fit_at(fit, coded_row: dict[str, float]) -> float:
    """Evaluate the fitted polynomial at a coded-factor row (dict)."""
    y = 0.0
    intercept = float(fit.params.get("Intercept", 0.0))
    y += intercept
    for term, coef in fit.params.items():
        if term == "Intercept":
            continue
        parts = term.split(":")
        v = 1.0
        for p in parts:
            v *= float(coded_row.get(p, 0.0))
        y += float(coef) * v
    return y


def curvature_test(
    results: pd.DataFrame,
    response_col: str,
    is_center: pd.Series,
) -> dict[str, float]:
    """Welch t-test comparing center-point mean vs corner-point mean."""
    centers = results.loc[is_center.values, response_col].to_numpy(dtype=float)
    corners = results.loc[~is_center.values, response_col].to_numpy(dtype=float)
    if len(centers) < 2 or len(corners) < 2:
        return {"mean_center": float(centers.mean()) if len(centers) else float("nan"),
                "mean_corner": float(corners.mean()) if len(corners) else float("nan"),
                "t": float("nan"), "p": float("nan")}
    # Guard against zero-variance inputs (e.g. perfect synthetic test data)
    if centers.var(ddof=1) < 1e-12 or corners.var(ddof=1) < 1e-12:
        return {"mean_center": float(centers.mean()),
                "mean_corner": float(corners.mean()),
                "t": float("nan"), "p": float("nan")}
    from scipy.stats import ttest_ind
    tstat, pval = ttest_ind(centers, corners, equal_var=False)
    return {
        "mean_center": float(centers.mean()),
        "mean_corner": float(corners.mean()),
        "t": float(tstat),
        "p": float(pval),
    }


def recommend_followup(
    curv: dict[str, float] | None,
    *,
    alpha: float = 0.05,
) -> dict[str, str] | None:
    """If curvature is significant, suggest a CCD follow-up.

    Returns `None` when there's no curvature signal, otherwise a dict with
    `headline`, `reason`, and a copy-pasteable `cli` command for the next
    experiment.
    """
    if not curv:
        return None
    p = curv.get("p")
    if p is None or (isinstance(p, float) and (p != p)):  # NaN
        return None
    if p >= alpha:
        return None
    direction = "above" if curv["mean_center"] > curv["mean_corner"] else "below"
    return {
        "headline": "Curvature is significant — run a central-composite follow-up",
        "reason": (
            f"Center-point mean is {direction} the corner-point mean "
            f"(Δ = {curv['mean_center'] - curv['mean_corner']:.4g}, p = {p:.4g}). "
            "The main + 2FI model likely underfits; a quadratic model from a "
            "CCD will capture the curvature."
        ),
        "cli": "screenase generate --config <same.yaml> --design ccd --alpha face --out-dir out-ccd/",
    }


def analyze_cli(
    results_path: Path,
    response_col: str,
    out_dir: Path,
) -> dict:
    results = pd.read_csv(results_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    factor_cols = [c for c in results.columns if c.endswith("_coded")]
    if not factor_cols:
        raise ValueError(
            "No `_coded` factor columns found in results. "
            "Re-run `screenase generate`, fill in responses, and pass that file."
        )

    fit = fit_model(results, response_col, factor_cols)
    effects = rank_effects(fit)
    png = pareto_plot(effects, out_dir / "pareto.png", df_resid=int(fit.df_resid))

    curv: dict[str, float] | None = None
    if "is_center" in results.columns:
        curv = curvature_test(results, response_col, results["is_center"].astype(bool))
    followup = recommend_followup(curv)

    report = out_dir / "analysis_report.md"
    lines = [
        f"# Analysis: `{response_col}`\n\n",
        f"- Model: `{fit.model.formula}`\n",
        f"- df_resid: {int(fit.df_resid)}\n",
        f"- R²: {fit.rsquared:.3f}\n",
        f"- Adjusted R²: {fit.rsquared_adj:.3f}\n\n",
        "## Ranked effects\n\n",
        "| Term | Coef | Std Err | t | p |\n",
        "|---|---:|---:|---:|---:|\n",
    ]
    for e in effects:
        lines.append(
            f"| `{e.term}` | {e.coef:.4g} | {e.std_err:.4g} | {e.t:.3f} | {e.p:.4g} |\n"
        )
    if curv:
        lines += [
            "\n## Center-point curvature\n\n",
            f"- Mean at centers: {curv['mean_center']:.4g}\n",
            f"- Mean at corners: {curv['mean_corner']:.4g}\n",
            f"- t = {curv['t']:.3f}, p = {curv['p']:.4g}\n",
        ]
    if followup:
        lines += [
            "\n## Suggested follow-up\n\n",
            f"**{followup['headline']}**\n\n",
            f"{followup['reason']}\n\n",
            f"```bash\n{followup['cli']}\n```\n",
        ]
    # Surface plot if we have ≥2 main effects (standard ≥2-factor screens)
    surface_png: str | None = None
    mains = [t for t in fit.params.index if t != "Intercept" and ":" not in t]
    if len(mains) >= 2:
        surface_png = str(surface_plot(fit, out_dir / "surface.png"))

    report.write_text("".join(lines))
    return {"effects": effects, "pareto_png": str(png), "report_md": str(report),
            "curvature": curv, "r2": float(fit.rsquared),
            "followup": followup, "surface_png": surface_png}


def optimize_response(
    fit,
    factor_cols: list[str],
    *,
    direction: Literal["maximize", "minimize"] = "maximize",
    bounds_coded: tuple[float, float] = (-1.0, 1.0),
) -> dict:
    """Find the coded factor setpoints that optimize the fitted polynomial.

    Returns `{"coded": {factor: value}, "predicted": float, "success": bool}`.
    Uses `scipy.optimize.minimize` with L-BFGS-B; the objective is the fitted
    polynomial (negated if `direction="maximize"`).
    """
    from scipy.optimize import minimize

    sign = -1.0 if direction == "maximize" else 1.0

    def objective(x: np.ndarray) -> float:
        row = {c: float(x[i]) for i, c in enumerate(factor_cols)}
        return sign * _eval_fit_at(fit, row)

    x0 = np.zeros(len(factor_cols))
    result = minimize(
        objective, x0, method="L-BFGS-B",
        bounds=[bounds_coded] * len(factor_cols),
    )
    coded = {c: float(result.x[i]) for i, c in enumerate(factor_cols)}
    predicted = _eval_fit_at(fit, coded)
    return {"coded": coded, "predicted": predicted, "success": bool(result.success)}
