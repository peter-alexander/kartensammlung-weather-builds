from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


module_path = Path(__file__).resolve().parents[1] / "scripts" / "inspect-claef-v2.py"
spec = importlib.util.spec_from_file_location("inspect_claef_v2", module_path)
assert spec is not None and spec.loader is not None
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def test_v2_inspector_preserves_parameter_definitions() -> None:
	metadata = {
		"parameters": {
			"rain_amount": {"name": "Total precipitation", "unit": "kg m-2"},
			"cloud_cover": {"name": "Cloud cover", "unit": "%"},
			"t": {"name": "Temperature", "unit": "K"}
		},
		"forecast_length": 61,
		"available_forecast_reftimes": ["2026-10-28T09:00:00Z"]
	}
	report = inspector.inspect(metadata)
	assert report["forecast_length"] == 61
	assert "rain_amount" in report["precipitation_candidates"]
	assert "cloud_cover" in report["cloud_candidates"]
	assert report["parameters"]["t"]["unit"] == "K"


def test_v2_inspector_refuses_missing_parameters() -> None:
	with pytest.raises(ValueError):
		inspector.inspect({"forecast_length": 61})
