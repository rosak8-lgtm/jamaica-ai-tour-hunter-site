#!/usr/bin/env bash
# Read-only BG selection audit on Oracle. Never copies operator login,
# passport data, birthdays, application XML, or supplier response bodies.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
[[ -f "$KEY" ]] || { echo "STOP_SSH_KEY_MISSING"; exit 2; }

# This dependency list is intentionally explicit. The private Oracle CLI
# imports backend.bg_price_age_scope and backend.bg_private_source_crosswalk.
for name in \
  scripts/oracle_bg_selected_quote_probe.py \
  scripts/oracle_bg_preview_export.py \
  scripts/tour_price_reference.py \
  scripts/oracle_bg_price_detail_probe.py \
  scripts/oracle_bg_route_sync.py \
  scripts/select_future_preview.py \
  backend/bg_price_age_scope.py \
  backend/bg_private_source_crosswalk.py \
  destination-directory.json tour-previews.json; do
 [[ -f "$ROOT/$name" ]] || { echo "STOP_REQUIRED_FILE_MISSING"; exit 2; }
done

PREVIEW_ID="${1:-}"
ROOMS_FILE="${2:-}"
if [[ -z "$PREVIEW_ID" ]]; then
 PREVIEW_ID="$(python3 -B "$ROOT/scripts/select_future_preview.py" --feed "$ROOT/tour-previews.json")"
fi
[[ "$PREVIEW_ID" =~ ^p_[a-f0-9]{24}$ ]] || { echo "STOP_INVALID_PREVIEW_ID"; exit 2; }

# Optional age-only private file: no passports, names or exact birthdates.
# Its bytes are never passed as shell arguments or printed to stdout.
if [[ -n "$ROOMS_FILE" ]]; then
 python3 -B - "$ROOMS_FILE" <<'PY'
import json, os, stat, sys
path=sys.argv[1]
try:
    flags=os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):flags|=os.O_NOFOLLOW
    fd=os.open(path, flags)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
                or stat.S_IMODE(info.st_mode)&0o077
                or not 2<=info.st_size<=2048):
            raise ValueError("Private age file ownership, size or mode")
        data=json.loads(os.read(fd,2049))
    finally:
        os.close(fd)
    if (not isinstance(data,list) or not 1<=len(data)<=5 or any(
            not isinstance(r,dict) or set(r)!={"adults","child_ages"} or
            type(r["adults"]) is not int or not 1<=r["adults"]<=12 or
            not isinstance(r["child_ages"],list) or
            any(type(a) is not int or not 0<=a<=17
                for a in r["child_ages"])
            for r in data)):
        raise ValueError("Only non-identifying room-age groups are permitted")
except (OSError,ValueError,UnicodeError,TypeError,KeyError):
    raise SystemExit("STOP_PRIVATE_ROOM_FILE_INVALID") from None
PY
fi

SSH=(ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes \
     -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
SCP=(scp -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes \
     -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
REMOTE_TMP=""
cleanup(){
 if [[ "$REMOTE_TMP" =~ ^/tmp/jamaica-selection\.[[:alnum:]]+$ ]]; then
  "${SSH[@]}" "$REMOTE" "rm -rf -- '$REMOTE_TMP'" >/dev/null 2>&1 || true
 fi
}
trap cleanup EXIT
REMOTE_TMP="$("${SSH[@]}" "$REMOTE" 'umask 077; mktemp -d /tmp/jamaica-selection.XXXXXXXX')"
[[ "$REMOTE_TMP" =~ ^/tmp/jamaica-selection\.[[:alnum:]]+$ ]] || exit 2

# Preserve Python package structure: the old script staged only top-level
# scripts, so importing backend modules on a clean Oracle temp dir failed.
"${SSH[@]}" "$REMOTE" "umask 077; mkdir -p '$REMOTE_TMP/backend'"
"${SCP[@]}" \
 "$ROOT/scripts/oracle_bg_selected_quote_probe.py" \
 "$ROOT/scripts/oracle_bg_preview_export.py" \
 "$ROOT/scripts/tour_price_reference.py" \
 "$ROOT/scripts/oracle_bg_price_detail_probe.py" \
 "$ROOT/scripts/oracle_bg_route_sync.py" \
 "$ROOT/destination-directory.json" "$ROOT/tour-previews.json" \
 "$REMOTE:$REMOTE_TMP/"
"${SCP[@]}" "$ROOT/backend/bg_price_age_scope.py" \
 "$ROOT/backend/bg_private_source_crosswalk.py" \
 "$REMOTE:$REMOTE_TMP/backend/"

# Verify all imports before any authenticated operator query.
"${SSH[@]}" "$REMOTE" \
 "python3 -B '$REMOTE_TMP/oracle_bg_selected_quote_probe.py' --help >/dev/null"

echo "=== ORACLE BG SELECTED TOUR: READ ONLY ==="
if [[ -n "$ROOMS_FILE" ]]; then
 "${SCP[@]}" "$ROOMS_FILE" "$REMOTE:$REMOTE_TMP/private-rooms.json"
 "${SSH[@]}" "$REMOTE" "chmod 600 '$REMOTE_TMP/private-rooms.json'"
 "${SSH[@]}" "$REMOTE" \
  "python3 -B '$REMOTE_TMP/oracle_bg_selected_quote_probe.py' --directory '$REMOTE_TMP/destination-directory.json' --previews '$REMOTE_TMP/tour-previews.json' --preview-id '$PREVIEW_ID' --private-rooms-file '$REMOTE_TMP/private-rooms.json'"
else
 "${SSH[@]}" "$REMOTE" \
  "python3 -B '$REMOTE_TMP/oracle_bg_selected_quote_probe.py' --directory '$REMOTE_TMP/destination-directory.json' --previews '$REMOTE_TMP/tour-previews.json' --preview-id '$PREVIEW_ID'"
fi
