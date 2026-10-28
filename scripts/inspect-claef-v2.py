#!/usr/bin/env python3
"""Inspect GeoSphere C-LAEF AlpeAdria v2 metadata without assuming parameter semantics."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://dataset.api.hub.geosphere.at/v1/grid/forecast/nwp-v2-1h-1km/metadata"


def inspect(metadata: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(metadata, dict):
		raise ValueError("Metadata response must be a JSON object")
	parameters = metadata.get("parameters")
	if not isinstance(parameters, dict) or not parameters:
		raise ValueError("No parameter metadata; check API response schema before migrating")
	reftimes = metadata.get("available_forecast_reftimes") or metadata.get("availableForecastReftimes")
	return {
		"resource_id": "nwp-v2-1h-1km",
		"inspected_at": datetime.now(timezone.utc).isoformat(),
		"available_forecast_reftimes": reftimes,
		"forecast_length": metadata.get("forecast_length", metadata.get("forecastLength")),
		"spatial_resolution": metadata.get("spatial_resolution", metadata.get("spatialResolution")),
		"spatial_resolution_unit": metadata.get("spatial_resolution_unit", metadata.get("spatialResolutionUnit")),
		"bbox_outer": metadata.get("bbox_outer", metadata.get("bboxOuter")),
		"crs": metadata.get("crs"),
		"parameters": parameters,
		"precipitation_candidates": {
			name: description
			for name, description in parameters.items()
			if any(word in (name + " " + json.dumps(description, ensure_ascii=False)).lower()
				for word in ("precip", "rain", "niederschlag", "rr_", "accum"))
		},
		"cloud_candidates": {
			name: description
			for name, description in parameters.items()
			if any(word in (name + " " + json.dumps(description, ensure_ascii=False)).lower()
				for word in ("cloud", "bewölk", "tcc"))
		}
	}


def download() -> dict[str, Any]:
	session = requests.Session()
	retries = Retry(total=5, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504))
	session.mount("https://", HTTPAdapter(max_retries=retries))
	response = session.get(URL, timeout=60)
	response.raise_for_status()
	return response.json()


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--output", type=Path, default=Path("claef-v2-metadata.json"))
	parser.add_argument("--report", type=Path, default=Path("claef-v2-report.json"))
	args = parser.parse_args()
	metadata = download()
	report = inspect(metadata)
	args.output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
