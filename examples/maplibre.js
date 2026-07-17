import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';

const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

export function addAromePrecipitation(map, pmtilesUrl) {
	const sourceId = 'arome-precipitation-source';
	const layerId = 'arome-precipitation';

	map.addSource(sourceId, {
		type: 'raster-dem',
		url: `pmtiles://${pmtilesUrl}`,
		tileSize: 256,
		encoding: 'custom',
		redFactor: 2.56,
		greenFactor: 0.01,
		blueFactor: 0,
		baseShift: 0
	});

	map.addLayer({
		id: layerId,
		type: 'color-relief',
		source: sourceId,
		paint: {
			'color-relief-opacity': 0.82,
			'color-relief-color': [
				'interpolate',
				['linear'],
				['elevation'],
				0, 'rgba(0,0,0,0)',
				0.1, '#d7f0ff',
				0.5, '#8ecae6',
				1, '#219ebc',
				2, '#126782',
				5, '#52b788',
				10, '#f9c74f',
				20, '#f9844a',
				40, '#d00000'
			],
			resampling: 'nearest'
		}
	});

	return { sourceId, layerId };
}

export function addAromeClouds(map, pmtilesUrl) {
	const sourceId = 'arome-cloud-source';
	const layerId = 'arome-cloud';

	map.addSource(sourceId, {
		type: 'raster-dem',
		url: `pmtiles://${pmtilesUrl}`,
		tileSize: 256,
		encoding: 'custom',
		redFactor: 0,
		greenFactor: 0,
		blueFactor: 100 / 255,
		baseShift: 0
	});

	map.addLayer({
		id: layerId,
		type: 'color-relief',
		source: sourceId,
		paint: {
			'color-relief-opacity': 0.55,
			'color-relief-color': [
				'interpolate',
				['linear'],
				['elevation'],
				0, 'rgba(255,255,255,0)',
				25, 'rgba(240,240,240,0.18)',
				50, 'rgba(215,215,215,0.35)',
				75, 'rgba(180,180,180,0.55)',
				100, 'rgba(130,130,130,0.75)'
			],
			resampling: 'linear'
		}
	});

	return { sourceId, layerId };
}
