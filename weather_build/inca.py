from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterable

import numpy as np
import xarray as xr
from rasterio.warp import Resampling

from .config import BuildConfig, load_config
from .geosphere import GeoSphereClient, ProbeResult, write_github_output, write_probe_json
from .netcdf import (
	ForecastDataError,
	_center_coordinate_transform,
	_datetime_values,
	_deduplicate_time,
	_find_time_name,
	_normalize_orientation,
	_source_crs,
	_spatial_axes,
	_validate_expected_times
)
from .tiles import (
	TileArchiveStats,
	_convert_to_pmtiles,
	_prepare_mbtiles,
	_reproject_field,
	_sha256_file,
	_write_zoom_tiles,
	decode_rgba,
	encode_rgba,
	tile_grid_for_bbox
)

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
	parser = _parser()
	arguments = parser.parse_args(argv)
	logging.basicConfig(
		level=getattr(logging, arguments.log_level.upper()),
		format="%(asctime)s %(levelname)s %(name)s: %(message)s"
	)
	config = load_config(arguments.config)

	try:
		if arguments.command == "probe":
			probe = GeoSphereClient(config).probe(
				forecast_offset=arguments.forecast_offset
			)
			write_probe_json(probe, arguments.output)
			if arguments.github_output:
				write_github_output(probe, arguments.github_output)
			print(json.dumps({
				"tag": probe.tag,
				"reference_time": _iso_time(probe.reference_time)
			}))
			return 0

		if arguments.command == "build":
			expected_reference_time = (
				_parse_datetime(arguments.reference_time)
				if arguments.reference_time
				else None
			)
			result = run_build(
				config=config,
				work_directory=arguments.work_directory,
				output_directory=arguments.output_directory,
				pmtiles_binary=arguments.pmtiles_binary,
				forecast_offset=arguments.forecast_offset,
				expected_reference_time=expected_reference_time
			)
			print(json.dumps(result, ensure_ascii=False))
			return 0

		raise RuntimeError(f"Unbekanntes Kommando: {arguments.command}")
	except Exception:
		LOGGER.exception("INCA-Build fehlgeschlagen")
		return 1


