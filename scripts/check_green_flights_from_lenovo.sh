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
[[ $# -le 1 ]] || { echo "STOP_ONLY_ONE_COUNTRY_ALLOWED"; exit 2; }
COUNTRY="${1:-}"
[[ ${#COUNTRY} -le 120 ]] || { echo "STOP_COUNTRY_NAME_TOO_LONG"; exit 2; }
REMOTE_COUNTRY_ARG=""
if [[ -n "$COUNTRY" ]]; then
  # GNU/bash printf %q shell-escapes all user-controlled bytes (including
  # spaces, quotes and metacharacters), prior to constructing remote argv.
  REMOTE_COUNTRY_ARG=" --country $(printf '%q' "$COUNTRY")"
fi
SSH=(ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
SCP=(scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
REMOTE_TMP=""
cleanup(){
 if [[ "$REMOTE_TMP" =~ ^/tmp/jamaica-flight-audit\.[[:alnum:]]+$ ]];then
   "${SSH[@]}" "$REMOTE" "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1 || true
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
echo "=== BG READONLY OUTBOUND/RETURN GREEN FLIGHT EVIDENCE ==="
"${SSH[@]}" "$REMOTE" "python3 -B '$REMOTE_TMP/oracle_bg_flight_evidence_probe.py' --directory '$REMOTE_TMP/destination-directory.json'$REMOTE_COUNTRY_ARG"
echo "JAMAICA_GREEN_PLANES_AUDIT_COMPLETE"
