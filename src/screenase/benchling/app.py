"""Webhook handlers shaped like `benchling-sdk` entrypoints.

No live API calls. Each handler reads a webhook payload (either from Benchling's
`request_created`/`results_submitted` events, or from a local fixture), uses
core `screenase` logic to do the real work, and returns a JSON-serializable dict
that a real deployment would POST back via the SDK.

The SDK is lazy-imported only if it's available — tests and the example
fixtures exercise these handlers without it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from screenase import __version__
from screenase.analyze import fit_model, rank_effects
from screenase.bench_sheet import build_context, render_bench_sheet
from screenase.benchling.entities import (
    design_to_benchling_request,
    effects_to_benchling_entry,
)
from screenase.config import ReactionConfig, config_hash
from screenase.design import build_design
from screenase.volumes import compute_volumes, validate_volumes


def _load_config_from_payload(payload: dict[str, Any]) -> ReactionConfig:
    cfg_dict = payload.get("config") or payload.get("fields", {}).get("config", {}).get("value")
    if not cfg_dict:
        raise ValueError("webhook payload missing `config` body")
    return ReactionConfig.model_validate(cfg_dict)


def handle_request_created(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle the `request_created` webhook: build the design + bench sheet, echo back.

    Real Benchling flow would POST the returned Request payload via the SDK and
    attach `benchSheetHTML` as an Entry blob. Here we return both as
    JSON-serializable strings.
    """
    cfg = _load_config_from_payload(payload)
    run_id = payload.get("runId") or datetime.now(UTC).strftime("run-%Y%m%d-%H%M%S")

    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    warnings = validate_volumes(vol_df, cfg)
    ctx = build_context(
        vol_df, design["is_center"], cfg,
        run_id=run_id,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        lib_version=__version__,
        config_hash=config_hash(cfg),
        warnings=warnings,
    )
    bench_html = render_bench_sheet(ctx)
    factor_cols = [f.name for f in cfg.factors]
    screen_csv = design[factor_cols].to_csv()

    return {
        "runId": run_id,
        "configHash": config_hash(cfg),
        "request": design_to_benchling_request(design, cfg, run_id=run_id),
        "benchSheetHTML": bench_html,
        "screenCSV": screen_csv,
        "warnings": [
            {"run": w.run, "reagent": w.reagent, "volume_uL": w.volume_uL, "reason": w.reason}
            for w in warnings
        ],
    }


def handle_results_submitted(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle the `results_submitted` webhook: run OLS, return the ranked-effects entry."""
    results_records = payload.get("results")
    if not results_records:
        raise ValueError("webhook payload missing `results` array")
    response_col = payload.get("responseColumn", "yield_ug_per_uL")
    run_id = payload.get("runId") or "run-unknown"

    results = pd.DataFrame(results_records)
    factor_cols = [c for c in results.columns if c.endswith("_coded")]
    if not factor_cols:
        raise ValueError("results array has no `_coded` factor columns")
    fit = fit_model(results, response_col, factor_cols)
    effects = rank_effects(fit)
    entry = effects_to_benchling_entry(effects, run_id=run_id)

    return {
        "runId": run_id,
        "responseColumn": response_col,
        "rSquared": float(fit.rsquared),
        "dfResid": int(fit.df_resid),
        "topTerm": effects[0].term if effects else None,
        "entry": entry,
        "effects": [
            {"term": e.term, "coef": e.coef, "t": e.t, "p": e.p}
            for e in effects
        ],
    }


def run_fixture(fixture_path: Path | str, handler: str = "request_created") -> dict[str, Any]:
    """Utility: dispatch a local fixture JSON through the named handler."""
    payload = json.loads(Path(fixture_path).read_text())
    if handler == "request_created":
        return handle_request_created(payload)
    if handler == "results_submitted":
        return handle_results_submitted(payload)
    raise ValueError(f"unknown handler {handler!r}")
