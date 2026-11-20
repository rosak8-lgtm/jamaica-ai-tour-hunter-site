#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
REPO="rosak8-lgtm/jamaica-ai-tour-hunter-site"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
test -f "$ROOT/destination-directory.json" || { echo "STOP_DIRECTORY_MISSING"; exit 2; }
test -f "$ROOT/scripts/oracle_bg_route_sync.py" || { echo "STOP_SYNC_SOURCE_MISSING"; exit 2; }
test -f "$KEY" || { echo "STOP_SSH_KEY_MISSING"; exit 2; }
command -v gh >/dev/null || { echo "STOP_GH_MISSING"; exit 2; }
test "$(gh api user --jq .login)" = "rosak8-lgtm" || { echo "STOP_WRONG_GITHUB_ACCOUNT"; exit 2; }
SSH="ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i $KEY"
SCP="scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i $KEY"
LOCAL_TMP="$(mktemp -d)"
REMOTE_TMP=""
cleanup() {
 if [[ -n "$REMOTE_TMP" && "$REMOTE_TMP" =~ ^/tmp/jamaica-bg-routes\.[[:alnum:]]+$ ]]; then
   $SSH "$REMOTE" "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1 || true
 fi
 rm -rf -- "$LOCAL_TMP"
}
trap cleanup EXIT
REMOTE_TMP="$($SSH "$REMOTE" 'umask 077; mktemp -d /tmp/jamaica-bg-routes.XXXXXXXX')"
[[ "$REMOTE_TMP" =~ ^/tmp/jamaica-bg-routes\.[[:alnum:]]+$ ]] || { echo "STOP_REMOTE_DIR_INVALID"; exit 2; }
$SCP "$ROOT/scripts/oracle_bg_route_sync.py" "$ROOT/destination-directory.json" "$REMOTE:$REMOTE_TMP/"
echo "=== READ ONLY ORACLE PRICE LIST DISCOVERY ==="
$SSH "$REMOTE" "python3 -B '$REMOTE_TMP/oracle_bg_route_sync.py' --directory '$REMOTE_TMP/destination-directory.json' --output '$REMOTE_TMP/route-discovery.json'"
$SCP "$REMOTE:$REMOTE_TMP/route-discovery.json" "$LOCAL_TMP/route-discovery.json"
python3 - "$LOCAL_TMP/route-discovery.json" "$LOCAL_TMP/upload.json" <<'PY'
import base64,json,pathlib,sys
p=pathlib.Path(sys.argv[1])
if p.stat().st_size>8000000:raise SystemExit("STOP_PUBLIC_DATA_TOO_LARGE")
d=json.loads(p.read_text())
if (d.get("schema")!="jamaica.route-discovery.v1" or d.get("bookable") is not False
 or d.get("quote_verified") is not False or d.get("availability_verified") is not False):
 raise SystemExit("STOP_DISCOVERY_SCHEMA_UNSAFE")
items=d.get("routes",[])
allowed={"id","country","origin","date","nights","route","status","quote_verified","availability_verified","bookable"}
if not isinstance(items,list) or len(items)>24000:raise SystemExit("STOP_ROUTES_TOO_MANY")
for row in items:
 if not isinstance(row,dict) or set(row).difference(allowed):
  raise SystemExit("STOP_PRIVATE_DATA_FIELD")
 if row.get("bookable") is not False or row.get("quote_verified") is not False:
  raise SystemExit("STOP_BOOKING_CLAIM")
payload={"message":"Refresh authorized route discovery with no prices and no booking claims",
 "branch":"main","content":base64.b64encode(p.read_bytes()).decode("ascii")}
pathlib.Path(sys.argv[2]).write_text(json.dumps(payload,separators=(",",":")))
print("SANITIZED_ROUTES="+str(len(items)))
PY
echo "=== PUBLISH SAFE ROUTE DISCOVERY ==="
OLD_SHA="$(gh api "repos/$REPO/contents/route-discovery.json" --jq .sha 2>/dev/null || true)"
if [[ "$OLD_SHA" =~ ^[0-9a-f]{40}$ ]]; then
 python3 - "$LOCAL_TMP/upload.json" "$OLD_SHA" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);o=json.loads(p.read_text());o["sha"]=sys.argv[2];p.write_text(json.dumps(o))
PY
fi
gh api -X PUT "repos/$REPO/contents/route-discovery.json" --input "$LOCAL_TMP/upload.json" --jq '.commit.sha'
echo "ROUTE_DISCOVERY_PUBLISHED=YES"
echo "PRIVATE_CREDENTIALS_REMAIN_ON_ORACLE=YES"
echo "NO_BOOKING_OR_PAYMENT_CALLS=YES"
