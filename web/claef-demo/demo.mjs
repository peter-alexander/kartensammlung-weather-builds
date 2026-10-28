import { PMTiles } from "https://cdn.jsdelivr.net/npm/pmtiles@3.2.1/+esm";
import maplibregl from "https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/+esm";
import { decodeAndStylePixels } from "../numeric-weather-decoder.mjs";

const status = document.querySelector("#status");
const setStatus = (message) => { status.textContent = message; };
const manifestURL = new URL("../manifest.json", import.meta.url);
const manifest = await fetch(manifestURL).then((response) => {
	if (!response.ok) throw new Error("Manifest HTTP " + response.status);
	return response.json();
});
const parameter = manifest.variables.find((item) => item.id === "2t");
if (!parameter || parameter.frames.length !== 1) throw new Error("Expected one temperature frame");
const archiveURL = new URL(parameter.frames[0].href, manifestURL).href;
const archive = new PMTiles(archiveURL);
const header = await archive.getHeader();
if (header.tileType !== 2) throw new Error("Expected PNG PMTiles (tileType=2)");
let activeStyle = parameter.style;
let processed = 0;
const rasterProtocol = "ksnumeric";
maplibregl.addProtocol(rasterProtocol, async (params, abortController) => {
	const match = new URL(params.url).pathname.match(/^\/(\d+)\/(\d+)\/(\d+)$/);
	if (!match) throw new Error("Malformed numeric tile URL");
	const [zoom, x, y] = match.slice(1).map(Number);
	const tile = await archive.getZxy(zoom, x, y, abortController?.signal);
	if (!tile) return { data: await transparentPNG() };
	const blob = new Blob([tile.data], { type: "image/png" });
	const bitmap = await createImageBitmap(blob);
	const canvas = document.createElement("canvas");
	canvas.width = bitmap.width;
	canvas.height = bitmap.height;
	const context = canvas.getContext("2d", { willReadFrequently: true });
	context.drawImage(bitmap, 0, 0);
	bitmap.close();
	const raw = context.getImageData(0, 0, canvas.width, canvas.height);
	const rgba = decodeAndStylePixels(raw.data, canvas.width, canvas.height, parameter.encoding, activeStyle);
	context.putImageData(new ImageData(rgba, canvas.width, canvas.height), 0, 0);
	const png = await new Promise((resolve, reject) => canvas.toBlob((out) => out ? resolve(out) : reject(new Error("PNG conversion failed")), "image/png"));
	processed++;
	setStatus("Decodierte PNG-Kacheln: " + processed + " · " + parameter.frames[0].valid_time);
	return { data: await png.arrayBuffer() };
});

let transparentTile;
async function transparentPNG() {
	if (!transparentTile) {
		const canvas = document.createElement("canvas");
		canvas.width = canvas.height = 256;
		transparentTile = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
	}
	return transparentTile.arrayBuffer();
}

const map = new maplibregl.Map({
	container: "map",
	style: {
		version: 8,
		sources: {
			base: {
				type: "raster",
				tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
				tileSize: 256,
				attribution: "© OpenStreetMap contributors"
			}
		},
		layers: [{ id: "base", type: "raster", source: "base" }]
	},
	center: [13.5, 47.5],
	zoom: 6
});
map.addControl(new maplibregl.NavigationControl());
map.on("load", () => {
	map.addSource("temperature", {
		type: "raster",
		tiles: [rasterProtocol + "://tiles/{z}/{x}/{y}"],
		tileSize: 256,
		minzoom: 5,
		maxzoom: 8,
	});
	map.addLayer({ id: "temperature", type: "raster", source: "temperature", paint: { "raster-opacity": 0.8, "raster-resampling": "nearest" } });
	setStatus("PMTiles geladen. Temperatur gültig: " + parameter.frames[0].valid_time);
});
map.on("error", (event) => setStatus("Fehler: " + (event.error?.message ?? event.error)));
document.querySelector("#style").addEventListener("change", (event) => {
	activeStyle = event.target.value === "alternate" ? {
		type: "color-ramp",
		stops: [[-25, "#03001e"], [0, "#4a90e2"], [15, "#ffe082"], [40, "#bc0000"]]
	} : parameter.style;
	processed = 0;
	const source = map.getSource("temperature");
	if (source) source.setTiles([rasterProtocol + "://tiles/{z}/{x}/{y}?style=" + event.target.value]);
});
