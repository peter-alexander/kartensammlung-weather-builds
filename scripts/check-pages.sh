#!/usr/bin/env bash
set -euo pipefail
: "${MODEL:?}"
: "${TAG:?}"
: "${GITHUB_OUTPUT:?}"
if git fetch --quiet origin gh-pages; then
	published="$(git show FETCH_HEAD:"${MODEL}/latest.json" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("release_tag", ""))' 2>/dev/null || true)"
else
	published=""
fi
# A branch push alone does not prove that the GitHub Pages deployment succeeded.
public_url="https://peter-alexander.github.io/kartensammlung-weather-builds/${MODEL}/latest.json"
public_tag="$(curl -fsSL --connect-timeout 5 --max-time 15 -H 'Cache-Control: no-cache' "${public_url}?check=${GITHUB_RUN_ID:-0}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("release_tag", ""))' 2>/dev/null || true)"
echo "Probe at $(date -u +%Y-%m-%dT%H:%M:%SZ); branch=${published:-none}; pages=${public_tag:-none}; requested=$TAG"
if [[ "$published" == "$TAG" && "$public_tag" == "$TAG" ]]; then
	echo "Build unnecessary: $MODEL $TAG is already published."
	echo "is_new=false" >> "$GITHUB_OUTPUT"
else
	echo "New run: $MODEL $TAG (published: ${published:-none})."
	echo "is_new=true" >> "$GITHUB_OUTPUT"
fi
