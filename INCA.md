# GeoSphere INCA Nowcast

Der zusätzliche Workflow **Build GeoSphere INCA nowcast tiles** verarbeitet die GeoSphere-Ressource:

```text
nowcast-v1-15min-1km
```

## Produkt

- Aktualisierung: alle 15 Minuten
- Zeitschritt: 15 Minuten
- Horizont: 3 Stunden
- Raster: 1 km
- Gebiet: Österreich
- verwendeter Parameter: `rr`

`rr` wird als Niederschlagsmenge des jeweiligen 15-Minuten-Intervalls verarbeitet und nicht wie AROME-`rr_acc` differenziert.

## Dateien

```text
inca_m000.pmtiles
inca_m015.pmtiles
inca_m030.pmtiles
...
inca_m180.pmtiles
manifest.json
validation.json
```

## PNG-Codierung

| Kanal | Inhalt |
|---|---|
| R + G | Niederschlag in 0,01 mm |
| B | unbenutzt, immer 0 |
| A | Gültigkeitsmaske |

Die Niederschlagsdekodierung ist identisch zu AROME:

```text
mm = R * 2.56 + G * 0.01
```

## Easyname

```text
Wetter/INCA/latest.json
Wetter/INCA/inca-YYYYMMDDTHHMMZ/
```

Es werden vier vollständige INCA-Läufe behalten.

## Start

Der Workflow wird zunächst manuell über `workflow_dispatch` gestartet. Der externe Easyname-Trigger muss anschließend zusätzlich auf `.github/workflows/build-inca.yml` zeigen.

Empfohlene Inputs:

```text
forecast_offset: 0
force: false
```

Jeder Lauf beginnt mit einem kleinen Probe-Job. Der eigentliche Build startet nur, wenn der INCA-Release noch nicht vollständig veröffentlicht ist.
