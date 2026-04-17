"""2^k full factorial + center points + seeded randomization."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from screenase.config import ReactionConfig


def full_factorial(k: int) -> np.ndarray:
    """Coded ±1 corners of the 2^k hypercube."""
    return np.array(list(itertools.product([-1, 1], repeat=k)), dtype=int)


def build_design(cfg: ReactionConfig) -> pd.DataFrame:
    """Real + `<factor>_coded` + `is_center`, Run-indexed (1..N)."""
    factor_names = [f.name for f in cfg.factors]
    k = len(cfg.factors)
    coded = full_factorial(k)

    df = pd.DataFrame(coded, columns=factor_names).astype(float)
    for f in cfg.factors:
        df[f.name] = df[f.name].map({-1.0: f.low, 1.0: f.high})

    if cfg.center_points > 0:
        center_row = {f.name: (f.low + f.high) / 2.0 for f in cfg.factors}
        centers = pd.DataFrame([center_row] * cfg.center_points)
        df = pd.concat([df, centers], ignore_index=True)

    df = df.sample(frac=1, random_state=cfg.seed).reset_index(drop=True)

    df["is_center"] = is_center_point(df, cfg)
    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        half = (f.high - f.low) / 2.0
        df[f"{f.name}_coded"] = (df[f.name] - mid) / half if half else 0.0

    df.index = pd.Index(range(1, len(df) + 1), name="Run")
    return df


def is_center_point(df: pd.DataFrame, cfg: ReactionConfig) -> pd.Series:
    centers = {f.name: (f.low + f.high) / 2.0 for f in cfg.factors}
    tol = 1e-6
    mask = np.ones(len(df), dtype=bool)
    for name, mid in centers.items():
        mask &= np.abs(df[name].to_numpy() - mid) < tol
    return pd.Series(mask, index=df.index, name="is_center")
