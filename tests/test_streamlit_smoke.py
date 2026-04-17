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
    assert set(out.keys()) == {"design", "volumes", "html", "csv", "coded_csv", "warnings"}
    assert isinstance(out["design"], pd.DataFrame)
    assert len(out["design"]) == 19
    assert b"NTPs_mM_each" in out["csv"]
    assert "<!DOCTYPE html>" in out["html"]
