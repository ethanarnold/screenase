"""Auto-narrated plain-English summary of an OLS analysis.

Takes a fit + ranked effects + curvature dict and emits a single-paragraph
summary that reads like a scientist wrote it. Used by the analyze tab in
Streamlit and appended to `analysis_report.md`.
"""

from __future__ import annotations

from screenase.analyze import EffectRow


def _sign(coef: float) -> str:
    return "positive" if coef > 0 else "negative"


def _clean_term(term: str) -> str:
    """Strip `_coded` suffix + render interactions as `A × B`."""
    parts = term.split(":")
    return " × ".join(p.removesuffix("_coded") for p in parts)


def narrate_analysis(
    effects: list[EffectRow],
    *,
    r_squared: float,
    curvature: dict[str, float] | None = None,
    predicted_optimum: float | None = None,
    alpha: float = 0.05,
) -> str:
    """One-paragraph narration of the fit for non-statisticians."""
    if not effects:
        return "No effects to narrate — the fit returned no coefficients."

    sig = [e for e in effects if e.p < alpha]
    strongest = effects[0]

    parts: list[str] = []
    if sig:
        if len(sig) == 1:
            e = sig[0]
            parts.append(
                f"The screen surfaced one significant driver: "
                f"`{_clean_term(e.term)}` ({_sign(e.coef)}, p = {e.p:.3g})."
            )
        else:
            names = ", ".join(f"`{_clean_term(e.term)}`" for e in sig[:3])
            parts.append(
                f"The screen surfaced {len(sig)} significant effects at α = {alpha}; "
                f"the strongest were {names}."
            )
        parts.append(
            f"`{_clean_term(strongest.term)}` had the {_sign(strongest.coef)} effect "
            f"on the response (t = {strongest.t:.2f}, coef = {strongest.coef:+.3g})."
        )
    else:
        parts.append(
            f"No effect cleared α = {alpha}; the strongest candidate was "
            f"`{_clean_term(strongest.term)}` (p = {strongest.p:.3g}) but its "
            f"signal is within noise at this sample size."
        )

    parts.append(f"Overall model R² is {r_squared:.2f}.")

    if predicted_optimum is not None:
        parts.append(
            f"At the predicted optimum inside the explored range, the response "
            f"is estimated at {predicted_optimum:.3g}."
        )

    if curvature and curvature.get("p") == curvature.get("p"):  # not NaN
        p_curv = curvature.get("p")
        if p_curv is not None and p_curv < alpha:
            parts.append(
                f"Center-point curvature is significant (p = {p_curv:.3g}) — "
                "a central-composite follow-up is warranted to fit the "
                "quadratic surface."
            )

    return " ".join(parts)
