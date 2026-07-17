from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import math
from pathlib import Path
import re
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import BuildConfig

LOGGER = logging.getLogger(__name__)


class GeoSphereError(RuntimeError):
	"""Raised for invalid metadata or failed GeoSphere requests."""


@dataclass(frozen=True)
class BoundingBox:
	south: float
	west: float
	north: float
	east: float

	def api_value(self) -> str:
		return f"{self.south:.10g},{self.west:.10g},{self.north:.10g},{self.east:.10g}"

	def maplibre_value(self) -> list[float]:
		return [self.west, self.south, self.east, self.north]


@dataclass(frozen=True)
class ProbeResult:
	reference_time: datetime
	forecast_length: int
	step: timedelta
	bbox: BoundingBox
	spatial_resolution: tuple[float, float]
	spatial_resolution_unit: str
	grid_width: int
	grid_height: int
	grid_points: int
	tag: str
	metadata: dict[str, Any]

	@property
	def valid_times(self) -> list[datetime]:
		return [self.reference_time + index * self.step for index in range(self.forecast_length)]


@dataclass(frozen=True)
class DownloadChunk:
	index: int
	start: datetime
	end: datetime
	time_count: int
	path: Path


class GeoSphereClient:
	def __init__(self, config: BuildConfig) -> None:
		self.config = config
		self.session = requests.Session()
		retry = Retry(
			total=config.request_retries,
			connect=config.request_retries,
			read=config.request_retries,
			status=config.request_retries,
			backoff_factor=1.5,
			status_forcelist=(429, 500, 502, 503, 504),
			allowed_methods=frozenset({"GET"}),
			respect_retry_after_header=True
		)
		self.session.mount("https://", HTTPAdapter(max_retries=retry))
		self.session.headers.update({"User-Agent": "kartensammlung-weather-builds/0.1"})

	@property
	def grid_endpoint(self) -> str:
		return f"{self.config.api_base}/grid/forecast/{self.config.resource_id}"

	@property
	def metadata_endpoint(self) -> str:
		return f"{self.grid_endpoint}/metadata"

	def get_metadata(self) -> dict[str, Any]:
		LOGGER.info("Lade GeoSphere-Metadaten")
		response = self.session.get(
			self.metadata_endpoint,
			timeout=self.config.request_timeout_seconds
		)
		response.raise_for_status()
		metadata = response.json()
		if not isinstance(metadata, dict):
			raise GeoSphereError("Die GeoSphere-Metadaten sind kein JSON-Objekt.")
		return metadata

	def probe(self, forecast_offset: int = 0) -> ProbeResult:
		metadata = self.get_metadata()
		parameter_names = _parameter_names(metadata)
		missing = [name for name in self.config.parameters if name not in parameter_names]
		if missing:
			raise GeoSphereError(f"Parameter fehlen in den Metadaten: {', '.join(missing)}")

		reference_times = _reference_times(metadata)
		if forecast_offset < 0 or forecast_offset >= len(reference_times):
			raise GeoSphereError(
				f"forecast_offset={forecast_offset} ist ungültig; verfügbar sind 0 bis {len(reference_times) - 1}."
			)

		reference_time = reference_times[forecast_offset]
		forecast_length = _positive_int(metadata, "forecast_length", "forecastLength")
		step = _forecast_step(metadata, self.config.resource_id)
		bbox = _bounding_box(metadata)
		resolution, resolution_unit = _spatial_resolution(metadata)
		grid_width, grid_height = _grid_shape(bbox, resolution)
		grid_points = grid_width * grid_height
		tag = f"{self.config.release_prefix}-{reference_time:%Y%m%dT%H%MZ}"

		return ProbeResult(
			reference_time=reference_time,
			forecast_length=forecast_length,
			step=step,
			bbox=bbox,
			spatial_resolution=resolution,
			spatial_resolution_unit=resolution_unit,
			grid_width=grid_width,
			grid_height=grid_height,
			grid_points=grid_points,
			tag=tag,
			metadata=metadata
		)

	def plan_downloads(self, probe: ProbeResult, directory: Path) -> list[DownloadChunk]:
		value_budget = math.floor(self.config.request_value_limit * self.config.request_safety_factor)
		values_per_time = probe.grid_points * len(self.config.parameters)
		max_times_per_request = value_budget // values_per_time
		if max_times_per_request < 1:
			raise GeoSphereError(
				"Das vollständige Raster überschreitet bereits für einen Zeitpunkt das NetCDF-Request-Limit."
			)

		directory.mkdir(parents=True, exist_ok=True)
		valid_times = probe.valid_times
		chunks: list[DownloadChunk] = []
		for chunk_index, start_index in enumerate(range(0, len(valid_times), max_times_per_request)):
			chunk_times = valid_times[start_index:start_index + max_times_per_request]
			chunks.append(
				DownloadChunk(
					index=chunk_index,
					start=chunk_times[0],
					end=chunk_times[-1],
					time_count=len(chunk_times),
					path=directory / f"source-{chunk_index:02d}.nc"
				)
			)

		LOGGER.info(
			"Plane %d NetCDF-Abfragen mit höchstens %d Zeitpunkten pro Abfrage",
			len(chunks),
			max_times_per_request
		)
		return chunks

	def download_chunks(self, probe: ProbeResult, chunks: Iterable[DownloadChunk]) -> list[dict[str, Any]]:
		records: list[dict[str, Any]] = []
		for chunk in chunks:
			offset = self._resolve_current_offset(probe.reference_time)
			params: list[tuple[str, str | int]] = [
				*(('parameters', parameter) for parameter in self.config.parameters),
				('bbox', probe.bbox.api_value()),
				('forecast_offset', offset),
				('start', _api_time(chunk.start)),
				('end', _api_time(chunk.end)),
				('output_format', 'netcdf'),
				('filename', chunk.path.stem)
			]
			LOGGER.info(
				"Lade NetCDF-Teil %d: %s bis %s (Offset %d)",
				chunk.index,
				_api_time(chunk.start),
				_api_time(chunk.end),
				offset
			)
			response = self.session.get(
				self.grid_endpoint,
				params=params,
				timeout=self.config.request_timeout_seconds,
				stream=True
			)
			response.raise_for_status()

			temporary = chunk.path.with_suffix(".nc.part")
			with temporary.open("wb") as handle:
				for block in response.iter_content(chunk_size=1024 * 1024):
					if block:
						handle.write(block)
			_validate_netcdf_magic(temporary)
			temporary.replace(chunk.path)

			records.append(
				{
					"chunk": chunk.index,
					"start": _iso_time(chunk.start),
					"end": _iso_time(chunk.end),
					"time_count": chunk.time_count,
					"forecast_offset_used": offset,
					"bytes": chunk.path.stat().st_size,
					"request_url": response.url
				}
			)
		return records

	def _resolve_current_offset(self, selected_reference_time: datetime) -> int:
		metadata = self.get_metadata()
		for index, reference_time in enumerate(_reference_times(metadata)):
			if reference_time == selected_reference_time:
				return index
		raise GeoSphereError(
			"Der ausgewählte Modelllauf ist während des Builds aus der verfügbaren Forecast-Liste verschwunden."
		)


