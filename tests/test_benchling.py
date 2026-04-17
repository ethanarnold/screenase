from __future__ import annotations

import json
from pathlib import Path

import pytest

from screenase.benchling.app import (
    handle_reagent_consumed,
    handle_request_created,
    handle_results_submitted,
    run_fixture,
)
from screenase.benchling.entities import (
    design_to_benchling_request,
    effects_to_benchling_entry,
    results_to_benchling_results,
)
from screenase.benchling.inventory import (
    build_inventory_decrement_payload,
    compute_reagent_consumption,
    post_run_inventory_summary,
)
from screenase.design import build_design
from screenase.volumes import compute_volumes

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


def test_compute_reagent_consumption_excludes_water_and_dna_by_default(cfg):
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    cons = compute_reagent_consumption(v, cfg, excess=1.2)
    assert "Water" not in cons
    assert "DNA" not in cons
    # Every cfg stock that's exercised via factors should be present
    for f in cfg.factors:
        assert f.reagent in cons
    # Values scaled by 1.2
    raw = compute_reagent_consumption(v, cfg, excess=1.0)
    for k in cons:
        assert cons[k] == pytest.approx(raw[k] * 1.2, rel=1e-6)


def test_compute_reagent_consumption_include_water_and_dna(cfg):
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    cons = compute_reagent_consumption(v, cfg, include_water=True, include_dna=True)
    assert "Water" in cons
    assert "DNA" in cons


def test_build_inventory_decrement_payload_shape(cfg):
    consumption = {"NTPs": 50.0, "MgCl2": 12.0, "T7": 8.5}
    lot_refs = {
        "NTPs": {"containerId": "con_ntp", "lotId": "lot_ntp"},
        "MgCl2": {"containerId": "con_mg", "lotId": "lot_mg"},
        # T7 deliberately missing → should land in `unresolved`
    }
    payload = build_inventory_decrement_payload(
        consumption, lot_refs, run_id="run-X", dry_run=True,
    )
    assert payload["operation"] == "inventoryDecrement"
    assert payload["runId"] == "run-X"
    assert payload["dryRun"] is True
    containers = {d["reagent"]: d for d in payload["decrements"]}
    assert containers["NTPs"]["volumeUL"] == 50.0
    assert containers["NTPs"]["containerId"] == "con_ntp"
    assert containers["NTPs"]["units"] == "uL"
    assert [u["reagent"] for u in payload["unresolved"]] == ["T7"]
    _assert_json_round_trip(payload)


def test_post_run_inventory_summary_roundtrip(cfg):
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    summary = post_run_inventory_summary(
        v, cfg,
        lot_refs={r: {"containerId": f"con_{r}", "lotId": f"lot_{r}"}
                  for r in cfg.stocks},
        run_id="run-X", excess=1.2,
    )
    assert summary["runId"] == "run-X"
    assert summary["excess"] == 1.2
    assert summary["totalPipettedUL"] > 0
    assert summary["consumptionUL"]
    assert summary["payload"]["dryRun"] is True
    _assert_json_round_trip(summary)


def test_handle_reagent_consumed_fixture_emits_decrements():
    out = run_fixture(FIX / "reagent_consumed.json", handler="reagent_consumed")
    assert "payload" in out
    assert out["payload"]["operation"] == "inventoryDecrement"
    assert out["consumptionUL"]
    # Every reagent in the fixture has lotRefs → no unresolved
    assert out["payload"]["unresolved"] == []
    # Each decrement carries a positive volume in µL
    for d in out["payload"]["decrements"]:
        assert d["volumeUL"] > 0
        assert d["units"] == "uL"
    _assert_json_round_trip(out)


def test_handle_reagent_consumed_rejects_missing_config():
    with pytest.raises(ValueError, match="missing"):
        handle_reagent_consumed({})


def test_handle_reagent_consumed_surfaces_unresolved_when_ref_missing():
    import json as _json

    payload = _json.loads((FIX / "reagent_consumed.json").read_text())
    # Drop one reagent mapping to trigger `unresolved`
    payload["lotRefs"].pop("T7")
    out = handle_reagent_consumed(payload)
    assert any(u["reagent"] == "T7" for u in out["payload"]["unresolved"])
