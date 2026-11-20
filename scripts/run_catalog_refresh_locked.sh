#!/usr/bin/env bash
# Lenovo scheduler: existing SSH+gh authorization, no passwords stored.
# Read-only operator import; updates public price-list snapshots, not bookings.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/.cache/jamaica-tour-catalog"
LOCK="$HOME/.cache/jamaica-tour-catalog/import.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "JAMAICA_CATALOG_REFRESH_SKIPPED=PREVIOUS_RUN_ACTIVE"
  exit 0
fi
echo "JAMAICA_CATALOG_REFRESH_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
bash "$ROOT/scripts/sync_tour_previews_from_lenovo.sh"
echo "JAMAICA_CATALOG_REFRESH_END=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
