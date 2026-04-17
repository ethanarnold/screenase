from __future__ import annotations

import json
from pathlib import Path

import pytest

from screenase.benchling.app import (
    handle_request_created,
    handle_results_submitted,
    run_fixture,
)
from screenase.benchling.entities import (
    design_to_benchling_request,
    effects_to_benchling_entry,
    results_to_benchling_results,
)
from screenase.design import build_design

FIX = Path(__file__).resolve().parent.parent / "src" / "screenase" / "benchling" / "fixtures"


def _assert_json_round_trip(obj):
    text = json.dumps(obj)
    back = json.loads(text)
    assert isinstance(back, (dict, list))


def test_design_to_benchling_request_schema(cfg):
    d = build_design(cfg)
    payload = design_to_benchling_request(d, cfg, run_id="run-X")
    expected_keys = {"schemaId", "name", "fields", "runs"}
    assert expected_keys.issubset(payload.keys())
    assert len(payload["runs"]) == len(d)
    for entry in payload["runs"]:
        assert "fields" in entry
        assert entry["fields"]["run"]["value"] == entry["run"]
    _assert_json_round_trip(payload)


def test_results_to_benchling_results(cfg):
    d = build_design(cfg)
    d = d.copy()
    d["yield_ug_per_uL"] = 1.0
    payload = results_to_benchling_results(d, ["yield_ug_per_uL"], run_id="run-X")
    assert len(payload) == len(d)
    assert all(p["fields"]["yield_ug_per_uL"]["value"] == 1.0 for p in payload)
    _assert_json_round_trip(payload)


def test_handle_request_created_fixture_returns_html_and_csv():
    out = run_fixture(FIX / "request_created.json", handler="request_created")
    assert "<!DOCTYPE html>" in out["benchSheetHTML"]
    assert "NTPs_mM_each" in out["screenCSV"]
    assert "request" in out and isinstance(out["request"], dict)
    assert out["configHash"]
    _assert_json_round_trip(out)


def test_handle_results_submitted_top_term_matches_seed():
    payload = json.loads((FIX / "results_submitted.json").read_text())
    out = handle_results_submitted(payload)
    assert out["topTerm"] == payload["expectedTopTerm"]
    _assert_json_round_trip(out)
    assert out["rSquared"] > 0.9  # σ=0.5 noise on effects {3, 2, 1.5}


def test_effects_to_benchling_entry():
    from screenase.analyze import EffectRow
    effects = [
        EffectRow("alpha", 1.0, 0.1, 10.0, 0.001, 1.0),
        EffectRow("beta", 0.5, 0.1, 5.0, 0.01, 0.5),
    ]
    entry = effects_to_benchling_entry(effects, run_id="run-X")
    assert entry["fields"]["topTerm"]["value"] == "alpha"
    assert len(entry["fields"]["topTerms"]["value"]) == 2
    _assert_json_round_trip(entry)


def test_missing_config_raises():
    with pytest.raises(ValueError, match="missing"):
        handle_request_created({})


def test_missing_results_raises():
    with pytest.raises(ValueError, match="missing"):
        handle_results_submitted({})
