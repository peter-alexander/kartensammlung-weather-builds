"""Experimental one-frame C-LAEF 2t build: live NetCDF -> PMTiles + manifest.

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


def read_2t_netcdf(path: Path, *, valid_time: datetime) -> tuple[np.ndarray, object, BoundingBox]:
	"""Strictly accept original rectilinear 1D lon/lat grid, no shape guessing."""
	with xr.open_dataset(path, decode_cf=True, mask_and_scale=True) as dataset:
		if "2t" not in dataset:
			raise ValueError("NetCDF missing parameter 2t")
		field = dataset["2t"]
		if tuple(field.dims) != ("time", "lat", "lon"):
			raise ValueError(f"Unexpected variable dimensions {field.dims}")
		if field.shape[0] != 1 or field.shape[1:] != EXPECTED_SHAPE:
			raise ValueError(f"Unexpected native grid {field.shape}; expected one {EXPECTED_SHAPE} frame")
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
		expected = np.datetime64(valid_time.replace(tzinfo=None), "s")
		if times.shape != (1,) or times[0] != expected:
			raise ValueError(f"Unexpected NetCDF time: {times}")
		unit = field.attrs.get("units")
		if unit != "degree Celsius":
			raise ValueError(f"Unexpected temperature unit: {unit}")
		values = np.flipud(np.asarray(field.values[0], dtype=np.float64))
		if np.any(np.isinf(values)):
			raise ValueError("Infinite 2t values")
		south = float(lat[0] - (lat[1] - lat[0]) / 2)
		north = float(lat[-1] + (lat[1] - lat[0]) / 2)
		west = float(lon[0] - (lon[1] - lon[0]) / 2)
		east = float(lon[-1] + (lon[1] - lon[0]) / 2)
		transform = from_bounds(west, south, east, north, len(lon), len(lat))
		return values, transform, BoundingBox(south=south, west=west, north=north, east=east)


def build(output: Path, inventory_path: Path, *, minimum: float, maximum: float,
	min_zoom: int, max_zoom: int, pmtiles_binary: str) -> dict:
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
	valid_iso = valid_time.strftime("%Y-%m-%dT%H:%M:%SZ")
	nc_path = output / "source-2t.nc"
	response = session.get(API, params={
		"parameters": "2t",
		"forecast_offset": 0,
		"start": valid_iso,
		"end": valid_iso,
		"output_format": "netcdf",
	}, timeout=180)
	response.raise_for_status()
	if not response.content.startswith(b"\\x89HDF\\r\\n\\x1a\\n") and not response.content.startswith(b"CDF"):
		raise ValueError("Expected NetCDF response")
	nc_path.write_bytes(response.content)
	values, source_transform, bbox = read_2t_netcdf(nc_path, valid_time=valid_time)
	inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
	contract = contract_from_audit(inventory, DATASET, "2t",
		declared_min=minimum, declared_max=maximum)
	archive = build_numeric_pmtiles(
		values, source_transform=source_transform, source_crs=CRS.from_epsg(4326),
		bbox=bbox, quantization=contract.quantization,
		parameter="2t", valid_time=valid_iso,
		min_zoom=min_zoom, max_zoom=max_zoom, tile_size=256,
		mbtiles_path=output / "2t-f001.mbtiles",
		pmtiles_path=output / "2t-f001.pmtiles",
		pmtiles_binary=pmtiles_binary,
	)
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
			"frames": [{"valid_time": valid_iso, "href": "2t-f001.pmtiles",
				"sha256": archive["sha256"], "bytes": archive["bytes"]}]
		}],
	}
	validate_manifest(manifest)
	(output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return archive


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--inventory", type=Path, default=Path("docs/geosphere-audit/parameter-inventory.json"))
	parser.add_argument("--min", dest="minimum", type=float, required=True,
		help="Explicit reviewed encoding lower bound in Celsius")
	parser.add_argument("--max", dest="maximum", type=float, required=True,
		help="Explicit reviewed encoding upper bound in Celsius")
	parser.add_argument("--min-zoom", type=int, default=5)
	parser.add_argument("--max-zoom", type=int, default=8)
	parser.add_argument("--pmtiles-binary", default="pmtiles")
	args = parser.parse_args()
	print(json.dumps(build(args.output, args.inventory, minimum=args.minimum,
		maximum=args.maximum, min_zoom=args.min_zoom, max_zoom=args.max_zoom,
		pmtiles_binary=args.pmtiles_binary), indent=2))


if __name__ == "__main__":
	main()
