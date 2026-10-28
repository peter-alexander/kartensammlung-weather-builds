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

Für `uint16/rg8` ist **noch verbindlich zu entscheiden und zu testen**, ob der 16-Bit-Code in RG (R=high byte, G=low byte) oder in einem nativen PNG-16-Bit-Kanal transportiert wird; vor dem produktiven Schreiben benötigen wir einen Browserdecoder-Test. Die Validierung des gegenwärtigen Manifests prüft Struktur, Dekodierung und Frames, **nicht** die Existenz oder Browserlesbarkeit der referenzierten PMTiles. Daher ist das Format vorerst ein Entwicklungsvertrag und kein freigegebener Produktivstandard.

Bei Veröffentlichung sollte ein unveränderlicher Modelllauf-Pfad verwendet und ein kleines `latest.json` atomar auf dieses Manifest verweisen. Die Kartensammlung darf die Layer-Farbskala ändern, aber niemals die zur Archivdatei gehörende Dekodierung ohne passende Daten ersetzen.