def write_probe_json(probe: ProbeResult, path: Path) -> None:
	payload = {
		"reference_time": _iso_time(probe.reference_time),
		"forecast_length": probe.forecast_length,
		"step_seconds": int(probe.step.total_seconds()),
		"bbox": probe.bbox.maplibre_value(),
		"spatial_resolution": list(probe.spatial_resolution),
		"spatial_resolution_unit": probe.spatial_resolution_unit,
		"grid_width": probe.grid_width,
		"grid_height": probe.grid_height,
		"grid_points": probe.grid_points,
		"tag": probe.tag
	}
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as handle:
		json.dump(payload, handle, ensure_ascii=False, indent=2)
		handle.write("\n")


def write_github_output(probe: ProbeResult, path: Path) -> None:
	with path.open("a", encoding="utf-8") as handle:
		handle.write(f"tag={probe.tag}\n")
		handle.write(f"reference_time={_iso_time(probe.reference_time)}\n")
		handle.write(f"forecast_length={probe.forecast_length}\n")


def _parameter_names(metadata: dict[str, Any]) -> set[str]:
	parameters = metadata.get("parameters", [])
	result: set[str] = set()
	if isinstance(parameters, dict):
		result.update(str(name) for name in parameters)
	elif isinstance(parameters, list):
		for item in parameters:
			if isinstance(item, str):
				result.add(item)
			elif isinstance(item, dict) and "name" in item:
				result.add(str(item["name"]))
	return result


def _reference_times(metadata: dict[str, Any]) -> list[datetime]:
	values = metadata.get("available_forecast_reftimes") or metadata.get("availableForecastReftimes")
	if not isinstance(values, list) or not values:
		last = metadata.get("last_forecast_reftime") or metadata.get("lastForecastReftime")
		if last is None:
			raise GeoSphereError("Keine Forecast-Referenzzeiten in den Metadaten gefunden.")
		values = [last]
	return [_parse_datetime(str(value)) for value in values]


