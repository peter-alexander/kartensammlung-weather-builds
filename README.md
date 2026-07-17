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
Kleine negative Rundungsartefakte bis 0,1 mm werden auf null gesetzt. Größere negative Differenzen brechen den Build ab.

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

## Veröffentlichungsmodell

Der GitHub-Workflow läuft stündlich, prüft aber zunächst die GeoSphere-Referenzzeit. Bereits veröffentlichte Modellläufe werden ohne Build beendet. Für einen neuen Lauf:

1. Metadaten und konkrete Modell-Referenzzeit ermitteln.
2. NetCDF-Abfragen unter dem 10-Millionen-Werte-Limit planen.
3. Bei jeder Teilabfrage den aktuellen Offset derselben Referenzzeit neu bestimmen.
4. NetCDF-Teile zusammenführen und vollständig validieren.
5. Je Zeitpunkt Raster-PMTiles für Zoom 3–8 bauen.
6. Einen Draft-Release erstellen und alle Assets hochladen.
7. Den Release erst nach vollständigem Upload veröffentlichen.
8. Nur die drei neuesten AROME-Releases behalten.

Der wechselnde `forecast_offset` ist wichtig: Er verhindert, dass ein während des Downloads neu erscheinender Modelllauf die Teilabfragen mischt.

## Release-Inhalt

```text
arome_f000.pmtiles
arome_f001.pmtiles
...
arome_f060.pmtiles
manifest.json
validation.json
```

`manifest.json` dokumentiert Modelllauf, Zeitpunkte, BBox, Aggregationsregeln, Codierung, Prüfsummen und Dateigrößen.

## Eigenes Repository einrichten

1. Ein leeres öffentliches Repository anlegen, empfohlen: `kartensammlung-weather-builds`.
2. Diesen Inhalt nach `main` pushen.
3. Unter **Settings → Actions → General → Workflow permissions** Schreibrechte für `GITHUB_TOKEN` erlauben, sofern die Repository-Voreinstellung nur Leserechte zulässt.
4. Den Workflow **Build GeoSphere AROME weather tiles** zunächst manuell starten.

Es werden keine Secrets benötigt. GeoSphere verlangt für diese öffentlich zugänglichen Daten derzeit keinen API-Key.

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
