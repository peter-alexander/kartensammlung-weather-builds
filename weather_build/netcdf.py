from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import xarray as xr
from rasterio.crs import CRS
from rasterio.transform import Affine

from .config import BuildConfig
from .geosphere import GeoSphereError, ProbeResult

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedForecast:
	times: list[datetime]
	precipitation_mm: np.ndarray
	cloud_fraction: np.ndarray
	source_transform: Affine
	source_crs: CRS
	x_values: np.ndarray
	y_values: np.ndarray
	validation: dict[str, Any]


class ForecastDataError(RuntimeError):
	"""Raised when downloaded model data is incomplete or inconsistent."""


def prepare_forecast(
	paths: Iterable[Path],
	probe: ProbeResult,
	config: BuildConfig
) -> PreparedForecast:
	datasets: list[xr.Dataset] = []
	try:
		for path in paths:
			LOGGER.info("Öffne %s", path)
			with xr.open_dataset(path, decode_cf=True, mask_and_scale=True) as source:
				datasets.append(source.load())
		if not datasets:
			raise ForecastDataError("Keine NetCDF-Dateien vorhanden.")

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
		cloud = combined[config.cloud_parameter]
		y_dim, x_dim, y_name, x_name = _spatial_axes(combined, precipitation, time_name)
		precipitation = precipitation.transpose(time_name, y_dim, x_dim)
		cloud = cloud.transpose(time_name, y_dim, x_dim)

		times = _datetime_values(combined[time_name].values)
		_validate_expected_times(times, probe.valid_times)

		x_values = np.asarray(combined[x_name].values, dtype=np.float64)
		y_values = np.asarray(combined[y_name].values, dtype=np.float64)
		if x_values.ndim != 1 or y_values.ndim != 1:
			raise ForecastDataError(
				"Kurvilineare 2D-Koordinaten werden absichtlich nicht stillschweigend interpoliert."
			)

		rr_acc = np.asarray(precipitation.values, dtype=np.float32)
		tcc = np.asarray(cloud.values, dtype=np.float32)
		if rr_acc.shape != tcc.shape:
			raise ForecastDataError(f"Parameterformen unterscheiden sich: {rr_acc.shape} vs. {tcc.shape}")

		rr_acc, tcc, x_values, y_values = _normalize_orientation(rr_acc, tcc, x_values, y_values)
		transform = _center_coordinate_transform(x_values, y_values)
		source_crs = _source_crs(combined, probe)

		precipitation_mm, precip_validation = accumulated_to_interval_precipitation(rr_acc, config)
		cloud_fraction, cloud_validation = validate_cloud_fraction(tcc, config)

		validation = {
			"shape": list(precipitation_mm.shape),
			"time_count": len(times),
			"source_crs": source_crs.to_string(),
			"source_transform": list(transform)[:6],
			"x_min": float(x_values.min()),
			"x_max": float(x_values.max()),
			"y_min": float(y_values.min()),
			"y_max": float(y_values.max()),
			"precipitation": precip_validation,
			"cloud": cloud_validation
		}

		return PreparedForecast(
			times=times,
			precipitation_mm=precipitation_mm,
			cloud_fraction=cloud_fraction,
			source_transform=transform,
			source_crs=source_crs,
			x_values=x_values,
			y_values=y_values,
			validation=validation
		)
	finally:
		for dataset in datasets:
			dataset.close()


