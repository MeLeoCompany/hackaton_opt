from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    osm_path: Path
    gtfs_path: Path
    source_wait_seconds: int
    metro_entry_seconds: int
    metro_exit_seconds: int
    reliability_buffer_ratio: float

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            osm_path=Path(
                os.getenv(
                    "R5_OSM_PATH",
                    "/data/osm/central-fed-district-latest.osm.pbf",
                )
            ),
            gtfs_path=Path(
                os.getenv("R5_GTFS_PATH", "/data/gtfs/moscow-pilot.gtfs.zip")
            ),
            source_wait_seconds=int(os.getenv("R5_SOURCE_WAIT_SECONDS", "900")),
            metro_entry_seconds=int(os.getenv("R5_METRO_ENTRY_SECONDS", "240")),
            metro_exit_seconds=int(os.getenv("R5_METRO_EXIT_SECONDS", "240")),
            reliability_buffer_ratio=float(
                os.getenv("R5_RELIABILITY_BUFFER_RATIO", "0.10")
            ),
        )
        if settings.source_wait_seconds < 0:
            raise ValueError("R5_SOURCE_WAIT_SECONDS не может быть отрицательным")
        if settings.metro_entry_seconds < 0 or settings.metro_exit_seconds < 0:
            raise ValueError("штрафы входа и выхода не могут быть отрицательными")
        if not math.isfinite(settings.reliability_buffer_ratio) or not (
            0 <= settings.reliability_buffer_ratio <= 1
        ):
            raise ValueError("R5_RELIABILITY_BUFFER_RATIO должен быть от 0 до 1")
        return settings
