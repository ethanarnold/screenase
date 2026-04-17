"""Streamlit frontend for Screenase — thin UI over the `screenase` package.

No business logic lives here. All computation delegates to the package.
Deploys to Streamlit Cloud: point at this file, free tier is sufficient.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from screenase import __version__
from screenase.analyze import fit_model, rank_effects
from screenase.bench_sheet import build_context, render_bench_sheet
from screenase.config import Factor, ReactionConfig, Stock, config_hash
from screenase.design import build_design
from screenase.volumes import compute_volumes, validate_volumes


def build_default_config() -> ReactionConfig:
    return ReactionConfig(
        reaction_volume_uL=20.0,
        dna_template_uL=3.2,
        center_points=3,
        seed=42,
        factors=[
            Factor(name="NTPs_mM_each", low=5, high=10, unit="mM", reagent="NTPs"),
            Factor(name="MgCl2_mM", low=30, high=60, unit="mM", reagent="MgCl2"),
            Factor(name="T7_uL", low=0.2, high=1.2, unit="uL", reagent="T7", dosing="volume"),
            Factor(name="PEG8000_pct", low=0, high=2, unit="%", reagent="PEG8000"),
        ],
        stocks={
            "NTPs": Stock(name="NTP Mix (each)", concentration=100, unit="mM"),
            "MgCl2": Stock(name="MgCl2", concentration=1000, unit="mM"),
            "T7": Stock(name="T7 Polymerase", concentration=3, unit="mg/mL"),
            "PEG8000": Stock(name="PEG8000", concentration=50, unit="%"),
            "Buffer": Stock(name="Reaction Buffer", concentration=20, unit="X"),
        },
        fixed_reagents={"Buffer": 1.0},
    )


def generate_from_ui(cfg: ReactionConfig) -> dict:
    """Pure helper — callable from `test_streamlit_smoke.py`."""
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    ws = validate_volumes(v, cfg)
    run_id = datetime.now(UTC).strftime("run-%Y%m%d-%H%M%S")
    ctx = build_context(
        v, d["is_center"], cfg,
        run_id=run_id,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        lib_version=__version__,
        config_hash=config_hash(cfg),
        warnings=ws,
    )
    html = render_bench_sheet(ctx)
    factor_cols = [f.name for f in cfg.factors]
    coded_cols = [c for c in d.columns if c.endswith("_coded")]
    csv_bytes = d[factor_cols].to_csv().encode("utf-8")
    coded_bytes = d[factor_cols + coded_cols + ["is_center"]].to_csv().encode("utf-8")
    return {
        "design": d,
        "volumes": v,
        "html": html,
        "csv": csv_bytes,
        "coded_csv": coded_bytes,
        "warnings": ws,
    }


def _factor_editor(cfg: ReactionConfig) -> ReactionConfig:
    st.sidebar.header("Factors")
    new_factors: list[Factor] = []
    for i, f in enumerate(cfg.factors):
        with st.sidebar.expander(f.name, expanded=False):
            low = st.number_input(f"{f.name} low", value=float(f.low), key=f"lo{i}")
            high = st.number_input(f"{f.name} high", value=float(f.high), key=f"hi{i}")
        new_factors.append(f.model_copy(update={"low": low, "high": high}))
    st.sidebar.header("Design")
    vol = st.sidebar.number_input("Reaction volume (µL)",
                                  value=float(cfg.reaction_volume_uL), min_value=1.0)
    cps = st.sidebar.number_input("Center points", value=int(cfg.center_points),
                                  min_value=0, max_value=10, step=1)
    seed = st.sidebar.number_input("Seed", value=int(cfg.seed), step=1)
    return cfg.model_copy(update={
        "factors": new_factors,
        "reaction_volume_uL": float(vol),
        "center_points": int(cps),
        "seed": int(seed),
    })


def main() -> None:
    st.set_page_config(page_title="Screenase — IVT DoE", layout="wide",
                       page_icon="🧪")
    st.title("Screenase — IVT DoE Planner")
    st.caption(f"v{__version__}  •  2^k full factorial + center points  •  bench-ready HTML")

    base = build_default_config()
    cfg = _factor_editor(base)

    tab_gen, tab_analyze = st.tabs(["Generate screen", "Analyze results"])

    with tab_gen:
        if st.button("Generate screen", type="primary") or "artifacts" not in st.session_state:
            st.session_state["artifacts"] = generate_from_ui(cfg)
        art = st.session_state["artifacts"]
        col_l, col_r = st.columns([1, 1])
        with col_l:
            st.subheader("Design")
            st.dataframe(art["design"], use_container_width=True, height=520)
            if art["warnings"]:
                st.warning(f"{len(art['warnings'])} volume warning(s) — see bench sheet")
        with col_r:
            st.subheader("Bench sheet preview")
            st.components.v1.html(art["html"], height=520, scrolling=True)
        st.download_button("Download screen CSV", art["csv"],
                           file_name="ivt_screen.csv", mime="text/csv")
        st.download_button("Download coded CSV (for analyze)", art["coded_csv"],
                           file_name="ivt_screen_coded.csv", mime="text/csv")
        st.download_button("Download bench sheet HTML", art["html"],
                           file_name="ivt_bench_sheet.html", mime="text/html")

    with tab_analyze:
        uploaded = st.file_uploader("Completed results CSV (with `_coded` columns + response)",
                                    type=["csv"])
        if uploaded is None:
            st.info("Upload a filled-in coded CSV to see the Pareto + ranked effects.")
            return
        results = pd.read_csv(uploaded)
        factor_cols = [c for c in results.columns if c.endswith("_coded")]
        factor_raw = {c.removesuffix("_coded") for c in factor_cols}
        candidates = [c for c in results.columns
                      if c not in ("Run",) and not c.endswith("_coded")
                      and c != "is_center" and c not in factor_raw]
        if not candidates:
            st.error("No response column found — CSV has only factors.")
            return
        if len(candidates) == 1:
            response = candidates[0]
            st.caption(f"Response: **{response}** (only candidate)")
        else:
            response = st.selectbox("Response column", candidates)
        if st.button("Analyze", type="primary") and response and factor_cols:
            fit = fit_model(results, response, factor_cols)
            effects = rank_effects(fit)
            st.metric("R²", f"{fit.rsquared:.3f}")
            st.metric("df_resid", int(fit.df_resid))
            eff_df = pd.DataFrame(
                [[e.term, e.coef, e.std_err, e.t, e.p] for e in effects],
                columns=["term", "coef", "std_err", "t", "p"],
            )
            st.dataframe(eff_df, use_container_width=True)
            buf = io.BytesIO()
            from matplotlib.figure import Figure
            fig = Figure(figsize=(7, max(3.0, 0.4 * len(effects) + 1)))
            ax = fig.subplots()
            ax.barh(range(len(effects)), [abs(e.t) for e in effects], color="#4a6fa5")
            ax.set_yticks(range(len(effects)))
            ax.set_yticklabels([e.term for e in effects])
            ax.invert_yaxis()
            ax.set_xlabel("|t|")
            ax.set_title("Pareto of standardized effects")
            fig.tight_layout()
            fig.savefig(buf, format="png", dpi=120)
            buf.seek(0)
            st.image(buf)


if __name__ == "__main__":
    main()
