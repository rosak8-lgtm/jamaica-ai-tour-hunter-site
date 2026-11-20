#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
[[ -f "$KEY" ]] || { echo "STOP_SSH_KEY_MISSING"; exit 2; }
for f in scripts/oracle_bg_multicountry_price_scan.py scripts/oracle_bg_selected_quote_probe.py scripts/oracle_bg_preview_export.py scripts/tour_price_reference.py scripts/oracle_bg_price_detail_probe.py scripts/oracle_bg_route_sync.py destination-directory.json tour-previews.json; do
 [[ -f "$ROOT/$f" ]] || { echo "STOP_REQUIRED_SOURCE_MISSING"; exit 2; }
done
SSH=(ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
SCP=(scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
REMOTE_TMP=""
cleanup(){
 if [[ "$REMOTE_TMP" =~ ^/tmp/jamaica-multiscan\.[[:alnum:]]+$ ]]; then
  "${SSH[@]}" "$REMOTE" "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1 || true
 fi
}
trap cleanup EXIT
REMOTE_TMP="$("${SSH[@]}" "$REMOTE" 'umask 077; mktemp -d /tmp/jamaica-multiscan.XXXXXXXX')"
[[ "$REMOTE_TMP" =~ ^/tmp/jamaica-multiscan\.[[:alnum:]]+$ ]] || { echo "STOP_BAD_REMOTE_DIRECTORY"; exit 2; }
"${SCP[@]}" "$ROOT/scripts/oracle_bg_multicountry_price_scan.py" "$ROOT/scripts/oracle_bg_selected_quote_probe.py" "$ROOT/scripts/oracle_bg_preview_export.py" "$ROOT/scripts/tour_price_reference.py" "$ROOT/scripts/oracle_bg_price_detail_probe.py" "$ROOT/scripts/oracle_bg_route_sync.py" "$ROOT/destination-directory.json" "$ROOT/tour-previews.json" "$REMOTE:$REMOTE_TMP/"
echo "=== READ ONLY MULTICOUNTRY TOUR PRICE SCAN ==="
"${SSH[@]}" "$REMOTE" "python3 -B '$REMOTE_TMP/oracle_bg_multicountry_price_scan.py' --directory '$REMOTE_TMP/destination-directory.json' --previews '$REMOTE_TMP/tour-previews.json' --limit 3"
