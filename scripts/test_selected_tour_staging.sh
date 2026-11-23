#!/usr/bin/env bash
# Reproduce Oracle's isolated read-only selected-tour staging locally in CI.
# No BG credentials, SSH, passenger data, live API, or production mutation.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
mkdir -p "$TMP/backend"
for name in oracle_bg_selected_quote_probe.py oracle_bg_preview_export.py \
            catalog_size_budget.py tour_price_reference.py oracle_bg_price_detail_probe.py \
            oracle_bg_route_sync.py oracle_bg_multicountry_price_scan.py \
            oracle_bg_booking_fields_audit.py \
            oracle_bg_flight_evidence_probe.py flight_availability_evidence.py; do
 cp "$ROOT/scripts/$name" "$TMP/$name"
done
cp "$ROOT/backend/bg_price_age_scope.py" \
   "$ROOT/backend/bg_private_source_crosswalk.py" "$TMP/backend/"
env PYTHONPATH="" python3 -B "$TMP/oracle_bg_selected_quote_probe.py" --help >"$TMP/help.txt"
grep -Fq -- "--private-rooms-file" "$TMP/help.txt"
# All independent read-only entrypoints share this isolated import stack.
env PYTHONPATH="" python3 -B "$TMP/oracle_bg_multicountry_price_scan.py" --help >/dev/null
env PYTHONPATH="" python3 -B "$TMP/oracle_bg_booking_fields_audit.py" --help >/dev/null
env PYTHONPATH="" python3 -B "$TMP/oracle_bg_flight_evidence_probe.py" --help >/dev/null
echo "JAMAICA_ORACLE_SELECTED_TOUR_STAGING_IMPORTS=PASS"
