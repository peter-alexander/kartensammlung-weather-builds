from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys

from .build import run_build
from .config import load_config
from .geosphere import GeoSphereClient, write_github_output, write_probe_json


def main(argv: list[str] | None = None) -> int:
	parser = _parser()
	arguments = parser.parse_args(argv)
	logging.basicConfig(
		level=getattr(logging, arguments.log_level.upper()),
		format="%(asctime)s %(levelname)s %(name)s: %(message)s"
	)
	config = load_config(arguments.config)

	try:
		if arguments.command == "probe":
			probe = GeoSphereClient(config).probe(forecast_offset=arguments.forecast_offset)
			write_probe_json(probe, arguments.output)
			if arguments.github_output:
				write_github_output(probe, arguments.github_output)
			print(json.dumps({"tag": probe.tag, "reference_time": probe.reference_time.isoformat()}))
			return 0

		if arguments.command == "build":
			expected_reference_time = None
			if arguments.reference_time:
				expected_reference_time = _parse_datetime(arguments.reference_time)
			result = run_build(
				config=config,
				work_directory=arguments.work_directory,
				output_directory=arguments.output_directory,
				pmtiles_binary=arguments.pmtiles_binary,
				forecast_offset=arguments.forecast_offset,
				expected_reference_time=expected_reference_time
			)
			print(json.dumps(result, ensure_ascii=False))
			return 0
		raise RuntimeError(f"Unbekanntes Kommando: {arguments.command}")
	except Exception:
		logging.getLogger(__name__).exception("Weather-Build fehlgeschlagen")
		return 1


def _parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="GeoSphere-AROME-Raster-PMTiles bauen")
	parser.add_argument("--config", type=Path, default=None)
	parser.add_argument(
		"--log-level",
		default=os.environ.get("LOG_LEVEL", "INFO"),
		choices=("DEBUG", "INFO", "WARNING", "ERROR")
	)
	subparsers = parser.add_subparsers(dest="command", required=True)

	probe = subparsers.add_parser("probe", help="Neuesten verfügbaren AROME-Lauf ermitteln")
	probe.add_argument("--forecast-offset", type=int, default=0)
	probe.add_argument("--output", type=Path, default=Path("probe.json"))
	probe.add_argument("--github-output", type=Path, default=None)

	build = subparsers.add_parser("build", help="Vollständigen Modelllauf bauen")
	build.add_argument("--forecast-offset", type=int, default=0)
	build.add_argument("--reference-time", default=None)
	build.add_argument("--work-directory", type=Path, default=Path("work"))
	build.add_argument("--output-directory", type=Path, default=Path("out"))
	build.add_argument("--pmtiles-binary", default=os.environ.get("PMTILES_BIN", "pmtiles"))
	return parser


def _parse_datetime(value: str) -> datetime:
	parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc).replace(microsecond=0)


if __name__ == "__main__":
	sys.exit(main())
