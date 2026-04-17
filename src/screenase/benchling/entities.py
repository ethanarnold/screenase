"""Map screenase design/results/effects → Benchling Request/Result/Entry payloads.

The output dicts are JSON-serializable and shaped like what Benchling's API
accepts: top-level `schemaId`, a `fields` object with `{name: {"value": ...}}`
wrappers, and run-level nested payloads. This module does not make network
calls; it produces payloads a caller could POST to Benchling via the SDK.

Mapping rationale (see docs/benchling_mapping.md):
- A screenase design → a Benchling **Request** with per-run metadata as fields
  plus a nested `runs` array of Result-shaped payloads (one per design row).
- Completed response columns → a list of Benchling **Result** payloads keyed
  by run id.
- Ranked effects (post-analysis) → a structured **Entry** payload (templated
  markdown-ish content with `fields` storing the top terms + curvature p).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from screenase.config import ReactionConfig, config_hash

DEFAULT_REQUEST_SCHEMA_ID = "sch_screenase_doe_request"
DEFAULT_RESULT_SCHEMA_ID = "sch_screenase_doe_result"
DEFAULT_ENTRY_SCHEMA_ID = "sch_screenase_doe_analysis"


def _field(value: Any) -> dict[str, Any]:
    return {"value": value}


def design_to_benchling_request(
    design_df: pd.DataFrame,
    cfg: ReactionConfig,
    *,
    run_id: str,
    schema_id: str | None = None,
) -> dict[str, Any]:
    """Shape a screenase design DataFrame as a Benchling Request payload.

    The payload top-level mirrors the Benchling Request schema:
    `{schemaId, name, fields, runs}`. `runs` is a Screenase-specific extension
    listing per-run factor setpoints + coded values; real Benchling tenants
    would normally store these as linked Result rows created after the Request
    is fulfilled, but emitting them inline keeps the export self-contained.
    """
    schema = schema_id or DEFAULT_REQUEST_SCHEMA_ID
    factor_cols = [f.name for f in cfg.factors]
    coded_cols = [f"{f.name}_coded" for f in cfg.factors]

    runs_payload: list[dict[str, Any]] = []
    for run_idx, row in design_df.iterrows():
        fields: dict[str, Any] = {
            "run": _field(int(run_idx)),
            "isCenterPoint": _field(bool(row.get("is_center", False))),
        }
        for col in factor_cols:
            fields[col] = _field(float(row[col]))
        for col in coded_cols:
            if col in design_df.columns:
                fields[col] = _field(float(row[col]))
        runs_payload.append({"run": int(run_idx), "fields": fields})

    return {
        "schemaId": schema,
        "name": f"Screenase DoE — {run_id}",
        "fields": {
            "runId": _field(run_id),
            "configHash": _field(config_hash(cfg)),
            "seed": _field(int(cfg.seed)),
            "reactionVolumeUL": _field(float(cfg.reaction_volume_uL)),
            "centerPoints": _field(int(cfg.center_points)),
            "factors": _field([{
                "name": f.name, "low": f.low, "high": f.high, "unit": f.unit,
            } for f in cfg.factors]),
        },
        "runs": runs_payload,
    }


def results_to_benchling_results(
    results_df: pd.DataFrame,
    response_cols: list[str],
    *,
    run_id: str,
    schema_id: str | None = None,
) -> list[dict[str, Any]]:
    """Shape completed response measurements as a list of Benchling Result payloads."""
    schema = schema_id or DEFAULT_RESULT_SCHEMA_ID
    out: list[dict[str, Any]] = []
    for run_idx, row in results_df.iterrows():
        fields: dict[str, Any] = {"runId": _field(run_id), "run": _field(int(run_idx))}
        for col in response_cols:
            if col in results_df.columns:
                fields[col] = _field(float(row[col]))
        out.append({"schemaId": schema, "fields": fields})
    return out


def effects_to_benchling_entry(
    effects: list,  # list[EffectRow] — avoid import cycle
    *,
    run_id: str,
    schema_id: str | None = None,
) -> dict[str, Any]:
    """Shape a ranked effects table as a Benchling Entry payload.

    The Entry carries the Pareto table as a structured `fields.topTerms` list
    plus a `name` that references the originating run id so Benchling users
    can navigate from the Request → the analysis Entry.
    """
    schema = schema_id or DEFAULT_ENTRY_SCHEMA_ID
    top_terms = [
        {
            "term": e.term,
            "coef": float(e.coef),
            "t": float(e.t),
            "p": float(e.p),
            "absStdEffect": float(e.abs_std_effect),
        }
        for e in effects
    ]
    return {
        "schemaId": schema,
        "name": f"Screenase analysis — {run_id}",
        "fields": {
            "runId": _field(run_id),
            "topTerms": _field(top_terms),
            "topTerm": _field(top_terms[0]["term"] if top_terms else None),
        },
    }
