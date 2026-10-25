#!/usr/bin/env bash
set -euo pipefail

: "${MODEL:?MODEL must be AROME or INCA}"
: "${TAG:?TAG missing}"
: "${REFERENCE_TIME:?REFERENCE_TIME missing}"
: "${LOCAL_DIR:?LOCAL_DIR missing}"
: "${GITHUB_TOKEN:?GITHUB_TOKEN missing}"

case "$MODEL" in
	AROME) prefix=arome; retain=3 ;;
	INCA) prefix=inca; retain=4 ;;
	*) echo "Unexpected MODEL: $MODEL" >&2; exit 1 ;;
esac
[[ "$TAG" =~ ^${prefix}-[0-9]{8}T[0-9]{4}Z$ ]] || { echo "Invalid tag $TAG" >&2; exit 1; }
test -s "$LOCAL_DIR/manifest.json"
test -s "$LOCAL_DIR/validation.json"
python3 - "$LOCAL_DIR" "$TAG" <<'PY'
import json
from pathlib import Path
import sys
folder = Path(sys.argv[1])
tag = sys.argv[2]
manifest = json.loads((folder / 'manifest.json').read_text())
validation = json.loads((folder / 'validation.json').read_text())
files = sorted(folder.glob('*.pmtiles'))
assert manifest['release_tag'] == tag
assert validation['status'] == 'passed'
assert len(files) == int(validation['asset_count']) > 0
assert all(p.stat().st_size > 0 for p in files)
assert {p.name for p in files} == {s['asset'] for s in manifest['timesteps']}
PY

site="$(mktemp -d)"
trap 'git worktree remove --force "$site" >/dev/null 2>&1 || true' EXIT
if git fetch --quiet origin gh-pages; then
	old_sha="$(git rev-parse FETCH_HEAD)"
	git worktree add --detach "$site" "$old_sha" >/dev/null
else
	old_sha=""
	git worktree add --orphan -b gh-pages "$site" >/dev/null
fi

# Never publish Jekyll transformations of binary PMTiles.
touch "$site/.nojekyll"
mkdir -p "$site/$MODEL/$TAG"
cp "$LOCAL_DIR"/*.pmtiles "$LOCAL_DIR/manifest.json" "$LOCAL_DIR/validation.json" "$site/$MODEL/$TAG/"

python3 - "$site/$MODEL/latest.json" "$TAG" "$REFERENCE_TIME" <<'PY'
import json
import sys
from pathlib import Path
destination, tag, reference_time = sys.argv[1:]
value = {
	'schema_version': 1,
	'release_tag': tag,
	'reference_time': reference_time,
	'manifest': f'{tag}/manifest.json',
	'asset_url_template': f'{tag}/{{asset}}'
}
Path(destination).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
PY

python3 - "$site/$MODEL" "$prefix" "$retain" <<'PY'
from pathlib import Path
import re
import shutil
import sys
folder, prefix, count = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
runs = sorted((p for p in folder.iterdir() if p.is_dir() and re.fullmatch(prefix + r'-\d{8}T\d{4}Z', p.name)), key=lambda p: p.name, reverse=True)
for path in runs[count:]:
	print('Prune old run:', path)
	shutil.rmtree(path)
PY

git -C "$site" add -A
tree="$(git -C "$site" write-tree)"
new_sha="$(printf 'Publish %s %s to GitHub Pages\n' "$MODEL" "$TAG" | git -C "$site" -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' commit-tree "$tree")"
git -C "$site" push --force-with-lease="refs/heads/gh-pages:${old_sha}" origin "${new_sha}:refs/heads/gh-pages"
# The branch is storage; GitHub Pages is explicitly deployed by deploy-pages.
mkdir -p "$RUNNER_TEMP/weather-pages-site"
rsync -a --delete --exclude='.git' "$site/" "$RUNNER_TEMP/weather-pages-site/"
echo "Prepared Pages snapshot $new_sha in $RUNNER_TEMP/weather-pages-site"
