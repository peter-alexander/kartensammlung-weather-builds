#!/usr/bin/env bash
set -euo pipefail

for variable_name in HOST USER PASS TAG REFERENCE_TIME; do
	if [[ -z "${!variable_name:-}" ]]; then
		echo "Fehlende Umgebungsvariable: ${variable_name}" >&2
		exit 1
	fi
done

if [[ ! "$TAG" =~ ^inca-[0-9]{8}T[0-9]{4}Z$ ]]; then
	echo "Ungültiger INCA-Tag: ${TAG}" >&2
	exit 1
fi

LOCAL_DIR="${LOCAL_DIR:-out-inca}"
REMOTE_BASE="${REMOTE_BASE:-Wetter/INCA}"
RETAINED_RUNS="${RETAINED_RUNS:-4}"
RUN_ID="${GITHUB_RUN_ID:-local}"
RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
REMOTE_TAG_DIR="${REMOTE_BASE}/${TAG}"
REMOTE_STAGING_DIR="${REMOTE_BASE}/_upload_${TAG}_${RUN_ID}_${RUN_ATTEMPT}"

if [[ -z "$REMOTE_BASE" || "$REMOTE_BASE" == "/" || "$REMOTE_BASE" == "." || "$REMOTE_BASE" == ".." ]]; then
	echo "Unsicheres Remote-Basisverzeichnis: ${REMOTE_BASE}" >&2
	exit 1
fi

if [[ ! -d "$LOCAL_DIR" ]]; then
	echo "Lokales Ausgabeverzeichnis fehlt: ${LOCAL_DIR}" >&2
	exit 1
fi

for required_file in manifest.json validation.json; do
	if [[ ! -s "${LOCAL_DIR}/${required_file}" ]]; then
		echo "Erforderliche Ausgabedatei fehlt oder ist leer: ${LOCAL_DIR}/${required_file}" >&2
		exit 1
	fi
done

mapfile -t PMTILES_FILES < <(find "$LOCAL_DIR" -maxdepth 1 -type f -name '*.pmtiles' -print | sort)
if [[ "${#PMTILES_FILES[@]}" -eq 0 ]]; then
	echo "Keine PMTiles-Dateien in ${LOCAL_DIR} gefunden." >&2
	exit 1
fi

EXPECTED_ASSET_COUNT="$(python3 - "$LOCAL_DIR/validation.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
	validation = json.load(handle)

print(int(validation["asset_count"]))
PY
)"

if [[ "${#PMTILES_FILES[@]}" -ne "$EXPECTED_ASSET_COUNT" ]]; then
	echo "PMTiles-Anzahl stimmt nicht: ${#PMTILES_FILES[@]} vorhanden, ${EXPECTED_ASSET_COUNT} erwartet." >&2
	exit 1
fi

LATEST_FILE="$(mktemp)"
trap 'rm -f "$LATEST_FILE"' EXIT

python3 - "$LATEST_FILE" "$TAG" "$REFERENCE_TIME" <<'PY'
import json
import sys

path, tag, reference_time = sys.argv[1:]
value = {
	"schema_version": 1,
	"release_tag": tag,
	"reference_time": reference_time,
	"manifest": f"{tag}/manifest.json",
	"asset_url_template": f"{tag}/{{asset}}"
}

with open(path, "w", encoding="utf-8") as handle:
	json.dump(value, handle, ensure_ascii=False, indent=2)
	handle.write("\n")
PY

export LFTP_PASSWORD="$PASS"

lftp --env-password -u "$USER" "$HOST" <<LFTP
set cmd:fail-exit yes
set ftp:ssl-force yes
set ftp:ssl-protect-data yes
set ftp:passive-mode yes
set ssl:verify-certificate yes
set net:max-retries 5
set net:timeout 30
set net:reconnect-interval-base 5
set cmd:fail-exit no
mkdir -p "$REMOTE_BASE"
set cmd:fail-exit yes
rm -rf "$REMOTE_STAGING_DIR"
mirror --reverse --parallel=4 --delete --no-perms --verbose "$LOCAL_DIR" "$REMOTE_STAGING_DIR"
rm -rf "$REMOTE_TAG_DIR"
mv "$REMOTE_STAGING_DIR" "$REMOTE_TAG_DIR"
put "$LATEST_FILE" -o "$REMOTE_BASE/latest.json.new"
rm -f "$REMOTE_BASE/latest.json"
mv "$REMOTE_BASE/latest.json.new" "$REMOTE_BASE/latest.json"
bye
LFTP

echo "Easyname-INCA-Upload vollständig: ${REMOTE_TAG_DIR}"
echo "Aktiver INCA-Lauf: ${REMOTE_BASE}/latest.json"

if [[ ! "$RETAINED_RUNS" =~ ^[1-9][0-9]*$ ]]; then
	echo "Ungültiger Wert für RETAINED_RUNS: ${RETAINED_RUNS}; Remote-Bereinigung wird übersprungen." >&2
	exit 0
fi

REMOTE_LIST="$(lftp --env-password -u "$USER" "$HOST" <<LFTP
set cmd:fail-exit yes
set ftp:ssl-force yes
set ftp:ssl-protect-data yes
set ftp:passive-mode yes
set ssl:verify-certificate yes
cd "$REMOTE_BASE"
cls -1
bye
LFTP
)" || {
	echo "INCA-Remote-Verzeichnis konnte für die Bereinigung nicht gelesen werden; Upload bleibt gültig." >&2
	exit 0
}

mapfile -t REMOTE_TAGS < <(
	printf '%s\n' "$REMOTE_LIST" \
		| sed 's#/$##' \
		| grep -E '^inca-[0-9]{8}T[0-9]{4}Z$' \
		| sort -r \
		|| true
)

if [[ "${#REMOTE_TAGS[@]}" -le "$RETAINED_RUNS" ]]; then
	exit 0
fi

for old_tag in "${REMOTE_TAGS[@]:$RETAINED_RUNS}"; do
	echo "Entferne alten Easyname-INCA-Lauf: ${old_tag}"
	if ! lftp --env-password -u "$USER" "$HOST" <<LFTP
set cmd:fail-exit yes
set ftp:ssl-force yes
set ftp:ssl-protect-data yes
set ftp:passive-mode yes
set ssl:verify-certificate yes
rm -rf "$REMOTE_BASE/$old_tag"
bye
LFTP
	then
		echo "Alter Easyname-INCA-Lauf konnte nicht entfernt werden: ${old_tag}" >&2
	fi
done
