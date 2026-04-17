"""Tests for Benchling schema scaffolding + entry_completed handler."""

from __future__ import annotations

import json
from pathlib import Path

from screenase.benchling.app import handle_entry_completed, run_fixture
from screenase.benchling.schemas import (
    entry_schema,
    request_schema,
    result_schema,
    scaffold_all,
)

FIXTURES = Path(__file__).resolve().parent.parent / "src" / "screenase" / "benchling" / "fixtures"


def test_scaffold_all_returns_three_schemas(cfg) -> None:
    schemas = scaffold_all(cfg)
    assert set(schemas) == {"request", "result", "entry"}


def test_request_schema_has_required_fields(cfg) -> None:
    s = request_schema(cfg)
    names = {f["name"] for f in s["fields"]}
    assert "runId" in names
    assert "configHash" in names
    assert s["schemaType"] == "request"


def test_result_schema_includes_per_factor_fields(cfg) -> None:
    s = result_schema(cfg)
    names = {f["name"] for f in s["fields"]}
    for f in cfg.factors:
        assert f.name in names
        assert f"{f.name}_coded" in names


def test_entry_schema_has_top_term(cfg) -> None:
    s = entry_schema(cfg)
    names = {f["name"] for f in s["fields"]}
    assert "topTerm" in names
    assert "rSquared" in names


def test_entry_completed_fixture_round_trips() -> None:
    path = FIXTURES / "entry_completed.json"
    assert path.exists(), "entry_completed fixture missing"
    result = run_fixture(path, handler="entry_completed")
    assert result["runId"]
    assert "entryUpdate" in result
    assert "topTerm" in result
    # Round-trips through JSON
    assert json.loads(json.dumps(result))


def test_handle_entry_completed_requires_results() -> None:
    import pytest

    with pytest.raises(ValueError, match="missing `results`"):
        handle_entry_completed({"entry": {}})
