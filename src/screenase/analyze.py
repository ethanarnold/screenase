"""OLS main + 2FI model, effect ranking, Pareto plot."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # noqa: E402

from dataclasses import dataclass
from pathlib import Path

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
    report.write_text("".join(lines))
    return {"effects": effects, "pareto_png": str(png), "report_md": str(report),
            "curvature": curv, "r2": float(fit.rsquared)}
