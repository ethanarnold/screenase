"""Property tests for `render_bench_sheet`: HTML escaping + row count."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from screenase import __version__
from screenase.bench_sheet import build_context, render_bench_sheet
from screenase.design import build_design
from screenase.volumes import compute_volumes


@given(prefix=st.text(alphabet="abc ", min_size=1, max_size=5))
@settings(max_examples=20, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_script_tag_in_operator_is_escaped(cfg, prefix: str) -> None:
    """Any <script>…</script> injected via operator must be HTML-escaped."""
    payload = f"{prefix}<script>alert('xss')</script>"
    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    ctx = build_context(
        vol_df, design["is_center"], cfg,
        run_id="prop-test",
        generated_at="2026-04-17",
        lib_version=__version__,
        config_hash="deadbeef",
        operator=payload,
    )
    out = render_bench_sheet(ctx)
    # The unescaped script tag must NOT appear in the rendered HTML.
    assert "<script>alert" not in out
    # The escaped `<script>` and `</script>` tags must appear.
    assert "&lt;script&gt;" in out
    assert "&lt;/script&gt;" in out


@given(run_id=st.text(alphabet="abc-0123456789", min_size=1, max_size=30))
@settings(max_examples=20, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_run_id_appears_in_footer(cfg, run_id: str) -> None:
    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    ctx = build_context(
        vol_df, design["is_center"], cfg,
        run_id=run_id,
        generated_at="2026-04-17",
        lib_version=__version__,
        config_hash="deadbeef",
    )
    out = render_bench_sheet(ctx)
    assert run_id in out


def test_row_count_matches_design_length(cfg) -> None:
    design = build_design(cfg)
    vol_df = compute_volumes(design, cfg)
    ctx = build_context(
        vol_df, design["is_center"], cfg,
        run_id="x",
        generated_at="2026-04-17",
        lib_version=__version__,
        config_hash="x",
    )
    out = render_bench_sheet(ctx)
    # Every run number should appear in the rendered HTML
    for run_idx in design.index:
        assert f">{run_idx}<" in out, f"run {run_idx} missing from bench sheet"
