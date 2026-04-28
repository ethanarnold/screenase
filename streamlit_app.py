"""Streamlit frontend for Screenase — thin UI over the `screenase` package.

No business logic lives here. All computation delegates to the package.
Deploys to Streamlit Cloud: point at this file, free tier is sufficient.
"""

from __future__ import annotations

import io
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from screenase import __version__
from screenase.analyze import (
    curvature_test,
    fit_model,
    optimize_response,
    rank_effects,
    recommend_followup,
    surface_plot,
)
from screenase.bench_sheet import build_context, render_bench_sheet
from screenase.benchling.inventory import compute_reagent_consumption
from screenase.config import Factor, ReactionConfig, Stock, config_hash
from screenase.design import build_ccd, build_design, build_pb
from screenase.narrate import narrate_analysis
from screenase.plate import assign_plate, render_plate_map_html
from screenase.share import decode_config, encode_config
from screenase.tutorial import run_ofat_vs_doe, truth_response
from screenase.volumes import compute_volumes, validate_volumes

REPO_URL = "https://github.com/ethanarnold/screenase"
DEMO_RESULTS_PATH = Path(__file__).parent / "examples" / "results_simulated.csv"

POS_COLOR = "#4a6fa5"
NEG_COLOR = "#c05454"

# Streamlit's native dual-theme support (`.streamlit/config.toml` with
# [theme.light] + [theme.dark]) drives dark mode — the user toggles via the
# three-dot menu → Settings → Choose app theme. glide-data-grid reads that
# config at page load, which is the only way to get dark dataframes.
#
# The only CSS we still inject ourselves is a white backing under iframes:
# the plate-map HTML has no body bg of its own, so on a dark Streamlit page
# its light-gray cell borders would render against a dark frame.
_IFRAME_SAFETY_CSS = """
<style>
.stApp iframe { background: #ffffff !important; }
[data-testid="stDeployButton"] { display: none !important; }
.stApp [data-testid="stMainBlockContainer"] { padding-top: 2rem; }

/* Swap Streamlit's default sidebar toggle (a Material Symbols ligature
   `keyboard_double_arrow_left/right` that renders as << / >>) for
   sidekickicons' sidebar-left outline icon — https://sidekickicons.com/.
   We hide the ligature text via font-size:0 on the icon span, then paint
   the sidekickicons glyph on a ::before using currentColor so it inherits
   the span's theme-driven color. */
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
  font-size: 0 !important;
  line-height: 0 !important;
  width: 1.25rem;
  height: 1.25rem;
  display: inline-block;
  position: relative;
}
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"]::before,
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"]::before {
  content: "";
  position: absolute;
  inset: 0;
  background-color: currentColor;
  -webkit-mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'><path d='M9 4.5v15M4.125 19.5h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125z'/></svg>") no-repeat center / contain;
          mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'><path d='M9 4.5v15M4.125 19.5h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125z'/></svg>") no-repeat center / contain;
}

.sn-label-with-info {
  font-size: 0.875rem; line-height: 1.6; margin-bottom: 0.25rem;
}
.sn-info-icon {
  position: relative; cursor: help; color: #888;
  display: inline-flex; align-items: center; vertical-align: middle;
  margin-left: 0.15rem; line-height: 1;
}
.sn-info-icon::after {
  content: attr(data-tooltip);
  position: absolute; bottom: calc(100% + 6px);
  left: 50%; transform: translateX(-50%);
  background: #262730; color: #fafafa;
  padding: 0.4rem 0.6rem; border-radius: 0.3rem;
  font-size: 0.78rem; font-weight: 400;
  white-space: normal; width: max-content; max-width: 14rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.18);
  opacity: 0; pointer-events: none; transition: opacity 120ms;
  z-index: 1000;
}
.sn-info-icon:hover::after,
.sn-info-icon:focus::after { opacity: 1; }
</style>
"""


def _inject_safety_css() -> None:
    """Inject the minimal CSS that's not covered by Streamlit's theme config."""
    st.markdown(_IFRAME_SAFETY_CSS, unsafe_allow_html=True)


def _config_from_url() -> ReactionConfig | None:
    """If ?cfg=… is present in the URL, decode it into a ReactionConfig."""
    try:
        params = st.query_params
    except AttributeError:
        return None
    blob = params.get("cfg")
    if not blob:
        return None
    if isinstance(blob, list):
        blob = blob[0]
    try:
        return decode_config(blob)
    except Exception:
        return None


