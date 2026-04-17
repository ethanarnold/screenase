# Screenase — DoE tool for IVT reaction optimization

[![CI](https://github.com/ethanarnold/screenase/actions/workflows/ci.yml/badge.svg)](https://github.com/ethanarnold/screenase/actions/workflows/ci.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://screenase.streamlit.app/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Plan a randomized 2^k full-factorial (or central-composite follow-up) DoE
screen for in-vitro transcription reactions, assign wells on a 96-/384-well
plate, print a bench-ready pipetting sheet, and analyze the resulting yields —
all from a single CLI, a Streamlit web app, or a Benchling-App-shaped Python
subpackage.

> **Live demo:** **[screenase.streamlit.app](https://screenase.streamlit.app/)** — click Generate, download the bench sheet, upload a results CSV to see the Pareto.
> `docs/screenshots/cli_demo.gif` shows the generate → bench sheet → analyze loop.

## Why

Scientists optimizing in-vitro transcription yields typically plan screens by
hand in a spreadsheet: pick factors, pick levels, randomize runs, compute
pipetting volumes per well, print, pipette, measure, eyeball the effects.
Each step is manual, every step is error-prone, and the bench sheet is usually
a one-off file that doesn't round-trip back into analysis.

Screenase automates the whole loop: `config.yaml` → design + bench sheet HTML
→ (bench work) → responses CSV → OLS ranked effects + Pareto plot. The design
is deterministic given the config hash and seed, so an identical screen can be
rerun months later without hunting for the spreadsheet.

## Quickstart

```bash
pip install -e '.[dev,ui]'
screenase generate --config examples/config.yaml --out-dir out/
open out/ivt_bench_sheet.html
```

Edit `examples/config.yaml` to change factors, levels, stocks, or center-point
count. The default reproduces a 4-factor IVT screen (NTPs, MgCl₂, T7, PEG8000).

After the bench run, fill in the response column in `out/ivt_screen_coded.csv`
and:

```bash
screenase analyze my_results.csv --response yield_ug_per_uL --out-dir out/
```

This writes `out/pareto.png` + `out/analysis_report.md` with ranked effects and
a center-point curvature test. If the curvature is significant at α = 0.05,
the report suggests a central-composite follow-up with the exact CLI invocation.

## Plate layout

For screens that ship to a 96- or 384-well plate, pass `--plate`:

```bash
screenase generate --config examples/config.yaml --out-dir out/ --plate 96 --plate-layout column-major
```

This writes `out/plate_layout.csv` + `out/plate_map.png` and embeds the
plate-map table inside the bench sheet. Layout modes: `column-major` (default,
fills A1..H1, then A2..H2, ...), `row-major` (fills A1..A12, then B1..B12, ...),
or `randomized` (seeded shuffle, reproducible).

## Central-composite follow-up

When the curvature test from `screenase analyze` rejects the main-effects model:

```bash
screenase generate --config examples/config.yaml --out-dir out-ccd/ --design ccd --alpha face
```

Emits a 2ᵏ factorial + 2k axial + N center CCD. `--alpha face` (default) keeps
axial setpoints within `low/high`; `--alpha rotatable` uses α = (2ᵏ)^(1/4) for
a rotatable design (only use this if your stocks allow the wider range).

## Customizing factors

```yaml
factors:
  - name: NTPs_mM_each
    low: 5
    high: 10
    unit: mM
    reagent: NTPs
    dosing: concentration
  - name: T7_uL
    low: 0.2
    high: 1.2
    unit: uL
    reagent: T7
    dosing: volume        # volume-based dosing (factor value is already µL)
```

`dosing: concentration` triggers `V = C_target · V_rxn / C_stock`;
`dosing: volume` passes the factor value through as a pipetting volume.

## Live demo

Try it in the browser: **[screenase.streamlit.app](https://screenase.streamlit.app/)**.
The hosted app wraps the same `screenase` package — two tabs:

- **Generate screen**: slider-edit factors, get CSV + rendered bench sheet + download buttons.
- **Analyze results**: upload the coded CSV with your yields filled in, get the Pareto + ranked-effects table.

## Benchling integration

`src/screenase/benchling/` shapes Screenase as a Benchling App: a manifest,
SDK-style webhook handlers, and entity mapping that converts the design /
results / inventory consumption into Benchling Request / Result / Entry /
Container-decrement payload shapes.

Handlers (runnable locally against fixtures, no live tenant needed):

- `handle_request_created` — build the design + bench sheet, return the Request payload.
- `handle_results_submitted` — run OLS on submitted responses, return the Entry payload.
- `handle_reagent_consumed` — sum reagent pipetting, return a container-decrement payload.

Or from the CLI:

```bash
screenase generate --config examples/config.yaml --out-dir out/ \
    --export benchling --export benchling-inventory --lot-refs lot_refs.json
```

- **What runs locally:** webhook handlers against fixture payloads
  (`fixtures/*.json`). `python -c "from screenase.benchling.app import run_fixture; run_fixture('...')"`.
- **What doesn't:** the live deployment. Benchling's Developer Platform is
  enterprise-gated; the shape is present, the tenant is the gap.

See [`docs/benchling_mapping.md`](docs/benchling_mapping.md) for the full
semantics and [`src/screenase/benchling/README.md`](src/screenase/benchling/README.md)
for the subpackage structure.

## Design rationale

Why 2⁴ + 3 center points? Why `(f1 + f2 + f3 + f4)**2`? Why randomize? See
[`docs/design_rationale.md`](docs/design_rationale.md).

## Dev

```bash
pip install -e '.[dev,ui]'
pytest -q
ruff check src tests streamlit_app.py
mypy --ignore-missing-imports src/screenase
streamlit run streamlit_app.py
```

Python ≥ 3.11, CI covers 3.11 and 3.12 on Ubuntu.

## Author

Ethan Arnold — [emailtoethan@gmail.com](mailto:emailtoethan@gmail.com). MIT-licensed.
