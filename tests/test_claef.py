from __future__ import annotations

import pytest

from weather_build.claef import (
	CLAEFMetadataError,
	parse_parameters,
	select_precipitation_and_cloud,
)


def test_metadata_parameter_array_retains_units() -> None:
	metadata = {"parameters": [
		{"name": "precip_v2", "unit": "mm", "description": "last hour"},
		{"name": "cloud_v2", "unit": "%", "description": "cloud fraction"},
	]}
	selection = select_precipitation_and_cloud(
		metadata, precipitation_name="precip_v2", cloud_name="cloud_v2"
	)
	assert selection.precipitation.unit == "mm"
	assert selection.cloud.unit == "%"


def test_metadata_parameter_dictionary() -> None:
	assert parse_parameters({"parameters": {"10u": {"unit": "m/s"}}})["10u"].unit == "m/s"


def test_unknown_parameter_is_not_silently_mapped() -> None:
	with pytest.raises(CLAEFMetadataError):
		select_precipitation_and_cloud(
			{"parameters": [{"name": "rr", "unit": "mm"}]},
			precipitation_name="rr_acc",
			cloud_name="tcc",
		)


def test_missing_unit_fails_closed() -> None:
	with pytest.raises(CLAEFMetadataError):
		select_precipitation_and_cloud(
			{"parameters": [{"name": "rain"}, {"name": "cloud", "unit": "1"}]},
			precipitation_name="rain",
			cloud_name="cloud",
		)
