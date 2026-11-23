#!/usr/bin/env bash
# READ ONLY flight evidence audit on Oracle. No logins/URLs/prices/IDs in output.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
test -r "$KEY" || { echo "STOP_ORACLE_SSH_KEY_MISSING"; exit 2; }
for file in oracle_bg_flight_evidence_probe.py flight_availability_evidence.py \
  oracle_bg_preview_export.py catalog_size_budget.py oracle_bg_route_sync.py \
  oracle_bg_price_detail_probe.py tour_price_reference.py; do
  test -f "$ROOT/scripts/$file" || { echo "STOP_MISSING_SCRIPT=$file"; exit 2; }
done
test -f "$ROOT/destination-directory.json" || {
 echo "STOP_DIRECTORY_MISSING"; exit 2; }
# Country, number of source lists, and rotation slot are the only inputs.
# No remote shell evaluation of unvalidated numeric arguments.
[[ $# -le 3 ]] || { echo "STOP_EXPECT_COUNTRY_LIST_COUNT_SLOT"; exit 2; }
COUNTRY="${1:-}"
MAX_LISTS="${2:-1}"
PROBE_SLOT="${3:-0}"
[[ ${#COUNTRY} -le 120 ]] || { echo "STOP_COUNTRY_NAME_TOO_LONG"; exit 2; }
[[ "$MAX_LISTS" =~ ^[1-5]$ ]] || { echo "STOP_INVALID_LIST_COUNT"; exit 2; }
[[ "$PROBE_SLOT" =~ ^(0|[1-9][0-9]{0,4})$ ]] || {
 echo "STOP_INVALID_ROTATION_SLOT"; exit 2;
}
(( PROBE_SLOT <= 10000 )) || { echo "STOP_ROTATION_SLOT_TOO_LARGE"; exit 2; }
REMOTE_COUNTRY_ARG=" --max-lists $MAX_LISTS --probe-slot $PROBE_SLOT"
if [[ -n "$COUNTRY" && "$COUNTRY" != "--all-observed" ]]; then
  # GNU/bash printf %q shell-escapes all user-controlled bytes (including
  # spaces, quotes and metacharacters), prior to constructing remote argv.
  REMOTE_COUNTRY_ARG+=" --country $(printf '%q' "$COUNTRY")"
fi
SSH=(ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
SCP=(scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
REMOTE_TMP=""
LOCAL_TMP=""
cleanup(){
 if [[ "$REMOTE_TMP" =~ ^/tmp/jamaica-flight-audit\.[[:alnum:]]+$ ]];then
   "${SSH[@]}" "$REMOTE" "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1 || true
 fi
 if [[ "$LOCAL_TMP" =~ ^/tmp/jamaica-observed-countries\.[[:alnum:]]+$ ]];then
   rm -rf -- "$LOCAL_TMP"
 fi
}
trap cleanup EXIT
REMOTE_TMP="$("${SSH[@]}" "$REMOTE" 'umask 077; mktemp -d /tmp/jamaica-flight-audit.XXXXXXXX')"
[[ "$REMOTE_TMP" =~ ^/tmp/jamaica-flight-audit\.[[:alnum:]]+$ ]] || {
 echo "STOP_REMOTE_TMP_INVALID"; exit 2; }
"${SCP[@]}" "$ROOT/scripts/oracle_bg_flight_evidence_probe.py" \
 "$ROOT/scripts/flight_availability_evidence.py" \
 "$ROOT/scripts/oracle_bg_preview_export.py" \
 "$ROOT/scripts/catalog_size_budget.py" \
 "$ROOT/scripts/oracle_bg_price_detail_probe.py" \
 "$ROOT/scripts/oracle_bg_route_sync.py" \
 "$ROOT/scripts/tour_price_reference.py" \
 "$ROOT/destination-directory.json" "$REMOTE:$REMOTE_TMP/"
if [[ "$COUNTRY" == "--all-observed" ]]; then
  # Source names ONLY from the complete locally verified hash-manifest feed.
  # No dummy locations or every country from the general 251-country list.
  LOCAL_TMP="$(mktemp -d /tmp/jamaica-observed-countries.XXXXXXXX)"
  python3 -B - "$ROOT" "$LOCAL_TMP/observed.json" <<'PY'
import json,os,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(sys.argv[1])
sys.path.insert(0,str(root))
from scripts.local_selected_preview import _all_previews
feed,rows=_all_previews(root/"tour-previews.json")
today=datetime.now(timezone.utc).date().isoformat()
names=sorted({x["country"] for x in rows
              if x["depart_date"]>today and x["origin"]=="Иркутск"})
if not 1<=len(names)<=20:
    raise SystemExit("STOP_OBSERVED_COUNTRY_COUNT_UNSAFE")
path=Path(sys.argv[2])
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,"w",encoding="utf-8") as dst:
    json.dump(names,dst,ensure_ascii=False,separators=(",",":"))
print("JAMAICA_OBSERVED_SOURCE_COUNTRIES="+str(len(names)))
PY
  "${SCP[@]}" "$LOCAL_TMP/observed.json" "$REMOTE:$REMOTE_TMP/observed.json"
  "${SSH[@]}" "$REMOTE" "chmod 600 '$REMOTE_TMP/observed.json'"
  REMOTE_COUNTRY_ARG+=" --countries-file '$REMOTE_TMP/observed.json'"
fi
echo "=== BG READONLY OUTBOUND/RETURN GREEN FLIGHT EVIDENCE ==="
"${SSH[@]}" "$REMOTE" "python3 -B '$REMOTE_TMP/oracle_bg_flight_evidence_probe.py' --directory '$REMOTE_TMP/destination-directory.json'$REMOTE_COUNTRY_ARG"
echo "JAMAICA_GREEN_PLANES_AUDIT_COMPLETE"
