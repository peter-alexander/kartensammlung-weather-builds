import assert from "node:assert/strict";
import { decodeCode, decodeValue, styleValue, decodeAndStylePixels } from "../web/numeric-weather-decoder.mjs";

const encoding = { type: "uint16", layout: "rg8", nodata: 0, scale: .1, offset: -50 };
assert.equal(decodeCode(2, 94, encoding), 606);
assert.ok(Math.abs(decodeValue(606, encoding) - 10.5) < 1e-9);
assert.equal(decodeValue(0, encoding), null);
const styleA = { stops: [[0, "#000000"], [20, "#ffffff"]] };
const styleB = { stops: [[0, "#ffffff"], [20, "#000000"]] };
const pixels = new Uint8ClampedArray([2, 94, 0, 255, 0, 0, 0, 255]);
const a = decodeAndStylePixels(pixels, 2, 1, encoding, styleA);
const b = decodeAndStylePixels(pixels, 2, 1, encoding, styleB);
assert.deepEqual([...a.slice(4)], [0, 0, 0, 0]);
assert.notDeepEqual([...a.slice(0, 4)], [...b.slice(0, 4)]);
assert.equal(styleValue(10, styleA)[3], 255);
console.log("Numeric decoder and style independence tests passed.");