def run_build(
	config: BuildConfig,
	work_directory: Path,
	output_directory: Path,
	pmtiles_binary: str,
	forecast_offset: int = 0,
	expected_reference_time: datetime | None = None
) -> dict[str, Any]:
	if config.precipitation_mode != "interval":
		raise RuntimeError("INCA erwartet precipitation_mode='interval'.")
	if config.cloud_parameter is not None:
		raise RuntimeError("Der INCA-Builder erwartet keinen Bewölkungsparameter.")

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
	prepared = prepare_inca_forecast(
		[chunk.path for chunk in chunks],
		probe,
		config
	)
	_roundtrip_encoding_check(prepared.precipitation_mm, config)

	assets: list[dict[str, Any]] = []
	for index, valid_time in enumerate(prepared.times):
		forecast_seconds = int((valid_time - probe.reference_time).total_seconds())
		if forecast_seconds < 0 or forecast_seconds % 60 != 0:
			raise RuntimeError(f"Ungültiger INCA-Zeitpunkt: {valid_time}")
		forecast_minutes = forecast_seconds // 60
		asset_stem = f"{config.asset_prefix}_m{forecast_minutes:03d}"
		asset_name = f"{asset_stem}.pmtiles"
		LOGGER.info(
			"Baue %s (%d/%d, %s)",
			asset_name,
			index + 1,
			len(prepared.times),
			_iso_time(valid_time)
		)
		stats = build_inca_pmtiles_archive(
			precipitation_mm=prepared.precipitation_mm[index],
			source_transform=prepared.source_transform,
			source_crs=prepared.source_crs,
			bbox=probe.bbox,
			config=config,
			name=f"GeoSphere INCA m{forecast_minutes:03d}",
			valid_time=_iso_time(valid_time),
			mbtiles_path=mbtiles_directory / f"{asset_stem}.mbtiles",
			pmtiles_path=output_directory / asset_name,
			pmtiles_binary=pmtiles_binary
		)
		assets.append({
			"forecast_minutes": forecast_minutes,
			"valid_time": _iso_time(valid_time),
			**asdict(stats)
		})
		(mbtiles_directory / f"{asset_stem}.mbtiles").unlink(missing_ok=True)

	manifest = _manifest(probe, config, prepared, assets)
	validation = {
		"schema_version": 1,
		"status": "passed",
		"generated_at": _iso_time(datetime.now(timezone.utc)),
		"source_downloads": download_records,
		"source_validation": prepared.validation,
		"encoding_validation": {
			"precipitation_max_absolute_error_mm": 0.005,
			"blue_channel": "unused_zero",
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


class PreparedIncaForecast:
	def __init__(
		self,
		times: list[datetime],
		precipitation_mm: np.ndarray,
		source_transform: Any,
		source_crs: Any,
		x_values: np.ndarray,
		y_values: np.ndarray,
		validation: dict[str, Any]
	) -> None:
		self.times = times
		self.precipitation_mm = precipitation_mm
		self.source_transform = source_transform
		self.source_crs = source_crs
		self.x_values = x_values
		self.y_values = y_values
		self.validation = validation


def prepare_inca_forecast(
	paths: Iterable[Path],
	probe: ProbeResult,
	config: BuildConfig
) -> PreparedIncaForecast:
	datasets: list[xr.Dataset] = []
	try:
		for path in paths:
			LOGGER.info("Öffne %s", path)
			with xr.open_dataset(path, decode_cf=True, mask_and_scale=True) as source:
				datasets.append(source.load())
		if not datasets:
			raise ForecastDataError("Keine INCA-NetCDF-Dateien vorhanden.")

		time_name = _find_time_name(datasets[0], config.precipitation_parameter)
		combined = xr.concat(
			datasets,
			dim=time_name,
			data_vars="minimal",
			coords="minimal",
			compat="override",
			combine_attrs="override"
		)
		combined = combined.sortby(time_name)
		combined = _deduplicate_time(combined, time_name)
		precipitation = combined[config.precipitation_parameter]
		y_dim, x_dim, y_name, x_name = _spatial_axes(
			combined,
			precipitation,
			time_name
		)
		precipitation = precipitation.transpose(time_name, y_dim, x_dim)

		times = _datetime_values(combined[time_name].values)
		_validate_expected_times(times, probe.valid_times)
		x_values = np.asarray(combined[x_name].values, dtype=np.float64)
		y_values = np.asarray(combined[y_name].values, dtype=np.float64)
		if x_values.ndim != 1 or y_values.ndim != 1:
			raise ForecastDataError("INCA-Koordinaten sind nicht eindimensional.")

		values = np.asarray(precipitation.values, dtype=np.float32)
		placeholder = np.where(np.isfinite(values), 0.0, np.nan).astype(
			np.float32,
			copy=False
		)
		values, _, x_values, y_values = _normalize_orientation(
			values,
			placeholder,
			x_values,
			y_values
		)
		values, precip_validation = validate_interval_precipitation(values, config)
		transform = _center_coordinate_transform(x_values, y_values)
		source_crs = _source_crs(combined, probe)

		return PreparedIncaForecast(
			times=times,
			precipitation_mm=values,
			source_transform=transform,
			source_crs=source_crs,
			x_values=x_values,
			y_values=y_values,
			validation={
				"shape": list(values.shape),
				"time_count": len(times),
				"source_crs": source_crs.to_string(),
				"source_transform": list(transform)[:6],
				"x_min": float(x_values.min()),
				"x_max": float(x_values.max()),
				"y_min": float(y_values.min()),
				"y_max": float(y_values.max()),
				"precipitation": precip_validation,
				"cloud": {
					"available": False,
					"encoded_placeholder_fraction": 0.0
				}
			}
		)
	finally:
		for dataset in datasets:
			dataset.close()


def validate_interval_precipitation(
	interval: np.ndarray,
	config: BuildConfig
) -> tuple[np.ndarray, dict[str, Any]]:
	if interval.ndim != 3:
		raise ForecastDataError(
			f"INCA-Niederschlag muss dreidimensional sein, erhalten: {interval.shape}"
		)
	result = interval.astype(np.float32, copy=True)
	finite = np.isfinite(result)
	serious = finite & (result < -config.negative_precipitation_tolerance_mm)
	serious_count = int(np.count_nonzero(serious))
	raw_minimum = float(np.nanmin(result))
	if serious_count:
		first = np.argwhere(serious)[0].tolist()
		raise ForecastDataError(
			f"{serious_count} unplausible negative INCA-Niederschlagswerte; "
			f"Minimum {raw_minimum:.3f} mm, erste Position {first}."
		)

	tiny_negative = finite & (result < 0)
	tiny_count = int(np.count_nonzero(tiny_negative))
	result[tiny_negative] = 0.0
	overflow = finite & (result > config.precipitation_max_mm)
	overflow_count = int(np.count_nonzero(overflow))
	if overflow_count:
		raise ForecastDataError(
			f"{overflow_count} INCA-Werte überschreiten "
			f"{config.precipitation_max_mm:.2f} mm."
		)
	return result, {
		"mode": "interval",
		"interval_minutes": config.precipitation_interval_minutes,
		"source_parameter": config.precipitation_parameter,
		"raw_min_mm": raw_minimum,
		"interval_min_mm": float(np.nanmin(result)),
		"interval_max_mm": float(np.nanmax(result)),
		"tiny_negative_values_clamped": tiny_count,
		"serious_negative_values": serious_count,
		"encoding_overflow_values": overflow_count,
		"nodata_values": int(np.count_nonzero(~np.isfinite(result)))
	}


def build_inca_pmtiles_archive(
	precipitation_mm: np.ndarray,
	source_transform: Any,
	source_crs: Any,
	bbox: Any,
	config: BuildConfig,
	name: str,
	valid_time: str,
	mbtiles_path: Path,
	pmtiles_path: Path,
	pmtiles_binary: str
) -> TileArchiveStats:
	mbtiles_path.parent.mkdir(parents=True, exist_ok=True)
	pmtiles_path.parent.mkdir(parents=True, exist_ok=True)
	mbtiles_path.unlink(missing_ok=True)
	pmtiles_path.unlink(missing_ok=True)
	cloud_fraction = np.where(
		np.isfinite(precipitation_mm),
		0.0,
		np.nan
	).astype(np.float32, copy=False)

	connection = sqlite3.connect(mbtiles_path)
	tile_count = 0
	try:
		_prepare_mbtiles(connection)
		_write_inca_metadata(connection, name, valid_time, bbox, config)
		for zoom in range(config.min_zoom, config.max_zoom + 1):
			grid = tile_grid_for_bbox(bbox, zoom, config.tile_size)
			precip_resampling = (
				Resampling.max
				if zoom <= config.aggregate_through_zoom
				else Resampling.nearest
			)
			precip_destination = _reproject_field(
				precipitation_mm,
				source_transform,
				source_crs,
				grid,
				precip_resampling
			)
			cloud_destination = np.where(
				np.isfinite(precip_destination),
				0.0,
				np.nan
			).astype(np.float32, copy=False)
			tile_count += _write_zoom_tiles(
				connection,
				grid,
				precip_destination,
				cloud_destination,
				config
			)
			connection.commit()
	finally:
		connection.close()

	_convert_to_pmtiles(mbtiles_path, pmtiles_path, pmtiles_binary)
	return TileArchiveStats(
		asset=pmtiles_path.name,
		tile_count=tile_count,
		bytes=pmtiles_path.stat().st_size,
		sha256=_sha256_file(pmtiles_path),
		precipitation_min_mm=float(np.nanmin(precipitation_mm)),
		precipitation_max_mm=float(np.nanmax(precipitation_mm)),
		cloud_min_fraction=0.0,
		cloud_max_fraction=0.0
	)


def _write_inca_metadata(
	connection: sqlite3.Connection,
	name: str,
	valid_time: str,
	bbox: Any,
	config: BuildConfig
) -> None:
	metadata = {
		"name": name,
		"description": f"GeoSphere INCA 15-Minuten-Niederschlag für {valid_time}",
		"version": "1",
		"type": "overlay",
		"format": "png",
		"bounds": f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}",
		"center": (
			f"{(bbox.west + bbox.east) / 2},"
			f"{(bbox.south + bbox.north) / 2},{config.min_zoom}"
		),
		"minzoom": str(config.min_zoom),
		"maxzoom": str(config.max_zoom),
		"attribution": "GeoSphere Austria, CC BY 4.0",
		"json": json.dumps({
			"kartensammlung:encoding": {
				"red_green": "precipitation_mm_0.01",
				"blue": "unused_zero",
				"alpha": "validity_mask"
			}
		}, separators=(",", ":"))
	}
	connection.executemany(
		"INSERT INTO metadata(name, value) VALUES (?, ?)",
		metadata.items()
	)


def _manifest(
	probe: ProbeResult,
	config: BuildConfig,
	prepared: PreparedIncaForecast,
	assets: list[dict[str, Any]]
) -> dict[str, Any]:
	return {
		"schema_version": 1,
		"provider": "GeoSphere Austria",
		"license": "CC BY 4.0",
		"model": config.model_name,
		"resource_id": config.resource_id,
		"reference_time": _iso_time(probe.reference_time),
		"release_tag": probe.tag,
		"generated_at": _iso_time(datetime.now(timezone.utc)),
		"forecast": {
			"step_minutes": int(probe.step.total_seconds() // 60),
			"precipitation_interval_minutes": config.precipitation_interval_minutes,
			"horizon_minutes": max(
				(asset["forecast_minutes"] for asset in assets),
				default=0
			)
		},
		"bounds": probe.bbox.maplibre_value(),
		"grid": {
			"width": len(prepared.x_values),
			"height": len(prepared.y_values),
			"points": len(prepared.x_values) * len(prepared.y_values),
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
				"above_aggregation_zoom": "nearest source cell"
			}
		},
		"encoding": {
			"red_green": {
				"parameter": config.precipitation_output_parameter,
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
				"availability": "unused",
				"encoded_value": 0
			},
			"alpha": {
				"parameter": "validity",
				"valid": 255,
				"nodata": 0
			}
		},
		"download_url_template": None,
		"timesteps": assets
	}


def _roundtrip_encoding_check(
	precipitation: np.ndarray,
	config: BuildConfig
) -> None:
	cloud = np.where(np.isfinite(precipitation), 0.0, np.nan).astype(
		np.float32,
		copy=False
	)
	indices = [0, len(precipitation) // 2, len(precipitation) - 1]
	for index in sorted(set(indices)):
		precipitation_sample = precipitation[index][::37, ::41]
		cloud_sample = cloud[index][::37, ::41]
		rgba = encode_rgba(precipitation_sample, cloud_sample, config)
		decoded_precipitation, decoded_cloud, valid = decode_rgba(rgba, config)
		expected_valid = np.isfinite(precipitation_sample)
		if not np.array_equal(valid, expected_valid):
			raise RuntimeError("INCA-Alpha-Roundtrip ist fehlgeschlagen.")
		if np.any(expected_valid):
			precipitation_error = np.nanmax(
				np.abs(decoded_precipitation - precipitation_sample)
			)
			if precipitation_error > 0.0051:
				raise RuntimeError(
					f"INCA-Niederschlags-Roundtripfehler zu groß: {precipitation_error}"
				)
			if np.nanmax(np.abs(decoded_cloud)) > 0:
				raise RuntimeError("INCA-Blaukanal ist nicht 0.")


def _probe_for_reference_time(
	client: GeoSphereClient,
	reference_time: datetime
) -> ProbeResult:
	metadata = client.get_metadata()
	values = (
		metadata.get("available_forecast_reftimes")
		or metadata.get("availableForecastReftimes")
		or []
	)
	for offset, value in enumerate(values):
		candidate = _parse_datetime(str(value))
		if candidate == reference_time:
			return client.probe(forecast_offset=offset)
	raise RuntimeError(
		f"Ausgewählter INCA-Lauf ist nicht mehr verfügbar: {_iso_time(reference_time)}"
	)


def _write_json(path: Path, value: dict[str, Any]) -> None:
	temporary = path.with_suffix(path.suffix + ".tmp")
	with temporary.open("w", encoding="utf-8") as handle:
		json.dump(value, handle, ensure_ascii=False, indent=2)
		handle.write("\n")
	temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="GeoSphere-INCA-Raster-PMTiles bauen"
	)
	parser.add_argument(
		"--config",
		type=Path,
		default=Path("config/inca-nowcast.json")
	)
	parser.add_argument(
		"--log-level",
		default=os.environ.get("LOG_LEVEL", "INFO"),
		choices=("DEBUG", "INFO", "WARNING", "ERROR")
	)
	subparsers = parser.add_subparsers(dest="command", required=True)

	probe = subparsers.add_parser("probe")
	probe.add_argument("--forecast-offset", type=int, default=0)
	probe.add_argument("--output", type=Path, default=Path("probe-inca.json"))
	probe.add_argument("--github-output", type=Path, default=None)

	build = subparsers.add_parser("build")
	build.add_argument("--forecast-offset", type=int, default=0)
	build.add_argument("--reference-time", default=None)
	build.add_argument("--work-directory", type=Path, default=Path("work-inca"))
	build.add_argument("--output-directory", type=Path, default=Path("out-inca"))
	build.add_argument(
		"--pmtiles-binary",
		default=os.environ.get("PMTILES_BIN", "pmtiles")
	)
	return parser


def _parse_datetime(value: str) -> datetime:
	parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _iso_time(value: datetime) -> str:
	return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
	sys.exit(main())
