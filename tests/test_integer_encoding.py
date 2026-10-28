import numpy as np
import pytest

from weather_build.integer_encoding import Quantization, QuantizationError, encode_integer, decode_integer


def test_uint16_roundtrip_preserves_temperature_quantization() -> None:
	spec = Quantization(bits=16, step=0.1, origin=-100)
	source = np.array([[-12.3, 0.0, np.nan, 48.7]], dtype=np.float64)
	codes, report = encode_integer(source, spec)
	recovered = decode_integer(codes, spec)
	assert codes.dtype == np.uint16
	assert codes[0, 2] == 0
	assert np.allclose(recovered[0, [0, 1, 3]], source[0, [0, 1, 3]])
	assert np.isnan(recovered[0, 2])
	assert report["maximum_absolute_error"] < 1e-10


def test_uint8_roundtrip_and_quantization_error() -> None:
	spec = Quantization(bits=8, step=0.5, origin=0)
	codes, report = encode_integer(np.array([[1.2, 2.0]]), spec)
	assert np.allclose(decode_integer(codes, spec), [[1.0, 2.0]])
	assert report["maximum_absolute_error"] == pytest.approx(0.2)


def test_range_violation_is_hard_failure_not_clamping() -> None:
	with pytest.raises(QuantizationError):
		encode_integer(np.array([[-0.1]]), Quantization(8, 0.1, 0.0))
	with pytest.raises(QuantizationError):
		encode_integer(np.array([[255.0]]), Quantization(8, 1, 0))


def test_invalid_spec_and_infinity_rejected() -> None:
	with pytest.raises(QuantizationError):
		Quantization(32, 0.1, 0)
	with pytest.raises(QuantizationError):
		encode_integer(np.array([[np.inf]]), Quantization(16, 0.1, 0))
