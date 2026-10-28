# GeoSphere-Wetterkarten: Manifest-Vertrag v1

Dieses Format ist der deklarative Vertrag zwischen Wetter-Build und Kartensammlung. Technische **Dekodierung** ist verbindlich, **Styling** eine frei austauschbare Empfehlung.

Ein Manifest gilt für eine Veröffentlichung eines GeoSphere-Produkts/Modelllaufs. Die `frames` referenzieren nur tatsächlich gebaute PMTiles. Werte, URLs und Zeiten in diesem Beispiel sind **schematisch** – keine veröffentlichten Assets und keine freigegebenen C-LAEF-Bereiche.

```json
{
	"schema_version": 1,
	"source": {
		"provider": "GeoSphere Austria",
		"dataset_id": "nwp-v2-1h-1km",
		"license": "CC BY 4.0"
	},
	"reference_time": "2026-10-28T12:00:00Z",
	"variables": [
		{
			"id": "2t",
			"unit": "degree Celsius",
			"temporal_semantics": "value_at_valid_time",
			"encoding": {
				"type": "uint16",
				"layout": "rg8",
				"nodata": 0,
				"scale": 0.1,
				"offset": -50
			},
			"style": {
				"type": "color-ramp",
				"stops": [
					[-20, "#3060af"],
					[0, "#d9eefa"],
					[30, "#d7191c"]
				]
			},
			"frames": [
				{
					"valid_time": "2026-10-28T13:00:00Z",
					"href": "2t/f001.pmtiles"
				}
			]
		}
	]
}
```

**Entwicklungsvertrag:** `uint16/rg8` wird als PNG-RGB mit `R=high byte`, `G=low byte`, `B=0` gespeichert, ohne Transparenz. `uint8/gray8` wird als PNG-Graustufenbild gespeichert. Der Python-PNG-Roundtrip ist durch Unit-Tests abgedeckt; ein erster JavaScript-Decoder unter `web/numeric-weather-decoder.mjs` kann nach dem PNG-Decoding die Codes und frei wählbare Farbskalen interpretieren. Ein echter MapLibre-/Safari-End-to-End-Test fehlt weiterhin. Die Validierung des gegenwärtigen Manifests prüft Struktur, Dekodierung und Frames, **nicht** die Existenz oder Browserlesbarkeit der referenzierten PMTiles. Daher ist das Format vorerst ein Entwicklungsvertrag und kein freigegebener Produktivstandard.

Bei Veröffentlichung sollte ein unveränderlicher Modelllauf-Pfad verwendet und ein kleines `latest.json` atomar auf dieses Manifest verweisen. Die Kartensammlung darf die Layer-Farbskala ändern, aber niemals die zur Archivdatei gehörende Dekodierung ohne passende Daten ersetzen.


Der Builder `weather_build/numeric_tiles.py` schreibt einzelne numerische Felder in MBTiles und konvertiert sie per bestehender PMTiles-CLI. Er führt pro Tile einen Roundtrip aus. Er ist **noch kein vollständiger GeoSphere-Modelllauf-Builder** und setzt verifizierte Rasterkoordinaten, explizite Quantisierung und fachlich korrektes Resampling voraus. Decoder-/Styletests können mit `node tests/test_numeric_weather_decoder.mjs` lokal ausgeführt werden; die für diesen Build zwingend zu prüfende Browser-/WebGL-Integration ist noch nicht getestet.
