#!/usr/bin/env bash
# JAMAICA Oracle catalog incident triage. READ ONLY. No API calls.
# Prints only file presence/byte counts, source checksums, service state and
# sanitized JAMAICA_* log lines. Never prints credentials, URLs, row data.
set -Eeuo pipefail
umask 077
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
[[ -r "$KEY" ]] || { echo "STOP_JAMAICA_SSH_KEY_UNAVAILABLE"; exit 2; }

ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY" \
    "$REMOTE" 'bash -s' <<'REMOTE_SH'
set -Eeuo pipefail
umask 077
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP_WRONG_ORACLE_USER"; exit 2; }
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
ROOT="$HOME/.local/share/jamaica-oracle-catalog"
CLONE="$ROOT/site"
BIN="$HOME/.local/opt/jamaica-oracle-catalog"
SERVICE="jamaica-oracle-catalog-5min.service"
TIMER="jamaica-oracle-catalog-5min.timer"

echo "=== JAMAICA ORACLE CATALOG INCIDENT READ-ONLY ==="
echo "TIMER_STATE=$(systemctl --user is-active "$TIMER" || true)"
echo "SERVICE_STATE=$(systemctl --user is-active "$SERVICE" || true)"
echo "SERVICE_RESULT=$(systemctl --user show "$SERVICE" -p Result --value)"
if [[ -d "$CLONE/.git" ]]; then
 echo "ORACLE_CLONE_REV=$(git -C "$CLONE" rev-parse --short HEAD)"
fi
echo "=== ORACLE FILE SIZE ONLY ==="
for file in \
 "$ROOT/generated-tour-previews.json" \
 "$ROOT/recent-price-list-previews.json" \
 "$CLONE/tour-previews.json"; do
 case "$file" in
 "$ROOT/generated-tour-previews.json") label="GENERATED_FEED";;
 "$ROOT/recent-price-list-previews.json") label="PRIVATE_RECENT_CACHE";;
 *) label="PUBLIC_CLONE_FEED";;
 esac
 if [[ -f "$file" && ! -L "$file" ]]; then
  echo "${label}_BYTES=$(stat -c %s -- "$file")"
 else
  echo "${label}_STATUS=ABSENT_OR_NOT_REGULAR"
 fi
done
echo "=== ORACLE PUBLISHER SOURCE VERSION ==="
for file in "$BIN/oracle_site_publisher.py" "$CLONE/scripts/oracle_site_publisher.py"; do
 if [[ -f "$file" && ! -L "$file" ]]; then
  case "$file" in
    "$BIN"/*) label="INSTALLED_PUBLISHER";;
    *) label="GIT_CHECKOUT_PUBLISHER";;
  esac
  echo "${label}_SHA256=$(sha256sum "$file" | cut -d' ' -f1)"
 fi
done
echo "=== SAFE INCIDENT EVENT LOG ==="
journalctl --user -u "$SERVICE" --no-pager -o cat -n 180 |
 grep -E '^JAMAICA_(GENERATED_FEED_BYTES|PREVIEW_OUTPUT_BYTES|PREVIEW_DROPPED_BY_BYTE_BUDGET|PREVIEWS_DROPPED_BY_BYTE_BUDGET|ORACLE_COUNTRY_COUNT|ORACLE_TOUR_COUNT|ORACLE_PUBLISH|ORACLE_5MIN_IMPORT_(PASS|HOLD)|RECENT_UNRECHECKED_PREVIEWS|RECENT_UNRECHECKED_COUNTRIES)=' |
 tail -n 45 || true
echo "JAMAICA_ORACLE_INCIDENT_DIAGNOSTIC_COMPLETE=YES"
REMOTE_SH
