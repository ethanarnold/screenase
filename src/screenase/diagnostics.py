"""Post-hoc statistical diagnostics: residuals, lack-of-fit, bootstrap CIs,
half-normal plot, model selection, heteroscedasticity tests.

None of these change the ranked-effects output — they layer additional
evidence on top of the OLS fit so a reviewer can decide whether to trust it.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from scipy import stats  # noqa: E402,I001

# ---------- Residual diagnostics ----------

def render_residual_diagnostics(
    fit,
    out_path: Path | str,
    *,
    studentized_flag: float = 3.0,
) -> Path:
    """3-panel residual diagnostic PNG: QQ, residuals-vs-fitted, scale-location.

    Annotates any point with |studentized residual| > `studentized_flag`.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fitted = fit.fittedvalues.to_numpy()
    resid = fit.resid.to_numpy()
    infl = fit.get_influence()
    student = infl.resid_studentized_internal

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    # 1. QQ plot
    sorted_resid = np.sort(resid)
    theoretical = stats.norm.ppf((np.arange(1, len(resid) + 1) - 0.5) / len(resid))
    axes[0].scatter(theoretical, sorted_resid, color="#4a6fa5", s=20)
    lo, hi = theoretical.min(), theoretical.max()
    axes[0].plot([lo, hi], [lo * resid.std() + resid.mean(),
                             hi * resid.std() + resid.mean()],
                 color="#c33", linestyle="--")
    axes[0].set_xlabel("Theoretical quantiles")
    axes[0].set_ylabel("Residuals")
    axes[0].set_title("QQ plot")

    # 2. Residuals vs fitted
    axes[1].scatter(fitted, resid, color="#4a6fa5", s=20)
    axes[1].axhline(0, color="#666", linestyle="-", linewidth=0.5)
    axes[1].set_xlabel("Fitted")
    axes[1].set_ylabel("Residuals")
    axes[1].set_title("Residuals vs fitted")
    for i, s in enumerate(student):
        if abs(s) > studentized_flag:
            axes[1].annotate(f"{i+1}", (fitted[i], resid[i]), fontsize=8, color="#c33")

    # 3. Scale-location — sqrt(|studentized|) vs fitted
    axes[2].scatter(fitted, np.sqrt(np.abs(student)), color="#4a6fa5", s=20)
    axes[2].set_xlabel("Fitted")
    axes[2].set_ylabel(r"√|studentized|")
    axes[2].set_title("Scale-location")

    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def flag_outliers(fit, *, threshold: float = 3.0) -> list[int]:
    """Row indices (0-based) where |studentized residual| > `threshold`."""
    student = fit.get_influence().resid_studentized_internal
    return [i for i, s in enumerate(student) if abs(s) > threshold]


# ---------- Lack-of-fit ----------

@dataclass
class LackOfFit:
    ss_pe: float       # pure-error sum of squares (from replicate centers)
    ss_lof: float      # lack-of-fit sum of squares
    df_pe: int
    df_lof: int
    f_stat: float
    p_value: float


def lack_of_fit_test(
    fit,
    results: pd.DataFrame,
    response_col: str,
    is_center: pd.Series,
) -> LackOfFit | None:
    """Pure-error / lack-of-fit decomposition from center-point replicates.

    Returns `None` when there aren't enough center points (need ≥ 2 replicates).
    F = (SSLOF / dfLOF) / (SSPE / dfPE), large F ⇒ model mis-specified.
    """
    is_center = is_center.astype(bool)
    centers = results.loc[is_center.values, response_col].to_numpy(dtype=float)
    if len(centers) < 2:
        return None

    ss_pe = float(((centers - centers.mean()) ** 2).sum())
    df_pe = len(centers) - 1

    ss_res = float((fit.resid ** 2).sum())
    ss_lof = ss_res - ss_pe
    df_lof = int(fit.df_resid) - df_pe

    if df_lof <= 0 or df_pe <= 0:
        return None
    if ss_pe <= 0 or ss_lof <= 0:
        return LackOfFit(ss_pe=ss_pe, ss_lof=ss_lof, df_pe=df_pe, df_lof=df_lof,
                         f_stat=float("nan"), p_value=float("nan"))
    f = (ss_lof / df_lof) / (ss_pe / df_pe)
    p = float(1 - stats.f.cdf(f, df_lof, df_pe))
    return LackOfFit(ss_pe=ss_pe, ss_lof=ss_lof, df_pe=df_pe, df_lof=df_lof,
                     f_stat=float(f), p_value=p)


# ---------- Bootstrap coefficient CIs ----------

