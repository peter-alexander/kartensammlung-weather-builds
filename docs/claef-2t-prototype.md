# C-LAEF-v2: erster Temperatur-Prototyp

**Status: experimentell, nicht automatisch veröffentlicht.**

Ein einzelner vollständiger C-LAEF-Zeitpunkt des Parameters `2t` wird direkt aus GeoSphere geladen (+1 h gegenüber dem neuesten Modelllauf). Die NetCDF-Datei muss genau `time, lat, lon`, 945×1300 Zellen, aufsteigende gleichabständige Koordinaten und Einheit `degree Celsius` enthalten. Die **aus den Zellzentren berechneten Zellkanten** bilden das Affine und die BBox für die Projektion. Nur das tatsächlich gelieferte NetCDF-Raster ist maßgeblich, nicht die bekannte falsche Shape-Schätzung des älteren Builders.

Anschließend entstehen numerische PNG-Kacheln in MBTiles und per PMTiles-CLI ein PMTiles-Archiv, sowie ein getrenntes `manifest.json` mit Dekodierung, Zeitbezug und empfohlener Temperatur-Farbskala. Die Werte werden beim Kachelbau gegengeprüft. Dieser Prototyp verändert weder bestehende INCA-/AROME-Workflows noch öffentliche Assets.

Voraussetzungen: installierte Python-Paketabhängigkeiten des Repositories und die ausführbare PMTiles-CLI.

```sh
python -m pip install -e '.[dev]'
python -m pytest -q tests/test_claef_2t_prototype.py tests/test_numeric_tiles.py tests/test_tile_png.py tests/test_tile_manifest.py
python scripts/build_claef_2t_prototype.py --output /tmp/claef-2t-test --min -50 --max 60
```

**Achtung:** `--min -50 --max 60` ist nur ein plausibler Testbereich, keine fachlich freigegebene Produktionsgrenze. Die tatsächlichen Grenzen dürfen nicht aus einzelnen Stichproben abgeleitet werden. Falls der aktuelle Modelllauf Werte außerhalb liefert, scheitert die Kodierung ausdrücklich.

Ergebnisse: `source-2t.nc`, `2t-f001.mbtiles`, `2t-f001.pmtiles` und `manifest.json`. Im Manifest verweist `frames[0].href` relativ auf das PMTiles-Archiv. Die Kachelkanäle enthalten Datenwerte und dürfen **nicht als gewöhnliches farbiges Raster angezeigt werden**. Zur Darstellung ist der Decoder `web/numeric-weather-decoder.mjs` mit einem numerischen Kachelladepfad zu verbinden.

**Noch offen:** Der reale API-Abruf und die PMTiles-CLI-Konvertierung wurden nicht in einer Live-CI ausgeführt. Die Testseite in MapLibre/OpenLayers und der Browser-Nachweis der verlustfreien PNG-Kanalwerte fehlen noch. Der Prototyp ist ein Baustein, kein produktiver Scheduler.
