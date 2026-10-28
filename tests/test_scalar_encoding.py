from __future__ import annotations

import numpy as np
import pytest

from weather_build.scalar_encoding import RasterEncodingError, encode_float32_rgba, decode_float32_rgba


def test_bit_exact_roundtrip_preserves_signed_and_fractional_values() -> None:
	values = np.array([[0.0, -12.75, 1.0 / 3], [100000.0, -0.0, np.nan]], dtype=np.float32)
	rgba, mask = encode_float32_rgba(values)
	decoded = decode_float32_rgba(rgba, mask)
	assert np.array_equal(decoded[np.isfinite(values)].view(np.uint32), values[np.isfinite(values)].view(np.uint32))
	assert np.isnan(decoded[1, 2])
	assert mask.tolist() == [[255, 255, 255], [255, 255, 0]]


def test_invalid_mask_is_rejected() -> None:
	values = np.array([[1.0]], dtype=np.float32)
	rgba, mask = encode_float32_rgba(values)
	mask[0, 0] = 128
	with pytest.raises(RasterEncodingError):
		decode_float32_rgba(rgba, mask)


def test_wrong_dtype_and_infinities_are_rejected() -> None:
	with pytest.raises(RasterEncodingError):
		encode_float32_rgba(np.array([[1.0]], dtype=np.float64))
	with pytest.raises(RasterEncodingError):
		encode_float32_rgba(np.array([[np.inf]], dtype=np.float32))