def bootstrap_coefficient_ci(
    results: pd.DataFrame,
    response_col: str,
    factor_cols: list[str],
    *,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> pd.DataFrame:
    """Case-resampling bootstrap CIs on OLS coefficients.

    Returns a DataFrame indexed by term with `coef`, `lo`, `hi`, `p_boot`.
    Useful when N is small and normal-theory CIs are optimistic.
    """
    from screenase.analyze import fit_model

    rng = np.random.default_rng(seed)
    base_fit = fit_model(results, response_col, factor_cols)
    terms = list(base_fit.params.index)
    samples = np.empty((n_boot, len(terms)))
    n = len(results)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot = results.iloc[idx]
        try:
            f = fit_model(boot, response_col, factor_cols)
        except Exception:
            samples[b, :] = np.nan
            continue
        for j, t in enumerate(terms):
            samples[b, j] = float(f.params.get(t, np.nan))

    lo_q, hi_q = alpha / 2, 1 - alpha / 2
    rows = []
    for j, t in enumerate(terms):
        col = samples[:, j]
        col = col[~np.isnan(col)]
        if len(col) == 0:
            rows.append({"term": t, "coef": float(base_fit.params[t]),
                         "lo": float("nan"), "hi": float("nan"),
                         "p_boot": float("nan")})
            continue
        lo = float(np.quantile(col, lo_q))
        hi = float(np.quantile(col, hi_q))
        # 2-sided bootstrap p (fraction crossing zero)
        p_boot = float(min((col <= 0).mean(), (col >= 0).mean()) * 2)
        rows.append({"term": t, "coef": float(base_fit.params[t]),
                     "lo": lo, "hi": hi, "p_boot": p_boot})
    return pd.DataFrame(rows).set_index("term")


# ---------- Half-normal plot ----------

def half_normal_plot(effects, out_path: Path | str) -> Path:
    """|standardized effect| vs half-normal quantiles — unreplicated-design staple.

    Points that lie on the line are noise; outliers upward are real effects.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    n = len(effects)
    abs_eff = np.sort(np.abs([e.t for e in effects]))
    # Half-normal quantile: Phi^-1( (i - 0.5) / (2n) + 0.5 )
    probs = (np.arange(1, n + 1) - 0.5) / (2 * n) + 0.5
    quantiles = stats.norm.ppf(probs)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(quantiles, abs_eff, color="#4a6fa5", s=24)
    # Label the top points
    sorted_effects = sorted(effects, key=lambda e: abs(e.t), reverse=True)[:3]
    top_terms = {e.term for e in sorted_effects}
    for e, q, a in zip(sorted(effects, key=lambda x: abs(x.t)), quantiles, abs_eff,
                       strict=True):
        if e.term in top_terms:
            ax.annotate(e.term, (q, a), fontsize=8, xytext=(4, -2),
                        textcoords="offset points")
    # Reference line through origin with slope = 1 (in std-effect units)
    ax.plot([0, quantiles.max()], [0, quantiles.max() * abs_eff.std()],
            color="#c33", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Half-normal quantile")
    ax.set_ylabel("|standardized effect (t)|")
    ax.set_title("Half-normal effects plot")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


# ---------- Model selection ----------

@dataclass
class ModelComparison:
    name: str
    formula: str
    aicc: float
    bic: float
    adj_r2: float
    df_resid: int


def _aicc(fit) -> float:
    k = int(fit.df_model) + 1  # +1 for the intercept
    n = int(fit.nobs)
    if n - k - 1 <= 0:
        return float("nan")
    return float(fit.aic + 2 * k * (k + 1) / (n - k - 1))


def compare_models(
    results: pd.DataFrame,
    response_col: str,
    factor_cols: list[str],
    *,
    include_quadratic: bool | None = None,
) -> list[ModelComparison]:
    """Fit and compare main-only, main+2FI, and (if feasible) quadratic models.

    Quadratic terms require at least 3 distinct coded levels per factor; by
    default this is detected automatically (presence of CCD axial points).
    Models are ranked by AICc; returns the list sorted ascending (best first).
    """
    joined = " + ".join(factor_cols)
    specs = [
        ("main-only", f"{response_col} ~ {joined}"),
        ("main+2FI", f"{response_col} ~ ({joined})**2"),
    ]
    if include_quadratic is None:
        # Heuristic: quadratic makes sense if any factor has ≥ 3 coded levels
        nlevels = [results[c].nunique() for c in factor_cols]
        include_quadratic = any(n >= 3 for n in nlevels)
    if include_quadratic:
        quad = " + ".join(f"I({c}**2)" for c in factor_cols)
        specs.append(("quadratic", f"{response_col} ~ ({joined})**2 + {quad}"))

    comparisons: list[ModelComparison] = []
    for name, formula in specs:
        try:
            fit = smf.ols(formula, data=results).fit()
        except Exception:
            continue
        comparisons.append(ModelComparison(
            name=name, formula=formula, aicc=_aicc(fit),
            bic=float(fit.bic), adj_r2=float(fit.rsquared_adj),
            df_resid=int(fit.df_resid),
        ))
    comparisons.sort(key=lambda c: c.aicc)
    return comparisons


# ---------- Heteroscedasticity ----------

def heteroscedasticity_tests(fit) -> dict[str, float]:
    """Breusch-Pagan + White statistics. Low p ⇒ variance depends on predictors."""
    from statsmodels.stats.diagnostic import het_breuschpagan, het_white

    exog = fit.model.exog
    resid = fit.resid
    bp_lm, bp_p, bp_f, bp_fp = het_breuschpagan(resid, exog)
    try:
        w_lm, w_p, _, _ = het_white(resid, exog)
    except Exception:
        w_lm = w_p = float("nan")
    return {
        "breusch_pagan_lm": float(bp_lm),
        "breusch_pagan_p": float(bp_p),
        "white_lm": float(w_lm),
        "white_p": float(w_p),
    }
