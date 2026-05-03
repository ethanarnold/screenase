# Screenase — DoE tool for IVT reaction optimization

[![CI](https://github.com/ethanarnold/screenase/actions/workflows/ci.yml/badge.svg)](https://github.com/ethanarnold/screenase/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/screenase.svg)](https://pypi.org/project/screenase/)
[![Live demo](https://img.shields.io/badge/demo-screenase.com-5E35B1?logo=huggingface&logoColor=white)](https://screenase.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Optimizing reactions one-variable-at-a-time is slow and costly. Design of
Experiments (DoE) is the statistical alternative. You do fewer runs and get more
information per run. 

**I wanted to use DoE for my own experiments,** but found that no DoE software existed that was **free, fast,
and tailor-made for biochemists**. That's why I built **Screenase**.

Screenase is a website that designs DoE screens for in-vitro transcription
reactions, builds bench-ready pipetting sheets, and analyzes the resulting
yields. Under the hood it generates 2ᵏ full-factorial designs (or
central-composite follow-ups), lays runs out on 96-/384-well plates, and runs
OLS + Pareto analysis on the returned data.

**Distribution surfaces:** [Streamlit web app](https://screenase.com) · [screenase-latch](https://github.com/ethanarnold/screenase-latch) · [screenase-benchling-app](https://github.com/ethanarnold/screenase-benchling-app) · [screenase-foundry](https://github.com/ethanarnold/screenase-foundry)
**Built by** Ethan Arnold ([emailtoethan@gmail.com](mailto:emailtoethan@gmail.com))

> **Live demo:** **[screenase.com](https://screenase.com)** — set your parameters, click Generate, download the bench sheet, upload a results CSV for analysis.

## Why

Even DoE done by hand in a spreadsheet stays painful: pick factors and levels,
randomize runs, compute pipetting volumes per well, print, pipette, measure,
eyeball the effects. Every step is error-prone, and the bench sheet is usually
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

Try it in the browser: **[screenase.com](https://screenase.com)**
(hosted on Hugging Face Spaces; source at [github.com/ethanarnold/screenase](https://github.com/ethanarnold/screenase)).
The hosted app wraps the same `screenase` package — two tabs:

- **Generate screen**: slider-edit factors, get CSV + rendered bench sheet + download buttons.
- **Analyze results**: upload the coded CSV with your yields filled in, get the Pareto + ranked-effects table.

## Worked examples

Pre-rendered artifacts (bench-sheet PDF, plate map, diagnostic plots, narrated
analysis report, CCD follow-up, Benchling schema JSON) live in
[`docs/examples/`](docs/examples/) — browse the look of a real run without
cloning. See [`docs/examples/README.md`](docs/examples/README.md) for the
regeneration commands.

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

## Distribution surfaces

The same screenase planning + analysis logic is wrapped for three additional
deployment targets, each in its own repo:

- **[screenase-latch](https://github.com/ethanarnold/screenase-latch)** —
  Latch workflow (`@workflow screenase_doe`). One `latch register .` away from
  a callable workflow on the Latch platform.
- **[screenase-benchling-app](https://github.com/ethanarnold/screenase-benchling-app)** —
  Benchling App (manifest, four webhook handlers, FastAPI server with HMAC).
  Extracted from `src/screenase/benchling/`, upgraded to the explicit-subscriptions
  manifest format.
- **[screenase-foundry](https://github.com/ethanarnold/screenase-foundry)** —
  Palantir Foundry ontology + OSDK React app + ready-to-PR
  [aip-community-registry](https://github.com/palantir/aip-community-registry)
  bundle.

Each is a thin wrapper — the heavy lifting stays in this package.

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
