# GeoSphere-Neuintegration: verifizierter Audit

Stand: 2026-10-28 (Europe/Vienna)

Repository-Revision: `6e9fc57d0deac3f374047933634e23e5220acd3c`

Branch: `feat/claef-alpeadria-v2`, Draft-PR: [#9](https://github.com/peter-alexander/ks-wetter-builds/pull/9)

## Kurzurteil

1. **Bestätigt:** Die Dataset-API stellt nicht einen homogenen „Wetterrastertyp“, sondern mindestens fünf praktisch relevante Gitterfamilien bereit: geographische C-LAEF-Gitter, EPSG:31287-INCA/APOLIS-Gitter, EPSG:3416-Klimagitter, zwei projektierte Chemiegitter sowie das geographische Staubgitter. Ein einzelner Produktadapter mit impliziten AROME-Annahmen ist daher falsch.
2. **Bestätigt:** Die 16 untersuchten aktuellen Produkt-Endpunkte enthalten zusammen 167 Parameter. Die vollständige, mit realen NetCDF-Proben verknüpfte Inventur steht in [`parameter-inventory.json`](parameter-inventory.json).
3. **Bestätigt:** Die realen NetCDF-Datenvariablen sind gepackte `int16`/`int32`-Werte mit `scale_factor`, `_FillValue` und `missing_value`; CF-Decoding macht daraus in den Proben `float64`. Ein `float32`-Datentyp im Arbeitsspeicher sagt deshalb nichts über die fachliche Originalgenauigkeit aus.
4. **Bestätigt:** C-LAEF-v2 liefert `tp`, `rain` und `sf` bereits als Menge **im letzten Prognoseintervall**. Eine zeitliche Differenzbildung wäre sachlich falsch. Zum Referenzzeitpunkt ist `tp` im untersuchten Lauf vollständig NoData; ab +1 h liegen Intervallwerte vor.
5. **Bestätigt:** Alle untersuchten Gitterdateien besitzen aufsteigende Y-Koordinaten (Süd nach Nord). Die bestehende koordinatengetriebene Umkehr auf Nord-nach-Süd ist für diese Dateien richtig; produktnamensbasierte Sonderregeln wären falsch.
6. **Bestätigt:** Die gegenwärtige `_grid_shape()`-Schätzung ist nicht belastbar. Gegen echte Vollgitter ergaben sich beispielsweise 1301×947 statt 1300×945 (NWP), 756×457 statt 701×431 (Nowcast) und 568×478 statt 450×450 (Chem 3 km).
7. **Abgeleitet:** Eine parametrisierte Integer-PNG-Kodierung mit reserviertem NoData-Code ist der sinnvollste erste Produktionskandidat. Float32-RGBA bleibt als Testorakel nützlich, ist aber kein guter Standardtransport.
8. **Bestätigt:** Standard-MapLibre-Rasterquellen behandeln PNG als Farbbild, premultiplizieren Alpha standardmäßig und verwenden lineares Texture-Filtering/Mipmaps. Damit ist eine IEEE-754-Bitbelegung in RGBA ohne eigenen Lade-/Shaderpfad nicht robust. OpenLayers `DataTile`/`WebGLTile` ist für numerische Typed Arrays wesentlich direkter geeignet.
9. **Bestätigt:** `inca-v2-1h-1km` ist seit Oktober 2026 aktiv und soll INCA-v1 bis Ende Dezember ablösen. Der direkte Grid- und Timeseries-Endpunkt funktioniert, obwohl er am Prüftag in `/v1/datasets` fehlte. Dies ist eine konkrete Portal/API-Verzeichnis-Diskrepanz.
10. **Urteil zum PR:** Die neuen Bausteine enthalten gute Prinzipien und einige wiederverwendbare Funktionen, sind aber noch kein tragfähiger allgemeiner Produktkern. Der bestehende Buildpfad bleibt AROME-spezifisch und würde C-LAEF-v2 unter anderem bei Bewölkung, Niederschlagssemantik und gemeinsamer Maske falsch behandeln.

## Statusbegriffe und Evidenz

- **Bestätigt:** direkt aus offizieller Dokumentation, Live-Metadaten oder heruntergeladener NetCDF-/CSV-Datei belegt.
- **Abgeleitet:** Schlussfolgerung aus bestätigten Eigenschaften; die Herleitung ist angegeben.
- **Ungeklärt:** Metadaten reichen für eine fachlich sichere Festlegung noch nicht aus.

Primärquellen:

- [GeoSphere Dataset API – Getting started](https://dataset.api.hub.geosphere.at/v1/docs/getting-started.html)
- [API-Endpunktverzeichnis](https://dataset.api.hub.geosphere.at/v1/datasets)
- [OpenAPI-Spezifikation](https://dataset.api.hub.geosphere.at/v1/openapi.json)
- [Request limits](https://dataset.api.hub.geosphere.at/v1/docs/user-guide/request-limit.html)
- [Typen und BBox-Reihenfolge](https://dataset.api.hub.geosphere.at/v1/docs/user-guide/type.html)
- [Forecast-Modus](https://dataset.api.hub.geosphere.at/v1/docs/user-guide/mode.html)
- [API-Changelog](https://dataset.api.hub.geosphere.at/v1/docs/changelog.html)
- [C-LAEF-v2-Datensatzseite](https://data.hub.geosphere.at/dataset/nwp-v2-1h-1km)
- [INCA-v2-Datensatzseite](https://data.hub.geosphere.at/dataset/inca-v2-1h-1km)

Maschinenlesbare Audit-Artefakte:

- [`dataset-catalog.json`](dataset-catalog.json): 16 relevante aktuelle Grid-Produkte mit Live- und Portalmetadaten
- [`parameter-inventory.json`](parameter-inventory.json): alle 167 Parameter einschließlich API-Namen, Einheiten, NetCDF-Kodierung, beobachteten Bereichen und zeitlicher Einordnung
- [`netcdf-samples.json`](netcdf-samples.json): Abfragen, Dateinamen, Größen und SHA-256
- [`raster-geometries.json`](raster-geometries.json): Koordinaten, Dimensionen, CRS und Achsrichtungen
- [`encoding-benchmarks.json`](encoding-benchmarks.json): vollständige Messwerte
- [`../../scripts/benchmark_grid_encodings.py`](../../scripts/benchmark_grid_encodings.py): reproduzierbarer Benchmark
- [`../../scripts/assemble_geosphere_audit.py`](../../scripts/assemble_geosphere_audit.py): deterministische Zusammenführung der erfassten Evidenz

## A. Verifizierter Datensatzkatalog

### A1. Aktuelle relevante Produkte

Alle Dimensionsangaben wurden an vollständigen NetCDF-Gittern gemessen; APOLIS wurde wegen des 10-Millionen-Werte-Limits aus vier räumlichen Ausschnitten zusammengesetzt.

| Dataset-ID | Modus | Inhalt | CRS | Raster Y×X | Takt / Horizont bzw. Zeitraum | Update / sichtbare Läufe | Parameter |
|---|---|---|---|---:|---|---|---:|
| `nwp-v2-1h-1km` | forecast | C-LAEF AlpeAdria, deterministischer Kontrolllauf | EPSG:4326 | 945×1300 | 1 h, 61 Zeiten = 60 h | 3 h / 6 | 16 |
| `ensemble-v2-1h-1km` | forecast | p10/p50/p90 aus 16 Membern + Kontrolllauf; API liefert nur Statistik | EPSG:4326 | 945×1300 | 1 h, 61 Zeiten = 60 h | 3 h / 4 | 42 |
| `nowcast-v1-15min-1km` | forecast | INCA-Kurzfristvorhersage | EPSG:31287 | 431×701 | 15 min, 13 Zeiten = 3 h | 15 min / 6 | 8 |
| `inca-v2-1h-1km` | historical | aktuelle stündliche INCA-Analyse | EPSG:31287 | 431×701 | ab 2026-10-01, stündlich | stündlich | 8 |
| `inca-v1-1h-1km` | historical | bisherige INCA-Analyse, größeres altes Gitter | EPSG:31287 | 401×701 | 2011-03-15 bis laufend | stündlich | 8 |
| `chem-v2-1h-3km` | forecast | NO₂, O₃, PM10, PM2.5 Mitteleuropa | Lambert Conformal (WKT) | 450×450 | 1 h, 73 Zeiten = 72 h | täglich / 6 | 4 |
| `chem-v2-1h-9km` | forecast | dieselben Schadstoffe, Europa | Lambert Conformal (WKT) | 680×680 | 1 h, 73 Zeiten = 72 h | täglich / 6 | 4 |
| `chem_aqi-v1-1d-3km` | forecast | Luftqualitätsindex | Lambert Conformal (WKT) | 450×450 | 1 d, 3 Zeiten | täglich / 6 | 1 |
| `chem_dust-v1-1h-0p2deg` | forecast | Wüstenstaublast | EPSG:4326 | 324×449 | 1 h, 121 Zeiten = 120 h | täglich / 6 | 1 |
| `apolis-v2-1d-100m` | historical | tägliche Solarstrahlung/Sonnenschein | EPSG:31287 | 4001×7001 | 2012-06-11 bis laufend | täglich | 5 |
| `snowgrid_cl-v2-1d-1km` | historical | Schneehöhe und Schneewasseräquivalent | EPSG:3416 | 329×584 | 1961-01-01 bis laufend | täglich | 2 |
| `spartacus-v3-1d-1km` | historical | tägliche Klimaanalyse | EPSG:3416 | 329×584 | 1961-01-01 bis laufend | täglich | 10 |
| `spartacus-v3-1m-1km` | historical | monatliche Klimaanalyse + Anomalien | EPSG:3416 | 329×584 | 1961-01 bis laufend | täglich aktualisiert | 18 |
| `spartacus-v3-1q-1km` | historical | saisonale Klimaanalyse + Anomalien | EPSG:3416 | 329×584 | 1960-12 bis laufend | täglich aktualisiert | 18 |
| `spartacus-v3-1y-1km` | historical | jährliche Klimaanalyse + Anomalien | EPSG:3416 | 329×584 | 1961 bis laufend | täglich aktualisiert | 18 |
| `winfore-v2-1d-1km` | historical | Referenzverdunstung und SPEI 30/90/365 | EPSG:3416 | 329×584 | 1961-01-01 bis laufend | täglich | 4 |

**Bestätigt:** Portalstatus von INCA-v1 ist `archived`, sein API-Endzeitpunkt wurde am Prüftag dennoch stündlich fortgeschrieben. `archived` darf deshalb nicht als technische Nichtverfügbarkeit interpretiert werden.

**Bestätigt:** `inca-v2-1h-1km` war über beide direkten API-Endpunkte abrufbar, fehlte aber im gleichzeitig abgerufenen offiziellen `/v1/datasets`. Der Katalog darf dieses Verzeichnis deshalb nicht als alleinige Source of Truth verwenden; Portalressourcen und direkte Metadaten müssen gegengeprüft werden.

**Bestätigt:** Veraltete, weiterhin gelistete Vorgänger sind unter anderem NWP/Ensemble v1, Chem v1, SPARTACUS v1/v2, WINFORE v1 und `apolis_short-v1`. Sie wurden nicht in den Zielkatalog aufgenommen. Eine Rückwärtskompatibilität ist nicht erforderlich.

### A2. API-Zugriff

**Bestätigt:** Für alle 16 Zielprodukte existieren Grid- und Timeseries-Endpunkte. Grid liefert `netcdf` oder `geojson`, Timeseries `csv` oder `geojson`. Für eine flächige Produktionspipeline ist NetCDF die richtige Eingabe: Typ-, Raster-, CRS-, Maskierungs- und CF-Information bleiben erhalten; GeoJSON ist für große Raster ineffizient.

**Bestätigt:** BBox-Abfragen verwenden EPSG:4326 und die Reihenfolge `south,west,north,east`, auch wenn das Zielgitter projiziert ist. `bbox_outer` beschreibt die äußere Zellumrandung, `bbox` die Mittelpunkte der äußersten Zellen.

**Bestätigt:** Die dokumentierten Limits sind 5 Requests/s und 240 Requests/h sowie höchstens 1 Mio. Werte für JSON/CSV und 10 Mio. Werte für NetCDF. Die Antworten enthielten passende `X-RateLimit-*`-Header.

**Abgeleitet:** Der Stunden-Limitwert ist praktisch strenger als 5/s. Downloader sollen serverseitige Header beachten, Requests möglichst bis knapp unter 10 Mio. Werte bündeln und höchstens geringe Parallelität verwenden. Bei 429/5xx: begrenzte exponentielle Wiederholung mit Jitter und `Retry-After`, nie unbeschränkt wiederholen.

**Abgeleitet:** Ein kompletter C-LAEF-Lauf mit 16×61×1.228.500 ≈ 1,20 Mrd. Werten erfordert selbst bei idealer Packung mindestens 120 NetCDF-Requests. Das Ensemble mit 42×61×1.228.500 ≈ 3,15 Mrd. Werten erfordert mindestens 315 Requests und überschreitet damit schon rechnerisch das Stundenlimit. „Alle Parameter jedes Laufs“ ist weder ein sinnvoller Standardbuild noch in einer Stunde über die API realistisch. Der Build muss produkt-/parameterselektiv und cachebar sein; für Vollbestände ist der offizielle Massendownload gesondert zu evaluieren.

**Bestätigt:** Die API benötigt keine Authentifizierung; die untersuchten öffentlichen Datensätze stehen unter CC BY 4.0. Attribution, Datensatz-DOI, Dataset-ID, Abrufzeit und Quellabfrage gehören ins Manifest.

## B. Parameter, Einheiten und Zeit

### B1. Vollständige Inventur

Die Tabelle mit 167 Zeilen wäre im Fließtext unhandlich. [`parameter-inventory.json`](parameter-inventory.json) enthält pro Parameter:

- exakten API-Namen, Langnamen, Beschreibung und Originaleinheit;
- Produkt, Modus und Endpunkt;
- nativen und CF-dekodierten Datentyp, Dimensionen und reale Beispielwerte;
- `scale_factor`, `add_offset`, Fill-/Missing-Werte und Kompression;
- gemessene Quantisierung und Float32-Rundtripfehler;
- Kategorie, zeitliche Einordnung, optionale Anzeigeumrechnung und Karten-Eignung;
- `null` statt erfundener dokumentierter Plausibilitätsgrenzen, wenn GeoSphere keine Grenze publiziert.

Wichtige C-LAEF-v2-Originalparameter:

| Name | Bedeutung laut API/NetCDF | Einheit | zeitliche Bedeutung |
|---|---|---|---|
| `2t` | Temperatur 2 m | degree Celsius | Wert zur Gültigkeitszeit (abgeleitet; keine Intervallmethode angegeben) |
| `2r` | relative Feuchte 2 m | % | Wert zur Gültigkeitszeit (abgeleitet) |
| `10u`,`10v` | ost-/nordwärtige Windkomponente | m s-1 | Wert zur Gültigkeitszeit (abgeleitet) |
| `10fg` | maximale 10-m-Böe im letzten Prognoseintervall | m s-1 | Intervallmaximum (bestätigt) |
| `msl` | Luftdruck auf Meeresniveau | Pa | Wert zur Gültigkeitszeit (abgeleitet) |
| `cape` | CAPE | m² s⁻² | Wert zur Gültigkeitszeit (abgeleitet) |
| `tcc` | Gesamtbewölkung | % | Wert zur Gültigkeitszeit (abgeleitet) |
| `tp`,`rain`,`sf` | Gesamt-/Regen-/Schneefallmenge im letzten Prognoseintervall | kg m⁻² | Intervallmenge (bestätigt) |
| `sund` | Sonnenscheindauer im letzten Prognoseintervall | s | Intervalldauer (bestätigt) |
| `ssrd` | Globalstrahlung | W m⁻² | nicht akkumulierte Flussgröße bestätigt; exakte Mittelungs-/Referenzkonvention ungeklärt |
| `snowlmt` | Schneefallgrenze | m | Wert zur Gültigkeitszeit (abgeleitet) |
| `pt`,`sy` | Niederschlagstyp/Wettersymbol | 1 | kategorisch; Codetabelle fehlt in der API-Antwort |

**Bestätigt:** Ensemble-v2 stellt keine Rohmember bereit, sondern p10/p50/p90 für 14 Größen (42 Parameter). Perzentile sind keine Eintrittswahrscheinlichkeiten und dürfen nicht als Prozentwerte dargestellt werden.

**Bestätigt:** Nowcast `dd` ist als `wind_from_direction` gespeichert, hat Werte 0…359,8 und Quantisierung 0,1; API und NetCDF deklarieren dennoch fälschlich `m s-1`. Die Einheit ist intern widersprüchlich und darf nicht übernommen werden. `pt` besitzt eine leere Einheit und zeigte den Code 255; eine belastbare Codetabelle fehlt.

**Bestätigt:** INCA-v2 ändert gegenüber v1 Namen und teilweise Einheiten: beispielsweise `T2M` → `2t`, `RR` → `tp`, Feuchte `%` → dimensionslos `1`; `tp` ist ausdrücklich eine 1-Stunden-Summe. Eine Namensumschreibung ohne Produktvertrag wäre gefährlich.

### B2. Zeitachsen

**Bestätigt (CSV/NetCDF):**

- NWP-v2: 61 eindeutige, stündliche Gültigkeitszeiten; NetCDF-`time.units` lautet beispielsweise `hours since 2026-10-28 09:00:00`, CF-Decoding erzeugt zusätzlich `leadtime`.
- Ensemble-v2: 61 eindeutige stündliche Zeiten.
- Nowcast-v1: 13 eindeutige 15-Minuten-Zeiten über 3 Stunden.
- In den drei geprüften Zeitreihen gab es keine Doppelungen.
- Am NWP-Lead 0 waren `10fg`, `rain`, `sf`, `ssrd`, `sund`, `sy` und `tp` leer; `pt=0` sowie Momentanwerte waren vorhanden. Eine gemeinsame Maske mehrerer Parameter würde daher gültige Daten verwerfen.
- NWP-`tp` betrug am geprüften Punkt ab +1 h bereits einzelne Stundenmengen (`0`, `0`, `0.023`, `0.077`, …), nicht eine monoton wachsende Laufakkumulation.

**Ungeklärt:** Die Metadaten sagen bei `ssrd` nur W m⁻² und „surface global radiation“. Das beweist eine dekumulierte Flussgröße, aber nicht, ob sie über das vorangegangene Intervall gemittelt oder zu einem Referenzzeitpunkt definiert ist. Vor einer zeitlichen Integration ist eine explizite GeoSphere-Definition erforderlich.

**Regel:** Keine Differenzbildung. Zeitliche Semantik ist ein Pflichtfeld im Parametervertrag. Doppelungen werden nicht still entfernt: nur identische Duplikate dürfen nach Vergleich zusammengeführt werden, sonst Build-Abbruch.

### B3. Umrechnungen

Nur explizit konfigurierte, einheiten- und parametergebundene Umrechnungen:

| Quelle | Anzeige | Transformation | Einschränkung |
|---|---|---|---|
| `m s-1` | km h⁻¹ | × 3,6 | optional, exakt |
| `Pa` | hPa | × 0,01 | optional, exakt |
| `degree Kelvin` | °C | − 273,15 | nur wenn Originaleinheit tatsächlich Kelvin ist; aktuelle NWP-v2-Probe ist bereits °C |
| dimensionslos `1` | % | × 100 | nur bestätigte Anteile, z. B. INCA-v2 `2r`; nicht Codes/Indizes |
| `kg m-2` | mm Wasseräquivalent | × 1 | für Niederschlags-/SWE-Masse pro Fläche; niemals als geometrische Schneehöhe interpretieren |

**Bestätigt:** SNOWGRID `snow_depth` ist `m` mit 0,01-m-Packing, `swe_tot` ist `kg m-2` mit 1-kg-m⁻²-Packing. Diese Größen dürfen nicht zusammengelegt werden.

## C. Reale NetCDF-Eingaben

### C1. Packing und CF-Decoding

Repräsentative Vollgitterdatei: `nwp-v2-20261028T10-full-2t-tp-tcc.nc`, SHA-256 `1f7e8ca887df8ab53813d782d3a6bccbf108664d3efd5fb2e630b21813242914`.

| Variable | gespeichert | `scale_factor` | Fill/Missing | CF-dekodiert | beobachteter physischer Schritt |
|---|---:|---:|---:|---:|---:|
| `2t` | int16 | 0,1 | −9999 | float64 | 0,1 °C |
| `tp` | int32 | 0,001 | −999 | float64 | 0,001 kg m⁻² |
| `tcc` | int16 | 0,01 | −999 | float64 | in der Probe überwiegend 0,5 % |

Alle 167 untersuchten Variablen waren gepackte `int16` oder `int32`; keine Datenvariable war nativ Float32/Float64. Alle Proben waren little-endian, HDF5/NetCDF4, zlib Level 4 mit Shuffle. `add_offset`, `valid_min`, `valid_max` und `valid_range` fehlten in den Proben. `_FillValue` und `missing_value` waren vorhanden und gleich.

`xarray.open_dataset(..., decode_cf=True, mask_and_scale=True)`:

1. ersetzt Fill/Missing durch NaN;
2. wendet `scale_factor`/`add_offset` an;
3. dekodiert Zeit und erzeugt in Forecastdateien `leadtime`;
4. liefert die Datenvariablen als `float64`;
5. entfernt die verarbeiteten Packing-Attribute aus `.attrs`, erhält sie aber in `.encoding`.

**Folgerung:** Validierung muss vor oder nach dem Decode bewusst gewählt werden. Für Provenienz und Quantisierungsentscheidungen sind `attrs` **und** `encoding` vor dem Zusammenführen zu sichern. Ein blindes `astype(float32)` verliert zwar in den Proben keine Quellquantisierung, verwischt aber deren Nachweis.

### C2. Tatsächliche Genauigkeit

Der größte Float64→Float32→Float64-Fehler lag in den NWP-Beispielen bei etwa:

- Temperatur: `7,63e-7 °C` gegenüber 0,1-°C-Packing;
- Niederschlag: `2,37e-7 kg m-2` gegenüber 0,001-Packing;
- Bewölkung: im Benchmark 0 bei den dort vorkommenden 0,5-%-Werten.

**Bestätigt für die Proben:** Float32 erhält die originale Quantisierung mit sehr großem Abstand. **Nicht abgeleitet:** dass jedes künftige Produkt stets gefahrlos nach Float32 konvertiert werden darf. Der Vertrag soll pro Parameter Quell-Packing und zulässigen Darstellungsfehler festhalten.

## D. Rastergeometrie und Resampling

### D1. Geometrie

| Familie | CRS/Gitter | Koordinaten |
|---|---|---|
| NWP/Ensemble | EPSG:4326, 0,0135°×0,009° | 1D `lon`/`lat`, beide aufsteigend |
| Dust | EPSG:4326, 0,2° | 1D `lon`/`lat`, aufsteigend |
| INCA/Nowcast/APOLIS | EPSG:31287 | 1D `x`/`y` aufsteigend + 2D `lat`/`lon` |
| Snow/SPARTACUS/WINFORE | EPSG:3416 | 1D `x`/`y` aufsteigend + 2D `lat`/`lon` |
| Chem/AQI | Lambert-Conformal-WKT | 1D `x`/`y` aufsteigend + 2D `lat`/`lon` |

**Bestätigt:** Für NWP liegen die äußeren Zellkanten exakt eine halbe Zellweite außerhalb der ersten/letzten Koordinate. Das ist ein Pixel-is-Area-Raster mit Zellmittelpunktkoordinaten. Der in der Datei enthaltene `GeoTransform` beginnt am ersten Mittelpunkt und hat positive Y-Schrittweite; er darf nicht ungeprüft als nordorientierter GDAL-Area-Transform verwendet werden.

**Bewertung des bestehenden Codes:** `_normalize_orientation()` entscheidet anhand der realen Koordinaten und dreht X bei Bedarf aufsteigend sowie Y auf absteigend. `_center_coordinate_transform()` zieht/addiert eine halbe Zellweite ab. Diese Kombination ist für alle untersuchten Dateien korrekt. Erforderlich sind Realdatei-Regressionstests für jede Gitterfamilie sowie ein Abbruch bei unregelmäßigen oder nicht monotonen Achsen.

### D2. Resamplingregeln

| Kategorie | Reprojektion/hohe Zooms | Aggregation/niedrige Zooms |
|---|---|---|
| kontinuierlicher Momentanwert | bilinear für Darstellung; nearest für exakte Abfrage | flächengewichtetes Mittel |
| Intervallmenge/-tiefe | bilinear nur als Darstellungsapproximation | flächengewichtetes Mittel der Tiefe; flächenerhaltend, wenn Gesamtmasse gefragt ist |
| Prozent/Anteil | bilinear mit Maskennormalisierung und Bereichsprüfung | Mittel; niemals Ensembleperzentile als Wahrscheinlichkeit behandeln |
| Kategorie/Code | nearest | Modus oder prioritätsgebundene Regel |
| Extremwert | nearest/geeignete konservative Methode | Maximum/Minimum, nicht Mittel |
| Windvektor | Komponenten gemeinsam transformieren/interpolieren | Komponenten mitteln, dann Betrag/Richtung ableiten |

Der reale 8×8-Blocktest zeigt die Semantikunterschiede: bei Niederschlag blieb das Maximum mit `max` 7,545, fiel beim Mittel auf 5,706 und bei nearest auf 6,037; der Mittelwert stieg bei `max` von rund 0,040 auf 0,074. Das bestehende „max für Niederschlag“ erhält also Extremzellen, aber keine Flächenmittel oder Mengenbilanz.

**Wind:** NWP-v2 und INCA-v2 deklarieren `eastward_wind`/`northward_wind`; bei INCA-v1 stehen dagegen `x_wind`/`y_wind` trotz Langtext „eastward/northward“. Ob v1-Komponenten gitter- oder geographisch orientiert sind, ist ungeklärt. Vor einem v1-Vektorlayer ist eine offizielle Bestätigung oder ein Vergleich mit Richtung/Messpunkten nötig. Komponenten dürfen nie getrennt mit unterschiedlichen Masken/Geometrien verarbeitet werden.

**NoData:** Maske vor dem Warp getrennt halten, keine Interpolation über ungültige Ränder, bei bilinearer Interpolation Gewichte über gültige Nachbarn normieren und eine Mindestabdeckung definieren. NoData nicht mit einem meteorologisch möglichen Zahlenwert verwechseln.

## E. Kachelformat und Benchmark

### E1. Gemessene Einzelbilder

Ein reales NWP-Vollgitter mit 1.228.500 Zellen; PNG-Kompression Level 6; Python/Pillow, daher Laufzeiten nur relativ interpretierbar.

| Parameter | Variante | PNG-Größe | MAE | max. Fehler | NoData |
|---|---|---:|---:|---:|---|
| `2t` | Float32-RGBA + Maske | 1.550.445 B | 2,29e−7 °C | 7,63e−7 °C | separate Textur |
| `2t` | UInt16, 0,1 °C, Code 0 | 781.648 B | 2,29e−7 °C | 7,63e−7 °C | integriert |
| `2t` | UInt8, 0,25 °C, Code 0 | 403.896 B | 0,060 °C | 0,100 °C | integriert |
| `tp` | Float32-RGBA + Maske | 559.188 B | 8,65e−10 | 2,37e−7 | separate Textur |
| `tp` | UInt16, 0,001 | 226.670 B | 8,65e−10 | 2,37e−7 | integriert |
| `tp` | UInt16, 0,01 | 113.136 B | 0,000366 | 0,005000 | integriert |
| `tp` | UInt8, 0,1 | 33.782 B | 0,002846 | 0,050000 | integriert |
| `tcc` | Float32-RGBA + Maske | 855.860 B | 0 | 0 | separate Textur |
| `tcc` | UInt16, 0,01 | 909.503 B | 0 | 0 | integriert |
| `tcc` | UInt16, 0,5 | 662.254 B | 0 | 0 | integriert |
| `tcc` | UInt8, 0,5 | 468.033 B | 0 | 0 | integriert |

Die scheinbar exakten quantisierten `tcc`-Ergebnisse gelten für diesen Zeitpunkt, weil die beobachteten Werte auf 0,5-%-Schritten lagen; die NetCDF-Packingschrittweite ist 0,01 %. Daraus folgt keine allgemeine 0,5-%-Garantie.

Ein reales Lead-0-`tp`-Raster mit 1.227.200 NoData-Zellen wurde separat geprüft: sowohl Float+Maske als auch reservierter UInt16-Code rekonstruierten die Gültigkeit exakt. Ein reservierter Code benötigt jedoch nur eine PNG-Datei.

### E2. Pyramidengröße und Vollveröffentlichung

Vier native, jeweils 2× dezimierte Kachelebenen aller drei Parameter ergaben zusammen pro Zeitpunkt:

- Float32-RGBA + Masken: ca. 4,05 MB;
- UInt16 in Quellschrittweite: ca. 2,72 MB;
- praktische UInt16-Schritte: ca. 2,24 MB;
- praktische UInt8-Schritte: ca. 1,31 MB.

Eine bloße Multiplikation mit 61 Zeiten ergibt 247/166/137/80 MB. **Das ist nur eine Abweichungsabschätzung**, kein PMTiles-Vollbuild: Web-Mercator-Reprojektion, Tile-Randkompression, zusätzliche Zooms, variable Wetterlagen, Header/Directory und mögliche Maskenränder fehlen. Eine belastbare Veröffentlichungsgröße erfordert im nächsten Schritt einen echten Web-Mercator-Pilotbuild über einen vollständigen Lauf.

### E3. Browser-/GPU-Eignung

**Bestätigt:** Der CPU-Encoder in `scalar_encoding.py` erhält endliche Float32-Bits beim Schreiben/Lesen mit Pillow. Das beweist nur den PNG-Rundtrip.

**Bestätigt aus aktuellem MapLibre-GL-JS-Code:** Normale Rastertiles werden standardmäßig mit premultipliziertem Alpha geladen und als lineare, mipmap-gefilterte RGBA-Textur gebunden ([RasterTileSource](https://github.com/maplibre/maplibre-gl-js/blob/main/src/source/raster_tile_source.ts)). Da der Prototyp alle vier Kanäle einschließlich Alpha als Datenbits verwendet, verändern Premultiplikation und Filtering die Codes. `setPremultiplyAlpha(false)` löst das Filtering-/Shaderproblem nicht. Die [Style Specification](https://maplibre.org/maplibre-style-spec/sources/#raster) beschreibt Raster als Bildquelle, nicht als beliebig dekodierbares numerisches Band.

**Bestätigt:** MapLibre Native iOS unterstützt normale Raster-/DEM-Quellen, aber keinen standardisierten Float32-RGBA-Datenvertrag ([iOS style sources](https://maplibre.org/maplibre-native/ios/latest/documentation/maplibre-native-for-ios/for_style_authors/)). Ein eigener Native-Shaderpfad wäre zusätzlicher Plattformcode.

**Bestätigt:** OpenLayers `DataTileSource` ist ausdrücklich eine Quelle für Typed-Array-Datentiles, unterstützt Bandanzahl und schaltet Interpolation standardmäßig aus ([API](https://openlayers.org/en/latest/apidoc/module-ol_source_DataTile-DataTileSource.html)). Das offizielle [16-bit-NumpyTile-Beispiel](https://openlayers.org/en/latest/examples/numpytile.html) zeigt Float32-Typed-Arrays und WebGL-Styling. Raster-PMTiles funktionieren in beiden Clients über Protomaps-Adapter ([MapLibre](https://docs.protomaps.com/pmtiles/maplibre), [OpenLayers](https://docs.protomaps.com/pmtiles/openlayers)).

**Empfehlung:**

1. Erste produktive Kodierung: pro Parameter ein manifestbeschriebenes UInt8/UInt16-Offset/Scale-Schema; Code 0 = NoData; Daten in RGB/Luminanz ohne datenbelegten Alpha-Kanal; nearest beim numerischen Decode.
2. Quantisierung pro fachlichem Vertrag, nicht dynamisch pro Tile. Sonst sind Wertabfrage, Vergleich und Legende instabil.
3. Styling getrennt von Daten: Client dekodiert Wert und wendet Farbskala/Legende an.
4. Float32-RGBA nur als Forschungs-/Testorakel behalten. Falls später benötigt, eigener numerischer Source-/Shaderpfad plus echte Safari/iPhone- und Native-Tests.
5. Für MapLibre ist vor Festlegung ein kleiner Client-Spike nötig, der UInt16-RG-PNG bytegenau liest, nearest sicherstellt, Werte abfragt und auf iPhone testet. OpenLayers kann denselben PMTiles-Inhalt über einen DataTile-Loader numerisch dekodieren.

## F. Parametertypen als Verträge

Eine generische Pipeline braucht keine Klassenhierarchie pro Modell, sondern einen kleinen deklarativen `ParameterContract`:

- `source_name`, `source_unit`, optional `standard_name`;
- `quantity_kind`: scalar, amount, bounded, vector component/pair, category, extreme, ensemble statistic;
- `temporal_kind`: instant/valid-time, interval mean/sum/max/min/duration/category;
- `interval_reference`: preceding/centered/following, soweit bestätigt;
- `display_conversion` getrennt vom Originalwert;
- `resampling_policy` für Reprojektion und Pyramidierung;
- `encoding` mit fester Basis, Schrittweite, Codebereich und NoData;
- fachliche QA-Grenzen getrennt von dokumentierten Quellgrenzen;
- Codetabelle/Attribution, falls kategorisch.

Vektoren werden als Paarvertrag behandelt. Ensemble-p10/p50/p90 bleiben drei statistische Felder; daraus dürfen keine Eintrittswahrscheinlichkeiten erfunden werden.

## G. Robuster Download- und Buildprozess

1. **Discovery-Snapshot:** Portalpaket, `/v1/datasets`, direkte `/metadata`-Antwort und deren SHA-256 sichern.
2. **Run/Zeitraum fixieren:** Forecast-Referenzzeit einmal auswählen; erwartete Gültigkeitszeiten und Produktvertrag festschreiben.
3. **Chunkplan:** mit realer Rastergröße und Parameterzahl unter 10 Mio. Werte planen; nicht aus geographischer BBox approximieren.
4. **Downloadcache:** kanonische Requestsignatur → unveränderliche Rohdatei + SHA-256 + HTTP-Metadaten. Parameter eines Laufs können dadurch separat neu gebaut werden.
5. **Runprüfung je Chunk:** Metadaten erneut abrufen; ausgewählte Referenzzeit muss weiterhin vorhanden sein. Im NetCDF `time.units`, `leadtime`, globale Referenzattribute, CRS, Koordinaten und Grid-Signatur gegen den Snapshot prüfen.
6. **Zusammenführen:** keine `compat="override"`; alle nichtzeitlichen Variablen/Attribute müssen übereinstimmen. Überlappungen und Doppelzeiten melden. Nur nach Gleichheitsnachweis deduplizieren.
7. **Vollständigkeit:** erwartete Zeitliste pro Parameter, inklusive absichtlich fehlender Lead-0-Intervalle, aus dem Vertrag prüfen. Fehlende neue Läufe nicht veröffentlichen; letzte vollständige immutable Version bleibt verfügbar.
8. **Build:** Decode → Validierung → optionale Anzeigeeinheit → Reprojektion/Resampling gemäß Vertrag → Encoding → Roundtrip- und Geometrietest.
9. **Staging/Publikation:** Artefakte und Manifest in neuen unveränderlichen Versionspfad schreiben; Prüfsummen prüfen; zuletzt einen kleinen Katalogzeiger atomar aktualisieren.
10. **Idempotenz:** Hash aus Quellchunks + Vertrag + Codeversion + Encodingversion. Gleicher Hash bedeutet keinen Neubau.

## H. Publikationsschema und Kartensammlung

Vorgeschlagener Pfad:

```text
weather/v1/catalog.json
weather/v1/products/{dataset_id}/product.json
weather/v1/products/{dataset_id}/runs/{reference_or_period_id}/manifest.json
weather/v1/products/{dataset_id}/runs/{reference_or_period_id}/parameters/{parameter_id}/{valid_time}.pmtiles
```

Bezeichner:

- Dataset-ID unverändert von GeoSphere, z. B. `nwp-v2-1h-1km`;
- Lauf-ID UTC: `20261028T090000Z`; historische Periode analog zum fachlichen Intervall;
- Parameter-ID = API-Name innerhalb des Produkts, nicht global umbenennen;
- Gültigkeitszeit UTC: `20261028T100000Z`;
- Schema- und Encodingversion explizit, niemals durch Dateinameninterpretation erraten.

Manifest-Pflichtfelder:

- Status `staging|complete|superseded`, Erstellzeit, Code-Commit;
- Quelle, DOI, Lizenz/Attribution, API-Abfrage, Metadatenhash und Rohchunk-Prüfsummen;
- Referenzzeit, Leadtime, Gültigkeitszeit und bestätigte Intervallsemantik;
- Original-/Ausgabeeinheit und Transformation;
- Grid-Signatur (CRS-WKT/EPSG, Shape, Koordinatenhash, Transform, Pixelmodell);
- Parameterkategorie, Resamplingverfahren, NoData-Regel;
- Encoding (Basis, Schritt, Codes, Kanalbelegung) und Fehlergrenze;
- PMTiles-URL, SHA-256, Bytegröße, Zoom-/Bounds-Angaben und beobachteter Wertebereich;
- Vollständigkeitsliste aller erwarteten/verfügbaren Parameter und Zeiten.

**Layerstrategie:** separate skalare Layer pro fachlicher Größe; Wind als gemeinsamer U/V-Layer; Ensemble p10/p50/p90 als wählbare Statistik oder Unsicherheitsband; Kategorien nur mit Codetabelle. Farbe, Legende und Sichtbarkeit gehören in Darstellungsmetadaten, nicht in die numerische Kodierung. Der Client zeigt Datenstand, Referenzlauf, Gültigkeitszeit und ggf. Unsicherheit sichtbar an.

## I. Audit von Draft-PR #9

### Wiederverwendbar / fachlich richtig

- `geosphere.BoundingBox` interpretiert die API-Reihenfolge south/west/north/east korrekt.
- Forecast-Referenzzeit wird vor dem Download ausgewählt und pro Chunk erneut gegen Metadaten geprüft.
- Exakte erwartete Zeitliste ist besser als bloßes Zählen.
- `xarray` wird mit `decode_cf=True, mask_and_scale=True` geöffnet.
- `_normalize_orientation()` und `_center_coordinate_transform()` sind koordinatengetrieben und passen zu den Realdateien.
- Trennung von expliziter Einheitenumrechnung, skalarem Validator und Encoding ist als Richtung richtig.
- `encode_float32_rgba()`/Decoder ist als CPU-Testorakel korrekt und gut getestet.
- Alle bestehenden 34 Tests bestehen an der geprüften Revision.

### Blockierende Fehler/Annahmen

1. **`grid_catalog.py`:** `endpoint` ist immer `/grid/forecast/`; historische Produkte sind falsch. `bbox` hat keine Semantik und der Test verwendet fälschlich west/south/east/north. Leere Einheiten werden abgelehnt, obwohl Nowcast-`pt` tatsächlich eine leere Einheit liefert.
2. **`geosphere._grid_shape()`:** BBox-/Auflösungsheuristik liefert nachweislich falsche Shapes und ist für projizierte Gitter besonders unzuverlässig.
3. **`netcdf.py`:** `compat="override"` und `combine_attrs="override"` können Chunkkonflikte verschweigen. `_deduplicate_time()` behält still den ersten Wert.
4. **Niederschlag:** Der alte Akkumulations-Differenzierer ist im allgemeinen Pfad noch vorhanden. C-LAEF-v2-`tp` darf nicht differenziert werden.
5. **Bewölkung:** `validate_cloud_fraction()` erwartet 0…1; NWP-v2-`tcc` ist bestätigte 0…100 `%`.
6. **Gemeinsame Maske:** `tiles.py` schneidet Gültigkeit von Niederschlag und Wolken. Am Lead 0 würde fehlendes `tp` gültiges `tcc`/Temperatur ausblenden.
7. **`build.py`, `config.py`, CLI und Metadaten:** weiterhin AROME-/`rr_acc`-/Niederschlag+Wolken-spezifisch; Produktnamen, Beschreibungen und Manifeste sind entsprechend falsch.
8. **Float32-Zwang:** `scalar_raster.py` wandelt unabhängig vom Quell-Packing alles über Float64 nach Float32 und speichert die ursprüngliche Quantisierung nicht im Vertrag.
9. **Einheitenvergleich:** exakte Stringgleichheit kann bestätigte Varianten wie `degree Celsius`, `degree_Celsius`, `%`, `1` nicht fachlich auflösen. Eine kleine kontrollierte UCUM-/Alias-Tabelle pro Vertrag ist nötig, kein Namensraten.
10. **`claef.py`:** eigenständige Auswahl nur von Niederschlag/Wolken ist zu produktspezifisch und dupliziert den künftigen Parameterkatalog.
11. **Tests:** fast ausschließlich synthetisch; keine fest eingecheckten Metadatenfixtures/kleinen NetCDF-Ausschnitte, keine Browser-/PMTiles- und keine Gitterfamilienregression.

### Behalten, ersetzen, entfernen

- **Behalten/ausbauen:** BoundingBox, Run-Fixierung, genaue Zeitvalidierung, koordinatengetriebene Orientierung, explizite Konvertierungen, Roundtrip-Prüfidee.
- **Ersetzen:** Gridshape-Heuristik durch echte Koordinaten/Shapes; lockeres Concat durch Grid-/Attributsignatur; globalen ScalarSpec durch Dataset-/ParameterContract; AROME-Build durch produktneutralen Orchestrator.
- **Nicht als Produktionsstandard übernehmen:** Float32-RGBA + separate Maske. Als experimentelles Testorakel kann es bleiben.
- **Entfernen aus allgemeinem Pfad:** implizite Akkumulationsdifferenz, 0…1-Wolkenannahme, Niederschlag/Wolken-Zwangspaar, stille Deduplikation und AROME-Namensreste.

## Architekturvorschlag

Kleine, explizite Schichten statt Modellvererbung:

```text
Portal/API discovery snapshots
        ↓
DatasetContract + ParameterContract (versioniert, geprüft)
        ↓
RunSnapshot / HistoricalSlice + immutable raw chunk cache
        ↓
CF decoder + source-metadata capture
        ↓
GridSignature + temporal/unit/category validation
        ↓
category-specific reprojection/pyramid policy
        ↓
manifest-driven numeric encoder
        ↓
immutable PMTiles artifacts + atomic catalog pointer
```

Der Katalog ist die fachliche Source of Truth; Live-Metadaten werden dagegen geprüft, ändern aber während eines Builds keinen Vertrag automatisch. Neue Produkte benötigen Daten- und Parameterverträge plus Realdatei-Fixtures, nicht neue globale Sonderfälle.

## Priorisierter Implementierungsplan

1. **Audit-Fixtures festschreiben:** die erzeugten JSON-Artefakte reviewen; kleine redistribuierbare NetCDF-Ausschnitte oder Metadatenfixtures mit SHA-256 für NWP-v2, INCA-v2, Chem und EPSG:3416 ergänzen.
2. **Katalogmodell reparieren:** `mode`, korrekte BBox-Struktur, CRS, Grid-Signatur und tolerierte leere/Code-Einheiten; direkte Endpunkte plus Portalabgleich. Realtest für das nicht gelistete INCA-v2.
3. **ParameterContract implementieren:** zunächst `nwp-v2` für `2t`, `tp`, `tcc`; Originaleinheit, Zeitsemantik, Kategorie, Packing und QA getrennt modellieren. Keine automatische Differenzbildung.
4. **NetCDF-Ingest härten:** Raw-Encoding vor Decode sichern; Referenz-/Leadtime prüfen; Concat-Konflikte und Doppelzeiten hart erkennen; Shape aus Datei, nicht Heuristik.
5. **Geometrietests:** eine Fixture pro Gitterfamilie; Außenkanten, Mittelpunkttransform, Nordorientierung und bekannte Kontrollpunkte nach EPSG:3857 testen.
6. **UInt-Encoding-Pilot:** `2t`, `tp`, `tcc` mit fester Basis/Schrittweite und Code 0; Roundtrip-Fehler gegen Quellquantisierung prüfen; Float-Encoder nur als Referenz.
7. **Echter PMTiles-Pilot:** vollständiger NWP-Zeitpunkt in Web Mercator, mindestens nearest/bilinear/flächengewichtete Aggregation; Größen, Extrema, Randmasken und Pixelalignment messen.
8. **Client-Spike:** MapLibre GL JS und OpenLayers aus demselben PMTiles; Wertabfrage, Legende, Styling, nearest numerischer Decode, Safari/iPhone. Danach Encoding endgültig festlegen.
9. **Runmanifest/Cache:** unveränderliche Chunkablage, Checksummen, Teilneubau je Parameter, vollständige erwartete Zeiten und atomare Veröffentlichung.
10. **Produkterweiterung:** INCA-v2/Nowcast, dann Ensemble-Statistiken, Chem/AQI/Dust, danach Klima/Schnee/APOLIS. Jede Kategorie erst nach eigenem Realdatei- und Resamplingtest.
11. **Legacy entfernen:** AROME-v1-Konfiguration, Akkumulationspfad und gemeinsame Niederschlag/Wolken-Kodierung löschen, sobald der NWP-v2-Pilot dieselben End-to-End-Checks besteht.

## Offene Punkte

1. Exakte zeitliche Mittelungs-/Referenzdefinition von `ssrd` in NWP-v2, Ensemble-v2 und INCA-v2.
2. Offizielle Codetabellen für `pt`, `sy`, Nowcast-`pt` und AQI-Klassen; API unterstützt laut Changelog `code_list_ref`, lieferte es hier aber nicht.
3. Fachlich begründete Zielgenauigkeit je Parameter. Der Benchmark zeigt technische Optionen, legt aber keine meteorologische Toleranz fest.
4. Rotation der INCA-v1-Windkomponenten (`x_wind`/`y_wind`) und gewünschte Behandlung beim Auslaufen von v1.
5. Reale, vollständige PMTiles-Größe und Buildzeit nach Web-Mercator-Reprojektion; die vorliegenden Werte sind Native-Grid-Benchmarks.
6. Bytegenauigkeit und Leistung des gewählten UInt-Pfads in MapLibre GL JS, MapLibre Native/iPhone und OpenLayers.
7. Verhalten bei partiellen NoData-Rändern: die untersuchten Vollgitterparameter waren entweder vollständig gültig oder bei NWP-Lead 0 vollständig leer; ein reales gemischtes Randmasken-Fixture fehlt.
8. Massendownloadstruktur und deren Eignung als Alternative für sehr große Ensemble-/APOLIS-Builds.
9. Vom Betreiber garantierte Publikationsverzögerung pro Produkt. Metadaten zeigen Aktualität, aber keine belastbare SLA.

## Reproduktion

Bestehende Tests:

```bash
python -m pytest -q
# 34 passed
```

Benchmark:

```bash
python -m scripts.benchmark_grid_encodings \
  nwp-v2-20261028T10-full-2t-tp-tcc.nc \
  encoding-benchmarks.json \
  --nodata-source nwp-v2-20261028T09-2t-tp-tcc.nc
```

Die Rohdateien selbst sind wegen ihrer Größe nicht eingecheckt; Dateinamen, API-Abfragen, Bytegrößen und SHA-256 stehen in [`netcdf-samples.json`](netcdf-samples.json).
