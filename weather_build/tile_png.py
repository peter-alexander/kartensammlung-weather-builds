"""Lossless integer-code PNG transport for gridded weather data.

PNG RGB/RGBA are byte containers, not color data: keep PNG channels unmodified.
A code of zero is NoData. UInt16 is packed R=high byte, G=low byte.
"""
from __future__ import annotations

from io import BytesIO
import numpy as np
from PIL import Image

from .integer_encoding import Quantization, encode_integer, decode_integer


class TilePNGError(ValueError):
	pass


def codes_to_png(codes: np.ndarray) -> bytes:
	codes = np.asarray(codes)
	if codes.ndim != 2 or codes.dtype not in (np.uint8, np.uint16):
		raise TilePNGError("Expected 2D uint8 or uint16 array")
	if codes.dtype == np.uint8:
		image = Image.fromarray(codes, mode="L")
	else:
		red = (codes >> 8).astype(np.uint8)
		green = (codes & 255).astype(np.uint8)
		blue = np.zeros_like(red)
		image = Image.fromarray(np.stack((red, green, blue), axis=-1), mode="RGB")
	buffer = BytesIO()
	image.save(buffer, format="PNG", optimize=True)
	return buffer.getvalue()


def png_to_codes(data: bytes, bits: int) -> np.ndarray:
	with Image.open(BytesIO(data)) as image:
		if image.format != "PNG":
			raise TilePNGError("Expected PNG")
		if bits == 8:
			if image.mode != "L":
				raise TilePNGError("uint8 codes require PNG grayscale mode")
			return np.array(image, dtype=np.uint8)
		if bits == 16:
			if image.mode != "RGB":
				raise TilePNGError("uint16 codes require PNG RGB mode")
			pixels = np.array(image, dtype=np.uint8)
			if np.any(pixels[..., 2]):
				raise TilePNGError("Unused blue channel must be zero")
			return (pixels[..., 0].astype(np.uint16) << 8) | pixels[..., 1].astype(np.uint16)
		raise TilePNGError("Only 8/16 bits supported")


def values_to_png(values: np.ndarray, spec: Quantization) -> tuple[bytes, dict]:
	codes, report = encode_integer(values, spec)
	return codes_to_png(codes), report


def png_to_values(data: bytes, spec: Quantization) -> np.ndarray:
	return decode_integer(png_to_codes(data, spec.bits), spec)
