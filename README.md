# Kartensammlung Wetterdaten

Datenproduzent für die Kartensammlung. Die Migration ersetzt das bisherige AROME-v1-Produkt vollständig durch **C-LAEF AlpeAdria v2** mit dem GeoSphere-Ressourcenbezeichner `nwp-v2-1h-1km`.

## Status

**Migration in Entwicklung, nicht einsatzbereit.** Der alte AROME-Workflow und seine alten Veröffentlichungswerkzeuge wurden auf diesem Branch entfernt. Für C-LAEF existiert noch **kein freigegebener Build- oder Publish-Workflow**. Diesen Branch erst zusammenführen, wenn die neue Pipeline einschließlich der Kartensammlung-Integration fertig getestet ist.

- Der Workflow `Inspect C-LAEF AlpeAdria v2 dataset` prüft die echten GeoSphere-Metadaten; er lässt sich nach dem Merge über GitHub Actions manuell starten und speichert Rohmetadaten sowie einen Bericht als Artefakt.
- **Verifiziert durch GeoSphere-Migrationshilfe:** v2 stellt Niederschlag und Strahlung ausschließlich **dekumuliert** bereit. Keine Differenz zwischen benachbarten Stunden berechnen; dafür ist eine direkte Eingangsvalidierung im Rastercode implementiert. Parameternamen und Einheiten folgen ausschließlich den tatsächlichen Metadaten.
- Keine Annahmen oder Kompatibilitätsumrechnungen aus dem alten 2,5-km-AROME-Produkt übernehmen.
- Ziel: 1-km-Modellraster, stündliche Prognose bis 60 Stunden, Aktualisierung alle drei Stunden. Die API-Limits, Speicher-/Buildlaufzeiten, Rasterprojektion und PMTiles-Kodierung müssen für das neue native Gitter geprüft werden.
- Der INCA-Nowcast (`nowcast-v1-15min-1km`) ist eine **andere GeoSphere-Ressource**. Seine Pipeline bleibt erhalten, solange keine offizielle Abschaltankündigung für diesen Datensatz vorliegt.

## Migration-Checkliste

1. Original-Metadaten vom neuen Endpoint als Artefakt erfassen.
2. Parameternamen und Einheiten anhand der offiziellen Metadaten verifizieren; stündliche Niederschlagswerte unmittelbar übernehmen und validieren.
3. Neuer C-LAEF-Builder ohne AROME-v1-Namen oder Kompatibilitätsschicht.
4. Vollständige PMTiles inklusive Encoding- und Raster-Qualitätsprüfungen erzeugen.
5. GitHub Pages und Kartensammlung auf den neuen Produktnamen und die neuen Assets umstellen.
6. Tests und vollständigen erfolgreichen End-to-End-Build nachweisen.

GeoSphere: https://data.hub.geosphere.at/dataset/nwp-v2-1h-1km

Offizielle Migrationshinweise: https://public.hub.geosphere.at/public/resources/misc/Hilfestellung_DE.pdf
