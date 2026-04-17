from __future__ import annotations

from pathlib import Path

import pytest

from screenase.config import ReactionConfig, load_config

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_CONFIG = ROOT / "examples" / "config.yaml"


@pytest.fixture
def example_config_path() -> Path:
    return EXAMPLE_CONFIG


@pytest.fixture
def cfg() -> ReactionConfig:
    return load_config(EXAMPLE_CONFIG)
