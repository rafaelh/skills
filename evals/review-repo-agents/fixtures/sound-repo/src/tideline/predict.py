"""Harmonic tide prediction for a single station."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Constituent:
    name: str
    amplitude: float
    phase_deg: float
    speed_deg_per_hour: float


def height(constituents: list[Constituent], hours: float, datum: float = 0.0) -> float:
    """Height in metres above chart datum at `hours` after the epoch.

    Phases are Greenwich phase lags in degrees, which is what the hydrographic
    office publishes; converting to radians here keeps the station files readable.
    """
    total = datum
    for c in constituents:
        angle = math.radians(c.speed_deg_per_hour * hours - c.phase_deg)
        total += c.amplitude * math.cos(angle)
    return total
