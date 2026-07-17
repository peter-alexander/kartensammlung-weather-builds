from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import os

import numpy as np
from pathlib import Path
import shutil
from typing import Any

from .config import BuildConfig
from .geosphere import GeoSphereClient, ProbeResult
from .netcdf import prepare_forecast
from .tiles import build_pmtiles_archive, decode_rgba, encode_rgba

LOGGER = logging.getLogger(__name__)


def run_build(
	config: BuildConfig,
	work_directory: Path,
	output_directory: Path,
	pmtiles_binary: str,
	forecast_offset: int = 0,
	expected_reference_time: datetime | None = None
) -> dict[str, Any]:
	client = GeoSphereClient(config)
	probe = client.probe(forecast_offset=forecast_offset)
	if expected_reference_time is not None and probe.reference_time != expected_reference_time:
		probe = _probe_for_reference_time(client, expected_reference_time)

	work_directory.mkdir(parents=True, exist_ok=True)
	output_directory.mkdir(parents=True, exist_ok=True)
	source_directory = work_directory / "source"
	mbtiles_directory = work_directory / "mbtiles"
	chunks = client.plan_downloads(probe, source_directory)
	download_records = client.download_chunks(probe, chunks)
	prepared = prepare_forecast([chunk.path for chunk in chunks], probe, config)
	_roundtrip_encoding_check(prepared.precipitation_mm, prepared.cloud_fraction, config)

	assets: list[dict[str, Any]] = []
	for index, valid_time in enumerate(prepared.times):
		forecast_seconds = int((valid_time - probe.reference_time).total_seconds())
		if forecast_seconds % 3600 != 0:
			raise RuntimeError(f"Nicht-stündlicher Zeitpunkt kann nicht als fHHH benannt werden: {valid_time}")
		forecast_hour = forecast_seconds // 3600
		asset_name = f"arome_f{forecast_hour:03d}.pmtiles"
		LOGGER.info(
			"Baue %s (%d/%d, %s)",
			asset_name,
			index + 1,
			len(prepared.times),
			_iso_time(valid_time)
		)
		stats = build_pmtiles_archive(
			precipitation_mm=prepared.precipitation_mm[index],
			cloud_fraction=prepared.cloud_fraction[index],
			source_transform=prepared.source_transform,
			source_crs=prepared.source_crs,
			bbox=probe.bbox,
			config=config,
			name=f"GeoSphere AROME f{forecast_hour:03d}",
			valid_time=_iso_time(valid_time),
			mbtiles_path=mbtiles_directory / asset_name.replace(".pmtiles", ".mbtiles"),
			pmtiles_path=output_directory / asset_name,
			pmtiles_binary=pmtiles_binary
		)
		assets.append(
			{
				"forecast_hour": forecast_hour,
				"valid_time": _iso_time(valid_time),
				**asdict(stats)
			}
		)
		(mbtiles_directory / asset_name.replace(".pmtiles", ".mbtiles")).unlink(missing_ok=True)

	manifest = _manifest(probe, config, assets)
	validation = {
		"schema_version": 1,
		"status": "passed",
		"generated_at": _iso_time(datetime.now(timezone.utc)),
		"source_downloads": download_records,
		"source_validation": prepared.validation,
		"encoding_validation": {
			"precipitation_max_absolute_error_mm": 0.005,
			"cloud_max_absolute_error_fraction": 0.5 / config.cloud_channel_max,
			"alpha_values": [0, 255]
		},
		"asset_count": len(assets),
		"total_tiles": sum(asset["tile_count"] for asset in assets),
		"total_asset_bytes": sum(asset["bytes"] for asset in assets)
	}
	_write_json(output_directory / "manifest.json", manifest)
	_write_json(output_directory / "validation.json", validation)
	return {
		"tag": probe.tag,
		"reference_time": _iso_time(probe.reference_time),
		"asset_count": len(assets),
		"output_directory": str(output_directory)
	}


def _probe_for_reference_time(client: GeoSphereClient, reference_time: datetime) -> ProbeResult:
	metadata = client.get_metadata()
	values = metadata.get("available_forecast_reftimes") or metadata.get("availableForecastReftimes") or []
	for offset, value in enumerate(values):
		candidate = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
		if candidate.tzinfo is None:
			candidate = candidate.replace(tzinfo=timezone.utc)
		candidate = candidate.astimezone(timezone.utc).replace(microsecond=0)
		if candidate == reference_time:
			return client.probe(forecast_offset=offset)
	raise RuntimeError(f"Ausgewählter Modelllauf ist nicht mehr verfügbar: {_iso_time(reference_time)}")


