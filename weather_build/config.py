from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BuildConfig:
	api_base: str = "https://dataset.api.hub.geosphere.at/v1"
	resource_id: str = "nwp-v1-1h-2500m"
	model_name: str = "AROME"
	release_prefix: str = "arome"
	asset_prefix: str = "arome"
	asset_time_unit: str = "hours"
	precipitation_parameter: str = "rr_acc"
	precipitation_mode: str = "accumulated"
	precipitation_interval_minutes: int = 60
	cloud_parameter: str | None = "tcc"
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
	negative_precipitation_tolerance_mm: float = 0.5
	precipitation_max_mm: float = 655.35
	cloud_min_tolerance: float = -0.01
	cloud_max_tolerance: float = 1.01
	pmtiles_version: str = "v1.30.1"
	retained_releases: int = 3

	def __post_init__(self) -> None:
		if self.precipitation_mode not in {"accumulated", "interval"}:
			raise ValueError(
				"precipitation_mode muss 'accumulated' oder 'interval' sein."
			)
		if self.asset_time_unit not in {"hours", "minutes"}:
			raise ValueError("asset_time_unit muss 'hours' oder 'minutes' sein.")
		if self.precipitation_interval_minutes < 1:
			raise ValueError("precipitation_interval_minutes muss mindestens 1 sein.")
		if not self.release_prefix or not self.asset_prefix:
			raise ValueError("release_prefix und asset_prefix dürfen nicht leer sein.")
		if self.min_zoom < 0 or self.max_zoom < self.min_zoom:
			raise ValueError("Ungültiger Zoom-Bereich.")
		if not self.min_zoom <= self.aggregate_through_zoom <= self.max_zoom:
			raise ValueError("aggregate_through_zoom muss innerhalb des Zoom-Bereichs liegen.")

	@property
	def parameters(self) -> tuple[str, ...]:
		result = [self.precipitation_parameter]
		if self.cloud_parameter is not None:
			result.append(self.cloud_parameter)
		return tuple(result)

	@property
	def has_cloud(self) -> bool:
		return self.cloud_parameter is not None

	@property
	def precipitation_output_parameter(self) -> str:
		if self.precipitation_interval_minutes == 60:
			return "precipitation_1h"
		return f"precipitation_{self.precipitation_interval_minutes}min"

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
