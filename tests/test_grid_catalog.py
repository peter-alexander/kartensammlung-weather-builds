from __future__ import annotations

import pytest

from weather_build.grid_catalog import (
	GridCatalogError,
	parameter_manifest,
	parse_grid_metadata,
)


def test_catalog_preserves_native_metadata() -> None:
	dataset = parse_grid_metadata("nwp-v2-1h-1km", {
		"parameters": [
			{"name": "precip", "long_name": "Hourly precipitation", "unit": "kg m-2"},
			{"name": "wind", "long_name": "10m wind", "unit": "m s-1"}
		],
		"bbox_outer": [5.03, 43, 22.57, 51.5],
		"crs": "EPSG:4326",
		"frequency": [{"frequency": "PT1H"}]
	})
	manifest = parameter_manifest(dataset, ["wind", "precip"])
	assert manifest["variables"][0]["source_unit"] == "m s-1"
	assert manifest["variables"][1]["source_parameter"] == "precip"
	assert manifest["variables"][1]["temporal_semantics"] == "unverified"
	assert manifest["variables"][1]["encoding"] is None


def test_catalog_accepts_dictionary_metadata_without_guessing() -> None:
	dataset = parse_grid_metadata("nwp-v2-1h-1km", {
		"parameters": {"t": {"unit": "K", "long_name": "Temperature"}}
	})
	assert dataset.parameter("t").unit == "K"


def test_missing_units_and_unknown_parameters_fail_closed() -> None:
	with pytest.raises(GridCatalogError):
		parse_grid_metadata("nwp-v2-1h-1km", {"parameters": [{"name": "rain"}]})
	dataset = parse_grid_metadata("nwp-v2-1h-1km", {
		"parameters": [{"name": "rain", "unit": "mm"}]
	})
	with pytest.raises(GridCatalogError):
		parameter_manifest(dataset, ["rr_acc"])
	with pytest.raises(GridCatalogError):
		parameter_manifest(dataset, ["rain", "rain"])
