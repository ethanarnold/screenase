"""2^k full factorial + center points + seeded randomization.

Also exports `build_ccd`, a central-composite follow-up design: factorial +
axial (star) points + center points. CCD is the canonical second-phase DoE
when a screening run flags significant curvature (see `analyze.curvature_test`).
"""

from __future__ import annotations

import itertools
from typing import Literal

import numpy as np
import pandas as pd

from screenase.config import ReactionConfig

AlphaMode = Literal["face", "rotatable"]


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


def ccd_alpha(k: int, mode: AlphaMode | float = "face") -> float:
    """Axial distance α in coded units.

    - "face"       → α = 1 (face-centered CCD; no setpoints outside the low/high range)
    - "rotatable"  → α = (2^k)^(1/4) (rotatable CCD; variance depends only on distance from center)
    - numeric      → used verbatim
    """
    if isinstance(mode, (int, float)):
        return float(mode)
    if mode == "face":
        return 1.0
    if mode == "rotatable":
        return float((2 ** k) ** 0.25)
    raise ValueError(f"unknown alpha mode {mode!r}")


def _axial_points_coded(k: int, alpha: float) -> np.ndarray:
    """2k axial (star) points in coded units — one factor at ±α, others at 0."""
    pts = np.zeros((2 * k, k), dtype=float)
    for i in range(k):
        pts[2 * i, i] = -alpha
        pts[2 * i + 1, i] = alpha
    return pts


def build_ccd(
    cfg: ReactionConfig,
    *,
    alpha: AlphaMode | float = "face",
    axial_center_points: int | None = None,
) -> pd.DataFrame:
    """Central-composite design: 2^k factorial + 2k axial points + center points.

    - `alpha="face"` (default) stays within each factor's low/high range
      (recommended when you can't exceed your original ranges in wet-lab reality).
    - `alpha="rotatable"` uses α = (2^k)^(1/4), extending axial setpoints beyond
      low/high — only use this if your stocks and physics allow the larger range.
    - `axial_center_points` overrides the center-point count if given. CCD best
      practice is 3–6 center points; defaults to `cfg.center_points`.

    Returns a DataFrame with real-valued factor columns, `_coded` columns,
    `is_center`, and `design_kind` ∈ {"factorial","axial","center"}.
    """
    k = len(cfg.factors)
    a = ccd_alpha(k, alpha)
    factor_names = [f.name for f in cfg.factors]
    corners = full_factorial(k).astype(float)
    axials = _axial_points_coded(k, a)

    n_center = cfg.center_points if axial_center_points is None else axial_center_points
    centers = np.zeros((n_center, k), dtype=float) if n_center > 0 else np.zeros((0, k))

    kinds = (["factorial"] * len(corners) + ["axial"] * len(axials)
             + ["center"] * len(centers))

    coded = np.vstack([corners, axials, centers])
    df = pd.DataFrame(coded, columns=factor_names)

    # Map coded → real via mid + coded * half
    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        half = (f.high - f.low) / 2.0
        df[f.name] = mid + df[f.name] * half

    df["design_kind"] = kinds
    df = df.sample(frac=1, random_state=cfg.seed).reset_index(drop=True)

    for f in cfg.factors:
        mid = (f.low + f.high) / 2.0
        half = (f.high - f.low) / 2.0
        df[f"{f.name}_coded"] = (df[f.name] - mid) / half if half else 0.0

    df["is_center"] = (df["design_kind"] == "center").to_numpy()
    df.index = pd.Index(range(1, len(df) + 1), name="Run")
    return df
