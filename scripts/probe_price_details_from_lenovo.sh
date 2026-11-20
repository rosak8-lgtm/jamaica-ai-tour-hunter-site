#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
test -f "$KEY" || { echo "STOP_ORACLE_SSH_KEY_MISSING"; exit 2; }
for file in scripts/oracle_bg_price_detail_probe.py scripts/oracle_bg_route_sync.py destination-directory.json; do
  test -f "$ROOT/$file" || { echo "STOP_SOURCE_MISSING"; exit 2; }
done
SSH=(ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
SCP=(scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
REMOTE_TMP="$("${SSH[@]}" "$REMOTE" 'umask 077; mktemp -d /tmp/jamaica-price-probe.XXXXXXXX')"
[[ "$REMOTE_TMP" =~ ^/tmp/jamaica-price-probe\.[[:alnum:]]+$ ]] || { echo "STOP_REMOTE_TMP_INVALID"; exit 2; }
cleanup(){
  "${SSH[@]}" "$REMOTE" "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1 || true
}
trap cleanup EXIT
"${SCP[@]}" "$ROOT/scripts/oracle_bg_price_detail_probe.py" "$ROOT/scripts/oracle_bg_route_sync.py" "$ROOT/destination-directory.json" "$REMOTE:$REMOTE_TMP/"
echo "=== ORACLE READ-ONLY DETAIL PRICE DIAGNOSTIC ==="
"${SSH[@]}" "$REMOTE" "python3 -B '$REMOTE_TMP/oracle_bg_price_detail_probe.py' --directory '$REMOTE_TMP/destination-directory.json' --max-countries 3"
