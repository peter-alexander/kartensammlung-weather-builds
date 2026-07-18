from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from weather_build.config import load_config
from weather_build.geosphere import BoundingBox, ProbeResult, _grid_shape
from weather_build.inca import _manifest, validate_interval_precipitation
from weather_build.netcdf import ForecastDataError


def _probe() -> ProbeResult:
	reference_time = datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc)
	return ProbeResult(
		reference_time=reference_time,
		forecast_length=13,
		step=timedelta(minutes=15),
		bbox=BoundingBox(south=45.5, west=8.1, north=49.48, east=17.74),
		spatial_resolution=(1000.0, 1000.0),
		spatial_resolution_unit="m",
		grid_width=10,
		grid_height=5,
		grid_points=50,
		tag="inca-20260718T0900Z",
		metadata={}
	)


def test_inca_config() -> None:
	config = load_config(Path("config/inca-nowcast.json"))
	assert config.resource_id == "nowcast-v1-15min-1km"
	assert config.parameters == ("rr",)
	assert config.has_cloud is False
	assert config.precipitation_output_parameter == "precipitation_15min"


def test_interval_precipitation_is_not_differenced() -> None:
	config = load_config(Path("config/inca-nowcast.json"))
	values = np.array([[[0.0]], [[0.2]], [[1.1]]], dtype=np.float32)
	result, validation = validate_interval_precipitation(values, config)
	assert np.allclose(result[:, 0, 0], [0.0, 0.2, 1.1])
	assert validation["mode"] == "interval"
	assert validation["interval_minutes"] == 15


def test_small_negative_interval_is_clamped() -> None:
	config = load_config(Path("config/inca-nowcast.json"))
	values = np.array([[[0.1]], [[-0.02]]], dtype=np.float32)
	result, validation = validate_interval_precipitation(values, config)
	assert np.allclose(result[:, 0, 0], [0.1, 0.0])
	assert validation["tiny_negative_values_clamped"] == 1


def test_serious_negative_interval_fails() -> None:
	config = load_config(Path("config/inca-nowcast.json"))
	values = np.array([[[0.1]], [[-0.6]]], dtype=np.float32)
	with pytest.raises(ForecastDataError):
		validate_interval_precipitation(values, config)


def test_inca_manifest_marks_blue_channel_unused(
	monkeypatch: pytest.MonkeyPatch
) -> None:
	config = load_config(Path("config/inca-nowcast.json"))
	probe = _probe()
	monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
	prepared = type(
		"Prepared",
		(),
		{"x_values": np.zeros(4), "y_values": np.zeros(3)}
	)()
	manifest = _manifest(probe, config, prepared, [])
	assert manifest["model"] == "INCA Nowcast"
	assert manifest["encoding"]["blue"]["availability"] == "unused"
	assert manifest["forecast"]["step_minutes"] == 15


def test_projected_grid_shape_uses_projected_bbox() -> None:
	width, height = _grid_shape(
		BoundingBox(south=45.5, west=8.1, north=49.48, east=17.74),
		(1000.0, 1000.0),
		"m",
		{"crs": "EPSG:31287"}
	)
	assert width > 500
	assert height > 300
	assert width * height < 1_000_000
