# Changelog

All notable changes to Screenase are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

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
