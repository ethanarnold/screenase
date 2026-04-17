# Benchling mapping

How Screenase objects map to Benchling's data model, and how a live tenant
would wire the webhook handlers up.

## Why shaped, not deployed?

Benchling's Developer Platform is enterprise-gated. There's no self-serve
tenant we could use for a portfolio demo. The shape of a Benchling App —
manifest, permissions, webhook handlers, entity-schema-shaped payloads —
is the interesting part anyway; swapping in live network calls via
`benchling-sdk` is a small edit once tenant access is available.

## Object mapping

| Screenase concept | Benchling concept | Notes |
|---|---|---|
| `ReactionConfig` | inputs to a **Request** | config lives in a top-level `fields` block; seed, config hash, factor table live there |
| One design row (a run) | entry in `request.runs` array | not a standard Benchling field, but a useful inline expansion |
| Pipetting bench sheet HTML | attached **Entry** (blob) | Entries carry rich HTML; operator marks checkboxes and uploads yields back into Benchling |
| Per-run response (yield) | a **Result** row | schema `sch_screenase_doe_result`, one per run |
| Ranked effects table | a **Entry** (structured) | schema `sch_screenase_doe_analysis`; `topTerms` is the Pareto in list form |

## Why an Entry for analysis output, not another Result schema?

A Result row models a single measurement at a single timepoint for a single
sample. The output of `analyze` is a *summary* over all 19 runs — the Pareto
ranking plus curvature test — which isn't a measurement, it's a derived
document. Entries (Benchling's notebook-ish object) handle derived documents
well: they accept structured fields plus rendered HTML/markdown bodies, they
back-link to the parent Request, and they show up in a scientist's search
results under "analyses" rather than "measurements."

If a lab wanted per-term rows as first-class Results (for cross-project
aggregation, say), the wrapper is trivial: call `effects_to_benchling_entry`
and then unroll `fields.topTerms.value` into N Result rows against a custom
schema.

## Webhook flow

```
 [ Benchling user ]                                [ Screenase app ]
        |                                                  |
        | create Request (sch_screenase_doe_request)       |
        |------------------------------------------------->|
        |                                                  | handle_request_created:
        |                                                  |   - build design + bench sheet
        |                                                  |   - return Request payload + HTML + CSV
        |                                                  |
        |<-------------------------------------------------|
        | Benchling attaches Entry (bench sheet),          |
        | creates empty Result rows                        |
        |                                                  |
        | scientist runs the bench, fills in yields,       |
        | submits Results                                  |
        |                                                  |
        |------------------------------------------------->|
        |                                                  | handle_results_submitted:
        |                                                  |   - fit OLS main + 2FI
        |                                                  |   - return ranked-effects Entry
        |<-------------------------------------------------|
        | Entry auto-attached to the Request               |
```

## Permissions

The manifest declares the minimum needed:

- `requests.read + write` — read the submitted Request, write back the expanded payload.
- `results.read + write` — create empty Result rows at request time; read them back when submitted.
- `entries.write` — attach the bench sheet and the analysis Entry.
- `schemas.read` — resolve the custom schemas at startup.

No `samples.*` or `projects.*` — Screenase doesn't need to see them.

## What this doesn't cover

- **Inventory integration.** A production deployment would also create Inventory entries for each reagent lot consumed, and subtract volumes. Screenase knows the required volumes (`stock_totals`) but stops at printing them in the bench sheet.
- **Scheduling / fulfillment.** Benchling has request-fulfillment workflows; Screenase doesn't opine on who pipettes what.
- **Plate maps.** A 19-run design fits on a strip; a 48- or 96-run extension would benefit from plate-layout generation, but that's a different feature.
