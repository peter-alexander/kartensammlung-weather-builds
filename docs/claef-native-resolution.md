# C-LAEF source resolution experiment

The first prototype used Web-Mercator PNG tiles to zoom 8. At display zoom 11.68, MapLibre enlarged those raster pixels and exposed apparently uneven blocks. Those display pixels are **not** the model's native cells.

This branch increases the test archive to **zoom 10**, keeping nearest-neighbor resampling and the source NetCDF unchanged. It prints a report with native cell pitch in EPSG:3857 and tile pixel pitch and rejects a configuration with fewer than two output pixels per shortest native cell. This reduces unintended omission of native source cells by undersampling. Exact shape and placement remain subject to the EPSG:4326 → EPSG:3857 reprojection.

**This is not a mathematically lossless copy of the original 945 × 1300 grid.** A tiled Web-Mercator raster cannot reproduce the source raster's cell boundaries and values bijectively. If we must guarantee every original cell/value is available without reprojection, store the native grid and its transform separately (or in a dedicated lossless grid asset) in addition to render-oriented PMTiles.

The new build remains manually triggered. Compare the output archive size against the earlier ~2.7 MB and inspect at zoom 11.68; production weather forecasts remain unchanged.