def build_default_config() -> ReactionConfig:
    return ReactionConfig(
        reaction_volume_uL=20.0,
        dna_template_uL=3.2,
        center_points=3,
        seed=42,
        factors=[
            Factor(name="NTPs_mM_each", low=5, high=10, unit="mM",
                   reagent="NTPs", display="NTPs, each (mM)"),
            Factor(name="MgCl2_mM", low=30, high=60, unit="mM",
                   reagent="MgCl2", display="MgCl\u2082 (mM)"),
            Factor(name="T7_uL", low=0.2, high=1.2, unit="uL",
                   reagent="T7", dosing="volume", display="T7 (µL)"),
            Factor(name="PEG8000_pct", low=0, high=2, unit="%",
                   reagent="PEG8000", display="PEG8000 (%)"),
        ],
        stocks={
            "NTPs": Stock(name="NTP Mix (each)", concentration=100, unit="mM"),
            "MgCl2": Stock(name="MgCl\u2082", concentration=1000, unit="mM"),
            "T7": Stock(name="T7 Polymerase", concentration=3, unit="mg/mL"),
            "PEG8000": Stock(name="PEG8000", concentration=50, unit="%"),
            "Buffer": Stock(name="Reaction Buffer", concentration=20, unit="X"),
        },
        fixed_reagents={"Buffer": 1.0},
    )


def generate_from_ui(
    cfg: ReactionConfig,
    min_pipet_uL: float = 0.1,
    *,
    design_kind: str = "full",
    alpha: str = "face",
    plate: str | None = None,
    plate_layout: str = "column-major",
) -> dict:
    """Pure helper — callable from `test_streamlit_smoke.py`."""
    if design_kind == "ccd":
        try:
            alpha_val: float | str = float(alpha)
        except (TypeError, ValueError):
            alpha_val = alpha
        d = build_ccd(cfg, alpha=alpha_val)  # type: ignore[arg-type]
    elif design_kind == "pb":
        d = build_pb(cfg, runs=12)
    else:
        d = build_design(cfg)
    v = compute_volumes(d, cfg)
    ws = validate_volumes(v, cfg, min_pipet_uL=min_pipet_uL)

    plate_html: str | None = None
    plate_df: pd.DataFrame | None = None
    if plate in ("96", "384"):
        plate_df = assign_plate(
            d, plate=plate, layout=plate_layout,  # type: ignore[arg-type]
            seed=cfg.seed if plate_layout == "randomized" else None,
        )
        plate_html = render_plate_map_html(plate_df, plate=plate)  # type: ignore[arg-type]

    run_id = datetime.now(UTC).strftime("run-%Y%m%d-%H%M%S")
    ctx = build_context(
        v, d["is_center"], cfg,
        run_id=run_id,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        lib_version=__version__,
        config_hash=config_hash(cfg),
        warnings=ws,
        plate_map_html=plate_html,
    )
    html = render_bench_sheet(ctx)
    factor_cols = [f.name for f in cfg.factors]
    coded_cols = [c for c in d.columns if c.endswith("_coded")]
    extra_cols = [c for c in ("is_center", "design_kind") if c in d.columns]
    csv_bytes = d[factor_cols].to_csv().encode("utf-8")
    coded_bytes = d[factor_cols + coded_cols + extra_cols].to_csv().encode("utf-8")

    consumption = compute_reagent_consumption(v, cfg, excess=1.2)
    return {
        "design": d,
        "volumes": v,
        "html": html,
        "csv": csv_bytes,
        "coded_csv": coded_bytes,
        "warnings": ws,
        "plate_df": plate_df,
        "plate_map_html": plate_html,
        "plate": plate,
        "design_kind": design_kind,
        "consumption": consumption,
    }


# ---------- sidebar ----------

