from __future__ import annotations

import importlib

import pandas as pd
import pytest

streamlit = pytest.importorskip("streamlit")


def test_streamlit_app_imports():
    mod = importlib.import_module("streamlit_app")
    assert hasattr(mod, "main")
    assert hasattr(mod, "generate_from_ui")
    assert hasattr(mod, "build_default_config")


def test_generate_from_ui_returns_expected_shape():
    mod = importlib.import_module("streamlit_app")
    cfg = mod.build_default_config()
    out = mod.generate_from_ui(cfg)
    expected_keys = {
        "design", "volumes", "html", "csv", "coded_csv", "warnings",
        "plate_df", "plate_map_html", "plate", "design_kind", "consumption",
    }
    assert expected_keys.issubset(out.keys())
    assert isinstance(out["design"], pd.DataFrame)
    assert len(out["design"]) == 19
    assert b"NTPs_mM_each" in out["csv"]
    assert "<!DOCTYPE html>" in out["html"]
    # Default options: full factorial, no plate
    assert out["design_kind"] == "full"
    assert out["plate"] is None
    assert out["plate_df"] is None
    assert out["consumption"]


def test_generate_from_ui_ccd_face_centered():
    mod = importlib.import_module("streamlit_app")
    cfg = mod.build_default_config()
    out = mod.generate_from_ui(cfg, design_kind="ccd", alpha="face")
    assert len(out["design"]) == 16 + 8 + 3
    assert out["design_kind"] == "ccd"


def test_generate_from_ui_with_plate():
    mod = importlib.import_module("streamlit_app")
    cfg = mod.build_default_config()
    out = mod.generate_from_ui(cfg, plate="96", plate_layout="column-major")
    assert out["plate"] == "96"
    assert out["plate_df"] is not None
    assert "plate-map" in out["plate_map_html"]
    # Bench sheet now embeds the plate map
    assert "Plate layout" in out["html"]
