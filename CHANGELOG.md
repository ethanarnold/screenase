# Changelog

All notable changes to Screenase are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [0.5.0] — 2026-04-17

### Added

- **`screenase.diagnostics` module.** Six new post-hoc analyses layered on
  top of the OLS fit:
  - `render_residual_diagnostics` — QQ / residuals-vs-fitted / scale-location
    triptych; auto-flags `|studentized residual| > 3`.
  - `lack_of_fit_test` — pure-error vs lack-of-fit F test from center-point
    replicates; surfaces an ANOVA-style p-value in `analysis_report.md`.
  - `bootstrap_coefficient_ci` — case-resampling bootstrap CIs + `p_boot`
    for small-N screens where normal-theory CIs are optimistic.
  - `half_normal_plot` — rank-based |t| vs half-normal quantiles; labels
    the top 3 terms as the real effects.
  - `compare_models` — AICc / BIC / adjusted R² comparison of main-only vs
    main+2FI vs (if ≥ 3 coded levels) quadratic fits.
  - `heteroscedasticity_tests` — Breusch-Pagan + White LM tests with p-values.
- `analyze_cli` now emits `residuals.png`, `half_normal.png`, and extends
  `analysis_report.md` with a Diagnostics + Model selection section.

## [0.4.0] — 2026-04-17

### Added

- **Benchling schema scaffolding (`screenase benchling-scaffold` +
  `benchling.schemas`):** emits Request / Result / Entry schema JSON files
  a tenant admin can paste into Benchling's schema builder.
- **Echo 525 transfer export (`automation.build_echo_transfer_csv`):** one
  row per reagent × destination well, volumes in nL (Echo convention).
  CLI: `--export echo` (requires `--plate`).
- **Opentrons OT-2 protocol export (`automation.build_ot2_protocol`):**
  emits a `pipette.transfer(...)` stub per pipetting step, ready to paste
  into the Opentrons app. CLI: `--export ot2` (requires `--plate`).
- **Wall-clock schedule (`screenase schedule` + `scheduling.plan_schedule`):**
  Gantt-style PNG + schedule CSV of pipet → incubate → read stages across
  plates.
- **Lot-expiry warnings (`scheduling.check_lot_expiry`):** fire on
  `--export benchling-inventory` when the `--lot-refs` JSON carries
  `expiryDate` fields — flags expired + soon-to-expire lots in the log.
- **Round-trip Entry ingestion (`benchling.app.handle_entry_completed` +
  `fixtures/entry_completed.json`):** parses a completed Benchling Entry's
  results table, refits OLS, and returns an Entry update payload that
  writes the analysis (top term, R²) back onto the same Entry.

## [0.3.0] — 2026-04-17

### Added

- **Response surface contour plots (`analyze.surface_plot`):** 2D contour over
  the two most-significant factors from an OLS fit, others held at coded zero.
  `analyze_cli` now emits `surface.png` alongside `pareto.png`.
- **Desirability optimization (`screenase optimize` subcommand + `analyze.optimize_response`):**
  L-BFGS-B on the fitted polynomial inside coded bounds; emits `optimum.md`
  plus a one-row `optimum_bench_sheet.html` for the predicted setpoints.
  Streamlit analyze tab surfaces the optimum inline.
- **Plackett-Burman screening design (`design.build_pb`, `design.plackett_burman`):**
  8/12/16/20/24-run Hadamard construction for `k > 5`. CLI: `--design pb
  --pb-runs N`. Streamlit adds a PB option in the design-type radio.

## [0.2.0] — 2026-04-17

### Added

- **Plate-layout generator (`screenase.plate`):** assigns design runs to wells
  on 96- or 384-well plates in column-major, row-major, or seeded-random order.
  Spills across plates automatically when runs exceed one plate. Emits
  `plate_layout.csv`, `plate_map.png`, and an inline HTML plate-map embedded in
  the bench sheet. CLI: `--plate {96,384} --plate-layout …`.
- **Central-composite (CCD) follow-up design (`design.build_ccd`):** 2ᵏ
  factorial + 2k axial + N center points. Supports `alpha="face"` (α=1, stays
  within low/high), `alpha="rotatable"` (α=(2ᵏ)^(1/4)), or a numeric α.
  Surfaced via `--design ccd --alpha {face,rotatable,N}`.
- **Curvature-driven follow-up recommendation (`analyze.recommend_followup`):**
  when the center-point curvature test rejects the flat model at α=0.05, the
  analysis report surfaces a ready-to-run `screenase generate --design ccd …`
  CLI suggestion explaining *why* a quadratic model is warranted.
- **Benchling inventory integration (`benchling.inventory`):**
  `compute_reagent_consumption`, `build_inventory_decrement_payload`, and
  `post_run_inventory_summary` shape a container-decrement payload that maps
  per-reagent µL consumption (scaled by excess) to Benchling container / lot
  references. New webhook handler `handle_reagent_consumed` + fixture
  `fixtures/reagent_consumed.json`. CLI: `--export benchling-inventory
  [--lot-refs refs.json]`.
- **Hypothesis-based property tests (`tests/test_design_hypothesis.py`):**
  50 generated configurations per invariant prove row count, corner coverage,
  center-point midpoint equality, coded ±1 structure, and seed determinism for
  2 ≤ k ≤ 5 and 0 ≤ center_points ≤ 6.
- `Factor.display` override so factor columns on the bench sheet can render
  pretty labels like `MgCl₂ (mM)` without renaming the underlying factor.
- Streamlit UI: design-type toggle (full / CCD), axial-α slider, plate-layout
  picker with embedded plate map, inventory-consumption expander, curvature
  follow-up recommendation in the analyze tab.

### Changed

- `bench_sheet.build_context` / `write_bench_sheet` now accept an optional
  `plate_map_html` snippet that's rendered as a new section on the bench sheet
  when the plate-layout generator has been invoked.
- CLI `--export` is now repeatable and accepts `benchling-inventory` in
  addition to `benchling`.

### Notes

- Adds `hypothesis>=6.100` to the `[dev]` extra.
- `build_design` and the byte-identical CSV contract for the default config +
  `seed=42` are unchanged — CCD is an additive, opt-in second-phase design.
- Benchling-SDK imports remain lazy; the core package does not require the
  SDK to be installed.

## [0.1.0] — 2026-04-17

Initial release. Core package, CLI, Streamlit frontend, Benchling-App-shaped
subpackage, 42 tests across 7 modules, CI on Python 3.11 + 3.12. See git
history for the detailed scope.