def _sidebar(default_cfg: ReactionConfig) -> tuple[ReactionConfig, float, dict]:
    if "expand_all" not in st.session_state:
        st.session_state["expand_all"] = False

    with st.sidebar:
        st.markdown("### Reaction Parameters")
        c1, c2 = st.columns(2)
        vol = c1.number_input(
            "Volume (µL)", value=float(default_cfg.reaction_volume_uL),
            min_value=1.0, step=1.0, key="vol",
        )
        dna = c2.number_input(
            "DNA (µL)", value=float(default_cfg.dna_template_uL),
            min_value=0.0, step=0.1, key="dna",
        )
        c1, c2 = st.columns(2)
        cps = c1.number_input(
            "Center pts", min_value=0, max_value=10,
            value=int(default_cfg.center_points), step=1, key="cps",
        )
        with c2:
            st.markdown(
                '<div class="sn-label-with-info">'
                '<span>Seed</span>'
                '<span class="sn-info-icon" tabindex="0" '
                'data-tooltip="Randomizes run order. Same seed yields identical output.">'
                '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
                'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                '<circle cx="12" cy="12" r="10"/>'
                '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>'
                '<line x1="12" y1="17" x2="12.01" y2="17"/>'
                '</svg></span>'
                '</div>',
                unsafe_allow_html=True,
            )
            seed = st.number_input(
                "Seed", value=int(default_cfg.seed), step=1, key="seed",
                label_visibility="collapsed",
            )

        ec1, ec2 = st.columns(2)
        if ec1.button("Expand all", width="stretch", key="expand_all_btn"):
            st.session_state["expand_all"] = True
            st.rerun()
        if ec2.button("Collapse all", width="stretch", key="collapse_all_btn"):
            st.session_state["expand_all"] = False
            st.rerun()

        expanded = st.session_state["expand_all"]

        with st.expander("Design Type", expanded=expanded):
            design_kind = st.radio(
                "Design type",
                options=["full", "ccd", "pb"],
                index=0,
                format_func=lambda k: {
                    "full": "Full factorial (2ᵏ + centers)",
                    "ccd": "Central-composite (CCD follow-up)",
                    "pb": "Plackett-Burman (screening, k > 5)",
                }[k],
                key="design_kind",
                horizontal=False,
                label_visibility="collapsed",
            )
            alpha = "face"
            if design_kind == "ccd":
                alpha = st.select_slider(
                    "Axial α",
                    options=["face", "rotatable"],
                    value="face",
                    help=(
                        "`face` (α=1) stays within low/high; `rotatable` extends "
                        "axial setpoints beyond the range — use only if your "
                        "stocks allow the wider span."
                    ),
                    key="ccd_alpha",
                )

        with st.expander("Plate Layout", expanded=expanded):
            plate_choice = st.radio(
                "Plate",
                options=["none", "96", "384"],
                horizontal=True,
                index=1,
                key="plate_choice",
                label_visibility="collapsed",
            )
            plate_layout = "column-major"
            if plate_choice != "none":
                plate_layout = st.radio(
                    "Fill order",
                    options=["column-major", "row-major", "randomized"],
                    index=0,
                    horizontal=True,
                    key="plate_layout",
                )

        with st.expander("High / Low Setpoints", expanded=expanded):
            factor_rows = [
                {
                    "factor": f.display or f.name,
                    "low": float(f.low),
                    "high": float(f.high),
                }
                for f in default_cfg.factors
            ]
            edited = st.data_editor(
                pd.DataFrame(factor_rows),
                hide_index=True,
                disabled=["factor"],
                key="factors_editor",
                column_config={
                    "factor": st.column_config.TextColumn("Factor", width="medium"),
                    "low": st.column_config.NumberColumn("Low", format="%.3g"),
                    "high": st.column_config.NumberColumn("High", format="%.3g"),
                },
            )
        new_factors: list[Factor] = []
        for orig, row in zip(default_cfg.factors, edited.itertuples(index=False),
                             strict=True):
            new_factors.append(orig.model_copy(update={
                "low": float(row.low), "high": float(row.high),
            }))

        with st.expander("Stock concentrations", expanded=expanded):
            stock_rows = [
                {
                    "key": k,
                    "name": s.name,
                    "concentration": float(s.concentration),
                    "unit": s.unit,
                }
                for k, s in default_cfg.stocks.items()
            ]
            stock_edit = st.data_editor(
                pd.DataFrame(stock_rows),
                hide_index=True,
                disabled=["key", "name", "unit"],
                key="stocks_editor",
                column_config={
                    "key": st.column_config.TextColumn("Key", width="small"),
                    "name": st.column_config.TextColumn("Name"),
                    "concentration": st.column_config.NumberColumn("Conc.", format="%.3g"),
                    "unit": st.column_config.TextColumn("Unit", width="small"),
                },
            )
            new_stocks = {
                row.key: default_cfg.stocks[row.key].model_copy(update={
                    "concentration": float(row.concentration),
                })
                for row in stock_edit.itertuples(index=False)
            }

        with st.expander("Fixed reagents", expanded=expanded):
            st.caption("Reagents with a constant volume per run (not swept).")
            fixed_rows = [
                {"reagent": k, "volume_uL": float(v)}
                for k, v in default_cfg.fixed_reagents.items()
            ]
            fixed_edit = st.data_editor(
                pd.DataFrame(fixed_rows),
                hide_index=True,
                disabled=["reagent"],
                key="fixed_editor",
                column_config={
                    "reagent": st.column_config.TextColumn("Reagent"),
                    "volume_uL": st.column_config.NumberColumn(
                        "Volume (µL)", min_value=0.0, format="%.3g",
                    ),
                },
            )
            new_fixed = {
                row.reagent: float(row.volume_uL)
                for row in fixed_edit.itertuples(index=False)
            }

        with st.expander("Advanced", expanded=expanded):
            min_pipet = st.number_input(
                "Min pipetting volume (µL)",
                value=0.1, min_value=0.0, step=0.1, key="min_pipet",
                help="Volumes below this threshold emit a warning on the bench sheet.",
            )

        st.divider()
        if st.button("Reset to defaults", width="stretch"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

        new_cfg = default_cfg.model_copy(update={
            "factors": new_factors,
            "stocks": new_stocks,
            "fixed_reagents": new_fixed,
            "reaction_volume_uL": float(vol),
            "dna_template_uL": float(dna),
            "center_points": int(cps),
            "seed": int(seed),
        })
        opts = {
            "design_kind": design_kind,
            "alpha": alpha,
            "plate": None if plate_choice == "none" else plate_choice,
            "plate_layout": plate_layout,
        }
        return new_cfg, float(min_pipet), opts


# ---------- tabs ----------

def _render_generate_tab(
    cfg: ReactionConfig,
    min_pipet_uL: float,
    opts: dict,
) -> None:
    cache_key = "|".join([
        config_hash(cfg), str(min_pipet_uL),
        opts["design_kind"], str(opts["alpha"]),
        str(opts["plate"]), opts["plate_layout"],
    ])
    if st.session_state.get("artifacts_hash") != cache_key:
        try:
            st.session_state["artifacts"] = generate_from_ui(
                cfg, min_pipet_uL=min_pipet_uL,
                design_kind=opts["design_kind"],
                alpha=opts["alpha"],
                plate=opts["plate"],
                plate_layout=opts["plate_layout"],
            )
            st.session_state["artifacts_hash"] = cache_key
            st.session_state["artifacts_error"] = None
        except Exception as exc:  # validation failure, impossible doses, etc.
            st.session_state["artifacts_error"] = str(exc)

    if st.session_state.get("artifacts_error"):
        st.error(f"Cannot generate design: {st.session_state['artifacts_error']}")
        return

    art = st.session_state["artifacts"]
    design = art["design"]
    n_runs = len(design)
    n_corners = int((~design["is_center"]).sum())
    n_centers = int(design["is_center"].sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Runs", n_runs)
    k2.metric("Factors", len(cfg.factors))
    if opts["design_kind"] == "ccd":
        n_axial = int((design.get("design_kind") == "axial").sum()) if "design_kind" in design.columns else 0
        n_factorial = int((design.get("design_kind") == "factorial").sum()) if "design_kind" in design.columns else 0
        k3.metric("Factorial / axial / centers", f"{n_factorial} / {n_axial} / {n_centers}")
    else:
        k3.metric("Corners / centers", f"{n_corners} / {n_centers}")
    k4.metric("Config hash", config_hash(cfg))

    if art["warnings"]:
        with st.expander(
            f"{len(art['warnings'])} volume warning(s) — click to review",
            expanded=False,
            icon=":material/warning:",
        ):
            wdf = pd.DataFrame([asdict(w) for w in art["warnings"]])
            st.dataframe(wdf, hide_index=True)
            st.caption(
                "These are also rendered inline on the bench sheet so the operator "
                "sees them at the bench."
            )

    st.markdown("#### Design")
    display_cols = [f.name for f in cfg.factors] + ["is_center"]
    st.dataframe(
        design[display_cols],
        height=540,
        width="stretch",
        column_config={
            "is_center": st.column_config.CheckboxColumn(
                "center?", help="Center-point replicate",
            ),
        },
    )

    with st.expander("Bench sheet preview", expanded=False):
        # Render inside a white-background iframe so the template's black
        # text stays legible regardless of the surrounding theme.
        st.components.v1.html(art["html"], height=540, scrolling=True)

    if art.get("plate_df") is not None:
        st.markdown("#### Plate layout")
        n_plates = int(art["plate_df"]["plate"].max())
        st.caption(
            f"{opts['plate']}-well plate · {opts['plate_layout']} · "
            f"{n_plates} plate(s)"
        )
        rows_per_plate = 8 if opts["plate"] == "96" else 16
        plate_map_height = n_plates * (40 + rows_per_plate * 27) + 20
        st.components.v1.html(
            art["plate_map_html"], height=plate_map_height, scrolling=True,
        )

    if art.get("consumption"):
        with st.expander("Inventory consumption (Benchling-shaped)", expanded=False):
            cons = art["consumption"]
            cdf = pd.DataFrame(
                [(k, v) for k, v in cons.items()],
                columns=["reagent", "volume_uL"],
            ).sort_values("volume_uL", ascending=False)
            st.dataframe(
                cdf, hide_index=True,
                column_config={
                    "volume_uL": st.column_config.NumberColumn(
                        "µL (incl. 20% excess)", format="%.2f",
                    ),
                },
            )
            st.caption(
                "These totals shape a Benchling inventory decrement payload via "
                "`screenase.benchling.inventory.build_inventory_decrement_payload`. "
                "On a real tenant, this would PATCH container volumes for each lot."
            )

    st.markdown("#### Share")
    blob = encode_config(cfg)
    st.code(f"?cfg={blob}", language="text")
    st.caption(
        "Append this query string to the app URL to reproduce the current "
        "sidebar state — copy the full URL out of your browser bar after "
        "visiting it to share the link."
    )

    st.markdown("#### Downloads")
    d1, d2, d3 = st.columns(3)
    d1.download_button(
        "Screen CSV (real values)", art["csv"],
        file_name="ivt_screen.csv", mime="text/csv",
        width="stretch",
    )
    d2.download_button(
        "Coded CSV (for analyze)", art["coded_csv"],
        file_name="ivt_screen_coded.csv", mime="text/csv",
        width="stretch",
    )
    d3.download_button(
        "Bench sheet (HTML)", art["html"],
        file_name="ivt_bench_sheet.html", mime="text/html",
        width="stretch",
    )
    if art.get("plate_df") is not None:
        plate_csv_bytes = (
            art["plate_df"][["plate", "well", "row_letter", "col_number", "is_center"]]
            .to_csv().encode("utf-8")
        )
        st.download_button(
            "Plate layout CSV", plate_csv_bytes,
            file_name="plate_layout.csv", mime="text/csv",
        )


def _render_analyze_tab() -> None:
    demo_available = DEMO_RESULTS_PATH.exists()
    st.markdown(
        "Upload a filled-in coded CSV (download it from the **Generate** tab, fill "
        "in the response column, then upload here) — or load the bundled demo "
        "results to see the full analysis path end-to-end."
    )

    source = st.radio(
        "Results source",
        options=["Upload CSV", "Demo results"] if demo_available else ["Upload CSV"],
        horizontal=True,
        label_visibility="collapsed",
    )

    results: pd.DataFrame | None = None
    if source == "Upload CSV":
        uploaded = st.file_uploader(
            "Completed results CSV (must include `_coded` columns and a response column)",
            type=["csv"],
        )
        if uploaded is not None:
            results = pd.read_csv(uploaded)
    else:
        results = pd.read_csv(DEMO_RESULTS_PATH)
        st.caption(
            f"Loaded `{DEMO_RESULTS_PATH.name}` — "
            f"{len(results)} rows from the seeded default design."
        )

    if results is None:
        st.info(
            "Upload a CSV to see the Pareto + ranked effects.",
            icon=":material/upload_file:",
        )
        return

    factor_cols = [c for c in results.columns if c.endswith("_coded")]
    factor_raw = {c.removesuffix("_coded") for c in factor_cols}
    candidates = [
        c for c in results.columns
        if c not in ("Run",)
        and not c.endswith("_coded")
        and c != "is_center"
        and c not in factor_raw
    ]
    if not factor_cols:
        st.error(
            "No `_coded` factor columns found. Make sure you're uploading the "
            "coded CSV from the Generate tab (not the real-values CSV)."
        )
        return
    if not candidates:
        st.error("No response column found — CSV has only factors.")
        return

    response = (
        candidates[0] if len(candidates) == 1
        else st.selectbox("Response column", candidates)
    )
    if len(candidates) == 1:
        st.caption(f"Response: **{response}**  _(only candidate)_")

    fit = fit_model(results, response, factor_cols)
    effects = rank_effects(fit)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("R²", f"{fit.rsquared:.3f}")
    k2.metric("Adj. R²", f"{fit.rsquared_adj:.3f}")
    k3.metric("df residual", int(fit.df_resid))
    k4.metric("N", len(results))

    sig_effects = [e for e in effects if e.p < 0.05]
    if sig_effects:
        top = ", ".join(f"`{e.term}`" for e in sig_effects[:3])
        st.success(
            f"**{len(sig_effects)} effect(s) significant at α=0.05.** Top drivers: {top}."
        )
    else:
        st.info("No effects significant at α=0.05 — noise dominates at this N.")

    narration = narrate_analysis(
        effects, r_squared=float(fit.rsquared),
        curvature=(
            None if "is_center" not in results.columns
            else curvature_test(results, response, results["is_center"].astype(bool))
        ),
    )
    st.markdown(f"##### Summary\n\n{narration}")

    curv: dict[str, float] | None = None
    if "is_center" in results.columns:
        curv = curvature_test(results, response, results["is_center"].astype(bool))
    rec = recommend_followup(curv)
    if rec:
        st.warning(
            f"**{rec['headline']}** — {rec['reason']}\n\n"
            f"```bash\n{rec['cli']}\n```",
            icon=":material/science:",
        )

    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.markdown("##### Pareto of standardized effects")
        st.image(_render_pareto_png(effects, int(fit.df_resid)))
    with right:
        st.markdown("##### Ranked effects")
        eff_df = pd.DataFrame(
            [[e.term, e.coef, e.std_err, e.t, e.p] for e in effects],
            columns=["term", "coef", "std_err", "t", "p"],
        )
        st.dataframe(
            eff_df, hide_index=True, height=480,
            column_config={
                "coef": st.column_config.NumberColumn("coef", format="%.3g"),
                "std_err": st.column_config.NumberColumn("std err", format="%.3g"),
                "t": st.column_config.NumberColumn("t", format="%.2f"),
                "p": st.column_config.NumberColumn("p", format="%.3g"),
            },
        )
        st.download_button(
            "Download effects CSV",
            eff_df.to_csv(index=False).encode("utf-8"),
            file_name=f"effects_{response}.csv",
            mime="text/csv",
            width="stretch",
        )

    # Surface plot + desirability optimum — only if ≥2 main effects
    main_terms = [t for t in fit.params.index if t != "Intercept" and ":" not in t]
    if len(main_terms) >= 2:
        st.markdown("##### Response surface")
        st.caption(
            "2D contour over the two most-significant factors; others held at "
            "the coded center."
        )
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            surface_plot(fit, tf.name)
            st.image(tf.name)

        with st.expander("Find the optimum (desirability)", expanded=False):
            direction = st.radio(
                "Direction", options=["maximize", "minimize"],
                horizontal=True, key="opt_direction",
            )
            opt = optimize_response(fit, factor_cols, direction=direction)
            opt_rows = []
            for col in factor_cols:
                fname = col.removesuffix("_coded")
                coded_v = opt["coded"][col]
                opt_rows.append({
                    "factor": fname,
                    "coded": coded_v,
                })
            st.metric("Predicted response at optimum", f"{opt['predicted']:.3g}")
            st.dataframe(
                pd.DataFrame(opt_rows), hide_index=True,
                column_config={
                    "coded": st.column_config.NumberColumn("coded ±1", format="%+.3f"),
                },
            )


def _render_pareto_png(effects, df_resid: int) -> bytes:
    from matplotlib.figure import Figure
    from scipy.stats import t as student_t

    fig = Figure(figsize=(6.5, max(2.8, 0.36 * len(effects) + 1)))
    ax = fig.subplots()
    terms = [e.term for e in effects]
    abs_t = [abs(e.t) for e in effects]
    colors = [POS_COLOR if e.coef >= 0 else NEG_COLOR for e in effects]
    y = range(len(terms))
    ax.barh(list(y), abs_t, color=colors)
    ax.set_yticks(list(y))
    ax.set_yticklabels(terms)
    ax.invert_yaxis()
    ax.set_xlabel("|t|  (blue = positive effect, red = negative)")
    if df_resid and df_resid > 0:
        t_crit = float(student_t.ppf(0.975, df_resid))
        ax.axvline(t_crit, color="#888", linestyle="--", linewidth=1,
                   label=f"α=0.05 (df={df_resid})")
        ax.legend(loc="lower right", frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140)
    buf.seek(0)
    return buf.getvalue()


def _render_tutorial_tab(default_cfg: ReactionConfig) -> None:
    st.markdown(
        "### New to DoE? Start here.\n\n"
        "Spoiler alert: It is way faster than optimizing one-factor-at-a-time!\n\n"
        "Two short sections: **Why DoE?** shows, numerically, what "
        "one-factor-at-a-time (OFAT) screening costs you on a realistic IVT "
        "surface. **Your first screen** walks you through the tool end-to-end."
    )

    why, how = st.tabs(["Why DoE?", "Your first screen"])

    with why:
        st.markdown(
            "Imagine a 4-factor IVT screen — NTPs, MgCl₂, T7, PEG8000 — "
            "with a realistic catch: **MgCl₂'s best setpoint depends on NTPs**. "
            "At low NTPs, more Mg²⁺ helps. At high NTPs, *even more* Mg²⁺ helps "
            "*disproportionately*. That's a two-factor interaction, and it's "
            "invisible to OFAT by construction.\n\n"
            "Below, we simulate the same ground-truth IVT under two plans:\n\n"
            "- **OFAT**: 3 center replicates + high/low spoke at each factor (11 runs). "
            "Pick each factor's best level independently.\n"
            "- **DoE**: 2⁴ full factorial + 3 center replicates (19 runs). "
            "Fit main effects + 2-factor interactions; search for the optimum.\n"
        )

        st.markdown(
            '<div class="sn-label-with-info">'
            '<span>Simulation seed</span>'
            '<span class="sn-info-icon" tabindex="0" '
            'data-tooltip="Different seeds give different noise draws — the '
            'conclusion is robust.">'
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="12" cy="12" r="10"/>'
            '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>'
            '<line x1="12" y1="17" x2="12.01" y2="17"/>'
            '</svg></span>'
            '</div>',
            unsafe_allow_html=True,
        )
        seed = st.slider(
            "Simulation seed",
            min_value=0, max_value=50, value=7, step=1,
            key="tutorial_seed",
            label_visibility="collapsed",
        )

        report = run_ofat_vs_doe(default_cfg, seed=seed)

        c1, c2, c3 = st.columns(3)
        c1.metric(
            "OFAT yield at its picked setpoint",
            f"{report.ofat.true_yield_at_optimum:.2f} µg/µL",
            help=f"{report.ofat.n_runs} runs · main effects only",
        )
        c2.metric(
            "DoE yield at its picked setpoint",
            f"{report.doe.true_yield_at_optimum:.2f} µg/µL",
            f"{report.yield_gap():+.2f} vs OFAT",
            help=f"{report.doe.n_runs} runs · main + 2-factor interactions",
        )
        c3.metric(
            "True best achievable yield",
            f"{report.true_best_yield:.2f} µg/µL",
            help="Noise-free maximum over the 2ᵏ corners.",
        )

        factor_names = [f.name for f in default_cfg.factors]
        picks_df = pd.DataFrame({
            "Factor": factor_names,
            "OFAT pick (coded)": [
                report.ofat.predicted_optimum_coded[n] for n in factor_names
            ],
            "DoE pick (coded)": [
                report.doe.predicted_optimum_coded[n] for n in factor_names
            ],
            "True best (coded)": [
                report.true_best_coded[n] for n in factor_names
            ],
        })
        st.markdown("##### Where each strategy lands")
        st.dataframe(
            picks_df, hide_index=True, width="stretch",
            column_config={
                c: st.column_config.NumberColumn(c, format="%+.2f")
                for c in picks_df.columns if c != "Factor"
            },
        )

        mismatched = [
            n for n in factor_names
            if abs(report.ofat.predicted_optimum_coded[n]
                   - report.true_best_coded[n]) > 0.5
        ]
        if mismatched:
            st.warning(
                f"**OFAT picks the wrong level on: {', '.join(mismatched)}.** "
                "That's because its rule ('hold everything at center and "
                "sweep one factor') can't see that MgCl₂ behaves differently "
                "when NTPs is high vs low. DoE sees it because every "
                "combination of ±1 is in the plan.",
                icon=":material/warning:",
            )

        if report.doe.caught_interactions:
            caught = ", ".join(
                f"`{t.replace('_coded', '')}`"
                for t in report.doe.caught_interactions
            )
            st.success(
                f"**DoE flagged {len(report.doe.caught_interactions)} "
                f"interaction(s) at α=0.05:** {caught}. OFAT can't even "
                "estimate these — the math literally doesn't work without "
                "pairwise variation in the design.",
                icon=":material/check_circle:",
            )

        st.markdown("##### Truth surface — NTPs × MgCl₂ slice")
        st.caption(
            "The ground-truth yield at every combination of NTPs and MgCl₂ "
            "(other factors held at center). The dot is where OFAT lands; "
            "the star is DoE's pick."
        )
        st.pyplot(_truth_heatmap_fig(report, factor_names), clear_figure=True)

        st.markdown("##### The takeaway")
        st.markdown(
            "DoE uses more runs than OFAT's minimal plan, but it finds "
            f"**{report.yield_gap():+.2f} µg/µL more yield** because it "
            "measures the interaction OFAT can't even see. In a real lab, "
            "that's the difference between shipping a 14 µg/µL IVT and a "
            "12 µg/µL one — same reagents, same day, just a better plan."
        )

    with how:
        st.markdown(
            "Here's the shortest path from blank slate to a bench-ready plan:"
        )

        st.markdown(
            "**1. Configure the screen in the sidebar.** "
            "The default is a 4-factor IVT (NTPs, MgCl₂, T7, PEG8000). "
            "For each reagent, set the high and low points to the highest "
            "and lowest amounts, respectively, that you'd still expect to "
            "give a non-zero yield — bracket the active range so the effect "
            "is big enough to see above noise without killing the corners. "
            "Stay within what your stocks and pipettes can actually hit. "
            "Center points give you a noise estimate — keep 3 unless you "
            "know why."
        )
        st.markdown(
            "**2. Pick a design type.** "
            "Start with **full factorial** (2ᵏ + centers) for k ≤ 5 factors. "
            "For k > 5 factors, switch to **Plackett-Burman** — 12 runs "
            "catches main effects across up to 11 factors. After you have "
            "a screen in hand and see curvature in the center-point test, "
            "come back and run a **CCD** follow-up to characterize it."
        )
        st.markdown(
            "**3. Assign a plate layout.** "
            "If you'll run in a 96- or 384-well plate, pick a layout in "
            "the sidebar. Column-major is the usual default; randomized "
            "breaks up position-dependent systematic error (edge effects, "
            "incubator gradients)."
        )
        st.markdown(
            "**4. Generate and download.** "
            "The **Generate** tab shows your randomized run table, a "
            "printable HTML bench sheet with per-run pipetting volumes, "
            "and a plate map. Download the **coded CSV** — that's the one "
            "you'll fill in with yields."
        )
        st.markdown(
            "**5. Run the screen at the bench.** "
            "Work down the bench sheet row by row; the volumes are already "
            "computed and the plate map tells you which well is which. "
            "Record your yield (or whatever response you're optimizing) "
            "in the empty response column of the coded CSV."
        )
        st.markdown(
            "**6. Upload the filled CSV to the Analyze tab.** "
            "You'll get a Pareto of standardized effects, an OLS fit, "
            "ranked significances, a response surface, and a desirability "
            "optimum. If curvature is significant, Screenase will "
            "auto-suggest a CCD follow-up."
        )

        st.divider()
        st.markdown("##### Try the demo end-to-end without a bench")
        st.markdown(
            "1. Click **Generate screen** above.\n"
            "2. Download the **Coded CSV**.\n"
            "3. Click **Analyze results** and pick **Demo results** — "
            "that's a pre-filled version of the same screen.\n"
            "4. Look for the Pareto bars that cross the red significance line, "
            "read the plain-English summary, and check the CCD recommendation.\n"
        )
        st.info(
            "The whole loop — plan, simulate, analyze — takes about "
            "90 seconds. You'll see exactly what a real DoE report looks like, "
            "generated from this same codebase.",
            icon=":material/lightbulb:",
        )


def _truth_heatmap_fig(report, factor_names: list[str]):
    """2D slice of the truth surface over (NTPs, MgCl2), others at 0."""
    from matplotlib.figure import Figure

    grid = np.linspace(-1.0, 1.0, 41)
    X, Y = np.meshgrid(grid, grid)
    coded = pd.DataFrame({
        factor_names[0]: X.ravel(),
        factor_names[1]: Y.ravel(),
        factor_names[2]: 0.0,
        factor_names[3]: 0.0,
    })
    Z = truth_response(coded, sigma=0.0).reshape(X.shape)

    fig = Figure(figsize=(6.5, 4.5))
    ax = fig.subplots()
    cs = ax.contourf(X, Y, Z, levels=16, cmap="viridis")
    fig.colorbar(cs, ax=ax, label="yield (µg/µL)")
    ax.set_xlabel(f"{factor_names[0]} (coded)")
    ax.set_ylabel(f"{factor_names[1]} (coded)")

    # OFAT pick
    ax.plot(
        report.ofat.predicted_optimum_coded[factor_names[0]],
        report.ofat.predicted_optimum_coded[factor_names[1]],
        marker="o", markersize=14, markerfacecolor="#c05454",
        markeredgecolor="white", markeredgewidth=2, label="OFAT pick",
    )
    # DoE pick
    ax.plot(
        report.doe.predicted_optimum_coded[factor_names[0]],
        report.doe.predicted_optimum_coded[factor_names[1]],
        marker="*", markersize=20, markerfacecolor="#f5d742",
        markeredgecolor="black", markeredgewidth=1.2, label="DoE pick",
    )
    ax.legend(loc="lower left", frameon=True, facecolor="white")
    ax.set_title("Truth surface (other factors at center)")
    return fig


def _render_about_tab() -> None:
    st.markdown(
        f"""
### What this is

**Screenase** plans and analyzes 2ᵏ full-factorial Design-of-Experiments screens
for in-vitro transcription (IVT) reactions — bench-ready in one click.

- **Generate**: choose factor ranges, get a randomized run table + printable
  bench sheet with per-run pipetting volumes.
- **Analyze**: upload the completed response column, get a Pareto of
  standardized effects, an OLS fit (main effects + 2-factor interactions),
  and ranked significance.

The full package (CLI, tests, Benchling-App-shaped subpackage) is on GitHub.

### Reproducibility

Every generated design carries a 12-character **config hash** — the same config
plus the same seed always yields byte-identical output. The default demo config
with `seed=42` is pinned by a contract test in the repo.

### Links

- **Source**: [{REPO_URL}]({REPO_URL})
- **Library version**: `screenase=={__version__}`
"""
    )


# ---------- main ----------

def main() -> None:
    st.set_page_config(
        page_title="Screenase — IVT DoE",
        layout="wide",
        menu_items={
            "Get help": REPO_URL,
            "Report a bug": f"{REPO_URL}/issues",
            "About": "Screenase — DoE planner for in-vitro transcription.",
        },
    )
    _inject_safety_css()

    header_l, header_r = st.columns([3, 1])
    with header_l:
        st.title("Screenase")
        st.caption(
            "[Design-of-Experiments](https://www.mathworks.com/help/stats/design-of-experiments.html)"
            " planner to catalyze your IVT screens."
        )
    with header_r:
        st.markdown(
            f"<div style='text-align:right; padding-top:1.8rem; color:#888;'>"
            f"v{__version__}  •  "
            f"<a href='{REPO_URL}' target='_blank' style='color:#888;'>source</a>"
            f"</div>",
            unsafe_allow_html=True,
        )

    starting_cfg = _config_from_url() or build_default_config()
    cfg, min_pipet_uL, opts = _sidebar(starting_cfg)

    tab_gen, tab_analyze, tab_tutorial, tab_about = st.tabs([
        "Generate screen", "Analyze results", "Tutorial", "About",
    ])
    with tab_gen:
        _render_generate_tab(cfg, min_pipet_uL, opts)
    with tab_analyze:
        _render_analyze_tab()
    with tab_tutorial:
        _render_tutorial_tab(starting_cfg)
    with tab_about:
        _render_about_tab()

    st.markdown(
        "<div style='text-align:center; color:#999; font-size:0.8rem; "
        "padding: 2rem 0 0.5rem;'>MIT License © Ethan Arnold</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
