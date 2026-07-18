from weather_build.geosphere import _bounding_box, _forecast_step, _grid_shape


def test_bbox_and_grid_shape() -> None:
	bbox = _bounding_box({"bbox_outer": [42.981, 5.498, 51.819, 22.102]})
	assert _grid_shape(bbox, (0.028, 0.018), "deg", {}) == (594, 493)


def test_resource_id_fallback_frequency() -> None:
	assert _forecast_step({}, "nwp-v1-1h-2500m").total_seconds() == 3600