def accumulated_to_interval_precipitation(
	rr_acc: np.ndarray,
	config: BuildConfig
) -> tuple[np.ndarray, dict[str, Any]]:
	if rr_acc.ndim != 3:
		raise ForecastDataError(f"rr_acc muss dreidimensional sein, erhalten: {rr_acc.shape}")

	rr_acc_work = rr_acc.copy()
	initial_accumulation_missing = bool(np.all(~np.isfinite(rr_acc_work[0])))
	if initial_accumulation_missing:
		rr_acc_work[0] = 0.0

	result = np.empty_like(rr_acc_work, dtype=np.float32)
	result[0] = rr_acc_work[0]
	result[1:] = rr_acc_work[1:] - rr_acc_work[:-1]

	finite = np.isfinite(result)
	serious_negative = finite & (result < -config.negative_precipitation_tolerance_mm)
	serious_count = int(np.count_nonzero(serious_negative))
	minimum = float(np.nanmin(result))
	if serious_count:
		indices = np.argwhere(serious_negative)
		first = indices[0].tolist()
		raise ForecastDataError(
			f"{serious_count} unplausible negative Niederschlagsdifferenzen; Minimum {minimum:.3f} mm, "
			f"erste Position {first}."
		)

	tiny_negative = finite & (result < 0)
	tiny_negative_count = int(np.count_nonzero(tiny_negative))
	result[tiny_negative] = 0.0

	overflow = finite & (result > config.precipitation_max_mm)
	overflow_count = int(np.count_nonzero(overflow))
	if overflow_count:
		raise ForecastDataError(
			f"{overflow_count} stündliche Niederschlagswerte überschreiten die 16-Bit-Codierung "
			f"von {config.precipitation_max_mm:.2f} mm."
		)

	return result, {
		"accumulated_min_mm": float(np.nanmin(rr_acc)),
		"accumulated_max_mm": float(np.nanmax(rr_acc)),
		"initial_accumulation_missing_assumed_zero": initial_accumulation_missing,
		"interval_min_mm": float(np.nanmin(result)),
		"interval_max_mm": float(np.nanmax(result)),
		"tiny_negative_values_clamped": tiny_negative_count,
		"serious_negative_values": serious_count,
		"encoding_overflow_values": overflow_count,
		"nodata_values": int(np.count_nonzero(~finite))
	}


def validate_cloud_fraction(
	tcc: np.ndarray,
	config: BuildConfig
) -> tuple[np.ndarray, dict[str, Any]]:
	if tcc.ndim != 3:
		raise ForecastDataError(f"tcc muss dreidimensional sein, erhalten: {tcc.shape}")

	finite = np.isfinite(tcc)
	below = finite & (tcc < config.cloud_min_tolerance)
	above = finite & (tcc > config.cloud_max_tolerance)
	if np.any(below) or np.any(above):
		raise ForecastDataError(
			"Bewölkungswerte liegen deutlich außerhalb des erwarteten Bereichs 0 bis 1: "
			f"Minimum {float(np.nanmin(tcc)):.4f}, Maximum {float(np.nanmax(tcc)):.4f}."
		)

	clamped = np.clip(tcc, 0.0, 1.0).astype(np.float32, copy=False)
	clamped_count = int(np.count_nonzero(finite & (clamped != tcc)))
	return clamped, {
		"min_fraction": float(np.nanmin(clamped)),
		"max_fraction": float(np.nanmax(clamped)),
		"values_clamped": clamped_count,
		"nodata_values": int(np.count_nonzero(~finite))
	}


def _find_time_name(dataset: xr.Dataset, variable_name: str) -> str:
	variable = dataset[variable_name]
	for candidate in ("time", "valid_time", "forecast_time"):
		if candidate in variable.dims:
			return candidate
	for dimension in variable.dims:
		if dimension in dataset.coords and np.issubdtype(dataset[dimension].dtype, np.datetime64):
			return dimension
	raise ForecastDataError(f"Keine Zeitdimension für {variable_name} gefunden: {variable.dims}")


def _spatial_axes(
	dataset: xr.Dataset,
	variable: xr.DataArray,
	time_name: str
) -> tuple[str, str, str, str]:
	spatial_dims = [dimension for dimension in variable.dims if dimension != time_name]
	if len(spatial_dims) != 2:
		raise ForecastDataError(f"Erwarte zwei räumliche Dimensionen, erhalten: {spatial_dims}")

	x_name = _axis_coordinate(dataset, spatial_dims, axis="x")
	y_name = _axis_coordinate(dataset, spatial_dims, axis="y")
	x_dim = dataset[x_name].dims[0]
	y_dim = dataset[y_name].dims[0]
	if x_dim == y_dim:
		raise ForecastDataError("X- und Y-Koordinate verwenden dieselbe Dimension.")
	return y_dim, x_dim, y_name, x_name


def _axis_coordinate(dataset: xr.Dataset, spatial_dims: list[str], axis: str) -> str:
	name_candidates = {
		"x": ("lon", "longitude", "x"),
		"y": ("lat", "latitude", "y")
	}[axis]
	standard_names = {
		"x": {"longitude", "projection_x_coordinate"},
		"y": {"latitude", "projection_y_coordinate"}
	}[axis]
	axis_letter = axis.upper()

	for name in name_candidates:
		if name in dataset.coords and dataset[name].ndim == 1 and dataset[name].dims[0] in spatial_dims:
			return name
	for name, coordinate in dataset.coords.items():
		if coordinate.ndim != 1 or coordinate.dims[0] not in spatial_dims:
			continue
		if str(coordinate.attrs.get("axis", "")).upper() == axis_letter:
			return name
		if str(coordinate.attrs.get("standard_name", "")).lower() in standard_names:
			return name
	for dimension in spatial_dims:
		lower = dimension.lower()
		if axis == "x" and lower in {"x", "lon", "longitude"} and dimension in dataset.coords:
			return dimension
		if axis == "y" and lower in {"y", "lat", "latitude"} and dimension in dataset.coords:
			return dimension
	raise ForecastDataError(f"Keine {axis.upper()}-Koordinate für Dimensionen {spatial_dims} gefunden.")


