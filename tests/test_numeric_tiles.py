from __future__ import annotations

import sqlite3

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from weather_build.geosphere import BoundingBox
from weather_build.integer_encoding import Quantization
from weather_build.numeric_tiles import build_numeric_pmtiles
from weather_build.tile_png import png_to_values


def test_real_mbtiles_tile_codes(tmp_path, monkeypatch) -> None:
	def fake_pmtiles(mb, pm, binary):
		pm.write_bytes(b"fake-pmtiles-for-writer-unit-test")

	monkeypatch.setattr("weather_build.numeric_tiles._convert_to_pmtiles", fake_pmtiles)
	mb = tmp_path / "test.mbtiles"
	pm = tmp_path / "test.pmtiles"
	bounds = BoundingBox(south=47, west=15, north=48, east=16)
	values = np.full((8, 8), 10.5, dtype=np.float32)
	report = build_numeric_pmtiles(
		values, source_transform=from_bounds(15, 47, 16, 48, 8, 8),
		source_crs=CRS.from_epsg(4326), bbox=bounds,
		quantization=Quantization(bits=16, step=0.1, origin=-50),
		parameter="2t", valid_time="2026-10-28T15:00:00Z",
		min_zoom=3, max_zoom=3, tile_size=16,
		mbtiles_path=mb, pmtiles_path=pm, pmtiles_binary="fake",
	)
	assert report["tile_count"] > 0
	with sqlite3.connect(mb) as conn:
		rows = conn.execute("SELECT tile_data FROM tiles").fetchall()
	assert rows
	decoded = png_to_values(rows[0][0], Quantization(16, 0.1, -50))
	assert np.any(np.isclose(decoded, 10.5))


def test_invalid_zoom_rejected(tmp_path) -> None:
	with pytest.raises(ValueError):
		build_numeric_pmtiles(
			np.ones((2, 2)), source_transform=from_bounds(0, 0, 1, 1, 2, 2),
			source_crs=CRS.from_epsg(4326),
			bbox=BoundingBox(south=0, west=0, north=1, east=1),
			quantization=Quantization(8, 1, 0), parameter="x", valid_time="x",
			min_zoom=4, max_zoom=2, tile_size=16,
			mbtiles_path=tmp_path / "x.mbtiles", pmtiles_path=tmp_path / "x.pmtiles",
			pmtiles_binary="fake",
		)
