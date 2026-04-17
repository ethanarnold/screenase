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
from screenase.analyze import analyze_cli
from screenase.bench_sheet import write_bench_sheet
from screenase.config import config_hash, load_config
from screenase.design import build_ccd, build_design
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
    g.add_argument("--export", choices=["benchling", "benchling-inventory"],
                   default=None, action="append",
                   help="Also emit Benchling-shaped payloads. `benchling` writes the "
                        "Request JSON; `benchling-inventory` writes the inventory "
                        "decrement JSON. May be passed multiple times.")
    g.add_argument("--lot-refs", type=Path, default=None,
                   help="JSON file mapping reagents → {containerId, lotId}. "
                        "Used with --export benchling-inventory.")
    g.add_argument("--operator", default="", help="Operator name for bench-sheet sign-off")
    g.add_argument("--plate", choices=["96", "384"], default=None,
                   help="Also assign runs to wells on a plate and emit plate-map PNG + CSV")
    g.add_argument("--plate-layout", choices=["column-major", "row-major", "randomized"],
                   default="column-major", help="How to fill wells when --plate is set")
    g.add_argument("--design", choices=["full", "ccd"], default="full",
                   help="`full` (default) = 2^k full factorial + center points. "
                        "`ccd` = central-composite follow-up (factorial + axial + center).")
    g.add_argument("--alpha", default="face",
                   help="CCD axial distance: `face` (=1, stays within low/high), "
                        "`rotatable` ((2^k)^(1/4)), or a numeric value. Ignored unless --design=ccd.")

    a = sub.add_parser("analyze", help="Analyze a completed screen")
    a.add_argument("results", type=Path, help="Results CSV (with `_coded` factor columns)")
    a.add_argument("--response", required=True, help="Response column name")
    a.add_argument("--out-dir", type=Path, required=True, help="Output directory")
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

    if warnings:
        log.warning("%d volume warning(s) — see bench sheet", len(warnings))
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    result = analyze_cli(args.results, args.response, args.out_dir)
    log.info("wrote %s", result["pareto_png"])
    log.info("wrote %s", result["report_md"])
    log.info("R² = %.3f", result["r2"])
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "generate":
            return _cmd_generate(args)
        if args.cmd == "analyze":
            return _cmd_analyze(args)
    except ValidationError as e:
        log.error("config validation failed:\n%s", e)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
