#!/usr/bin/env bash
set -euo pipefail

KEEP="${1:-3}"
PREFIX="${2:-arome-}"

mapfile -t TAGS < <(
	gh release list --limit 100 --json tagName,isDraft \
		--jq ".[] | select(.isDraft == false and (.tagName | startswith(\"${PREFIX}\"))) | .tagName"
)

if (( ${#TAGS[@]} <= KEEP )); then
	exit 0
fi

for TAG in "${TAGS[@]:KEEP}"; do
	echo "Deleting old release ${TAG}"
	gh release delete "${TAG}" --yes --cleanup-tag
done
