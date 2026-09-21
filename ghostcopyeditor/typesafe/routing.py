"""Toggle resolution and Noul band routing."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ghostcopyeditor.config import GhostCopyeditorConfig

# Mid-band lower bound; upper bound is typesafe_noul_positive_threshold (config).
NOUL_MID_BAND_LOW = 0.35


def resolve_typesafe_enabled(
    cli_flag: bool | None, cfg: GhostCopyeditorConfig
) -> bool:
    """CLI flag wins when not None; else config; else False."""
    if cli_flag is not None:
        return bool(cli_flag)
    return bool(cfg.typesafe_enabled)


def noul_band(
    noul: float,
    *,
    positive_threshold: float = 0.65,
    mid_low: float = NOUL_MID_BAND_LOW,
) -> str:
    """Return ``positive``, ``mid``, or ``negative`` for a Noul probability."""
    if noul >= positive_threshold:
        return "positive"
    if noul >= mid_low:
        return "mid"
    return "negative"