def _normalize_orientation(
	rr_acc: np.ndarray,
	tcc: np.ndarray,
	x_values: np.ndarray,
	y_values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
	if x_values[0] > x_values[-1]:
		x_values = x_values[::-1].copy()
		rr_acc = rr_acc[:, :, ::-1]
		tcc = tcc[:, :, ::-1]
	if y_values[0] < y_values[-1]:
		y_values = y_values[::-1].copy()
		rr_acc = rr_acc[:, ::-1, :]
		tcc = tcc[:, ::-1, :]
	return rr_acc, tcc, x_values, y_values


def _center_coordinate_transform(x_values: np.ndarray, y_values: np.ndarray) -> Affine:
	if len(x_values) < 2 or len(y_values) < 2:
		raise ForecastDataError("Mindestens zwei X- und Y-Koordinaten sind erforderlich.")

	dx_values = np.diff(x_values)
	dy_values = np.diff(y_values)
	dx = float(np.median(dx_values))
	dy = float(np.median(dy_values))
	if dx <= 0 or dy >= 0:
		raise ForecastDataError(f"Unerwartete Koordinatenrichtung: dx={dx}, dy={dy}")
	if not np.allclose(dx_values, dx, rtol=1e-4, atol=1e-10):
		raise ForecastDataError("X-Koordinaten sind nicht regelmäßig genug für verlustfreie Rasterbehandlung.")
	if not np.allclose(dy_values, dy, rtol=1e-4, atol=1e-10):
		raise ForecastDataError("Y-Koordinaten sind nicht regelmäßig genug für verlustfreie Rasterbehandlung.")

	left = float(x_values[0] - dx / 2)
	top = float(y_values[0] - dy / 2)
	return Affine(dx, 0.0, left, 0.0, dy, top)


def _source_crs(dataset: xr.Dataset, probe: ProbeResult) -> CRS:
	for source in (probe.metadata, dataset.attrs):
		for key in ("crs", "spatial_ref", "projection"):
			value = source.get(key) if isinstance(source, dict) else None
			if value:
				try:
					return CRS.from_user_input(value)
				except Exception:
					pass
	for variable_name in ("crs", "spatial_ref"):
		if variable_name in dataset.variables:
			variable = dataset[variable_name]
			for key in ("spatial_ref", "crs_wkt"):
				if key in variable.attrs:
					return CRS.from_wkt(str(variable.attrs[key]))
	if probe.spatial_resolution_unit.lower() in {"deg", "degree", "degrees"}:
		return CRS.from_epsg(4326)
	raise GeoSphereError("Quell-CRS konnte weder aus NetCDF noch aus Metadaten bestimmt werden.")


def _datetime_values(values: np.ndarray) -> list[datetime]:
	result: list[datetime] = []
	for value in values:
		nanoseconds = np.datetime64(value, "ns").astype("int64")
		seconds, remainder = divmod(int(nanoseconds), 1_000_000_000)
		result.append(datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=remainder // 1000))
	return result


def _validate_expected_times(actual: list[datetime], expected: list[datetime]) -> None:
	actual_seconds = [item.replace(microsecond=0) for item in actual]
	expected_seconds = [item.replace(microsecond=0) for item in expected]
	if actual_seconds != expected_seconds:
		missing = sorted(set(expected_seconds) - set(actual_seconds))
		extra = sorted(set(actual_seconds) - set(expected_seconds))
		raise ForecastDataError(
			"Zeitachse ist nicht vollständig oder nicht in der erwarteten Reihenfolge. "
			f"Fehlend: {missing[:5]}, zusätzlich: {extra[:5]}, "
			f"erwartet {len(expected_seconds)}, erhalten {len(actual_seconds)}."
		)


def _deduplicate_time(dataset: xr.Dataset, time_name: str) -> xr.Dataset:
	values = np.asarray(dataset[time_name].values)
	_, unique_indices = np.unique(values, return_index=True)
	if len(unique_indices) == len(values):
		return dataset
	return dataset.isel({time_name: np.sort(unique_indices)})
