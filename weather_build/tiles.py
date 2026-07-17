from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import logging
import math
from pathlib import Path
import sqlite3
import subprocess
from typing import Any

import numpy as np
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import Affine, from_bounds
from rasterio.warp import Resampling, reproject

from .config import BuildConfig
from .geosphere import BoundingBox

LOGGER = logging.getLogger(__name__)
NODATA = np.float32(-9999.0)


@dataclass(frozen=True)
class TileArchiveStats:
	asset: str
	tile_count: int
	bytes: int
	sha256: str
	precipitation_min_mm: float
	precipitation_max_mm: float
	cloud_min_fraction: float
	cloud_max_fraction: float


@dataclass(frozen=True)
class TileGrid:
	zoom: int
	x_min: int
	x_max: int
	y_min: int
	y_max: int
	width: int
	height: int
	transform: Affine


class TileBuildError(RuntimeError):
	"""Raised for tile encoding or archive conversion failures."""


def build_pmtiles_archive(
	precipitation_mm: np.ndarray,
	cloud_fraction: np.ndarray,
	source_transform: Affine,
	source_crs: CRS,
	bbox: BoundingBox,
	config: BuildConfig,
	name: str,
	valid_time: str,
	mbtiles_path: Path,
	pmtiles_path: Path,
	pmtiles_binary: str
) -> TileArchiveStats:
	mbtiles_path.parent.mkdir(parents=True, exist_ok=True)
	pmtiles_path.parent.mkdir(parents=True, exist_ok=True)
	if mbtiles_path.exists():
		mbtiles_path.unlink()
	if pmtiles_path.exists():
		pmtiles_path.unlink()

	connection = sqlite3.connect(mbtiles_path)
	tile_count = 0
	try:
		_prepare_mbtiles(connection)
		_write_metadata(connection, name, valid_time, bbox, config)
		for zoom in range(config.min_zoom, config.max_zoom + 1):
			grid = tile_grid_for_bbox(bbox, zoom, config.tile_size)
			precip_resampling = Resampling.max if zoom <= config.aggregate_through_zoom else Resampling.nearest
			cloud_resampling = Resampling.average if zoom <= config.aggregate_through_zoom else Resampling.nearest
			precip_destination = _reproject_field(
				precipitation_mm,
				source_transform,
				source_crs,
				grid,
				precip_resampling
			)
			cloud_destination = _reproject_field(
				cloud_fraction,
				source_transform,
				source_crs,
				grid,
				cloud_resampling
			)
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
	archive_hash = _sha256_file(pmtiles_path)
	return TileArchiveStats(
		asset=pmtiles_path.name,
		tile_count=tile_count,
		bytes=pmtiles_path.stat().st_size,
		sha256=archive_hash,
		precipitation_min_mm=float(np.nanmin(precipitation_mm)),
		precipitation_max_mm=float(np.nanmax(precipitation_mm)),
		cloud_min_fraction=float(np.nanmin(cloud_fraction)),
		cloud_max_fraction=float(np.nanmax(cloud_fraction))
	)


def encode_rgba(
	precipitation_mm: np.ndarray,
	cloud_fraction: np.ndarray,
	config: BuildConfig
) -> np.ndarray:
	if precipitation_mm.shape != cloud_fraction.shape:
		raise TileBuildError("Niederschlag und Bewölkung müssen dieselbe Rasterform haben.")

	valid = np.isfinite(precipitation_mm) & np.isfinite(cloud_fraction)
	precipitation_safe = np.where(valid, precipitation_mm, 0.0)
	cloud_safe = np.where(valid, cloud_fraction, 0.0)
	precipitation_encoded = np.rint(
		precipitation_safe * config.precipitation_units_per_mm
	).astype(np.uint16)
	cloud_encoded = np.rint(
		np.clip(cloud_safe, 0.0, 1.0) * config.cloud_channel_max
	).astype(np.uint8)

	rgba = np.empty((*precipitation_mm.shape, 4), dtype=np.uint8)
	rgba[..., 0] = (precipitation_encoded >> 8).astype(np.uint8)
	rgba[..., 1] = (precipitation_encoded & 255).astype(np.uint8)
	rgba[..., 2] = cloud_encoded
	rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
	return rgba


