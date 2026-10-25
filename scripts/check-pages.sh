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
if [[ "$published" == "$TAG" ]]; then
	echo "Build unnecessary: $MODEL $TAG is already published."
	echo "is_new=false" >> "$GITHUB_OUTPUT"
else
	echo "New run: $MODEL $TAG (published: ${published:-none})."
	echo "is_new=true" >> "$GITHUB_OUTPUT"
fi
