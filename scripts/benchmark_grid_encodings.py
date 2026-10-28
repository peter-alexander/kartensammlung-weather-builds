#!/usr/bin/env python3
"""Benchmark candidate lossless/quantized PNG transports on a real grid.

This is deliberately an audit tool, not production encoding code.  It keeps
the native grid and therefore does not claim to benchmark reprojection or a
complete PMTiles build.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import PIL
from PIL import Image
import xarray as xr

from weather_build.scalar_encoding import decode_float32_rgba, encode_float32_rgba


SPECS = {
	"2t": {
		"source_step": 0.1,
		"practical_step": 0.1,
		"byte_base": -40.0,
		"byte_step": 0.25,
	},
	"tp": {
		"source_step": 0.001,
		"practical_step": 0.01,
		"byte_base": 0.0,
		"byte_step": 0.1,
	},
	"tcc": {
		"source_step": 0.01,
		"practical_step": 0.5,
		"byte_base": 0.0,
		"byte_step": 0.5,
	},
}


def _png_bytes(array: np.ndarray, mode: str) -> bytes:
	buffer = io.BytesIO()
	Image.fromarray(array, mode=mode).save(buffer, format="PNG", compress_level=6)
	return buffer.getvalue()


def _png_array(payload: bytes, mode: str) -> np.ndarray:
	with Image.open(io.BytesIO(payload)) as image:
		return np.asarray(image.convert(mode)).copy()


def _error_metrics(source: np.ndarray, decoded: np.ndarray, nominal_step: float) -> dict[str, Any]:
	valid = np.isfinite(source)
	mask_equal = bool(np.array_equal(valid, np.isfinite(decoded)))
	diff = np.abs(decoded[valid].astype(np.float64) - source[valid].astype(np.float64))
	values = np.abs(source[valid].astype(np.float64))
	rel_mask = values >= max(10.0 * nominal_step, 1e-12)
	relative = diff[rel_mask] / values[rel_mask] if np.any(rel_mask) else np.array([], dtype=np.float64)
	span = float(np.max(source[valid]) - np.min(source[valid]))
	return {
		"validity_exact": mask_equal,
		"valid_cells": int(np.count_nonzero(valid)),
		"nodata_cells": int(np.count_nonzero(~valid)),
		"mean_absolute_error": float(np.mean(diff)),
		"max_absolute_error": float(np.max(diff)),
		"p95_relative_error_for_abs_ge_10_steps": (
			float(np.quantile(relative, 0.95)) if relative.size else None
		),
		"max_error_divided_by_sample_range": float(np.max(diff) / span) if span else 0.0,
	}


def _encode_float(values: np.ndarray) -> tuple[list[bytes], Callable[[list[bytes]], np.ndarray], dict[str, Any]]:
	float_values = values.astype(np.float32)
	rgba, mask = encode_float32_rgba(float_values)
	payloads = [_png_bytes(rgba, "RGBA"), _png_bytes(mask, "L")]

	def decode(parts: list[bytes]) -> np.ndarray:
		return decode_float32_rgba(_png_array(parts[0], "RGBA"), _png_array(parts[1], "L"))

	return payloads, decode, {"textures": 2, "bits_per_valid_value": 32, "nodata": "separate 8-bit mask"}


def _integer_codes(values: np.ndarray, base: float, step: float, max_code: int) -> np.ndarray:
	valid = np.isfinite(values)
	codes = np.zeros(values.shape, dtype=np.uint32)
	codes[valid] = np.rint((values[valid] - base) / step).astype(np.int64) + 1
	if np.any(codes[valid] < 1) or np.any(codes[valid] > max_code):
		raise ValueError(f"Values exceed code range for base={base}, step={step}, max_code={max_code}")
	return codes


def _encode_uint16(values: np.ndarray, base: float, step: float) -> tuple[list[bytes], Callable[[list[bytes]], np.ndarray], dict[str, Any]]:
	codes = _integer_codes(values, base, step, 65535)
	rgb = np.zeros((*values.shape, 3), dtype=np.uint8)
	rgb[..., 0] = (codes >> 8).astype(np.uint8)
	rgb[..., 1] = (codes & 255).astype(np.uint8)
	payloads = [_png_bytes(rgb, "RGB")]

	def decode(parts: list[bytes]) -> np.ndarray:
		decoded_rgb = _png_array(parts[0], "RGB")
		decoded_codes = decoded_rgb[..., 0].astype(np.uint32) << 8
		decoded_codes |= decoded_rgb[..., 1].astype(np.uint32)
		result = np.full(values.shape, np.nan, dtype=np.float32)
		valid = decoded_codes != 0
		result[valid] = base + (decoded_codes[valid].astype(np.float64) - 1.0) * step
		return result

	return payloads, decode, {
		"textures": 1,
		"bits_per_code": 16,
		"base": base,
		"step": step,
		"nodata": "reserved code 0",
	}


def _encode_uint8(values: np.ndarray, base: float, step: float) -> tuple[list[bytes], Callable[[list[bytes]], np.ndarray], dict[str, Any]]:
	codes = _integer_codes(values, base, step, 255).astype(np.uint8)
	payloads = [_png_bytes(codes, "L")]

	def decode(parts: list[bytes]) -> np.ndarray:
		decoded_codes = _png_array(parts[0], "L")
		result = np.full(values.shape, np.nan, dtype=np.float32)
		valid = decoded_codes != 0
		result[valid] = base + (decoded_codes[valid].astype(np.float64) - 1.0) * step
		return result

	return payloads, decode, {
		"textures": 1,
		"bits_per_code": 8,
		"base": base,
		"step": step,
		"nodata": "reserved code 0",
	}


def _timed_variant(values: np.ndarray, encoder: Callable[[], tuple[list[bytes], Callable[[list[bytes]], np.ndarray], dict[str, Any]]], step: float) -> dict[str, Any]:
	started = time.perf_counter()
	payloads, decoder, metadata = encoder()
	encoded_at = time.perf_counter()
	decoded = decoder(payloads)
	finished = time.perf_counter()
	return {
		**metadata,
		"png_files": len(payloads),
		"png_bytes": int(sum(map(len, payloads))),
		"png_component_bytes": [len(part) for part in payloads],
		"encode_and_png_ms": (encoded_at - started) * 1000.0,
		"png_decode_and_numeric_decode_ms": (finished - encoded_at) * 1000.0,
		"errors_against_decoded_source": _error_metrics(values, decoded, step),
	}


def _block_reduce(values: np.ndarray, factor: int, reducer: str) -> np.ndarray:
	height = values.shape[0] // factor * factor
	width = values.shape[1] // factor * factor
	blocks = values[:height, :width].reshape(height // factor, factor, width // factor, factor)
	if reducer == "mean":
		return np.nanmean(blocks, axis=(1, 3))
	if reducer == "max":
		return np.nanmax(blocks, axis=(1, 3))
	if reducer == "nearest":
		return blocks[:, 0, :, 0]
	raise ValueError(reducer)


def _pyramid_sizes(values: np.ndarray, encoder_factory: Callable[[np.ndarray], tuple[list[bytes], Callable[[list[bytes]], np.ndarray], dict[str, Any]]]) -> dict[str, Any]:
	levels: list[dict[str, Any]] = []
	for factor in (1, 2, 4, 8):
		level = values if factor == 1 else _block_reduce(values, factor, "nearest")
		payload_total = 0
		tile_count = 0
		for row in range(0, level.shape[0], 256):
			for col in range(0, level.shape[1], 256):
				payloads, _, _ = encoder_factory(level[row:row + 256, col:col + 256])
				payload_total += sum(map(len, payloads))
				tile_count += len(payloads)
		levels.append({
			"factor": factor,
			"shape": list(level.shape),
			"png_file_count": tile_count,
			"png_bytes": payload_total,
		})
	return {"levels": levels, "four_level_total_png_bytes": sum(level["png_bytes"] for level in levels)}


def _resampling_observations(values: np.ndarray) -> list[dict[str, Any]]:
	results = []
	for factor in (2, 4, 8):
		for reducer in ("nearest", "mean", "max"):
			reduced = _block_reduce(values, factor, reducer)
			valid = np.isfinite(reduced)
			results.append({
				"factor": factor,
				"method": reducer,
				"shape": list(reduced.shape),
				"minimum": float(np.min(reduced[valid])),
				"maximum": float(np.max(reduced[valid])),
				"mean": float(np.mean(reduced[valid])),
				"valid_cells": int(np.count_nonzero(valid)),
			})
	return results


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("source", type=Path)
	parser.add_argument("output", type=Path)
	parser.add_argument("--nodata-source", type=Path)
	args = parser.parse_args()

	decoded = xr.open_dataset(args.source, decode_cf=True, mask_and_scale=True)
	raw = xr.open_dataset(args.source, decode_cf=False, mask_and_scale=False)
	try:
		report: dict[str, Any] = {
			"scope": "One real native-grid NWP snapshot; no reprojection and no PMTiles container overhead.",
			"source_file": args.source.name,
			"source_file_bytes": args.source.stat().st_size,
			"source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
			"environment": {
				"python": platform.python_version(),
				"numpy": np.__version__,
				"xarray": xr.__version__,
				"pillow": PIL.__version__,
			},
			"parameters": {},
		}
		for name, spec in SPECS.items():
			values = decoded[name].isel(time=0).values.astype(np.float64)
			valid = np.isfinite(values)
			base_source = math.floor(float(np.min(values[valid])) / spec["source_step"]) * spec["source_step"]
			base_practical = math.floor(float(np.min(values[valid])) / spec["practical_step"]) * spec["practical_step"]
			variants = {
				"float32_rgba_plus_mask": _timed_variant(
					values, lambda: _encode_float(values), np.finfo(np.float32).eps
				),
				"uint16_source_increment_rgb": _timed_variant(
					values,
					lambda: _encode_uint16(values, base_source, spec["source_step"]),
					spec["source_step"],
				),
				"uint16_practical_rgb": _timed_variant(
					values,
					lambda: _encode_uint16(values, base_practical, spec["practical_step"]),
					spec["practical_step"],
				),
			}
			try:
				variants["uint8_practical_gray"] = _timed_variant(
					values,
					lambda: _encode_uint8(values, spec["byte_base"], spec["byte_step"]),
					spec["byte_step"],
				)
			except ValueError as error:
				variants["uint8_practical_gray"] = {"not_applicable": str(error)}

			factories = {
				"float32_rgba_plus_mask": lambda array: _encode_float(array),
				"uint16_source_increment_rgb": lambda array: _encode_uint16(array, base_source, spec["source_step"]),
				"uint16_practical_rgb": lambda array: _encode_uint16(array, base_practical, spec["practical_step"]),
			}
			if "not_applicable" not in variants["uint8_practical_gray"]:
				factories["uint8_practical_gray"] = lambda array: _encode_uint8(array, spec["byte_base"], spec["byte_step"])

			report["parameters"][name] = {
				"description": decoded[name].attrs.get("description"),
				"unit": decoded[name].attrs.get("units"),
				"shape": list(values.shape),
				"raw_dtype": str(raw[name].dtype),
				"decoded_dtype": str(decoded[name].dtype),
				"source_scale_factor": float(raw[name].attrs["scale_factor"]),
				"sample_minimum": float(np.min(values[valid])),
				"sample_maximum": float(np.max(values[valid])),
				"valid_cells": int(np.count_nonzero(valid)),
				"nodata_cells": int(np.count_nonzero(~valid)),
				"variants": variants,
				"native_grid_tile_pyramids": {
					variant: _pyramid_sizes(values, factory) for variant, factory in factories.items()
				},
				"block_resampling": _resampling_observations(values),
			}
	finally:
		decoded.close()
		raw.close()

	if args.nodata_source:
		probe = xr.open_dataset(args.nodata_source, decode_cf=True, mask_and_scale=True)
		try:
			values = probe["tp"].isel(time=0).values.astype(np.float64)
			float_parts, float_decoder, _ = _encode_float(values)
			integer_parts, integer_decoder, _ = _encode_uint16(values, 0.0, SPECS["tp"]["source_step"])
			report["actual_nodata_probe"] = {
				"source_file": args.nodata_source.name,
				"source_sha256": hashlib.sha256(args.nodata_source.read_bytes()).hexdigest(),
				"parameter": "tp",
				"valid_cells": int(np.count_nonzero(np.isfinite(values))),
				"nodata_cells": int(np.count_nonzero(~np.isfinite(values))),
				"float32_rgba_plus_mask_png_bytes": int(sum(map(len, float_parts))),
				"float32_rgba_plus_mask_validity_exact": bool(
					np.array_equal(np.isfinite(values), np.isfinite(float_decoder(float_parts)))
				),
				"uint16_reserved_zero_png_bytes": int(sum(map(len, integer_parts))),
				"uint16_reserved_zero_validity_exact": bool(
					np.array_equal(np.isfinite(values), np.isfinite(integer_decoder(integer_parts)))
				),
			}
		finally:
			probe.close()

	args.output.parent.mkdir(parents=True, exist_ok=True)
	args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
	main()
