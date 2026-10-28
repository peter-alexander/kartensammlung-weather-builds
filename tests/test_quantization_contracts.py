from __future__ import annotations

import pytest

from weather_build.quantization_contracts import ContractError, contract_from_audit
from weather_build.integer_encoding import encode_integer, decode_integer
import numpy as np


def row(name="2t", unit="degree Celsius", step=0.1):
	return {
		"dataset_id": "nwp-v2-1h-1km",
		"api_name": name,
		"api_unit": unit,
		"netcdf_evidence": {
			"units_netcdf": unit,
			"raw_dtype": "int16",
			"scale_factor": step,
			"add_offset": None,
			"sample_decoded_min": 4.2,
			"sample_decoded_max": 10.9,
		},
		"temporal_interpretation": {"kind": "value_at_valid_time"},
	}


def test_reviewed_bounds_and_native_packing_step() -> None:
	contract = contract_from_audit([row()], "nwp-v2-1h-1km", "2t",
		declared_min=-40, declared_max=60)
	assert contract.quantization.bits == 16
	assert contract.quantization.step == 0.1
	assert contract.manifest()["storage"]["nodata"] == 0
	source = np.array([[4.2, 10.9, np.nan]])
	codes, _ = encode_integer(source, contract.quantization)
	decoded = decode_integer(codes, contract.quantization)
	assert np.allclose(decoded[0, :2], source[0, :2])
	assert np.isnan(decoded[0, 2])


def test_sample_extrema_are_not_automatic_product_bounds() -> None:
	with pytest.raises(TypeError):
		contract_from_audit([row()], "nwp-v2-1h-1km", "2t")


def test_reject_inconsistent_metadata_or_unrepresentable_range() -> None:
	bad = row()
	bad["netcdf_evidence"]["units_netcdf"] = "K"
	with pytest.raises(ContractError):
		contract_from_audit([bad], "nwp-v2-1h-1km", "2t",
			declared_min=-40, declared_max=60)
	with pytest.raises(ContractError):
		contract_from_audit([row(step=0.001)], "nwp-v2-1h-1km", "2t",
			declared_min=-100, declared_max=100)
