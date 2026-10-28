/**
 * Decode numeric PNG image pixels in a browser without color-based interpolation.
 * The PNG must be read as opaque RGB (uint16) or grayscale (uint8).
 * Styling is independent and accepts a manifest's recommended color-ramp stops.
 */
export function decodeCode(r, g, encoding) {
	if (encoding.type === "uint8" && encoding.layout === "gray8") return r;
	if (encoding.type === "uint16" && encoding.layout === "rg8") return r * 256 + g;
	throw new Error("Unsupported numeric weather encoding");
}

export function decodeValue(code, encoding) {
	if (code === encoding.nodata) return null;
	if (code < 0 || code > (encoding.type === "uint8" ? 255 : 65535)) throw new Error("Invalid code");
	return encoding.offset + (code - 1) * encoding.scale;
}

function parseHex(color) {
	if (!/^#[0-9a-f]{6}$/i.test(color)) throw new Error("Expected 6-digit hex color");
	return [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
}

export function styleValue(value, style) {
	if (value === null || Number.isNaN(value)) return [0, 0, 0, 0];
	const stops = style.stops;
	if (!stops?.length) throw new Error("Missing styling stops");
	if (value <= stops[0][0]) return [...parseHex(stops[0][1]), 255];
	if (value >= stops[stops.length - 1][0]) return [...parseHex(stops[stops.length - 1][1]), 255];
	for (let i = 0; i + 1 < stops.length; i++) {
		const [low, c0] = stops[i], [high, c1] = stops[i + 1];
		if (value <= high) {
			const t = (value - low) / (high - low);
			const a = parseHex(c0), b = parseHex(c1);
			return a.map((channel, j) => Math.round(channel + (b[j] - channel) * t)).concat(255);
		}
	}
	throw new Error("Unreachable style interpolation");
}

export function decodeAndStylePixels(pixels, width, height, encoding, style) {
	if (!(pixels instanceof Uint8ClampedArray) || pixels.length !== width * height * 4) {
		throw new Error("Expected ImageData RGBA bytes");
	}
	const output = new Uint8ClampedArray(pixels.length);
	for (let i = 0; i < pixels.length; i += 4) {
		const code = decodeCode(pixels[i], pixels[i + 1], encoding);
		output.set(styleValue(decodeValue(code, encoding), style), i);
	}
	return output;
}