def _bounding_box(metadata: dict[str, Any]) -> BoundingBox:
	value = metadata.get("bbox_outer") or metadata.get("bboxOuter") or metadata.get("bbox")
	if isinstance(value, dict):
		lookup = {str(key).lower(): item for key, item in value.items()}
		try:
			return BoundingBox(
				south=float(lookup["south"]),
				west=float(lookup["west"]),
				north=float(lookup["north"]),
				east=float(lookup["east"])
			)
		except KeyError as exc:
			raise GeoSphereError(f"Unbekanntes bbox_outer-Objekt: {value!r}") from exc
	if isinstance(value, (list, tuple)) and len(value) == 4:
		south, west, north, east = (float(item) for item in value)
		return BoundingBox(south=south, west=west, north=north, east=east)
	if isinstance(value, str):
		parts = [float(item.strip()) for item in value.split(",")]
		if len(parts) == 4:
			return BoundingBox(south=parts[0], west=parts[1], north=parts[2], east=parts[3])
	raise GeoSphereError(f"bbox_outer konnte nicht gelesen werden: {value!r}")


def _spatial_resolution(metadata: dict[str, Any]) -> tuple[tuple[float, float], str]:
	value = metadata.get("spatial_resolution") or metadata.get("spatialResolution")
	unit = str(metadata.get("spatial_resolution_unit") or metadata.get("spatialResolutionUnit") or "")
	if isinstance(value, (list, tuple)) and len(value) == 2:
		return (abs(float(value[0])), abs(float(value[1]))), unit

	legacy = metadata.get("spatial_resolution_m") or metadata.get("spatialResolutionM")
	if legacy is not None:
		resolution = abs(float(legacy))
		return (resolution, resolution), "m"
	raise GeoSphereError("Keine räumliche Auflösung in den Metadaten gefunden.")


def _grid_shape(bbox: BoundingBox, resolution: tuple[float, float]) -> tuple[int, int]:
	dx, dy = resolution
	width = round((bbox.east - bbox.west) / dx) + 1
	height = round((bbox.north - bbox.south) / dy) + 1
	if width < 1 or height < 1:
		raise GeoSphereError(f"Ungültige Rasterform aus BBox und Auflösung: {width} × {height}")
	return width, height


def _forecast_step(metadata: dict[str, Any], resource_id: str) -> timedelta:
	for key in ("frequency", "freq", "temporal_resolution", "temporalResolution"):
		if key not in metadata:
			continue
		value = metadata[key]
		if isinstance(value, dict):
			number = value.get("value") or value.get("step") or value.get("amount")
			unit = str(value.get("unit") or value.get("units") or "").lower()
			if number is not None:
				return _duration(float(number), unit)
		if isinstance(value, (int, float)):
			return timedelta(hours=float(value))
		if isinstance(value, str):
			parsed = _parse_duration_text(value)
			if parsed is not None:
				return parsed

	match = re.search(r"-(\d+)(min|h|d)-", resource_id)
	if match:
		return _duration(float(match.group(1)), match.group(2))
	raise GeoSphereError("Forecast-Zeitschritt konnte nicht bestimmt werden.")


def _parse_duration_text(value: str) -> timedelta | None:
	text = value.strip().lower()
	iso_match = re.fullmatch(r"pt(\d+(?:\.\d+)?)h", text)
	if iso_match:
		return timedelta(hours=float(iso_match.group(1)))
	match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(min|m|h|hour|hours|d|day|days)", text)
	if match:
		return _duration(float(match.group(1)), match.group(2))
	return None


def _duration(number: float, unit: str) -> timedelta:
	if unit in {"min", "m", "minute", "minutes"}:
		return timedelta(minutes=number)
	if unit in {"h", "hour", "hours"}:
		return timedelta(hours=number)
	if unit in {"d", "day", "days"}:
		return timedelta(days=number)
	raise GeoSphereError(f"Unbekannte Zeiteinheit: {unit!r}")


def _positive_int(metadata: dict[str, Any], *keys: str) -> int:
	for key in keys:
		if key in metadata:
			value = int(metadata[key])
			if value > 0:
				return value
	raise GeoSphereError(f"Kein positiver Integer für {', '.join(keys)} gefunden.")


def _parse_datetime(value: str) -> datetime:
	text = value.strip().replace("Z", "+00:00")
	parsed = datetime.fromisoformat(text)
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _api_time(value: datetime) -> str:
	return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _iso_time(value: datetime) -> str:
	return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_netcdf_magic(path: Path) -> None:
	if path.stat().st_size < 8:
		raise GeoSphereError(f"NetCDF-Datei ist leer oder zu klein: {path}")
	with path.open("rb") as handle:
		magic = handle.read(8)
	if not (magic.startswith(b"CDF") or magic.startswith(b"\x89HDF\r\n\x1a\n")):
		raise GeoSphereError(f"Antwort ist keine erkennbare NetCDF-Datei: {path} ({magic!r})")
