from __future__ import annotations

from screenase.bench_sheet import build_context, render_bench_sheet, write_bench_sheet
from screenase.config import ReactionConfig, config_hash
from screenase.design import build_design
from screenase.volumes import compute_volumes, validate_volumes

STABLE_META = dict(
    run_id="run-TEST",
    generated_at="2026-04-16T00:00:00+00:00",
    lib_version="0.1.0",
    config_hash="deadbeefcafe",
)


def _render(cfg: ReactionConfig, **kwargs) -> str:
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    ws = validate_volumes(v, cfg)
    ctx = build_context(v, d["is_center"], cfg, warnings=ws, **{**STABLE_META, **kwargs})
    return render_bench_sheet(ctx)


def test_html_contains_all_run_numbers(cfg: ReactionConfig):
    html = _render(cfg)
    for run in range(1, 20):
        assert f">{run}<" in html, f"Run {run} missing"


def test_center_point_class_count_matches_config(cfg: ReactionConfig):
    html = _render(cfg)
    assert html.count('class="center-point"') == cfg.center_points


def test_config_hash_and_seed_in_footer(cfg: ReactionConfig):
    html = _render(cfg)
    assert STABLE_META["config_hash"] in html
    assert f"<code>{cfg.seed}</code>" in html


def test_operator_is_escaped(cfg: ReactionConfig):
    html = _render(cfg, operator="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_warnings_block_only_when_nonempty(cfg: ReactionConfig):
    # Default config triggers warnings (T7 low + PEG center)
    html = _render(cfg)
    assert "Volume warnings" in html

    # Narrow T7 to volumes above min_pipet and PEG high to no-center-warn
    safe = cfg.model_copy(deep=True)
    for f in safe.factors:
        if f.name == "T7_uL":
            f.low, f.high = 1.0, 1.4
        if f.name == "PEG8000_pct":
            f.low, f.high = 4.0, 6.0
    html2 = _render(safe)
    assert "Volume warnings" not in html2


def test_snapshot_is_deterministic(cfg: ReactionConfig):
    """Rendering twice with identical inputs yields identical HTML."""
    a = _render(cfg)
    b = _render(cfg)
    assert a == b


def test_write_bench_sheet_round_trip(cfg: ReactionConfig, tmp_path):
    d = build_design(cfg)
    v = compute_volumes(d, cfg)
    out = tmp_path / "bench.html"
    write_bench_sheet(
        v, d["is_center"], cfg, out,
        warnings=[], **STABLE_META,
    )
    assert out.exists()
    text = out.read_text()
    assert "IVT Optimization Screen" in text
    assert config_hash(cfg) not in text  # we passed a stub hash; the real one shouldn't leak
