#!/usr/bin/env python3
"""Assemble the captured GeoSphere metadata and NetCDF evidence for the audit.

Inputs are explicit snapshots made by the audit.  The script performs no
network access and does not silently refresh evidence while producing output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
import xarray as xr


DATASETS = (
	("nwp-v2-1h-1km", "forecast"),
	("ensemble-v2-1h-1km", "forecast"),
	("nowcast-v1-15min-1km", "forecast"),
	("inca-v2-1h-1km", "historical"),
	("inca-v1-1h-1km", "historical"),
	("chem-v2-1h-3km", "forecast"),
	("chem-v2-1h-9km", "forecast"),
	("chem_aqi-v1-1d-3km", "forecast"),
	("chem_dust-v1-1h-0p2deg", "forecast"),
	("apolis-v2-1d-100m", "historical"),
	("snowgrid_cl-v2-1d-1km", "historical"),
	("spartacus-v3-1d-1km", "historical"),
	("spartacus-v3-1m-1km", "historical"),
	("spartacus-v3-1q-1km", "historical"),
	("spartacus-v3-1y-1km", "historical"),
	("winfore-v2-1d-1km", "historical"),
)

FULL_GRID_SHAPES = {
	"nwp-v2-1h-1km": [945, 1300],
	"ensemble-v2-1h-1km": [945, 1300],
	"nowcast-v1-15min-1km": [431, 701],
	"inca-v2-1h-1km": [431, 701],
	"inca-v1-1h-1km": [401, 701],
	"chem-v2-1h-3km": [450, 450],
	"chem-v2-1h-9km": [680, 680],
	"chem_aqi-v1-1d-3km": [450, 450],
	"chem_dust-v1-1h-0p2deg": [324, 449],
	"apolis-v2-1d-100m": [4001, 7001],
	"snowgrid_cl-v2-1d-1km": [329, 584],
	"spartacus-v3-1d-1km": [329, 584],
	"spartacus-v3-1m-1km": [329, 584],
	"spartacus-v3-1q-1km": [329, 584],
	"spartacus-v3-1y-1km": [329, 584],
	"winfore-v2-1d-1km": [329, 584],
}


def load(path: Path) -> Any:
	return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any) -> None:
	path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _json_scalar(value: Any) -> Any:
	if value is None:
		return None
	if isinstance(value, np.ndarray):
		return value.tolist()
	if isinstance(value, np.generic):
		return value.item()
	return value


def inspect_extra_sample(dataset_id: str, path: Path, parameter_names: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
	raw = xr.open_dataset(path, decode_cf=False, mask_and_scale=False)
	decoded = xr.open_dataset(path, decode_cf=True, mask_and_scale=True)
	native = netCDF4.Dataset(path)
	try:
		variables = []
		for name in parameter_names:
			raw_variable = raw[name]
			decoded_variable = decoded[name]
			raw_values = raw_variable.values
			decoded_values = decoded_variable.values
			fill = raw_variable.attrs.get("_FillValue")
			missing = raw_variable.attrs.get("missing_value")
			valid_raw = np.ones(raw_values.shape, dtype=bool)
			for marker in (fill, missing):
				if marker is not None:
					valid_raw &= raw_values != marker
			valid_decoded = np.isfinite(decoded_values)
			unique = np.unique(raw_values[valid_raw])
			increments = np.diff(unique.astype(np.float64))
			positive = increments[increments > 0]
			native_variable = native.variables[name]
			filters = native_variable.filters() or {}
			chunking = native_variable.chunking()
			variables.append({
				"resource_id": dataset_id,
				"sample_file": path.name,
				"variable": name,
				"raw_dtype": str(raw_variable.dtype),
				"decoded_dtype": str(decoded_variable.dtype),
				"dimensions": list(raw_variable.dims),
				"shape": list(raw_variable.shape),
				"scale_factor": _json_scalar(raw_variable.attrs.get("scale_factor")),
				"add_offset": _json_scalar(raw_variable.attrs.get("add_offset")),
				"fill_value": None if fill is None else str(_json_scalar(fill)),
				"missing_value": None if missing is None else str(_json_scalar(missing)),
				"valid_min": _json_scalar(raw_variable.attrs.get("valid_min")),
				"valid_max": _json_scalar(raw_variable.attrs.get("valid_max")),
				"valid_range": _json_scalar(raw_variable.attrs.get("valid_range")),
				"units_netcdf": raw_variable.attrs.get("units"),
				"long_name_netcdf": raw_variable.attrs.get("long_name"),
				"standard_name": raw_variable.attrs.get("standard_name"),
				"cell_method": raw_variable.attrs.get("cell_method", ""),
				"endian": native_variable.endian(),
				"chunking": list(chunking) if isinstance(chunking, (list, tuple)) else chunking,
				"filters": filters,
				"sample_valid_count": int(np.count_nonzero(valid_decoded)),
				"sample_nodata_count": int(np.count_nonzero(~valid_decoded)),
				"sample_raw_min": _json_scalar(np.min(raw_values[valid_raw])) if np.any(valid_raw) else None,
				"sample_raw_max": _json_scalar(np.max(raw_values[valid_raw])) if np.any(valid_raw) else None,
				"sample_decoded_min": float(np.min(decoded_values[valid_decoded])) if np.any(valid_decoded) else None,
				"sample_decoded_max": float(np.max(decoded_values[valid_decoded])) if np.any(valid_decoded) else None,
				"sample_unique_raw_count": int(unique.size),
				"sample_min_raw_increment": float(np.min(positive)) if positive.size else None,
				"sample_min_physical_increment": (
					float(np.min(positive) * raw_variable.attrs.get("scale_factor", 1.0)) if positive.size else None
				),
				"float32_roundtrip_max_abs_error": (
					float(np.max(np.abs(decoded_values[valid_decoded] - decoded_values[valid_decoded].astype(np.float32))))
					if np.any(valid_decoded) else None
				),
			})

		coordinates = {}
		for name in ("lat", "lon", "x", "y"):
			if name not in decoded:
				continue
			coordinate = decoded[name]
			values = coordinate.values
			if values.ndim == 1 and values.size > 1:
				differences = np.diff(values.astype(np.float64))
			else:
				differences = np.diff(values.astype(np.float64), axis=-1).ravel() if values.shape[-1] > 1 else np.array([])
			coordinates[name] = {
				"axis": coordinate.attrs.get("axis", ""),
				"standard_name": coordinate.attrs.get("standard_name"),
				"dtype": str(coordinate.dtype),
				"shape": list(coordinate.shape),
				"first": float(values.flat[0]),
				"last": float(values.flat[-1]),
				"min": float(np.nanmin(values)),
				"max": float(np.nanmax(values)),
				"step_min": float(np.min(differences)) if differences.size else None,
				"step_max": float(np.max(differences)) if differences.size else None,
				"units": coordinate.attrs.get("units"),
			}
		geometry = {
			"resource_id": dataset_id,
			"sample_file": path.name,
			"data_model": native.data_model,
			"dimensions": {name: int(size) for name, size in decoded.sizes.items()},
			"coordinates": coordinates,
			"global_crs": decoded.attrs.get("crs"),
			"grid_mapping": decoded.attrs.get("grid_mapping"),
			"spatial_resolution": str(decoded.attrs.get("spatial_resolution")),
			"spatial_resolution_unit": decoded.attrs.get("spatial_resolution_unit"),
			"data_variables": parameter_names,
		}
		return variables, geometry
	finally:
		raw.close()
		decoded.close()
		native.close()


def temporal_interpretation(dataset_id: str, variable: str, description: str, cell_method: str, frequency: str) -> dict[str, Any]:
	text = f"{description} {cell_method}".lower()
	if "last forecast interval" in text:
		if "maximum" in text or "gust" in text:
			kind = "interval_maximum"
		elif "duration" in text:
			kind = "interval_duration"
		elif "type" in text or "symbol" in text:
			kind = "interval_category"
		else:
			kind = "interval_amount"
		return {"status": "confirmed", "kind": kind, "interval": frequency, "evidence": description}
	if "time: sum" in text or "precipitation sum" in text:
		return {"status": "confirmed", "kind": "interval_sum", "interval": frequency, "evidence": cell_method or description}
	if any(token in text for token in ("daily mean", "monthly mean", "seasonal mean", "annual mean", "time: mean")):
		return {"status": "confirmed", "kind": "interval_mean", "interval": frequency, "evidence": cell_method or description}
	if any(token in text for token in ("daily minimum", "daily maximum")):
		kind = "interval_minimum" if "minimum" in text else "interval_maximum"
		return {"status": "confirmed", "kind": kind, "interval": frequency, "evidence": description}
	if dataset_id == "nowcast-v1-15min-1km" and variable == "rr":
		return {"status": "derived", "kind": "interval_sum", "interval": frequency, "evidence": "API says precipitation sum; dataset resolution is 15 min"}
	if variable.startswith("ssrd"):
		return {"status": "unresolved", "kind": None, "interval": None, "evidence": "W m-2 and description are insufficient to prove averaging interval/reference convention"}
	return {"status": "derived", "kind": "value_at_valid_time", "interval": None, "evidence": "No accumulation/interval method declared in captured metadata"}


def category(variable: str, description: str) -> str:
	name = variable.lower()
	text = description.lower()
	if name in {"pt", "sy", "aqi"} or "type" in text or "symbol" in text or "index" in text:
		return "categorical_or_ordinal"
	if name in {"10u", "10v", "uu", "vv"} or "eastward direction" in text or "northward direction" in text:
		return "vector_component"
	if "percentile" in text or name.endswith(("_p10", "_p50", "_p90")):
		return "ensemble_percentile"
	if "maximum" in text or "minimum" in text or "gust" in text:
		return "extreme"
	if any(token in text for token in ("amount", "sum", "duration", "radiation")):
		return "amount_or_interval_quantity"
	if "%" in text or "probability" in text or "cloud cover" in text or "relative humidity" in text:
		return "bounded_fraction_or_percent"
	return "continuous_scalar"


def conversion(variable: str, unit: str) -> dict[str, Any] | None:
	if unit == "m s-1":
		return {"display_unit": "km h-1", "scale": 3.6, "offset": 0.0, "status": "exact_optional"}
	if unit == "Pa":
		return {"display_unit": "hPa", "scale": 0.01, "offset": 0.0, "status": "exact_optional"}
	if unit == "degree Kelvin":
		return {"display_unit": "degree Celsius", "scale": 1.0, "offset": -273.15, "status": "exact_optional"}
	if unit == "1" and variable.lower() in {"2r", "rh2m"}:
		return {"display_unit": "%", "scale": 100.0, "offset": 0.0, "status": "exact_optional"}
	if unit == "kg m-2" and variable.lower() in {"tp", "rain", "rr", "sf", "swe_tot"}:
		return {
			"display_unit": "mm water equivalent",
			"scale": 1.0,
			"offset": 0.0,
			"status": "conditional_physical_equivalence",
			"note": "Mass per area is water-equivalent depth; it is not snow depth.",
		}
	return None


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--grid-metadata", type=Path, required=True)
	parser.add_argument("--portal-metadata", type=Path, required=True)
	parser.add_argument("--variables", type=Path, required=True)
	parser.add_argument("--geometries", type=Path, required=True)
	parser.add_argument("--sample-report", type=Path, required=True)
	parser.add_argument("--all-parameter-report", type=Path, required=True)
	parser.add_argument("--apolis-report", type=Path, required=True)
	parser.add_argument("--benchmarks", type=Path, required=True)
	parser.add_argument("--inca-v2-sample", type=Path, required=True)
	parser.add_argument("--output", type=Path, required=True)
	args = parser.parse_args()
	args.output.mkdir(parents=True, exist_ok=True)

	variables = load(args.variables)
	geometries = load(args.geometries)
	inca_v2_parameter_names = [item["name"] for item in load(args.grid_metadata / "grid__historical__inca-v2-1h-1km.json")["parameters"]]
	inca_v2_variables, inca_v2_geometry = inspect_extra_sample("inca-v2-1h-1km", args.inca_v2_sample, inca_v2_parameter_names)
	variables.extend(inca_v2_variables)
	geometries.append(inca_v2_geometry)
	geometry_by_dataset = {item["resource_id"]: item for item in geometries}
	raw_by_key = {(item["resource_id"], item["variable"]): item for item in variables}

	catalog = []
	parameters = []
	for dataset_id, mode in DATASETS:
		grid_file = args.grid_metadata / f"grid__{mode}__{dataset_id}.json"
		grid = load(grid_file)
		portal = load(args.portal_metadata / f"{dataset_id}.json")
		endpoint = f"https://dataset.api.hub.geosphere.at/v1/grid/{mode}/{dataset_id}"
		catalog.append({
			"dataset_id": dataset_id,
			"mode": mode,
			"title": portal.get("title"),
			"description": portal.get("notes"),
			"dataset_status": portal.get("dataset_status"),
			"version": portal.get("version"),
			"issued": portal.get("issued"),
			"modified": portal.get("modified"),
			"doi": str(portal.get("identifier", "")).strip() or None,
			"license": {"id": portal.get("license_id"), "title": portal.get("license_title"), "uri": portal.get("license_uri")},
			"api": {
				"grid": endpoint,
				"grid_metadata": endpoint + "/metadata",
				"timeseries": f"https://dataset.api.hub.geosphere.at/v1/timeseries/{mode}/{dataset_id}",
				"response_formats": grid.get("response_formats"),
			},
			"crs": grid.get("crs"),
			"bbox_centers_south_west_north_east": grid.get("bbox"),
			"bbox_outer_south_west_north_east": grid.get("bbox_outer"),
			"spatial_resolution": grid.get("spatial_resolution"),
			"spatial_resolution_unit": grid.get("spatial_resolution_unit"),
			"full_grid_shape_y_x": FULL_GRID_SHAPES[dataset_id],
			"full_grid_shape_evidence": "Downloaded complete-grid NetCDF; APOLIS union of four API-limit-safe quadrants",
			"frequency_api": grid.get("frequency"),
			"temporal_resolution_portal": portal.get("temporal_resolution"),
			"update_frequency_portal": portal.get("update_frequency"),
			"start_time": grid.get("start_time"),
			"end_time": grid.get("end_time"),
			"forecast_length_count": grid.get("forecast_length"),
			"available_forecast_reftimes": grid.get("available_forecast_reftimes"),
			"last_forecast_reftime": grid.get("last_forecast_reftime"),
			"parameter_count": len(grid.get("parameters", [])),
			"sample_geometry": geometry_by_dataset[dataset_id],
		})

		for api_parameter in grid.get("parameters", []):
			variable = api_parameter["name"]
			raw = raw_by_key[(dataset_id, variable)]
			description = api_parameter.get("desc") or api_parameter.get("long_name") or raw.get("long_name_netcdf") or ""
			unit = api_parameter.get("unit", "")
			item = {
				"dataset_id": dataset_id,
				"mode": mode,
				"api_endpoint": endpoint,
				"api_name": variable,
				"api_long_name": api_parameter.get("long_name"),
				"api_description": api_parameter.get("desc"),
				"api_unit": unit,
				"category": category(variable, description),
				"temporal_interpretation": temporal_interpretation(dataset_id, variable, description, raw.get("cell_method") or "", grid.get("frequency") or ""),
				"display_conversion": conversion(variable, unit),
				"documented_plausible_range": None,
				"map_suitability": "blocked_pending_code_table" if variable.lower() in {"pt", "sy"} else "suitable_with_category_specific_resampling",
				"netcdf_evidence": raw,
			}
			parameters.append(item)

	dump(args.output / "dataset-catalog.json", catalog)
	dump(args.output / "parameter-inventory.json", parameters)
	dump(args.output / "raster-geometries.json", geometries)
	representative_downloads = load(args.sample_report)
	representative_downloads.append({
		"rid": "inca-v2-1h-1km",
		"mode": "historical",
		"params": inca_v2_parameter_names,
		"at": "2026-10-28T15:00",
		"bbox": "45.50288351657135,8.098133748352293,49.47817568460958,17.742270413233744",
		"status": 200,
		"bytes": args.inca_v2_sample.stat().st_size,
		"sha256": hashlib.sha256(args.inca_v2_sample.read_bytes()).hexdigest(),
		"datapoint_count": str(431 * 701 * len(inca_v2_parameter_names)),
		"file": args.inca_v2_sample.name,
	})
	dump(args.output / "netcdf-samples.json", {
		"representative_downloads": representative_downloads,
		"all_parameter_downloads": load(args.all_parameter_report),
		"apolis_full_grid_quadrants": load(args.apolis_report),
	})
	dump(args.output / "encoding-benchmarks.json", load(args.benchmarks))


if __name__ == "__main__":
	main()
