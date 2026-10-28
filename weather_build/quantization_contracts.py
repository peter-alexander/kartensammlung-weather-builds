"""Derive explicit integer raster encoding contracts from verified audit metadata.

A sample maximum is not a safe future bound. The caller must provide a reviewed
operational range independently; this module only validates it against the audit.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .integer_encoding import Quantization, QuantizationError


class ContractError(ValueError):
	pass


@dataclass(frozen=True)
class QuantizationContract:
	dataset_id: str
	parameter: str
	source_unit: str
	temporal_kind: str
	quantization: Quantization
	declared_min: float
	declared_max: float
	evidence_scale_factor: float

	def manifest(self) -> dict[str, Any]:
		return {
			"schema_version": 1,
			"dataset_id": self.dataset_id,
			"parameter": self.parameter,
			"unit": self.source_unit,
			"temporal_kind": self.temporal_kind,
			"storage": {
				"type": f"uint{self.quantization.bits}",
				"nodata": self.quantization.nodata_code,
				"scale": self.quantization.step,
				"offset": self.quantization.origin,
				"decoding": "physical = offset + (code - 1) * scale; code 0 = NoData",
			},
			"declared_min": self.declared_min,
			"declared_max": self.declared_max,
			"evidence_scale_factor": self.evidence_scale_factor,
		}


def contract_from_audit(
	inventory: list[dict[str, Any]],
	dataset_id: str,
	parameter: str,
	*,
	declared_min: float,
	declared_max: float,
) -> QuantizationContract:
	rows = [row for row in inventory
		if row.get("dataset_id") == dataset_id and row.get("api_name") == parameter]
	if len(rows) != 1:
		raise ContractError(f"Expected one verified audit record: {dataset_id}/{parameter}; got {len(rows)}")
	row = rows[0]
	evidence = row.get("netcdf_evidence") or {}
	unit = row.get("api_unit")
	if not isinstance(unit, str) or not unit or unit != evidence.get("units_netcdf"):
		raise ContractError("API and NetCDF units absent or inconsistent.")
	step = evidence.get("scale_factor")
	if not isinstance(step, (int, float)) or not math.isfinite(step) or step <= 0:
		raise ContractError("Positive source packing scale_factor required.")
	if evidence.get("add_offset") not in (None, 0, 0.0):
		raise ContractError("Source add_offset requires explicit review.")
	if evidence.get("raw_dtype") not in ("int16", "int32"):
		raise ContractError("Unsupported source packing type.")
	temporal = row.get("temporal_interpretation") or {}
	kind = temporal.get("kind")
	if not kind:
		raise ContractError("Temporal semantics required.")
	if not all(math.isfinite(v) for v in (declared_min, declared_max)) or declared_min >= declared_max:
		raise ContractError("Reviewed finite minimum and maximum required.")
	sample_min = evidence.get("sample_decoded_min")
	sample_max = evidence.get("sample_decoded_max")
	if sample_min is not None and declared_min > sample_min + step / 2:
		raise ContractError("Reviewed minimum excludes observed sample.")
	if sample_max is not None and declared_max < sample_max - step / 2:
		raise ContractError("Reviewed maximum excludes observed sample.")
	# Avoid pushing values outside the declared range because of floating-point division.
	positions = (declared_max - declared_min) / step
	if not math.isfinite(positions):
		raise ContractError("Invalid quantization span.")
	bits = next((b for b in (8, 16) if positions <= ((1 << b) - 2) + 1e-8), None)
	if bits is None:
		raise ContractError("Reviewed range does not fit uint16 at source resolution; split/adjust explicitly.")
	try:
		spec = Quantization(bits=bits, step=float(step), origin=float(declared_min))
	except QuantizationError as exc:
		raise ContractError(str(exc)) from exc
	return QuantizationContract(
		dataset_id=dataset_id, parameter=parameter, source_unit=unit,
		temporal_kind=str(kind), quantization=spec,
		declared_min=declared_min, declared_max=declared_max,
		evidence_scale_factor=float(step),
	)
