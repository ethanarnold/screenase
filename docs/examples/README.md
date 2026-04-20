# Worked examples

Pre-rendered artifacts from the CLI, so you can browse the look of a
screenase run without cloning or installing anything. Everything here
was produced from `examples/config.yaml` with the commands shown per
subdirectory; regenerate locally with `pip install -e '.[dev,ui,serve,pdf]'`.

| Folder | Shows | How it was generated |
| --- | --- | --- |
| [`flat/`](flat/) | 96-well plate layout, HTML bench sheet, **branded PDF bench sheet**, plate-map PNG | `screenase generate --config examples/config.yaml --out-dir docs/examples/flat --plate 96 --plate-layout column-major --pdf` |
| [`ccd/`](ccd/) | Central-composite follow-up design (factorial + axial + center) | `screenase generate --config examples/config.yaml --out-dir docs/examples/ccd --design ccd --alpha face` |
| [`analyze/`](analyze/) | Full stats pack: narrated `analysis_report.md`, Pareto, half-normal, residuals, 2-factor surface | `screenase analyze examples/results_simulated.csv --response yield_ug_per_uL --out-dir docs/examples/analyze` |
| [`optimize/`](optimize/) | Desirability-maximized factor setpoint + bench sheet for the single optimal run | `screenase optimize examples/results_simulated.csv --response yield_ug_per_uL --out-dir docs/examples/optimize` |
| [`schedule/`](schedule/) | Wall-clock schedule + timeline PNG from a plate-layout CSV | `screenase schedule docs/examples/flat/plate_layout.csv --out-dir docs/examples/schedule` |
| [`project/`](project/) | Project-scoped screen tree (multi-screen organization) | `screenase project init …` |
| [`benchling/`](benchling/) | Benchling Request / Result / Entry schema JSON, ready for admin import | `screenase benchling-scaffold --out-dir docs/examples/benchling` |

Highlights worth clicking:

- [`flat/ivt_bench_sheet.pdf`](flat/ivt_bench_sheet.pdf) — branded,
  print-ready pipetting sheet with embedded plate map.
- [`flat/plate_map.png`](flat/plate_map.png) — color-coded 96-well layout.
- [`analyze/analysis_report.md`](analyze/analysis_report.md) — OLS fit
  with auto-narrated plain-English summary, ranked effects, curvature
  test, and an auto-generated CCD follow-up recommendation.
- [`analyze/pareto.png`](analyze/pareto.png),
  [`analyze/half_normal.png`](analyze/half_normal.png),
  [`analyze/residuals.png`](analyze/residuals.png),
  [`analyze/surface.png`](analyze/surface.png) — the diagnostic plot set.
