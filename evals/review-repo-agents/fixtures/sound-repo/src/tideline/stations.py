"""Load a station's published constituents."""

from __future__ import annotations

import json
from pathlib import Path

from tideline.predict import Constituent

STATIONS = Path(__file__).resolve().parents[2] / "stations"


def load(name: str) -> tuple[list[Constituent], float]:
    """Constituents and chart datum for a station, by file stem."""
    data = json.loads((STATIONS / f"{name}.json").read_text(encoding="utf-8"))
    constituents = [
        Constituent(
            name=c["name"],
            amplitude=c["amplitude"],
            phase_deg=c["phase_deg"],
            speed_deg_per_hour=c["speed_deg_per_hour"],
        )
        for c in data["constituents"]
    ]
    return constituents, data["datum_m"]
