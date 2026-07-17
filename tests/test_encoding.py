import numpy as np

from weather_build.config import BuildConfig
from weather_build.tiles import decode_rgba, encode_rgba


def test_encoding_roundtrip() -> None:
	config = BuildConfig()
	precipitation = np.array([[0.0, 0.01, 12.34, 255.99, np.nan]], dtype=np.float32)
	cloud = np.array([[0.0, 0.5, 1.0, 0.123, np.nan]], dtype=np.float32)
	rgba = encode_rgba(precipitation, cloud, config)
	decoded_precipitation, decoded_cloud, valid = decode_rgba(rgba, config)

	assert rgba[0, 0].tolist() == [0, 0, 0, 255]
	assert rgba[0, 1].tolist() == [0, 1, 128, 255]
	assert rgba[0, 4].tolist() == [0, 0, 0, 0]
	assert np.array_equal(valid, np.array([[True, True, True, True, False]]))
	assert np.nanmax(np.abs(decoded_precipitation - precipitation)) <= 0.0051
	assert np.nanmax(np.abs(decoded_cloud - cloud)) <= 0.5 / 255 + 1e-6
