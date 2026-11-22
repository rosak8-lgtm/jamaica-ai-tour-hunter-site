#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
[[ -f "$KEY" ]] || { echo "STOP_ORACLE_SSH_KEY_MISSING"; exit 2; }
set -- \
 "$ROOT/scripts/oracle_bg_booking_fields_audit.py" \
 "$ROOT/scripts/oracle_bg_multicountry_price_scan.py" \
 "$ROOT/scripts/oracle_bg_selected_quote_probe.py" \
 "$ROOT/scripts/oracle_bg_preview_export.py" \
 "$ROOT/scripts/catalog_size_budget.py" \
 "$ROOT/scripts/oracle_bg_price_detail_probe.py" \
 "$ROOT/scripts/oracle_bg_route_sync.py" \
 "$ROOT/scripts/tour_price_reference.py" \
 "$ROOT/destination-directory.json" \
 "$ROOT/tour-previews.json"
for file in "$@"; do
 [[ -f "$file" ]] || { echo "STOP_REQUIRED_SOURCE_MISSING"; exit 2; }
done
DIR=""
cleanup(){
 if [[ "$DIR" =~ ^/tmp/jamaica-booking-audit\.[[:alnum:]]+$ ]]; then
  ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
   -i "$KEY" "$REMOTE" "rm -rf -- '$DIR'" >/dev/null 2>&1 || true
 fi
}
trap cleanup EXIT
DIR="$(ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes \
 -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY" "$REMOTE" \
 'umask 077; mktemp -d /tmp/jamaica-booking-audit.XXXXXXXX')"
[[ "$DIR" =~ ^/tmp/jamaica-booking-audit\.[[:alnum:]]+$ ]] || {
 echo "STOP_REMOTE_DIR_INVALID"; exit 2;
}
ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
 -o ConnectTimeout=15 -i "$KEY" "$REMOTE" "umask 077; mkdir -p '$DIR/backend'"
scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
 -o ConnectTimeout=15 -i "$KEY" "$@" "$REMOTE:$DIR/"
scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
 -o ConnectTimeout=15 -i "$KEY" "$ROOT/backend/bg_price_age_scope.py" \
 "$ROOT/backend/bg_private_source_crosswalk.py" "$REMOTE:$DIR/backend/"
echo "=== JAMAICA SERVER ONLY READ-ONLY BOOKING FIELD AUDIT ==="
ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
 -o ConnectTimeout=15 -i "$KEY" "$REMOTE" \
 "python3 -B '$DIR/oracle_bg_booking_fields_audit.py' --directory '$DIR/destination-directory.json' --previews '$DIR/tour-previews.json' --limit 3"
