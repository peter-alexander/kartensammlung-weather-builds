import numpy as np
import pytest

from weather_build.integer_encoding import Quantization
from weather_build.tile_png import TilePNGError, codes_to_png, png_to_codes, values_to_png, png_to_values


def test_uint8_png_roundtrip_nodata() -> None:
	spec = Quantization(8, 0.5, 0)
	values = np.array([[0, 1.5, np.nan], [22, 4, 127]], dtype=np.float64)
	data, report = values_to_png(values, spec)
	decoded = png_to_values(data, spec)
	assert np.allclose(decoded[np.isfinite(values)], values[np.isfinite(values)])
	assert np.isnan(decoded[0, 2])
	assert report["nodata_count"] == 1


def test_uint16_png_roundtrip_extreme_codes() -> None:
	codes = np.array([[0, 1, 255, 256, 65534, 65535]], dtype=np.uint16)
	assert np.array_equal(png_to_codes(codes_to_png(codes), 16), codes)


def test_uint16_real_values() -> None:
	spec = Quantization(16, .001, 0)
	values = np.array([[np.nan, .001, 12.345, 65]], dtype=np.float64)
	data, _ = values_to_png(values, spec)
	decoded = png_to_values(data, spec)
	assert np.isnan(decoded[0, 0])
	assert np.allclose(decoded[0, 1:], values[0, 1:])


def test_png_layout_mismatch_fails() -> None:
	codes = np.array([[1, 2]], dtype=np.uint16)
	with pytest.raises(TilePNGError):
		png_to_codes(codes_to_png(codes), 8)
