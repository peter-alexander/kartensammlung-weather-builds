#!/usr/bin/env bash
set -euo pipefail

: "${LOCAL_DIR:?Missing LOCAL_DIR}"
: "${GITHUB_TOKEN:?Missing GITHUB_TOKEN}"
test -s "$LOCAL_DIR/manifest.json"
test -s "$LOCAL_DIR/2t-f001.pmtiles"

TAG="$(python3 - "$LOCAL_DIR" <<'PY'
import json, re, sys
from pathlib import Path
from weather_build.tile_manifest import validate_manifest

folder = Path(sys.argv[1])
manifest = validate_manifest(json.loads((folder / "manifest.json").read_text()))
assert manifest["source"]["dataset_id"] == "nwp-v2-1h-1km"
assert len(manifest["variables"]) == 1
variable = manifest["variables"][0]
assert variable["id"] == "2t" and len(variable["frames"]) == 61
import hashlib
from datetime import datetime, timedelta, timezone
reference_time = datetime.fromisoformat(manifest["reference_time"].replace("Z", "+00:00"))
for index, frame in enumerate(variable["frames"], start=1):
	assert frame["href"] == f"2t-f{index:03d}.pmtiles"
	assert frame["valid_time"] == (reference_time + timedelta(hours=index)).strftime("%Y-%m-%dT%H:%M:%SZ")
	asset = folder / frame["href"]
	assert asset.is_file() and asset.stat().st_size == frame["bytes"]
	assert hashlib.sha256(asset.read_bytes()).hexdigest() == frame["sha256"]
reference = manifest["reference_time"]
assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:00:00Z", reference)
print("claef2t-" + reference.replace("-", "").replace(":", "").replace("T", "T").replace("Z", "Z"))
PY
)"
[[ "$TAG" =~ ^claef2t-[0-9]{8}T[0-9]{6}Z$ ]]

site="$(mktemp -d)"
trap 'git worktree remove --force "$site" >/dev/null 2>&1 || true' EXIT
if git fetch --quiet origin gh-pages; then
	old_sha="$(git rev-parse FETCH_HEAD)"
	git worktree add --detach "$site" "$old_sha" >/dev/null
else
	echo "Expected existing gh-pages branch; refusing to overwrite it" >&2
	exit 1
fi

touch "$site/.nojekyll"
target="$site/CLAEF2T/$TAG"
mkdir -p "$target"
cp "$LOCAL_DIR/manifest.json" "$LOCAL_DIR"/2t-f???.pmtiles "$target/"
python3 - "$site/CLAEF2T/latest.json" "$TAG" <<'PY'
import json, sys
from pathlib import Path
path, tag = sys.argv[1:]
Path(path).write_text(json.dumps({
	"schema_version": 1,
	"release_tag": tag,
	"manifest": f"{tag}/manifest.json"
}, indent=2) + "\n")
PY

# Retain only the latest C-LAEF full forecast; do not touch INCA/AROME.
python3 - "$site/CLAEF2T" <<'PY'
from pathlib import Path
import re, shutil, sys
folder = Path(sys.argv[1])
runs = sorted((p for p in folder.iterdir() if p.is_dir() and re.fullmatch(r"claef2t-\d{8}T\d{6}Z", p.name)), reverse=True)
for old in runs[1:]:
	shutil.rmtree(old)
PY

python3 - "$site" <<'PY'
from pathlib import Path
import sys
site = Path(sys.argv[1])
size = sum(file.stat().st_size for file in site.rglob("*") if file.is_file() and ".git" not in file.parts)
print(f"GitHub Pages snapshot: {size / 1048576:.1f} MiB")
if size > 950 * 1048576:
	raise SystemExit("Pages snapshot exceeds 950 MiB safety limit; refusing publication")
PY

git -C "$site" add -A
tree="$(git -C "$site" write-tree)"
new_sha="$(printf 'Publish %s to GitHub Pages\n' "$TAG" | git -C "$site" -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' commit-tree "$tree")"
git -C "$site" push --force-with-lease="refs/heads/gh-pages:${old_sha}" origin "${new_sha}:refs/heads/gh-pages"
mkdir -p "$RUNNER_TEMP/weather-pages-site"
rsync -a --delete --exclude='.git' "$site/" "$RUNNER_TEMP/weather-pages-site/"
echo "Published CLAEF2T $TAG with manifest and PMTiles"
