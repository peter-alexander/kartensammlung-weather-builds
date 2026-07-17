from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BuildConfig:
	api_base: str = "https://dataset.api.hub.geosphere.at/v1"
	resource_id: str = "nwp-v1-1h-2500m"
	precipitation_parameter: str = "rr_acc"
	cloud_parameter: str = "tcc"
	min_zoom: int = 3
	max_zoom: int = 8
	aggregate_through_zoom: int = 5
	tile_size: int = 256
	precipitation_units_per_mm: int = 100
	cloud_channel_max: int = 255
	request_value_limit: int = 10_000_000
	request_safety_factor: float = 0.98
	request_timeout_seconds: int = 300
	request_retries: int = 5
	negative_precipitation_tolerance_mm: float = 0.05
	precipitation_max_mm: float = 655.35
	cloud_min_tolerance: float = -0.01
	cloud_max_tolerance: float = 1.01
	pmtiles_version: str = "v1.30.1"
	release_prefix: str = "arome"
	retained_releases: int = 3

	@property
	def parameters(self) -> tuple[str, str]:
		return self.precipitation_parameter, self.cloud_parameter

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)


def load_config(path: Path | None) -> BuildConfig:
	if path is None:
		return BuildConfig()

	with path.open("r", encoding="utf-8") as handle:
		data = json.load(handle)

	if not isinstance(data, dict):
		raise ValueError("Die Konfigurationsdatei muss ein JSON-Objekt enthalten.")

	allowed = {field.name for field in fields(BuildConfig)}
	unknown = sorted(set(data) - allowed)
	if unknown:
		raise ValueError(f"Unbekannte Konfigurationswerte: {', '.join(unknown)}")

	return BuildConfig(**data)
