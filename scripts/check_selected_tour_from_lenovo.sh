#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
[[ -f "$KEY" ]] || { echo "STOP_SSH_KEY_MISSING"; exit 2; }
for name in scripts/oracle_bg_selected_quote_probe.py scripts/oracle_bg_preview_export.py scripts/oracle_bg_price_detail_probe.py scripts/oracle_bg_route_sync.py destination-directory.json tour-previews.json; do
 [[ -f "$ROOT/$name" ]] || { echo "STOP_REQUIRED_FILE_MISSING"; exit 2; }
done
PREVIEW_ID="${1:-}"
if [[ -z "$PREVIEW_ID" ]]; then
 PREVIEW_ID="$(python3 -B "$ROOT/scripts/select_future_preview.py" --feed "$ROOT/tour-previews.json")"
fi
[[ "$PREVIEW_ID" =~ ^p_[a-f0-9]{24}$ ]] || { echo "STOP_INVALID_PREVIEW_ID"; exit 2; }
SSH=(ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
SCP=(scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
REMOTE_TMP=""
cleanup(){
 if [[ "$REMOTE_TMP" =~ ^/tmp/jamaica-selection\.[[:alnum:]]+$ ]]; then
  "${SSH[@]}" "$REMOTE" "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1 || true
 fi
}
trap cleanup EXIT
REMOTE_TMP="$("${SSH[@]}" "$REMOTE" 'umask 077; mktemp -d /tmp/jamaica-selection.XXXXXXXX')"
[[ "$REMOTE_TMP" =~ ^/tmp/jamaica-selection\.[[:alnum:]]+$ ]] || exit 2
"${SCP[@]}" "$ROOT/scripts/oracle_bg_selected_quote_probe.py" "$ROOT/scripts/oracle_bg_preview_export.py" "$ROOT/scripts/oracle_bg_price_detail_probe.py" "$ROOT/scripts/oracle_bg_route_sync.py" "$ROOT/destination-directory.json" "$ROOT/tour-previews.json" "$REMOTE:$REMOTE_TMP/"
echo "=== READ ONLY MATCH SELECTED PREVIEW TO LIVE PRICE LIST ==="
"${SSH[@]}" "$REMOTE" "python3 -B '$REMOTE_TMP/oracle_bg_selected_quote_probe.py' --directory '$REMOTE_TMP/destination-directory.json' --previews '$REMOTE_TMP/tour-previews.json' --preview-id '$PREVIEW_ID'"