def decode_rgba(rgba: np.ndarray, config: BuildConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
	precipitation_encoded = rgba[..., 0].astype(np.uint16) * 256 + rgba[..., 1].astype(np.uint16)
	precipitation_mm = precipitation_encoded.astype(np.float32) / config.precipitation_units_per_mm
	cloud_fraction = rgba[..., 2].astype(np.float32) / config.cloud_channel_max
	valid = rgba[..., 3] == 255
	precipitation_mm = np.where(valid, precipitation_mm, np.nan)
	cloud_fraction = np.where(valid, cloud_fraction, np.nan)
	return precipitation_mm, cloud_fraction, valid


def tile_grid_for_bbox(bbox: BoundingBox, zoom: int, tile_size: int) -> TileGrid:
	if bbox.west >= bbox.east or bbox.south >= bbox.north:
		raise TileBuildError(f"Ungültige BBox: {bbox}")
	n = 1 << zoom
	x_min = _tile_x(bbox.west, n)
	x_max = _tile_x(math.nextafter(bbox.east, -math.inf), n)
	y_min = _tile_y(bbox.north, n)
	y_max = _tile_y(math.nextafter(bbox.south, math.inf), n)
	width = (x_max - x_min + 1) * tile_size
	height = (y_max - y_min + 1) * tile_size
	left, _, _, top = _tile_bounds_mercator(x_min, y_min, n)
	_, bottom, right, _ = _tile_bounds_mercator(x_max, y_max, n)
	transform = from_bounds(left, bottom, right, top, width, height)
	return TileGrid(
		zoom=zoom,
		x_min=x_min,
		x_max=x_max,
		y_min=y_min,
		y_max=y_max,
		width=width,
		height=height,
		transform=transform
	)


def _tile_x(longitude: float, n: int) -> int:
	value = math.floor((longitude + 180.0) / 360.0 * n)
	return min(max(value, 0), n - 1)


def _tile_y(latitude: float, n: int) -> int:
	clamped = min(max(latitude, -85.0511287798066), 85.0511287798066)
	radians = math.radians(clamped)
	value = math.floor((1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * n)
	return min(max(value, 0), n - 1)


def _tile_bounds_mercator(x: int, y: int, n: int) -> tuple[float, float, float, float]:
	extent = 20037508.342789244
	tile_span = 2.0 * extent / n
	left = -extent + x * tile_span
	right = left + tile_span
	top = extent - y * tile_span
	bottom = top - tile_span
	return left, bottom, right, top


def _reproject_field(
	source: np.ndarray,
	source_transform: Affine,
	source_crs: CRS,
	grid: TileGrid,
	resampling: Resampling
) -> np.ndarray:
	source_filled = np.where(np.isfinite(source), source, NODATA).astype(np.float32, copy=False)
	destination = np.full((grid.height, grid.width), NODATA, dtype=np.float32)
	reproject(
		source=source_filled,
		destination=destination,
		src_transform=source_transform,
		src_crs=source_crs,
		src_nodata=float(NODATA),
		dst_transform=grid.transform,
		dst_crs=CRS.from_epsg(3857),
		dst_nodata=float(NODATA),
		resampling=resampling,
		init_dest_nodata=True,
		num_threads=2
	)
	return np.where(destination == NODATA, np.nan, destination)


def _prepare_mbtiles(connection: sqlite3.Connection) -> None:
	connection.execute("PRAGMA journal_mode=OFF")
	connection.execute("PRAGMA synchronous=OFF")
	connection.execute("PRAGMA temp_store=MEMORY")
	connection.execute("CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT)")
	connection.execute(
		"CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB, "
		"PRIMARY KEY (zoom_level, tile_column, tile_row))"
	)


def _write_metadata(
	connection: sqlite3.Connection,
	name: str,
	valid_time: str,
	bbox: BoundingBox,
	config: BuildConfig
) -> None:
	metadata = {
		"name": name,
		"description": f"GeoSphere AROME Niederschlag und Bewölkung für {valid_time}",
		"version": "1",
		"type": "overlay",
		"format": "png",
		"bounds": f"{bbox.west},{bbox.south},{bbox.east},{bbox.north}",
		"center": f"{(bbox.west + bbox.east) / 2},{(bbox.south + bbox.north) / 2},{config.min_zoom}",
		"minzoom": str(config.min_zoom),
		"maxzoom": str(config.max_zoom),
		"attribution": "GeoSphere Austria, CC BY 4.0",
		"json": json.dumps(
			{
				"kartensammlung:encoding": {
					"red_green": "precipitation_mm_0.01",
					"blue": "cloud_fraction_0_255",
					"alpha": "validity_mask"
				}
			},
			separators=(",", ":")
		)
	}
	connection.executemany("INSERT INTO metadata(name, value) VALUES (?, ?)", metadata.items())


def _write_zoom_tiles(
	connection: sqlite3.Connection,
	grid: TileGrid,
	precipitation: np.ndarray,
	cloud: np.ndarray,
	config: BuildConfig
) -> int:
	written = 0
	for tile_y in range(grid.y_min, grid.y_max + 1):
		row_start = (tile_y - grid.y_min) * config.tile_size
		row_end = row_start + config.tile_size
		for tile_x in range(grid.x_min, grid.x_max + 1):
			column_start = (tile_x - grid.x_min) * config.tile_size
			column_end = column_start + config.tile_size
			precipitation_tile = precipitation[row_start:row_end, column_start:column_end]
			cloud_tile = cloud[row_start:row_end, column_start:column_end]
			rgba = encode_rgba(precipitation_tile, cloud_tile, config)
			if not np.any(rgba[..., 3]):
				continue
			png = _png_bytes(rgba)
			tms_row = (1 << grid.zoom) - 1 - tile_y
			connection.execute(
				"INSERT INTO tiles(zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
				(grid.zoom, tile_x, tms_row, sqlite3.Binary(png))
			)
			written += 1
	return written


def _png_bytes(rgba: np.ndarray) -> bytes:
	buffer = BytesIO()
	Image.fromarray(rgba, mode="RGBA").save(
		buffer,
		format="PNG",
		compress_level=9,
		optimize=False
	)
	return buffer.getvalue()


def _convert_to_pmtiles(mbtiles_path: Path, pmtiles_path: Path, binary: str) -> None:
	LOGGER.info("Konvertiere %s nach %s", mbtiles_path.name, pmtiles_path.name)
	completed = subprocess.run(
		[binary, "convert", str(mbtiles_path), str(pmtiles_path)],
		check=False,
		text=True,
		capture_output=True
	)
	if completed.returncode != 0:
		raise TileBuildError(
			f"pmtiles convert ist mit Exitcode {completed.returncode} fehlgeschlagen.\n"
			f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
		)
	if not pmtiles_path.is_file() or pmtiles_path.stat().st_size == 0:
		raise TileBuildError(f"PMTiles-Ausgabe fehlt oder ist leer: {pmtiles_path}")


def _sha256_file(path: Path) -> str:
	digest = sha256()
	with path.open("rb") as handle:
		for block in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()
