# Browsertest für C-LAEF-Temperatur

Der Test lädt **dasselbe numerische PMTiles-Archiv** und das `manifest.json` des manuellen `Test C-LAEF Temperature Build`. Temperaturwerte werden aus den verlustfrei gespeicherten PNG-Kanälen dekodiert; erst danach werden Farbwerte erzeugt. Der Wechsel zwischen **Manifest** und **Alternative** soll die Farben ändern, nicht die PMTiles.

## Start

1. Diesen PR mergen.
2. Unter GitHub Actions `Test C-LAEF Temperature Build` erneut ausführen.
3. Artefakt `claef-2t-prototype` als ZIP herunterladen und in ein Verzeichnis entpacken.
4. Ein Terminal **im entpackten Verzeichnis**, das die Datei `manifest.json` enthält, öffnen und `python -m http.server 8000` starten.
5. Im Browser `http://localhost:8000/demo/` aufrufen.
6. Farbskala wechseln und prüfen, ob sich die Darstellung ändert, ohne das PMTiles-Archiv neu zu erzeugen.

Die Testseite benötigt eine Internetverbindung für MapLibre, PMTiles-JavaScript und die OpenStreetMap-Basiskarte. Die numerischen Wetterdaten selbst kommen aus der entpackten lokalen PMTiles-Datei.

**Erfolgskriterien:** sichtbare Temperaturkarte, kein Decoderfehler in der Browserkonsole, erfolgreiche Änderung der Farbskala, weiterhin dieselbe PMTiles-Datei. Zusätzlich bitte auf iOS/Safari ausprobieren. Noch kein automatischer Browser-/WebGL-End-to-End-Test; PNG-Bytes können im Canvas-Pfad browserspezifische Probleme verursachen. Diese Seite dient gerade dazu, das zu verifizieren.

**Wichtig:** Sie läuft nicht sinnvoll über `file://` wegen Browsermodul-, Fetch- und Range-Anforderungen. Dieser PR ändert weder die Kartensammlung noch den produktiven Veröffentlichungsweg.
