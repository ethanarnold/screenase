"""Benchling schema scaffolding.

Emits JSON shaped like the admin-facing schema definitions a Benchling tenant
admin would paste into the Registry / Request / Result / Entry schema builder
UIs — one file per schema. The exact field names match the keys written by
`entities.py`, so a tenant that installs these schemas will accept Screenase
payloads out of the box.

Reference: https://help.benchling.com/hc/en-us/articles/9684253726093
"""

from __future__ import annotations

from typing import Any

from screenase.config import ReactionConfig

# Benchling field types — only the subset we use. `dropdown` + `entity_link`
# would be needed for reagent/lot references; left as `text` here so the
# scaffolding is self-contained without tenant-specific dropdown IDs.
_FT_FLOAT = "float"
_FT_INT = "integer"
_FT_BOOL = "boolean"
_FT_TEXT = "text"
_FT_JSON = "long_text"  # Benchling lacks a native JSON type; store as long_text.


def _field_spec(
    name: str, display: str, ftype: str, *, required: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "displayName": display,
        "fieldType": ftype,
        "isRequired": required,
        "isMulti": False,
    }


def request_schema(cfg: ReactionConfig, *, schema_id: str | None = None) -> dict[str, Any]:
    """Schema definition for the top-level DoE Request."""
    fields = [
        _field_spec("runId", "Run ID", _FT_TEXT, required=True),
        _field_spec("configHash", "Config Hash", _FT_TEXT, required=True),
        _field_spec("seed", "Seed", _FT_INT),
        _field_spec("reactionVolumeUL", "Reaction Volume (µL)", _FT_FLOAT),
        _field_spec("centerPoints", "Center Points", _FT_INT),
        _field_spec("factors", "Factors (JSON)", _FT_JSON),
    ]
    return {
        "schemaId": schema_id or "sch_screenase_doe_request",
        "schemaType": "request",
        "displayName": "Screenase DoE Request",
        "fields": fields,
    }


def result_schema(cfg: ReactionConfig, *, schema_id: str | None = None) -> dict[str, Any]:
    """Schema definition for a single-run Result row.

    Pre-declares one numeric field per factor so the raw setpoints are queryable
    in the Benchling Results table. A `response_ugPerUL` field is included as
    the canonical yield response; tenants can add more via the admin UI.
    """
    fields = [
        _field_spec("runId", "Run ID", _FT_TEXT, required=True),
        _field_spec("run", "Run", _FT_INT, required=True),
        _field_spec("isCenterPoint", "Center Point?", _FT_BOOL),
    ]
    for f in cfg.factors:
        fields.append(_field_spec(f.name, f.display or f.name, _FT_FLOAT))
        fields.append(_field_spec(f"{f.name}_coded", f"{f.name} (coded)", _FT_FLOAT))
    fields.append(_field_spec("response_ugPerUL", "Yield (µg/µL)", _FT_FLOAT))
    return {
        "schemaId": schema_id or "sch_screenase_doe_result",
        "schemaType": "result",
        "displayName": "Screenase DoE Result",
        "fields": fields,
    }


def entry_schema(cfg: ReactionConfig, *, schema_id: str | None = None) -> dict[str, Any]:
    """Schema definition for the post-analysis Entry."""
    fields = [
        _field_spec("runId", "Run ID", _FT_TEXT, required=True),
        _field_spec("topTerm", "Top Term", _FT_TEXT),
        _field_spec("topTerms", "Top Terms (JSON)", _FT_JSON),
        _field_spec("rSquared", "R²", _FT_FLOAT),
        _field_spec("curvatureP", "Curvature p-value", _FT_FLOAT),
    ]
    return {
        "schemaId": schema_id or "sch_screenase_doe_analysis",
        "schemaType": "entry",
        "displayName": "Screenase Analysis",
        "fields": fields,
    }


def scaffold_all(cfg: ReactionConfig) -> dict[str, dict[str, Any]]:
    """Emit all three schemas as a single dict keyed by kind."""
    return {
        "request": request_schema(cfg),
        "result": result_schema(cfg),
        "entry": entry_schema(cfg),
    }
