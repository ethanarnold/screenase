"""Pydantic models + YAML loader + reproducible config hash."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Factor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    low: float
    high: float
    unit: str
    reagent: str
    dosing: Literal["concentration", "volume"] = "concentration"


class Stock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    concentration: float
    unit: str


class ReactionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reaction_volume_uL: float
    dna_template_uL: float
    center_points: int = 3
    seed: int = 42
    factors: list[Factor] = Field(min_length=1)
    stocks: dict[str, Stock]
    fixed_reagents: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _factors_reference_known_stocks(self) -> ReactionConfig:
        missing = sorted({f.reagent for f in self.factors} - set(self.stocks))
        if missing:
            raise ValueError(
                f"factors reference unknown stocks: {missing} "
                f"(known stocks: {sorted(self.stocks)})"
            )
        return self


def load_config(path: Path | str) -> ReactionConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return ReactionConfig.model_validate(raw)


def config_hash(cfg: ReactionConfig) -> str:
    """Deterministic 12-hex-char sha256 over a canonically-ordered JSON dump."""
    canonical = json.dumps(cfg.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
