"""Versioned contract between GeoSphere tile producers and map consumers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


class ManifestError(ValueError):
	pass


def _time(value: str) -> datetime:
	if not isinstance(value, str):
		raise ManifestError("Timestamps must be ISO 8601 UTC strings.")
	try:
		parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError as exc:
		raise ManifestError(f"Invalid timestamp: {value!r}") from exc
	if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
		raise ManifestError("Timestamps must explicitly use UTC.")
	return parsed.astimezone(timezone.utc)


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
		raise ManifestError("Unsupported tile manifest schema.")
	source = manifest.get("source")
	if not isinstance(source, dict) or not all(source.get(x) for x in ("provider", "dataset_id", "license")):
		raise ManifestError("Source provenance and license required.")
	variables = manifest.get("variables")
	if not isinstance(variables, list) or not variables:
		raise ManifestError("At least one variable is required.")
	seen_ids = set()
	for variable in variables:
		if not isinstance(variable, dict):
			raise ManifestError("Invalid variable descriptor.")
		name = variable.get("id")
		if not isinstance(name, str) or not name or name in seen_ids:
			raise ManifestError("Variable identifiers must be unique and nonempty.")
		seen_ids.add(name)
		if not all(variable.get(x) for x in ("unit", "temporal_semantics")):
			raise ManifestError(f"Missing unit or temporal semantics: {name}")
		encoding = variable.get("encoding")
		if not isinstance(encoding, dict) or encoding.get("type") not in ("uint8", "uint16"):
			raise ManifestError(f"Unsupported encoding for {name}")
		if encoding.get("nodata") != 0 or encoding.get("layout") not in ("gray8", "rg8"):
			raise ManifestError(f"Invalid NoData/layout for {name}")
		if (encoding["type"] == "uint8") != (encoding["layout"] == "gray8"):
			raise ManifestError(f"Encoding layout conflicts with bit depth: {name}")
		scale, offset = encoding.get("scale"), encoding.get("offset")
		if not isinstance(scale, (int, float)) or not isinstance(offset, (int, float)) or not 0 < scale < float("inf") or abs(offset) == float("inf") or offset != offset:
			raise ManifestError(f"Invalid decoding scale/offset: {name}")
		style = variable.get("style")
		if not isinstance(style, dict) or style.get("type") != "color-ramp":
			raise ManifestError(f"Missing recommended styling for {name}")
		stops = style.get("stops")
		if not isinstance(stops, list) or not stops or any(
			not isinstance(stop, list) or len(stop) != 2 or not isinstance(stop[0], (int, float)) or not isinstance(stop[1], str)
			for stop in stops
		):
			raise ManifestError(f"Invalid styling stops for {name}")
		if any(stops[i][0] >= stops[i + 1][0] for i in range(len(stops) - 1)):
			raise ManifestError(f"Color stops must be strictly increasing: {name}")
		frames = variable.get("frames")
		if not isinstance(frames, list) or not frames:
			raise ManifestError(f"No frames for {name}")
		seen_times = set()
		for frame in frames:
			if not isinstance(frame, dict):
				raise ManifestError("Invalid frame")
			time = _time(frame.get("valid_time"))
			if time in seen_times:
				raise ManifestError(f"Duplicate time for {name}")
			seen_times.add(time)
			href = frame.get("href")
			if not isinstance(href, str) or not href or href.startswith("/") or urlsplit(href).scheme or urlsplit(href).netloc or ".." in href.split("/"):
				raise ManifestError(f"Unsafe frame URL for {name}")
		if frames != sorted(frames, key=lambda frame: _time(frame["valid_time"])):
			raise ManifestError(f"Frames out of order for {name}")
	reference_time = manifest.get("reference_time")
	if reference_time is not None:
		_time(reference_time)
	return manifest
