"""Lossless-for-float32 RGBA raster transport.

Each finite float32 is represented by its exact IEEE-754 bits in RGBA.
A separate 8-bit validity mask is required: no sentinel or NaN payload is
ever used to signal NoData. PNG must preserve all four channels byte-for-byte;
no lossy conversion, resampling or color-management may touch encoded tiles.
"""
from __future__ import annotations

import numpy as np


class RasterEncodingError(ValueError):
	pass


def encode_float32_rgba(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
	array = np.asarray(values)
	if array.ndim != 2 or array.dtype != np.float32:
		raise RasterEncodingError("Expect a 2D float32 scalar raster.")
	if np.any(np.isinf(array)):
		raise RasterEncodingError("Infinite values cannot be encoded.")
	valid = np.isfinite(array)
	bits = np.ascontiguousarray(np.where(valid, array, np.float32(0))).view(np.uint32)
	rgba = np.empty((*array.shape, 4), dtype=np.uint8)
	for channel, shift in enumerate((24, 16, 8, 0)):
		rgba[..., channel] = ((bits >> shift) & 255).astype(np.uint8)
	return rgba, (valid.astype(np.uint8) * 255)


def decode_float32_rgba(rgba: np.ndarray, validity: np.ndarray) -> np.ndarray:
	bytes_ = np.asarray(rgba)
	mask = np.asarray(validity)
	if bytes_.ndim != 3 or bytes_.shape[-1] != 4 or bytes_.dtype != np.uint8:
		raise RasterEncodingError("Expected uint8 RGBA raster.")
	if mask.shape != bytes_.shape[:2] or mask.dtype != np.uint8:
		raise RasterEncodingError("Expected matching uint8 validity mask.")
	if np.any((mask != 0) & (mask != 255)):
		raise RasterEncodingError("Validity mask must be binary (0 or 255).")
	bits = np.zeros(bytes_.shape[:2], dtype=np.uint32)
	for channel, shift in enumerate((24, 16, 8, 0)):
		bits |= bytes_[..., channel].astype(np.uint32) << shift
	result = bits.view(np.float32).copy()
	if np.any(~np.isfinite(result[mask == 255])):
		raise RasterEncodingError("Encoded finite cells contain invalid values.")
	result[mask == 0] = np.nan
	return result
