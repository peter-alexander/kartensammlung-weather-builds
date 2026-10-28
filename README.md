# Kartensammlung Weather Builds

Eigenständiger Datenproduzent für numerische Wetterraster der Kartensammlung. Der Workflow lädt einen vollständigen GeoSphere-AROME-Modelllauf und veröffentlicht pro Vorhersagezeitpunkt eine kombinierte Raster-PMTiles-Datei mit:

- stündlichem Niederschlag aus der Differenz von `rr_acc`
- gesamter Bewölkung aus `tcc`
- transparenter NoData-Maske

Das Repository hat absichtlich keine technische Abhängigkeit zu `kartensammlung-overlay-builds`.

## Fachliche Regeln

### Niederschlag

`rr_acc` ist seit Modellstart akkumuliert. Der Build berechnet:

```text
precipitation_1h[t] = rr_acc[t] - rr_acc[t - 1]
```

Wenn GeoSphere den Startzeitpunkt des Modelllaufs für `rr_acc` vollständig als NoData liefert, wird dieser Startwert als 0 mm behandelt.
Kleine lokale Rückgänge des Akkumulationsfelds bis 0,5 mm werden als Quantisierungs- oder Modellartefakte behandelt. Ein einzelner Ausreißer bis 0,75 mm darf ebenfalls korrigiert werden; Zahl und Korrekturhöhe werden in der Validierung erfasst. Mehrere oder größere Ausreißer bleiben harte Fehler. Der Build macht die betroffene Zeitreihe monoton, sodass weder negativer Niederschlag noch ein künstlicher Nachholeffekt in der Folgestunde entsteht. Die Korrekturen werden in `validation.json` protokolliert. Größere negative Differenzen brechen den Build weiterhin ab.

### Zoomabhängige Rasterung

| Zoom | Niederschlag | Bewölkung |
|---:|---|---|
| 3–5 | Maximum aller betroffenen AROME-Zellen | Flächenmittel |
| 6–8 | nächstgelegene originale AROME-Zelle | nächstgelegene originale AROME-Zelle |
| >8 | Overscaling durch MapLibre | Overscaling durch MapLibre |

Damit wird in Übersichtszoomstufen keine konvektive Niederschlagszelle durch Mittelwertbildung unsichtbar. Ab Zoom 6 ist der Kartenpixel feiner als das etwa 2,5-km-Modellraster; dort wird nicht mehr aggregiert.

## PNG-Kanalbelegung

| Kanal | Inhalt |
|---|---|
| R + G | Niederschlag als unsigned 16 Bit, Auflösung 0,01 mm |
| B | Bewölkung 0–255 entsprechend 0–100 % |
| A | 255 = gültig, 0 = NoData/außerhalb des Modells |

Dekodierung Niederschlag:

```text
mm = R * 2.56 + G * 0.01
```

Dekodierung Bewölkung in Prozent:

```text
percent = B * (100 / 255)
```

## Veröffentlichung über GitHub Pages

Beide Workflows prüfen die GeoSphere-Referenzzeit automatisch. AROME wird alle zehn Minuten geprüft, INCA alle fünf Minuten. Der Zeitplan ist Best Effort: GitHub kann Scheduled Runs verzögern oder auslassen. Ein manueller Start per `workflow_dispatch` bleibt möglich.

- Die Probe vergleicht den ausgewählten Lauf mit `gh-pages` **und** der öffentlich abrufbaren `latest.json`.
- Bereits erfolgreich veröffentlichte Läufe werden ohne Build beendet.
- Neue Läufe werden vollständig gebaut und alle PMTiles-Dateien verifiziert.
- Der gemeinsame Workflow-Concurrency-Key verhindert konkurrierende Veröffentlichungen.
- Der Veröffentlichungs-Snapshot wird im `gh-pages`-Branch gespeichert. Dieser wird absichtlich durch einen parentlosen Snapshot-Commit ersetzt, um ein unbegrenzt wachsendes Archiv historischer Wetterdateien in Git zu vermeiden.
- Zusätzlich wird der vollständige Snapshot als Pages-Artefakt mit `actions/upload-pages-artifact` und `actions/deploy-pages` publiziert. Der Branch-Push allein löst keine GitHub-Pages-Veröffentlichung aus.
- AROME behält drei Versionen, INCA vier. Metadaten für beide Modelle werden beim jeweils nächsten Build gemeinsam erhalten.

**Einmalige Konfiguration:** Unter `Settings → Pages → Build and deployment` muss `GitHub Actions` als Quelle ausgewählt werden. Die GitHub-Actions-Workflowberechtigung zum Schreiben des Repository-Inhalts muss verfügbar sein. Der GitHub-Pages-Host wird nach der ersten erfolgreichen Veröffentlichung erreichbar.

Der öffentliche Inhalt lautet:

```text
https://peter-alexander.github.io/ks-wetter-builds/AROME/latest.json
https://peter-alexander.github.io/kartensammlung-weather-builds/INCA/latest.json
```

Die `latest.json` verweist relativ auf `<tag>/manifest.json` und die PMTiles-Dateien:

```json
{
	"schema_version": 1,
	"release_tag": "arome-20260717T1500Z",
	"reference_time": "2026-07-17T15:00:00Z",
	"manifest": "arome-20260717T1500Z/manifest.json",
	"asset_url_template": "arome-20260717T1500Z/{asset}"
}
```

**Inbetriebnahme:** Vor der Umstellung der Kartensammlung HTTP-Range (206), CORS, Manifest und alle erforderlichen PMTiles-URLs im Browser testen. Nur `kartensammlung-weather-builds` wird durch diese Migration verändert; die eigentliche Kartensammlung bleibt unverändert.

## Lokal testen

Voraussetzungen: Python 3.12+ und genügend freier Speicher.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
mkdir -p .local/bin
curl -fsSL \
	https://github.com/protomaps/go-pmtiles/releases/download/v1.30.1/go-pmtiles_1.30.1_Linux_x86_64.tar.gz \
	| tar -xz -C .local/bin pmtiles
python -m weather_build probe --output probe.json
python -m weather_build build \
	--work-directory work \
	--output-directory out \
	--pmtiles-binary "$PWD/.local/bin/pmtiles"
```

## MapLibre

Die Datei `examples/maplibre.js` zeigt beide Darstellungen aus derselben PMTiles-Datei. Erforderlich ist:

- MapLibre GL JS ab 5.6 für `color-relief`
- MapLibre GL JS ab 5.20 für explizites `resampling: nearest` beim 16-Bit-Niederschlag
- PMTiles-Protokollregistrierung

Für Niederschlag muss `nearest` verwendet werden. Lineare Texturinterpolation über zwei Bytes kann sonst an einem Byte-Übertrag falsche Zwischenwerte erzeugen. Bewölkung kann linear dargestellt werden.

## Datenquelle und Lizenz

Modelldaten: GeoSphere Austria, Numerical Weather Prediction `nwp-v1-1h-2500m`, Lizenz CC BY 4.0.

Die Build-Software selbst steht unter MIT-Lizenz.
