# C-LAEF: sechs stündliche Temperaturfelder

Der manuelle Workflow `Test C-LAEF Temperature Build` erzeugt jetzt die Vorhersagestunden **+1 bis +6** eines Modelllaufs in **einem einzigen GeoSphere-NetCDF-Request** und verarbeitet die sechs Zeitfelder sequenziell zu:

- `2t-f001.pmtiles` bis `2t-f006.pmtiles` (Zoom 5–10, numerische PNGs),
- einem `manifest.json` mit sechs chronologisch geordneten `frames`-Einträgen,
- einem GitHub-Actions-Artefakt zur technischen Prüfung.

Die GitHub-Pages-Veröffentlichung validiert **alle sechs** Manifest-Einträge, UTC-Zeitpunkte, Dateigrößen und SHA-256-Prüfsummen **bevor** sie den Versionszeiger `CLAEF2T/latest.json` umstellt. Das ist weiterhin ein **manuell** gestarteter Experimentallauf, keine automatische Modellüberwachung.

Die bestehende Kartensammlung-Integration liest aktuell weiterhin nur `frames[0]`; die Zeitauswahl folgt in einem separaten PR, sobald der sechsfache Build und die Veröffentlichung erfolgreich geprüft wurden.

**Größenordnung:** Bei bisherigen rund 7 MB pro Temperaturframe erwarten wir grob 42 MB für sechs Frames, zuzüglich weiterer auf GitHub Pages liegender Daten. Die tatsächliche Größe muss der Actions-Lauf zeigen. R2 wird hier nicht genutzt.

**Grenzen:** Die unveränderte Quellgitterauflösung ist durch die NetCDF-Datei belegt. Web-Mercator-Kacheln sind nach wie vor eine Reprojektion, keine mathematisch verlustfreie Archivierung des nativen Gitters. Die Quantisierungsgrenzen −50 °C bis +60 °C bleiben experimentelle Werte.
