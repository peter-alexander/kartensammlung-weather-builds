"""Independent C-LAEF AlpeAdria v2 parameter contract.

GeoSphere's live metadata is the authority for parameter names and units.
No legacy AROME parameter mappings, deaccumulation, or arbitrary unit assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CLAEFMetadataError(ValueError):
	pass


@dataclass(frozen=True)
class Parameter:
	name: str
	unit: str
	description: str


@dataclass(frozen=True)
class CLAEFSelection:
	precipitation: Parameter
	cloud: Parameter


def parse_parameters(metadata: dict[str, Any]) -> dict[str, Parameter]:
	raw = metadata.get("parameters")
	if not isinstance(raw, (list, dict)):
		raise CLAEFMetadataError("GeoSphere metadata has no parameters")
	items = ({**value, "name": name} if isinstance(value, dict) else {"name": name}
		for name, value in raw.items()) if isinstance(raw, dict) else raw
	result: dict[str, Parameter] = {}
	for item in items:
		if not isinstance(item, dict):
			if not isinstance(item, str):
				continue
			item = {"name": item}
		name = str(item.get("name") or item.get("code") or "").strip()
		if not name:
			continue
		result[name] = Parameter(
			name=name,
			unit=str(item.get("unit") or "").strip(),
			description=" ".join(str(item.get(key) or "") for key in ("long_name", "description")).strip(),
		)
	if not result:
		raise CLAEFMetadataError("No valid parameters in metadata")
	return result


def require_parameter(parameters: dict[str, Parameter], name: str, units: set[str]) -> Parameter:
	if name not in parameters:
		raise CLAEFMetadataError(f"Parameter {name!r} missing in C-LAEF v2 metadata")
	parameter = parameters[name]
	if parameter.unit not in units:
		raise CLAEFMetadataError(
			f"{name!r}: unexpected unit {parameter.unit!r}; allowed: {sorted(units)}"
		)
	return parameter


def select_precipitation_and_cloud(
	metadata: dict[str, Any], *, precipitation_name: str, cloud_name: str
) -> CLAEFSelection:
	"""Require explicit, verified v2 names; do not guess from legacy names."""
	if not precipitation_name or not cloud_name or precipitation_name == cloud_name:
		raise CLAEFMetadataError("Two distinct explicit C-LAEF parameter names are required")
	parameters = parse_parameters(metadata)
	return CLAEFSelection(
		precipitation=require_parameter(parameters, precipitation_name, {"mm", "kg/m²", "kg m-2", "kg m^-2"}),
		cloud=require_parameter(parameters, cloud_name, {"%", "1", "0-1"}),
	)
