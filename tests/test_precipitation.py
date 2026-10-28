import numpy as np
import pytest

from weather_build.config import BuildConfig
from weather_build.netcdf import ForecastDataError, accumulated_to_interval_precipitation, validate_interval_precipitation


def test_accumulated_precipitation_is_differenced() -> None:
	config = BuildConfig()
	accumulated = np.array(
		[
			[[0.0, 0.0]],
			[[1.0, 0.4]],
			[[3.5, 0.39]]
		],
		dtype=np.float32
	)
	interval, validation = accumulated_to_interval_precipitation(accumulated, config)
	assert np.allclose(interval[:, 0, 0], [0.0, 1.0, 2.5])
	assert np.allclose(interval[:, 0, 1], [0.0, 0.4, 0.0])
	assert validation["tiny_negative_values_clamped"] == 1


def test_small_negative_difference_within_tolerance_is_corrected_monotonically() -> None:
	config = BuildConfig()
	accumulated = np.array(
		[
			[[0.0]],
			[[1.0]],
			[[0.76]],
			[[1.1]]
		],
		dtype=np.float32
	)
	interval, validation = accumulated_to_interval_precipitation(accumulated, config)
	assert np.allclose(interval[:, 0, 0], [0.0, 1.0, 0.0, 0.1])
	assert validation["tiny_negative_values_clamped"] == 1
	assert validation["negative_accumulation_values_corrected"] == 1
	assert validation["raw_interval_min_mm"] == pytest.approx(-0.24, abs=1e-6)
	assert validation["maximum_accumulation_correction_mm"] == pytest.approx(0.24, abs=1e-6)


def test_missing_initial_accumulation_is_assumed_zero() -> None:
	config = BuildConfig()
	accumulated = np.array([[[np.nan]], [[2.5]]], dtype=np.float32)
	interval, validation = accumulated_to_interval_precipitation(accumulated, config)
	assert np.allclose(interval[:, 0, 0], [0.0, 2.5])
	assert validation["initial_accumulation_missing_assumed_zero"] is True


def test_serious_negative_difference_fails() -> None:
	config = BuildConfig()
	accumulated = np.array([[[1.0]], [[0.4]]], dtype=np.float32)
	with pytest.raises(ForecastDataError):
		accumulated_to_interval_precipitation(accumulated, config)

def test_v2_hourly_precipitation_is_not_differenced() -> None:
	config = BuildConfig(precipitation_mode="interval")
	values = np.array([[[0.7]], [[0.1]], [[1.2]]], dtype=np.float32)
	output, validation = validate_interval_precipitation(values, config)
	assert np.array_equal(output, values)
	assert validation["mode"] == "interval"
	assert validation["interval_min_mm"] == pytest.approx(0.1)


def test_v2_negative_hourly_precipitation_is_rejected() -> None:
	config = BuildConfig(precipitation_mode="interval")
	with pytest.raises(ForecastDataError):
		validate_interval_precipitation(np.array([[[0.1]], [[-0.001]]], dtype=np.float32), config)


def test_v2_nodata_preserved() -> None:
	config = BuildConfig(precipitation_mode="interval")
	values = np.array([[[np.nan]], [[2.3]]], dtype=np.float32)
	output, validation = validate_interval_precipitation(values, config)
	assert np.isnan(output[0, 0, 0])
	assert validation["nodata_values"] == 1
