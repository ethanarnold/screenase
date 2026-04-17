# `screenase.benchling` — Benchling-App-shaped subpackage

This directory shapes Screenase as a Benchling App: a manifest declaring
permissions and webhooks, SDK-style handler signatures, and an entity-mapping
module that converts Screenase's design/results/effects into the JSON payload
shapes Benchling's API accepts.

**Nothing here calls the live Benchling API.** Running a real Benchling App
requires enterprise-tier Developer Platform access, which is not self-serve.
Instead, the handlers in `app.py` are invoked against static fixtures in
`fixtures/` — see `tests/test_benchling.py` for end-to-end runs.

## Files

| File | Role |
|---|---|
| `manifest.yaml` | App manifest: name, version, permissions, webhook bindings. |
| `entities.py` | Maps Screenase objects → Benchling Request/Result/Entry payloads. |
| `app.py` | SDK-style webhook handlers. Lazy-import for the SDK itself. |
| `fixtures/request_created.json` | Simulated `v2.request.created` payload. |
| `fixtures/results_submitted.json` | Simulated `v2.results.submitted` payload (seeded truth: top term `NTPs_mM_each_coded`). |

## Mapping summary

- A Screenase **design** → one Benchling **Request** (`schemaId: sch_screenase_doe_request`). Request fields carry config hash, seed, reaction volume, and the factor table; a Screenase-specific `runs` array expands per-row setpoints.
- Submitted **response measurements** → a list of **Result** rows (`schemaId: sch_screenase_doe_result`), one per run.
- Ranked **effects** from `analyze` → an **Entry** (`schemaId: sch_screenase_doe_analysis`), with `topTerms` as a structured field.

See [`docs/benchling_mapping.md`](../../../docs/benchling_mapping.md) for deeper
notes on why the mapping uses an Entry for analysis output rather than another
Result schema.

## Running the fixtures locally

```bash
python -c "from screenase.benchling.app import run_fixture; \
import json; \
print(json.dumps(run_fixture('src/screenase/benchling/fixtures/request_created.json'), indent=2)[:2000])"
```

## Why not a full live deployment?

Benchling's Developer Platform and App framework are enterprise-gated (no
self-serve tenant). Shipping the manifest + entity mapping + handlers is the
high-signal portion of "integrating with Benchling" — it demonstrates that the
tool understands the platform's data model without needing to host a webhook
server on a tenant that doesn't exist.