def _manifest(
	probe: ProbeResult,
	config: BuildConfig,
	assets: list[dict[str, Any]]
) -> dict[str, Any]:
	repository = os.environ.get("GITHUB_REPOSITORY")
	download_template = None
	if repository:
		download_template = (
			f"https://github.com/{repository}/releases/download/{probe.tag}/{{asset}}"
		)
	return {
		"schema_version": 1,
		"provider": "GeoSphere Austria",
		"license": "CC BY 4.0",
		"model": "AROME",
		"resource_id": config.resource_id,
		"reference_time": _iso_time(probe.reference_time),
		"release_tag": probe.tag,
		"generated_at": _iso_time(datetime.now(timezone.utc)),
		"bounds": probe.bbox.maplibre_value(),
		"grid": {
			"width": probe.grid_width,
			"height": probe.grid_height,
			"points": probe.grid_points,
			"spatial_resolution": list(probe.spatial_resolution),
			"spatial_resolution_unit": probe.spatial_resolution_unit
		},
		"tiles": {
			"format": "pmtiles",
			"content_type": "image/png",
			"tile_size": config.tile_size,
			"minzoom": config.min_zoom,
			"maxzoom": config.max_zoom,
			"aggregation": {
				"through_zoom": config.aggregate_through_zoom,
				"precipitation": "maximum",
				"cloud": "mean",
				"above_aggregation_zoom": "nearest source cell"
			}
		},
		"encoding": {
			"red_green": {
				"parameter": "precipitation_1h",
				"unit": "mm",
				"formula": "(R * 256 + G) / 100",
				"maplibre_custom_encoding": {
					"encoding": "custom",
					"redFactor": 2.56,
					"greenFactor": 0.01,
					"blueFactor": 0,
					"baseShift": 0
				}
			},
			"blue": {
				"parameter": "total_cloud_cover",
				"unit": "percent",
				"formula": "B / 255 * 100",
				"maplibre_custom_encoding": {
					"encoding": "custom",
					"redFactor": 0,
					"greenFactor": 0,
					"blueFactor": 100 / 255,
					"baseShift": 0
				}
			},
			"alpha": {
				"parameter": "validity",
				"valid": 255,
				"nodata": 0
			}
		},
		"download_url_template": download_template,
		"timesteps": assets
	}


def _roundtrip_encoding_check(
	precipitation: Any,
	cloud: Any,
	config: BuildConfig
) -> None:
	indices = [0, len(precipitation) // 2, len(precipitation) - 1]
	for index in sorted(set(indices)):
		precipitation_sample = precipitation[index][::37, ::41]
		cloud_sample = cloud[index][::37, ::41]
		rgba = encode_rgba(precipitation_sample, cloud_sample, config)
		decoded_precipitation, decoded_cloud, valid = decode_rgba(rgba, config)
		expected_valid = np.isfinite(precipitation_sample) & np.isfinite(cloud_sample)
		if not np.array_equal(valid, expected_valid):
			raise RuntimeError("Alpha-Roundtrip ist fehlgeschlagen.")
		if np.any(expected_valid):
			precipitation_error = np.nanmax(np.abs(decoded_precipitation - precipitation_sample))
			cloud_error = np.nanmax(np.abs(decoded_cloud - cloud_sample))
			if precipitation_error > 0.0051:
				raise RuntimeError(f"Niederschlags-Roundtripfehler zu groß: {precipitation_error}")
			if cloud_error > (0.5 / config.cloud_channel_max + 1e-6):
				raise RuntimeError(f"Bewölkungs-Roundtripfehler zu groß: {cloud_error}")


def _write_json(path: Path, value: dict[str, Any]) -> None:
	temporary = path.with_suffix(path.suffix + ".tmp")
	with temporary.open("w", encoding="utf-8") as handle:
		json.dump(value, handle, ensure_ascii=False, indent=2)
		handle.write("\n")
	temporary.replace(path)


def _iso_time(value: datetime) -> str:
	return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
