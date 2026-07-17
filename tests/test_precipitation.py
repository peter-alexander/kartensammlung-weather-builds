import numpy as np
import pytest

from weather_build.config import BuildConfig
from weather_build.netcdf import ForecastDataError, accumulated_to_interval_precipitation


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


def test_small_negative_difference_within_tolerance_is_clamped() -> None:
	config = BuildConfig()
	accumulated = np.array([[[1.0]], [[0.934]]], dtype=np.float32)
	interval, validation = accumulated_to_interval_precipitation(accumulated, config)
	assert np.allclose(interval[:, 0, 0], [1.0, 0.0])
	assert validation["tiny_negative_values_clamped"] == 1


def test_missing_initial_accumulation_is_assumed_zero() -> None:
	config = BuildConfig()
	accumulated = np.array([[[np.nan]], [[2.5]]], dtype=np.float32)
	interval, validation = accumulated_to_interval_precipitation(accumulated, config)
	assert np.allclose(interval[:, 0, 0], [0.0, 2.5])
	assert validation["initial_accumulation_missing_assumed_zero"] is True


def test_serious_negative_difference_fails() -> None:
	config = BuildConfig()
	accumulated = np.array([[[1.0]], [[0.8]]], dtype=np.float32)
	with pytest.raises(ForecastDataError):
		accumulated_to_interval_precipitation(accumulated, config)
