"""`screenase` CLI — argparse with `generate` and `analyze` subcommands."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from screenase import __version__
from screenase.analyze import analyze_cli, fit_model, optimize_response
from screenase.bench_sheet import write_bench_sheet
from screenase.config import config_hash, load_config
from screenase.design import build_ccd, build_design, build_pb
from screenase.plate import assign_plate, render_plate_map_html, render_plate_map_png
from screenase.volumes import compute_volumes, validate_volumes

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="screenase", description="DoE tool for IVT reaction optimization")
    p.add_argument("-V", "--version", action="version", version=f"screenase {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Generate a DoE screen + bench sheet")
    g.add_argument("--config", type=Path, required=True, help="Path to reaction config YAML")
    g.add_argument("--out-dir", type=Path, required=True, help="Output directory")
    g.add_argument("--seed", type=int, default=None, help="Override config.seed")
    g.add_argument("--export",
                   choices=["benchling", "benchling-inventory", "echo", "ot2"],
                   default=None, action="append",
                   help="Also emit an additional artifact. `benchling` writes the "
                        "Request JSON; `benchling-inventory` writes the inventory "
                        "decrement JSON; `echo` writes a Labcyte Echo transfer CSV; "
                        "`ot2` writes an Opentrons OT-2 Python protocol. "
                        "May be passed multiple times.")
    g.add_argument("--lot-refs", type=Path, default=None,
                   help="JSON file mapping reagents → {containerId, lotId}. "
                        "Used with --export benchling-inventory.")
    g.add_argument("--operator", default="", help="Operator name for bench-sheet sign-off")
    g.add_argument("--plate", choices=["96", "384"], default=None,
                   help="Also assign runs to wells on a plate and emit plate-map PNG + CSV")
    g.add_argument("--plate-layout", choices=["column-major", "row-major", "randomized"],
                   default="column-major", help="How to fill wells when --plate is set")
    g.add_argument("--design", choices=["full", "ccd", "pb"], default="full",
                   help="`full` (default) = 2^k full factorial + center points. "
                        "`ccd` = central-composite follow-up. "
                        "`pb` = Plackett-Burman screening for k > 5.")
    g.add_argument("--alpha", default="face",
                   help="CCD axial distance: `face` (=1, stays within low/high), "
                        "`rotatable` ((2^k)^(1/4)), or a numeric value. Ignored unless --design=ccd.")
    g.add_argument("--pb-runs", type=int, default=12,
                   help="Plackett-Burman run count (8, 12, 16, 20, 24). "
                        "Ignored unless --design=pb.")

    a = sub.add_parser("analyze", help="Analyze a completed screen")
    a.add_argument("results", type=Path, help="Results CSV (with `_coded` factor columns)")
    a.add_argument("--response", required=True, help="Response column name")
    a.add_argument("--out-dir", type=Path, required=True, help="Output directory")

    pj = sub.add_parser("project", help="Project-level organization (init, status)")
    pj_sub = pj.add_subparsers(dest="project_cmd", required=True)
    pj_init = pj_sub.add_parser("init", help="Initialize a new project skeleton")
    pj_init.add_argument("root", type=Path, help="Directory to create the project in")
    pj_init.add_argument("--name", required=True, help="Project display name")
    pj_init.add_argument("--owner", default="", help="Project owner (email or handle)")
    pj_status = pj_sub.add_parser("status", help="Scan screens/ and print a status table")
    pj_status.add_argument("root", type=Path, help="Project root directory")

    po = sub.add_parser("power", help="Sample-size / power calculator")
    po.add_argument("-k", type=int, required=True, help="Number of factors")
    po.add_argument("--effect-std", type=float, required=True,
                    help="Expected coefficient magnitude (coded ±1)")
    po.add_argument("--noise-std", type=float, required=True,
                    help="Per-observation residual σ")
    po.add_argument("--alpha", type=float, default=0.05)
    po.add_argument("--power", type=float, default=0.80)

    sv = sub.add_parser("serve", help="Run the FastAPI webhook server (requires extras)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)

    s = sub.add_parser("benchling-scaffold",
                       help="Emit Benchling Request / Result / Entry schema JSON for admin import")
    s.add_argument("--config", type=Path, required=True, help="Path to reaction config YAML")
    s.add_argument("--out-dir", type=Path, required=True, help="Output directory")

    sch = sub.add_parser("schedule",
                         help="Plan a wall-clock schedule from a plate-layout CSV")
    sch.add_argument("plate_csv", type=Path, help="plate_layout.csv from `screenase generate --plate …`")
    sch.add_argument("--out-dir", type=Path, required=True, help="Output directory")
    sch.add_argument("--incubate-min", type=float, default=120.0)
    sch.add_argument("--read-min", type=float, default=15.0)
    sch.add_argument("--pipet-min-per-run", type=float, default=1.0)

    o = sub.add_parser("optimize", help="Find factor setpoints that maximize the response")
    o.add_argument("results", type=Path, help="Results CSV (with `_coded` factor columns)")
    o.add_argument("--response", required=True, help="Response column name")
    o.add_argument("--config", type=Path, required=True,
                   help="Original reaction config (to write a one-row bench sheet at the optimum)")
    o.add_argument("--out-dir", type=Path, required=True, help="Output directory")
    o.add_argument("--direction", choices=["maximize", "minimize"], default="maximize")
    o.add_argument("--operator", default="", help="Operator name for bench-sheet sign-off")
    return p


def _cmd_generate(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.seed is not None:
        cfg = cfg.model_copy(update={"seed": args.seed})
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.design == "ccd":
        try:
            alpha_arg: float | str = float(args.alpha)
        except (TypeError, ValueError):
            alpha_arg = args.alpha
        design = build_ccd(cfg, alpha=alpha_arg)  # type: ignore[arg-type]
    elif args.design == "pb":
        design = build_pb(cfg, runs=args.pb_runs)
    else:
        design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    warnings = validate_volumes(vol_df, cfg)

    factor_cols = [f.name for f in cfg.factors]
    screen_csv = args.out_dir / "ivt_screen.csv"
    design[factor_cols].to_csv(screen_csv)
    log.info("wrote %s", screen_csv)

    # Results-ready CSV with _coded columns + is_center, for easy feedback to `analyze`
    results_template = args.out_dir / "ivt_screen_coded.csv"
    coded_cols = [c for c in design.columns if c.endswith("_coded")]
    design[factor_cols + coded_cols + ["is_center"]].to_csv(results_template)

    run_id = datetime.now(UTC).strftime("run-%Y%m%d-%H%M%S")
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    cfg_hash = config_hash(cfg)
    is_center = design["is_center"]

    plate_map_html: str | None = None
    assigned = None
    if args.plate:
        assigned = assign_plate(
            design, plate=args.plate, layout=args.plate_layout,
            seed=cfg.seed if args.plate_layout == "randomized" else None,
        )
        plate_csv = args.out_dir / "plate_layout.csv"
        assigned[["plate", "well", "row_letter", "col_number", "is_center"]].to_csv(plate_csv)
        log.info("wrote %s", plate_csv)
        plate_png = args.out_dir / "plate_map.png"
        files = render_plate_map_png(assigned, plate_png, plate=args.plate)
        for f in files:
            log.info("wrote %s", f)
        plate_map_html = render_plate_map_html(assigned, plate=args.plate)

    bench_html = args.out_dir / "ivt_bench_sheet.html"
    write_bench_sheet(
        vol_df, is_center, cfg, bench_html,
        run_id=run_id,
        generated_at=generated_at,
        lib_version=__version__,
        config_hash=cfg_hash,
        warnings=warnings,
        operator=args.operator,
        plate_map_html=plate_map_html,
    )
    log.info("wrote %s", bench_html)

    exports = set(args.export or [])
    if "benchling" in exports:
        from screenase.benchling.entities import design_to_benchling_request
        payload = design_to_benchling_request(design, cfg, run_id=run_id)
        out = args.out_dir / "benchling_request.json"
        out.write_text(json.dumps(payload, indent=2))
        log.info("wrote %s", out)
    if "echo" in exports:
        if assigned is None:
            log.error("--export echo requires --plate")
            return 1
        from screenase.automation import write_echo_csv
        echo_out = args.out_dir / "echo_transfer.csv"
        write_echo_csv(vol_df, assigned, echo_out)
        log.info("wrote %s", echo_out)
    if "ot2" in exports:
        if assigned is None:
            log.error("--export ot2 requires --plate")
            return 1
        from screenase.automation import write_ot2_protocol
        ot2_out = args.out_dir / "ot2_protocol.py"
        write_ot2_protocol(vol_df, assigned, cfg, ot2_out,
                           run_id=run_id, version=__version__,
                           plate_size=int(args.plate))
        log.info("wrote %s", ot2_out)
    if "benchling-inventory" in exports:
        from screenase.benchling.inventory import post_run_inventory_summary
        lot_refs: dict[str, dict[str, str]] = {}
        if args.lot_refs:
            lot_refs = json.loads(Path(args.lot_refs).read_text())
        summary = post_run_inventory_summary(
            vol_df, cfg, lot_refs, run_id=run_id, excess=1.2, dry_run=True,
        )
        out = args.out_dir / "benchling_inventory.json"
        out.write_text(json.dumps(summary, indent=2))
        log.info("wrote %s", out)
        if summary["payload"]["unresolved"]:
            log.warning(
                "%d reagent(s) missing lot refs — pass --lot-refs to resolve",
                len(summary["payload"]["unresolved"]),
            )
        # Lot-expiry warnings — only fire when lot_refs carry expiryDate fields
        if lot_refs:
            from datetime import date

            from screenase.scheduling import check_lot_expiry
            lot_warns = check_lot_expiry(lot_refs, today=date.today().isoformat())
            for w in lot_warns:
                log.warning("lot-expiry: %s (%s) — %s", w.reagent, w.lot_id, w.reason)

    if warnings:
        log.warning("%d volume warning(s) — see bench sheet", len(warnings))
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    result = analyze_cli(args.results, args.response, args.out_dir)
    log.info("wrote %s", result["pareto_png"])
    log.info("wrote %s", result["report_md"])
    if result.get("surface_png"):
        log.info("wrote %s", result["surface_png"])
    log.info("R² = %.3f", result["r2"])
    return 0


def _cmd_project(args: argparse.Namespace) -> int:
    from screenase.project import init_project, project_status

    if args.project_cmd == "init":
        root = init_project(args.root, name=args.name, owner=args.owner)
        log.info("initialized project at %s", root)
        return 0
    if args.project_cmd == "status":
        df = project_status(args.root)
        if df.empty:
            print("(no screens yet — run `screenase generate` inside this project)")
            return 0
        print(df.to_string(index=False))
        return 0
    return 2


def _cmd_power(args: argparse.Namespace) -> int:
    from screenase.multiresponse import recommend_sample_size

    out = recommend_sample_size(
        k=args.k, effect_std=args.effect_std, noise_std=args.noise_std,
        alpha=args.alpha, power=args.power,
    )
    print(f"Recommended for k={args.k}, α={args.alpha}, power={args.power}:")
    print(f"  Factorial runs: {out['factorial_runs']}")
    print(f"  Center points:  {out['recommended_center_points']}")
    print(f"  Total runs:     {out['total_runs']}")
    print(f"  df_resid:       {out['df_resid']}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        log.error("`screenase serve` requires the `[serve]` extra: "
                  "pip install 'screenase[serve]'")
        return 1
    uvicorn.run("screenase.serve:app", host=args.host, port=args.port, reload=False)
    return 0


def _cmd_benchling_scaffold(args: argparse.Namespace) -> int:
    from screenase.benchling.schemas import scaffold_all

    cfg = load_config(args.config)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for kind, schema in scaffold_all(cfg).items():
        out = args.out_dir / f"{kind}_schema.json"
        out.write_text(json.dumps(schema, indent=2))
        log.info("wrote %s", out)
    return 0


def _cmd_schedule(args: argparse.Namespace) -> int:
    import pandas as pd

    from screenase.scheduling import plan_schedule, render_gantt_png

    args.out_dir.mkdir(parents=True, exist_ok=True)
    plate_df = pd.read_csv(args.plate_csv, index_col=0)
    stages = plan_schedule(
        plate_df,
        pipet_min_per_run=args.pipet_min_per_run,
        incubate_min=args.incubate_min,
        read_min=args.read_min,
    )
    png = render_gantt_png(stages, args.out_dir / "schedule.png")
    log.info("wrote %s", png)
    schedule_csv = args.out_dir / "schedule.csv"
    pd.DataFrame([
        {"plate": s.plate, "stage": s.stage,
         "start_min": s.start_min, "end_min": s.end_min}
        for s in stages
    ]).to_csv(schedule_csv, index=False)
    log.info("wrote %s", schedule_csv)
    return 0


def _cmd_optimize(args: argparse.Namespace) -> int:
    import pandas as pd

    cfg = load_config(args.config)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    results = pd.read_csv(args.results)
    factor_cols = [c for c in results.columns if c.endswith("_coded")]
    if not factor_cols:
        log.error("Results CSV lacks `_coded` factor columns.")
        return 1
    fit = fit_model(results, args.response, factor_cols)
    opt = optimize_response(fit, factor_cols, direction=args.direction)

    # Map coded → real per config factor
    by_coded = {f"{f.name}_coded": f for f in cfg.factors}
    real: dict[str, float] = {}
    for c, v in opt["coded"].items():
        f = by_coded.get(c)
        if f is None:
            continue
        mid = (f.low + f.high) / 2.0
        half = (f.high - f.low) / 2.0
        real[f.name] = mid + v * half

    out_md = args.out_dir / "optimum.md"
    lines = [
        f"# Optimum: `{args.response}` ({args.direction})\n\n",
        f"- Predicted response: **{opt['predicted']:.4g}**\n",
        f"- scipy.optimize success: {opt['success']}\n\n",
        "## Setpoints\n\n",
        "| Factor | Coded | Real |\n|---|---:|---:|\n",
    ]
    for f in cfg.factors:
        coded_val = opt["coded"].get(f"{f.name}_coded", 0.0)
        real_val = real.get(f.name, 0.0)
        lines.append(f"| `{f.name}` ({f.unit}) | {coded_val:+.3f} | {real_val:.4g} |\n")
    out_md.write_text("".join(lines))
    log.info("wrote %s", out_md)

    # One-row bench sheet at the optimum
    from datetime import UTC, datetime

    one_row = pd.DataFrame([{**real, "is_center": False}])
    one_row.index = pd.Index([1], name="Run")
    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        half = (f.high - f.low) / 2.0
        one_row[f"{f.name}_coded"] = (one_row[f.name] - mid) / half if half else 0.0
    vol_df = compute_volumes(one_row, cfg)
    warnings = validate_volumes(vol_df, cfg)
    bench_html = args.out_dir / "optimum_bench_sheet.html"
    write_bench_sheet(
        vol_df, one_row["is_center"], cfg, bench_html,
        run_id=datetime.now(UTC).strftime("opt-%Y%m%d-%H%M%S"),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        lib_version=__version__,
        config_hash=config_hash(cfg),
        warnings=warnings,
        operator=args.operator,
    )
    log.info("wrote %s", bench_html)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "generate":
            return _cmd_generate(args)
        if args.cmd == "analyze":
            return _cmd_analyze(args)
        if args.cmd == "optimize":
            return _cmd_optimize(args)
        if args.cmd == "benchling-scaffold":
            return _cmd_benchling_scaffold(args)
        if args.cmd == "schedule":
            return _cmd_schedule(args)
        if args.cmd == "project":
            return _cmd_project(args)
        if args.cmd == "power":
            return _cmd_power(args)
        if args.cmd == "serve":
            return _cmd_serve(args)
    except ValidationError as e:
        log.error("config validation failed:\n%s", e)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
