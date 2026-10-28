from __future__ import annotations

from copy import deepcopy
import pytest

from weather_build.tile_manifest import ManifestError, validate_manifest


def sample() -> dict:
	return {
		"schema_version": 1,
		"source": {"provider": "GeoSphere Austria", "dataset_id": "nwp-v2-1h-1km", "license": "CC BY 4.0"},
		"reference_time": "2026-10-28T12:00:00Z",
		"variables": [{
			"id": "2t", "unit": "degree Celsius", "temporal_semantics": "value_at_valid_time",
			"encoding": {"type": "uint16", "layout": "rg8", "nodata": 0, "scale": 0.1, "offset": -50},
			"style": {"type": "color-ramp", "stops": [[-20, "#123456"], [20, "#abcdef"]]},
			"frames": [{"valid_time": "2026-10-28T13:00:00Z", "href": "2t/f001.pmtiles"}]
		}]
	}


def test_valid_manifest() -> None:
	assert validate_manifest(sample())["variables"][0]["id"] == "2t"


@pytest.mark.parametrize("mutation", [
	lambda m: m["variables"][0]["encoding"].update({"layout": "gray8"}),
	lambda m: m["variables"][0]["encoding"].update({"scale": 0}),
	lambda m: m["variables"][0]["frames"].append(m["variables"][0]["frames"][0].copy()),
	lambda m: m["variables"][0]["frames"][0].update({"href": "../outside.pmtiles"}),
	lambda m: m["variables"][0]["style"].update({"stops": [[20, "#aaa"], [-20, "#bbb"]]}),
])
def test_reject_invalid_contract(mutation) -> None:
	value = deepcopy(sample())
	mutation(value)
	with pytest.raises(ManifestError):
		validate_manifest(value)


def test_style_is_independent_of_quantization() -> None:
	value = sample()
	value["variables"][0]["style"]["stops"] = [[-30, "#000000"], [30, "#ffffff"]]
	assert validate_manifest(value)["variables"][0]["encoding"]["scale"] == 0.1
