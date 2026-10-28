"""Explicit scalar raster quantization for future numeric tile transport.

This module is format-independent: it does not claim that ordinary MapLibre
raster PNG sources can decode numeric UInt16 pixels.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


class QuantizationError(ValueError):
	pass


@dataclass(frozen=True)
class Quantization:
	bits: int
	step: float
	origin: float
	nodata_code: int = 0

	def __post_init__(self) -> None:
		if self.bits not in (8, 16):
			raise QuantizationError("Only uint8 and uint16 are supported.")
		if not math.isfinite(self.step) or self.step <= 0 or not math.isfinite(self.origin):
			raise QuantizationError("Step must be positive and origin finite.")
		if self.nodata_code != 0:
			raise QuantizationError("NoData code 0 is reserved.")

	@property
	def maximum_code(self) -> int:
		return (1 << self.bits) - 1

	@property
	def maximum_value(self) -> float:
		return self.origin + (self.maximum_code - 1) * self.step


def encode_integer(values: np.ndarray, spec: Quantization) -> tuple[np.ndarray, dict]:
	source = np.asarray(values)
	if source.ndim not in (2, 3) or not np.issubdtype(source.dtype, np.number):
		raise QuantizationError("Expected numeric 2D or 3D raster.")
	source = source.astype(np.float64)
	if np.any(np.isinf(source)):
		raise QuantizationError("Infinite raster values are not allowed.")
	valid = np.isfinite(source)
	codes = np.zeros(source.shape, dtype=np.uint8 if spec.bits == 8 else np.uint16)
	max_error = 0.0
	if np.any(valid):
		quantized = np.floor((source[valid] - spec.origin) / spec.step + 0.5)
		if np.any(~np.isfinite(quantized)) or np.any(quantized < 0) or np.any(quantized > spec.maximum_code - 1):
			raise QuantizationError("Values exceed the declared integer quantization range.")
		codes[valid] = (quantized.astype(np.uint32) + 1).astype(codes.dtype)
		reconstructed = spec.origin + quantized * spec.step
		max_error = float(np.max(np.abs(reconstructed - source[valid])))
	return codes, {
		"schema_version": 1,
		"bits": spec.bits,
		"step": spec.step,
		"origin": spec.origin,
		"nodata_code": 0,
		"valid_count": int(np.count_nonzero(valid)),
		"nodata_count": int(np.count_nonzero(~valid)),
		"maximum_absolute_error": max_error,
	}


def decode_integer(codes: np.ndarray, spec: Quantization) -> np.ndarray:
	array = np.asarray(codes)
	dtype = np.uint8 if spec.bits == 8 else np.uint16
	if array.ndim not in (2, 3) or array.dtype != dtype:
		raise QuantizationError(f"Expected {dtype.__name__} 2D or 3D raster.")
	result = np.full(array.shape, np.nan, dtype=np.float64)
	valid = array != 0
	result[valid] = spec.origin + (array[valid].astype(np.float64) - 1) * spec.step
	return result
