# Design rationale

## Why a 2⁴ full factorial + 3 center points?

With four factors at two levels, the full factorial costs 16 runs. That's the smallest design that resolves all main effects plus every 2-factor interaction (Resolution V by construction — there's no aliasing because no effects are confounded). At this scale there's no reason to pick a fractional design: the 8-run 2⁴⁻¹ would collapse 2-factor interactions onto 3-factor ones, and the 12-run Plackett–Burman wouldn't separate interactions at all.

The three center points at the factor midpoints buy two things:

1. A **pure-error estimate** of reaction variance, independent of the model. With 3 replicate center runs we get 2 df for pure error, which lets us distinguish "model lack-of-fit" from "experimental noise" if we need to.
2. A **curvature test** — if the mean response at the center differs significantly from the mean of the 16 corners, a linear-plus-interactions model is under-fitting, and a follow-up central-composite or face-centered design is warranted. Screenase computes this as a Welch t-test in `analyze.curvature_test`.

Total: 19 runs per screen. That fits comfortably on two 12-well PCR strips with one reagent-prep blank.

## Why randomize?

`df.sample(frac=1, random_state=seed)` shuffles run order after centers are appended. This matters because pipetting drift, bench temperature changes, and lot-to-lot reagent variation correlate with **run order** in real labs. Randomizing the run order turns that correlation into noise, which OLS handles; without randomization, it becomes a confounder.

The seed is stored in the config and printed in the bench-sheet footer, so the randomization is reproducible but not ordered.

## Why `(x1 + x2 + x3 + x4)**2` and not something richer?

With 19 runs and 11 model terms (1 intercept + 4 main + 6 two-way interactions), we have 8 residual df. That's enough to get meaningful standard errors. Going to three-way interactions would eat the remaining df and produce unstable estimates; we don't have the budget for them here. If a three-way interaction is physically expected, the right response is a larger design, not a richer model on the same data.

## Why a separate `_pipet_uL` suffix for computed volumes?

Because `T7_uL` is both a **factor name** (the volume-based dose of T7 polymerase is the thing being varied) and, in the legacy script, a **pipetting-volume column** in the same DataFrame. When a reagent is dosed by volume rather than by concentration, the two collide. Using `{reagent}_pipet_uL` for computed columns keeps the factor axis clean, so downstream code can always locate factors by their config names and volumes by suffix convention.

## Why Jinja2 + autoescape for the bench sheet?

The legacy script built the HTML with f-strings, which meant any operator name with an angle-bracket character would break the page or — worse — inject script. Jinja with `autoescape=True` is one line of config and one test to assert it works (`test_operator_is_escaped`).

## Why pydantic v2 for config?

The `ReactionConfig` → `config_hash()` pipeline relies on a stable JSON dump (`model_dump(mode="json")` + `json.dumps(sort_keys=True)` + sha256). Pydantic v2's `model_dump` is faster and the `mode="json"` switch deterministically coerces enums, Decimals, and datetimes. Mixing v1/v2 would force us to hand-roll the canonical form.

## What Screenase is not

- It is **not** a general-purpose DoE library. There is one concrete full-factorial builder. Adding Plackett–Burman or central-composite support means adding a module, not configuring a strategy. Keeping the scope narrow is a feature.
- It is **not** a Benchling client. The `screenase.benchling` subpackage shapes payloads for Benchling's API but does not make network calls. See `docs/benchling_mapping.md` for the mapping.
