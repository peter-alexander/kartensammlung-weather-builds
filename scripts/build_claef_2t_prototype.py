"""Experimental six-frame C-LAEF 2t build: live NetCDF -> PMTiles + manifest.

Run manually; this script does not publish or modify the existing forecast builds.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import numpy as np
import requests
import xarray as xr
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from weather_build.geosphere import BoundingBox
from weather_build.quantization_contracts import contract_from_audit
from weather_build.numeric_tiles import build_numeric_pmtiles
from weather_build.tile_manifest import validate_manifest


API = "https://dataset.api.hub.geosphere.at/v1/grid/forecast/nwp-v2-1h-1km"
DATASET = "nwp-v2-1h-1km"
EXPECTED_SHAPE = (945, 1300)


def read_2t_frames_netcdf(path: Path, *, valid_times: list[datetime]) -> tuple[np.ndarray, object, BoundingBox]:
	"""Strictly accept original rectilinear 1D lon/lat grid, no shape guessing."""
	with xr.open_dataset(path, decode_cf=True, mask_and_scale=True) as dataset:
		if "2t" not in dataset:
			raise ValueError("NetCDF missing parameter 2t")
		field = dataset["2t"]
		if tuple(field.dims) != ("time", "lat", "lon"):
			raise ValueError(f"Unexpected variable dimensions {field.dims}")
		if field.shape[0] != len(valid_times) or field.shape[1:] != EXPECTED_SHAPE:
			raise ValueError(f"Unexpected native grid {field.shape}; expected {len(valid_times)} {EXPECTED_SHAPE} frames")
		lat = np.asarray(dataset["lat"].values, dtype=np.float64)
		lon = np.asarray(dataset["lon"].values, dtype=np.float64)
		if lat.ndim != 1 or lon.ndim != 1 or len(lat) != 945 or len(lon) != 1300:
			raise ValueError("Expected full original 1D lat/lon coordinates")
		if not (np.all(np.diff(lat) > 0) and np.all(np.diff(lon) > 0)):
			raise ValueError("Unexpected axis directions")
		if not (np.allclose(np.diff(lat), lat[1] - lat[0], atol=1e-8)
			and np.allclose(np.diff(lon), lon[1] - lon[0], atol=1e-8)):
			raise ValueError("Irregular coordinates")
		times = np.asarray(dataset["time"].values, dtype="datetime64[s]")
		expected = np.array([np.datetime64(value.replace(tzinfo=None), "s") for value in valid_times])
		if times.shape != expected.shape or not np.array_equal(times, expected):
			raise ValueError(f"Unexpected NetCDF time: {times}")
		unit = field.attrs.get("units")
		if unit != "degree Celsius":
			raise ValueError(f"Unexpected temperature unit: {unit}")
		values = np.asarray(field.values, dtype=np.float64)[:, ::-1, :]
		if np.any(np.isinf(values)):
			raise ValueError("Infinite 2t values")
		south = float(lat[0] - (lat[1] - lat[0]) / 2)
		north = float(lat[-1] + (lat[1] - lat[0]) / 2)
		west = float(lon[0] - (lon[1] - lon[0]) / 2)
		east = float(lon[-1] + (lon[1] - lon[0]) / 2)
		transform = from_bounds(west, south, east, north, len(lon), len(lat))
		return values, transform, BoundingBox(south=south, west=west, north=north, east=east)


def read_2t_netcdf(path: Path, *, valid_time: datetime) -> tuple[np.ndarray, object, BoundingBox]:
	frames, transform, bbox = read_2t_frames_netcdf(path, valid_times=[valid_time])
	return frames[0], transform, bbox


def forecast_request_parameters(valid_time: datetime, bbox: list[float], *, frame_count: int = 1) -> dict[str, str | int]:
	"""Request a non-empty minute interval containing exactly one hourly grid timestamp."""
	if not 1 <= frame_count <= 6:
		raise ValueError("Expected 1 to 6 forecast frames")
	if valid_time.tzinfo is None or valid_time.utcoffset() != timedelta(0):
		raise ValueError("Forecast timestamp must be UTC")
	if not isinstance(bbox, list) or len(bbox) != 4 or not all(isinstance(v, (int, float)) and np.isfinite(v) for v in bbox):
		raise ValueError("Expected four finite GeoSphere bbox coordinates")
	if not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
		raise ValueError("Invalid GeoSphere bbox ordering")
	return {
		"parameters": "2t",
		"bbox": ",".join(str(value) for value in bbox),
		"forecast_offset": 0,
		"start": valid_time.strftime("%Y-%m-%dT%H:%M"),
		"end": (valid_time + timedelta(hours=frame_count - 1, minutes=1)).strftime("%Y-%m-%dT%H:%M"),
		"output_format": "netcdf",
	}


def raise_geosphere_error(response: requests.Response) -> None:
	if response.ok:
		return
	body = response.text[:4000]
	raise RuntimeError(
		f"GeoSphere Grid API returned HTTP {response.status_code} for "
		f"{response.url}; response body: {body}"
	)



def projected_source_cell_size_m(source_transform: object, bbox: BoundingBox) -> tuple[float, float]:
	"""Native lon/lat cell pitch measured in EPSG:3857 (not a lossless grid transform)."""
	from math import pi, radians, cos, log, tan
	earth_radius = 6378137.0
	lon_m = abs(float(source_transform.a)) * pi / 180 * earth_radius
	lat_step = abs(float(source_transform.e))
	def mercator_y(lat: float) -> float:
		return earth_radius * log(tan(pi / 4 + radians(lat) / 2))
	lat_m = min(
		abs(mercator_y(bbox.south + lat_step) - mercator_y(bbox.south)),
		abs(mercator_y(bbox.north) - mercator_y(bbox.north - lat_step)),
	)
	return lon_m, lat_m


def check_numeric_tile_resolution(source_transform: object, bbox: BoundingBox,
		max_zoom: int, min_pixels_per_cell: float = 2.0) -> dict:
	"""Fail when the highest zoom undersamples the native grid spatially."""
	from math import pi
	x_m, y_m = projected_source_cell_size_m(source_transform, bbox)
	output_pixel_m = 2 * pi * 6378137.0 / (256 * (2 ** max_zoom))
	ratio = min(x_m, y_m) / output_pixel_m
	if ratio < min_pixels_per_cell:
		raise ValueError(
			f"Zoom {max_zoom} undersamples native C-LAEF cells: "
			f"{ratio:.2f} output pixels per shortest source cell; "
			f"require >= {min_pixels_per_cell:.1f}"
		)
	return {
		"zoom": max_zoom,
		"source_cell_webmercator_m": [round(x_m, 2), round(y_m, 2)],
		"output_pixel_webmercator_m": round(output_pixel_m, 2),
		"minimum_pixels_per_source_cell": round(ratio, 2),
	}


def build(output: Path, inventory_path: Path, *, minimum: float, maximum: float,
	min_zoom: int, max_zoom: int, pmtiles_binary: str, frame_count: int = 6) -> dict:
	output.mkdir(parents=True, exist_ok=True)
	session = requests.Session()
	session.headers["User-Agent"] = "ks-wetter-builds/claef-prototype"
	metadata = session.get(f"{API}/metadata", timeout=60)
	metadata.raise_for_status()
	meta = metadata.json()
	if meta.get("crs") != "EPSG:4326":
		raise ValueError("Unexpected model CRS")
	reftimes = meta.get("available_forecast_reftimes") or []
	if not reftimes:
		raise ValueError("No forecast reference times")
	reftime = datetime.fromisoformat(reftimes[0].replace("Z", "+00:00"))
	if reftime.tzinfo is None or reftime.utcoffset() != timedelta(0):
		raise ValueError("Invalid model reference time")
	valid_time = reftime + timedelta(hours=1)
	reftime_iso = reftime.strftime("%Y-%m-%dT%H:%M:%SZ")
	valid_times = [valid_time + timedelta(hours=step) for step in range(frame_count)]
	nc_path = output / "source-2t.nc"
	response = session.get(API, params=forecast_request_parameters(valid_time, meta["bbox_outer"], frame_count=frame_count), timeout=180)
	raise_geosphere_error(response)
	if not response.content.startswith(b"\x89HDF\r\n\x1a\n") and not response.content.startswith(b"CDF"):
		raise ValueError("Expected NetCDF response")
	nc_path.write_bytes(response.content)
	values, source_transform, bbox = read_2t_frames_netcdf(nc_path, valid_times=valid_times)
	resolution_report = check_numeric_tile_resolution(source_transform, bbox, max_zoom)
	print("Native grid sampling:", json.dumps(resolution_report), flush=True)
	inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
	contract = contract_from_audit(inventory, DATASET, "2t",
		declared_min=minimum, declared_max=maximum)
	frames = []
	for step, (field, timestamp) in enumerate(zip(values, valid_times), start=1):
		valid_iso = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
		filename = f"2t-f{step:03d}.pmtiles"
		archive = build_numeric_pmtiles(
			field, source_transform=source_transform, source_crs=CRS.from_epsg(4326),
			bbox=bbox, quantization=contract.quantization,
			parameter="2t", valid_time=valid_iso,
			min_zoom=min_zoom, max_zoom=max_zoom, tile_size=256,
			mbtiles_path=output / f"2t-f{step:03d}.mbtiles",
			pmtiles_path=output / filename,
			pmtiles_binary=pmtiles_binary,
		)
		frames.append({
			"valid_time": valid_iso, "href": filename,
			"sha256": archive["sha256"], "bytes": archive["bytes"]
		})
		print(f"Built {filename} ({archive['bytes']} bytes)", flush=True)
	manifest = {
		"schema_version": 1,
		"source": {"provider": "GeoSphere Austria", "dataset_id": DATASET,
			"license": "CC BY 4.0"},
		"reference_time": reftime_iso,
		"variables": [{
			"id": "2t",
			"unit": contract.source_unit,
			"temporal_semantics": contract.temporal_kind,
			"encoding": {
				"type": f"uint{contract.quantization.bits}",
				"layout": "gray8" if contract.quantization.bits == 8 else "rg8",
				"nodata": 0,
				"scale": contract.quantization.step,
				"offset": contract.quantization.origin,
			},
			"style": {"type": "color-ramp", "stops": [
				[-20, "#304c9e"], [0, "#a9d5e7"], [15, "#f5eba5"], [30, "#cf342d"]
			]},
			"frames": frames
		}],
	}
	validate_manifest(manifest)
	(output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return {"frame_count": len(frames), "total_bytes": sum(frame["bytes"] for frame in frames),
		"resolution_report": resolution_report}


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--inventory", type=Path, default=Path("docs/geosphere-audit/parameter-inventory.json"))
	parser.add_argument("--min", dest="minimum", type=float, required=True,
		help="Explicit reviewed encoding lower bound in Celsius")
	parser.add_argument("--max", dest="maximum", type=float, required=True,
		help="Explicit reviewed encoding upper bound in Celsius")
	parser.add_argument("--min-zoom", type=int, default=5)
	parser.add_argument("--max-zoom", type=int, default=10)
	parser.add_argument("--frames", type=int, default=6)
	parser.add_argument("--pmtiles-binary", default="pmtiles")
	args = parser.parse_args()
	print(json.dumps(build(args.output, args.inventory, minimum=args.minimum,
		maximum=args.maximum, min_zoom=args.min_zoom, max_zoom=args.max_zoom,
		pmtiles_binary=args.pmtiles_binary, frame_count=args.frames), indent=2))


if __name__ == "__main__":
	main()
