"""Product-neutral catalog for GeoSphere gridded weather data.

Only API metadata is authoritative. The catalog never guesses units, temporal
semantics, or parameter aliases from another weather model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class GridCatalogError(ValueError):
	pass


@dataclass(frozen=True)
class GridParameter:
	name: str
	unit: str
	long_name: str
	description: str


@dataclass(frozen=True)
class GridDataset:
	resource_id: str
	endpoint: str
	parameters: tuple[GridParameter, ...]
	crs: str | None
	bbox: tuple[float, float, float, float] | None
	frequency: Any

	def parameter(self, name: str) -> GridParameter:
		for parameter in self.parameters:
			if parameter.name == name:
				return parameter
		raise GridCatalogError(f"Unbekannter Parameter in {self.resource_id}: {name}")


def parse_grid_metadata(resource_id: str, metadata: dict[str, Any]) -> GridDataset:
	if not resource_id or not isinstance(metadata, dict):
		raise GridCatalogError("Ungültige Ressourcen-ID oder Metadaten.")
	raw_parameters = metadata.get("parameters")
	if not isinstance(raw_parameters, (list, dict)):
		raise GridCatalogError("Metadaten enthalten keine Parameterliste.")
	if isinstance(raw_parameters, dict):
		items = [
			{"name": name, **(value if isinstance(value, dict) else {})}
			for name, value in raw_parameters.items()
		]
	else:
		items = raw_parameters
	parameters = []
	seen = set()
	for item in items:
		if not isinstance(item, dict):
			raise GridCatalogError("Ungültiger Parametereintrag.")
		name = str(item.get("name") or "").strip()
		unit = str(item.get("unit") or "").strip()
		if not name or not unit or name in seen:
			raise GridCatalogError(f"Parameter ohne Namen/Einheit oder doppelt: {name!r}")
		seen.add(name)
		parameters.append(GridParameter(
			name=name,
			unit=unit,
			long_name=str(item.get("long_name") or ""),
			description=str(item.get("desc") or item.get("description") or "")
		))
	if not parameters:
		raise GridCatalogError("Keine Parameter vorhanden.")
	bbox_raw = metadata.get("bbox_outer")
	bbox = None
	if bbox_raw is not None:
		if not isinstance(bbox_raw, list) or len(bbox_raw) != 4:
			raise GridCatalogError("Ungültige bbox_outer.")
		bbox = tuple(float(value) for value in bbox_raw)
	return GridDataset(
		resource_id=resource_id,
		endpoint=f"https://dataset.api.hub.geosphere.at/v1/grid/forecast/{resource_id}",
		parameters=tuple(parameters),
		crs=str(metadata["crs"]) if metadata.get("crs") else None,
		bbox=bbox,
		frequency=metadata.get("frequency")
	)


def parameter_manifest(dataset: GridDataset, names: list[str]) -> dict[str, Any]:
	"""Stable handoff contract for a future raster encoder and map client."""
	if len(names) != len(set(names)):
		raise GridCatalogError("Doppelte Parameterauswahl.")
	return {
		"schema_version": 1,
		"resource_id": dataset.resource_id,
		"source_endpoint": dataset.endpoint,
		"crs": dataset.crs,
		"bounds": list(dataset.bbox) if dataset.bbox else None,
		"variables": [
			{
				"id": parameter.name,
				"source_parameter": parameter.name,
				"source_unit": parameter.unit,
				"long_name": parameter.long_name,
				"description": parameter.description,
				"temporal_semantics": "unverified",
				"encoding": None
			}
			for name in names
			for parameter in [dataset.parameter(name)]
		]
	}
