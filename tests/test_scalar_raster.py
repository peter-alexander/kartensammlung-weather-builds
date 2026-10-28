from __future__ import annotations

import numpy as np
import pytest

from weather_build.scalar_raster import (
	ScalarRasterError, ScalarSpec, validate_metadata_unit, validate_scalar
)


def test_explicit_kelvin_to_celsius_conversion() -> None:
	spec = ScalarSpec("temperature", "K", "°C", scale=1, offset=-273.15, min_value=-100, max_value=70)
	values = np.array([[273.15, 280.15], [np.nan, 300.15]], dtype=np.float32)
	output, report = validate_scalar(values, spec)
	assert np.allclose(output[0], [0, 7], atol=1e-4)
	assert np.isnan(output[1, 0])
	assert report["nodata_cells"] == 1
	assert report["source_unit"] == "K"


def test_native_precipitation_identity_preserves_values() -> None:
	spec = ScalarSpec("rain", "kg m-2", "kg m-2", min_value=0)
	values = np.array([[[0.2]], [[0.1]]], dtype=np.float32)
	output, _ = validate_scalar(values, spec)
	assert np.array_equal(output, values)


def test_invalid_range_is_rejected_not_clamped() -> None:
	with pytest.raises(ScalarRasterError):
		validate_scalar(np.array([[-0.1]]), ScalarSpec("rain", "mm", "mm", min_value=0))


def test_no_valid_values_and_infinity_fail() -> None:
	spec = ScalarSpec("temp", "K", "K")
	for data in (np.array([[np.nan]]), np.array([[np.inf]])):
		with pytest.raises(ScalarRasterError):
			validate_scalar(data, spec)


def test_unit_change_requires_explicit_contract() -> None:
	spec = ScalarSpec("temp", "K", "°C", offset=-273.15)
	with pytest.raises(ScalarRasterError):
		validate_metadata_unit("°C", spec)
	validate_metadata_unit("K", spec)


def test_reject_bad_dimensions() -> None:
	with pytest.raises(ScalarRasterError):
		validate_scalar(np.array([1, 2]), ScalarSpec("t", "K", "K"))
