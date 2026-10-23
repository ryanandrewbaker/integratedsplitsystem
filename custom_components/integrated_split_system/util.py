"""Shared helpers."""

from __future__ import annotations

import re

from .const import MINIMUM_TARGET_SEPARATION_C

_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def normalize_profile_id(name: str) -> str:
    """Derive a stable profile id slug from a display name."""
    slug = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        return "profile"
    if not slug[0].isalpha():
        slug = f"p_{slug}"
    return slug[:64]


def is_valid_profile_id(profile_id: str) -> bool:
    """Return True when profile_id is a safe stored identifier."""
    return bool(_PROFILE_ID_RE.match(profile_id))


def clamp_temperature_band(
    low: float,
    high: float,
    *,
    min_separation: float = MINIMUM_TARGET_SEPARATION_C,
) -> tuple[float, float]:
    """Enforce ordering and minimum heat/cool separation on the virtual band."""
    low_f = float(low)
    high_f = float(high)
    if high_f < low_f:
        low_f, high_f = high_f, low_f
    if high_f - low_f < min_separation:
        high_f = low_f + min_separation
    return low_f, high_f
