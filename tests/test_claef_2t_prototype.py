from datetime import datetime, timezone

import numpy as np
import pytest
import xarray as xr

from scripts.build_claef_2t_prototype import read_2t_netcdf


def _sample(tmp_path, *, nlat=945, nlon=1300, unit="degree Celsius", direction=1):
	lat = np.arange(nlat, dtype=float) * 0.009 + 43
	lon = np.arange(nlon, dtype=float) * 0.0135 + 5
	if direction < 0:
		lat = lat[::-1]
	values = np.tile(lat[:, None] * np.ones(nlon), (1, 1))
	data = xr.Dataset(
		{"2t": (("time", "lat", "lon"), values[None], {"units": unit})},
		coords={"time": [np.datetime64("2026-10-28T13:00:00")], "lat": lat, "lon": lon}
	)
	path = tmp_path / "sample.nc"
	data.to_netcdf(path)
	return path


def test_native_geometry_and_north_up(tmp_path) -> None:
	path = _sample(tmp_path)
	values, transform, bbox = read_2t_netcdf(path,
		valid_time=datetime(2026, 10, 28, 13, tzinfo=timezone.utc))
	assert values.shape == (945, 1300)
	assert values[0, 0] > values[-1, 0]
	assert transform.e < 0
	assert bbox.south < bbox.north


def test_wrong_crs_axis_or_grid_cannot_silently_pass(tmp_path) -> None:
	path = _sample(tmp_path, nlat=944)
	with pytest.raises(ValueError, match="Unexpected native grid"):
		read_2t_netcdf(path, valid_time=datetime(2026, 10, 28, 13, tzinfo=timezone.utc))
	path = _sample(tmp_path, direction=-1)
	with pytest.raises(ValueError, match="axis directions"):
		read_2t_netcdf(path, valid_time=datetime(2026, 10, 28, 13, tzinfo=timezone.utc))


def test_unit_and_time_must_match(tmp_path) -> None:
	path = _sample(tmp_path, unit="K")
	with pytest.raises(ValueError, match="unit"):
		read_2t_netcdf(path, valid_time=datetime(2026, 10, 28, 13, tzinfo=timezone.utc))
	path = _sample(tmp_path)
	with pytest.raises(ValueError, match="time"):
		read_2t_netcdf(path, valid_time=datetime(2026, 10, 28, 14, tzinfo=timezone.utc))
