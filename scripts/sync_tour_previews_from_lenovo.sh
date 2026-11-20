#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
REPO="rosak8-lgtm/jamaica-ai-tour-hunter-site"
test -f "$KEY" || { echo "STOP_ORACLE_SSH_KEY_MISSING"; exit 2; }
command -v gh >/dev/null || { echo "STOP_GH_MISSING"; exit 2; }
test "$(gh api user --jq .login)" = "rosak8-lgtm" || { echo "STOP_WRONG_GITHUB_ACCOUNT"; exit 2; }
for f in scripts/oracle_bg_preview_export.py scripts/oracle_bg_price_detail_probe.py scripts/oracle_bg_route_sync.py destination-directory.json; do
  test -f "$ROOT/$f" || { echo "STOP_REQUIRED_SOURCE_MISSING"; exit 2; }
done
SSH=(ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
SCP=(scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
TMP="$(mktemp -d)"
REMOTE_TMP=""
cleanup(){
 if [[ "$REMOTE_TMP" =~ ^/tmp/jamaica-previews\.[[:alnum:]]+$ ]]; then
   "${SSH[@]}" "$REMOTE" "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1 || true
 fi
 rm -rf -- "$TMP"
}
trap cleanup EXIT
REMOTE_TMP="$("${SSH[@]}" "$REMOTE" 'umask 077; mktemp -d /tmp/jamaica-previews.XXXXXXXX')"
[[ "$REMOTE_TMP" =~ ^/tmp/jamaica-previews\.[[:alnum:]]+$ ]] || { echo "STOP_REMOTE_TMP_INVALID"; exit 2; }
"${SCP[@]}" "$ROOT/scripts/oracle_bg_preview_export.py" "$ROOT/scripts/oracle_bg_price_detail_probe.py" "$ROOT/scripts/oracle_bg_route_sync.py" "$ROOT/destination-directory.json" "$REMOTE:$REMOTE_TMP/"
echo "=== AUTHENTICATED ORACLE TOUR PREVIEWS (READ ONLY) ==="
"${SSH[@]}" "$REMOTE" "python3 -B '$REMOTE_TMP/oracle_bg_preview_export.py' --directory '$REMOTE_TMP/destination-directory.json' --output '$REMOTE_TMP/tour-previews.json' --max-countries 12 --per-country 2"
"${SCP[@]}" "$REMOTE:$REMOTE_TMP/tour-previews.json" "$TMP/tour-previews.json"
python3 - "$TMP/tour-previews.json" "$TMP/upload.json" <<'PY'
import base64,json,pathlib,sys
source=pathlib.Path(sys.argv[1])
if source.stat().st_size>8_000_000:
    raise SystemExit("STOP_PREVIEWS_TOO_LARGE")
obj=json.loads(source.read_text(encoding="utf-8"))
allowed={"id","hotel_id","hotel","country","origin","resort","room","depart_date","nights","status","quote_verified","availability_verified","flight_verified","bookable"}
rows=obj.get("previews")
if obj.get("schema")!="jamaica.tour-previews.v1" or obj.get("bookable") is not False or not isinstance(rows,list) or not 0<len(rows)<=6000:
    raise SystemExit("STOP_PREVIEW_SCHEMA_INVALID")
for row in rows:
    if not isinstance(row,dict) or set(row)!=allowed:
        raise SystemExit("STOP_UNAPPROVED_PREVIEW_FIELD")
    if row.get("bookable") is not False or row.get("availability_verified") is not False or row.get("quote_verified") is not False or row.get("flight_verified") is not False:
        raise SystemExit("STOP_UNVERIFIED_SALE_CLAIM")
payload={"message":"Refresh real read-only hotel date and room previews without prices","branch":"main",
         "content":base64.b64encode(source.read_bytes()).decode("ascii")}
pathlib.Path(sys.argv[2]).write_text(json.dumps(payload,separators=(",",":")))
print("PREVIEW_EXPORT_VALIDATED="+str(len(rows)))
PY
OLD_SHA="$(gh api "repos/$REPO/contents/tour-previews.json" --jq .sha 2>/dev/null || true)"
if [[ "$OLD_SHA" =~ ^[0-9a-f]{40}$ ]]; then
 python3 - "$TMP/upload.json" "$OLD_SHA" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);obj=json.loads(p.read_text());obj["sha"]=sys.argv[2]
p.write_text(json.dumps(obj,separators=(",",":")))
PY
fi
echo "=== PUBLISH SANITIZED HOTEL-DATE PREVIEWS ==="
gh api -X PUT "repos/$REPO/contents/tour-previews.json" --input "$TMP/upload.json" --jq '.commit.sha'
echo "JAMAICA_TOUR_PREVIEWS_PUBLISHED=YES"
echo "NO_PRICE_NO_BOOKING_NO_SECRET_EXPORTED=YES"
