"""Single-variable numeric raster MBTiles writer; PMTiles conversion via pinned CLI.

Georeferencing must come from actual NetCDF coordinates, never estimated metadata.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import numpy as np
from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.warp import Resampling

from .geosphere import BoundingBox
from .integer_encoding import Quantization
from .tile_png import values_to_png, png_to_values
from .tiles import (
	_convert_to_pmtiles, _prepare_mbtiles, _reproject_field, _sha256_file,
	tile_grid_for_bbox,
)


class NumericTileError(ValueError):
	pass


def build_numeric_pmtiles(
	values: np.ndarray,
	*,
	source_transform: Affine,
	source_crs: CRS,
	bbox: BoundingBox,
	quantization: Quantization,
	parameter: str,
	valid_time: str,
	min_zoom: int,
	max_zoom: int,
	tile_size: int,
	mbtiles_path: Path,
	pmtiles_path: Path,
	pmtiles_binary: str,
	resampling: Resampling = Resampling.nearest,
) -> dict:
	if values.ndim != 2 or not np.issubdtype(values.dtype, np.number):
		raise NumericTileError("Expected 2D numeric raster")
	if min_zoom < 0 or max_zoom < min_zoom or tile_size < 1:
		raise NumericTileError("Invalid zoom range or tile size")
	mbtiles_path.parent.mkdir(parents=True, exist_ok=True)
	pmtiles_path.parent.mkdir(parents=True, exist_ok=True)
	mbtiles_path.unlink(missing_ok=True)
	pmtiles_path.unlink(missing_ok=True)
	total = 0
	with sqlite3.connect(mbtiles_path) as db:
		_prepare_mbtiles(db)
		metadata = {
			"name": f"GeoSphere {parameter} {valid_time}",
			"format": "png", "type": "overlay", "version": "1",
			"minzoom": str(min_zoom), "maxzoom": str(max_zoom),
			"bounds": f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}",
			"attribution": "GeoSphere Austria, CC BY 4.0",
			"json": json.dumps({
				"numeric_encoding": {
					"type": f"uint{quantization.bits}",
					"layout": "gray8" if quantization.bits == 8 else "rg8",
					"nodata": 0, "scale": quantization.step, "offset": quantization.origin
				}
			}),
		}
		db.executemany("INSERT INTO metadata(name,value) VALUES (?,?)", metadata.items())
		for zoom in range(min_zoom, max_zoom + 1):
			grid = tile_grid_for_bbox(bbox, zoom, tile_size)
			projected = _reproject_field(values, source_transform, source_crs, grid, resampling)
			for tile_y in range(grid.y_min, grid.y_max + 1):
				y0 = (tile_y - grid.y_min) * tile_size
				for tile_x in range(grid.x_min, grid.x_max + 1):
					x0 = (tile_x - grid.x_min) * tile_size
					tile = projected[y0:y0 + tile_size, x0:x0 + tile_size]
					if not np.any(np.isfinite(tile)):
						continue
					png, _ = values_to_png(tile, quantization)
					decoded = png_to_values(png, quantization)
					diff = np.abs(decoded[np.isfinite(tile)] - tile[np.isfinite(tile)])
					if diff.size and float(np.max(diff)) > quantization.step / 2 + 1e-6:
						raise NumericTileError("Numeric tile roundtrip exceeds half quantization step")
					db.execute(
						"INSERT INTO tiles(zoom_level,tile_column,tile_row,tile_data) VALUES (?,?,?,?)",
						(zoom, tile_x, (1 << zoom) - 1 - tile_y, sqlite3.Binary(png)),
					)
					total += 1
			db.commit()
	_convert_to_pmtiles(mbtiles_path, pmtiles_path, pmtiles_binary)
	return {
		"parameter": parameter,
		"valid_time": valid_time,
		"tile_count": total,
		"bytes": pmtiles_path.stat().st_size,
		"sha256": _sha256_file(pmtiles_path),
	}
