"""Product-independent scalar raster validation and lossless numeric encoding.

Store native physical values as float32 with explicit metadata; styling and
PNG/PMTiles quantization are separate later steps. No implicit unit guesses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


class ScalarRasterError(ValueError):
	pass


@dataclass(frozen=True)
class ScalarSpec:
	parameter: str
	source_unit: str
	output_unit: str
	scale: float = 1.0
	offset: float = 0.0
	min_value: float | None = None
	max_value: float | None = None

	def __post_init__(self) -> None:
		if not self.parameter or not self.source_unit or not self.output_unit:
			raise ScalarRasterError("Parameter und Einheiten müssen angegeben werden.")
		if not np.isfinite(self.scale) or not np.isfinite(self.offset) or self.scale == 0:
			raise ScalarRasterError("Ungültige lineare Transformation.")
		if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
			raise ScalarRasterError("Ungültiger Wertebereich.")


def validate_scalar(values: np.ndarray, spec: ScalarSpec) -> tuple[np.ndarray, dict[str, Any]]:
	"""Convert only with an explicitly supplied transformation and preserve missing cells."""
	source = np.asarray(values)
	if source.ndim not in (2, 3) or not np.issubdtype(source.dtype, np.number):
		raise ScalarRasterError("Skalares Wetterraster muss ein numerisches 2D- oder 3D-Array sein.")
	source = source.astype(np.float64)
	if np.any(np.isinf(source)):
		raise ScalarRasterError("Unendliche Eingabewerte sind unzulässig.")
	finite = np.isfinite(source)
	if not np.any(finite):
		raise ScalarRasterError("Das Wetterraster enthält keinen gültigen Wert.")
	transformed = np.full(source.shape, np.nan, dtype=np.float64)
	transformed[finite] = source[finite] * spec.scale + spec.offset
	if not np.all(np.isfinite(transformed[finite])):
		raise ScalarRasterError("Die Umrechnung erzeugt ungültige Zahlen.")
	if spec.min_value is not None and np.any(transformed[finite] < spec.min_value):
		raise ScalarRasterError(f"{spec.parameter}: Werte unter {spec.min_value} {spec.output_unit}.")
	if spec.max_value is not None and np.any(transformed[finite] > spec.max_value):
		raise ScalarRasterError(f"{spec.parameter}: Werte über {spec.max_value} {spec.output_unit}.")
	output = transformed.astype(np.float32)
	if not np.all(np.isfinite(output[finite])):
		raise ScalarRasterError("Float32-Überlauf beim Kodieren.")
	return output, {
		"parameter": spec.parameter,
		"source_unit": spec.source_unit,
		"output_unit": spec.output_unit,
		"scale": spec.scale,
		"offset": spec.offset,
		"minimum": float(np.min(transformed[finite])),
		"maximum": float(np.max(transformed[finite])),
		"valid_cells": int(np.count_nonzero(finite)),
		"nodata_cells": int(np.count_nonzero(~finite)),
		"dtype": "float32"
	}


def validate_metadata_unit(metadata_unit: str, spec: ScalarSpec) -> None:
	if metadata_unit != spec.source_unit:
		raise ScalarRasterError(
			f"{spec.parameter}: erwartete Einheit {spec.source_unit!r}, API meldet {metadata_unit!r}"
		)
