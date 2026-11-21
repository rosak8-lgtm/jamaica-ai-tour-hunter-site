#!/usr/bin/env bash
# Run ON ORACLE after obtaining genuine HBX commercial media permission,
# an independently validated BG-HBX hotel-ID map, and HBX credentials.
# No keys, photos, passwords or private mappings are copied into this repo.
set -Eeuo pipefail
umask 077
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP_ORACLE_UBUNTU_REQUIRED"; exit 2; }
ROOT="$(cd "$(dirname "$0")" && pwd)"
PRIV="$HOME/.config/jamaica-hbx"
LOCK="$HOME/.cache/jamaica-oracle-catalog/refresh.lock"
SERVICE="jamaica-hbx-hotel-media-daily"
for command in python3 git flock systemctl; do
 command -v "$command" >/dev/null || { echo "STOP_REQUIRED_TOOL=$command"; exit 2; }
done
[[ -r "$ROOT/hbx_licensed_hotel_photos.py" &&
   -r "$ROOT/oracle_hbx_media_sync.py" ]] || {
 echo "STOP_LATEST_PHOTO_ADAPTER_NOT_INSTALLED"; exit 2; }
for file in "$PRIV/grant.json" "$PRIV/crosswalk.json" "$PRIV/credentials.env"; do
 [[ -f "$file" && ! -L "$file" ]] || {
  echo "STOP_PRIVATE_HBX_GRANT_MAPPING_OR_CREDENTIALS_MISSING"; exit 2; }
 [[ "$(stat -c '%a' "$file")" == "600" ]] || {
  echo "STOP_HBX_PRIVATE_FILES_MUST_BE_600"; exit 2; }
done
[[ "$(stat -c '%a' "$PRIV")" == "700" ]] || {
 echo "STOP_HBX_PRIVATE_DIRECTORY_MUST_BE_700"; exit 2; }
# An actual license must already exist. Never generate a fake approval.
python3 -B - "$ROOT" "$PRIV" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from hbx_licensed_hotel_photos import license_gate
grant=json.loads((Path(sys.argv[2])/"grant.json").read_text())
license_gate(grant)
print("JAMAICA_HBX_WRITTEN_MEDIA_LICENSE=VERIFIED")
PY
mkdir -p "$HOME/.config/systemd/user" "$(dirname "$LOCK")"
chmod 700 "$(dirname "$LOCK")"
cat > "$HOME/.config/systemd/user/$SERVICE.service" <<EOF
[Unit]
Description=JAMAICA licensed HBX hotel photographs with exact crosswalk, read-only Content API
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile=$PRIV/credentials.env
ExecStart=/usr/bin/flock -n $LOCK /usr/bin/python3 -B $ROOT/oracle_hbx_media_sync.py
TimeoutStartSec=55min
NoNewPrivileges=true

EOF
cat > "$HOME/.config/systemd/user/$SERVICE.timer" <<EOF
[Unit]
Description=Daily permitted hotel photo metadata import (not reservations)

[Timer]
OnCalendar=*-*-* 02:30:00 UTC
AccuracySec=5min
Persistent=true
Unit=$SERVICE.service

[Install]
WantedBy=timers.target

EOF
chmod 600 "$HOME/.config/systemd/user/$SERVICE.service" \
 "$HOME/.config/systemd/user/$SERVICE.timer"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[[ -d "$XDG_RUNTIME_DIR" ]] || { echo "STOP_ORACLE_USER_SYSTEMD_UNAVAILABLE"; exit 2; }
systemctl --user daemon-reload
# Publish only after the first real authenticated, licensed import succeeds.
if ! systemctl --user start "$SERVICE.service"; then
 echo "STOP_HBX_FIRST_LICENSED_IMPORT_FAILED"; exit 2; fi
[[ "$(systemctl --user show "$SERVICE.service" -p Result --value)" == "success" ]] || {
 echo "STOP_HBX_FIRST_IMPORT_NOT_SUCCESSFUL"; exit 2; }
systemctl --user enable --now "$SERVICE.timer"
[[ "$(systemctl --user is-active "$SERVICE.timer")" == "active" ]] || {
 echo "STOP_HBX_DAILY_TIMER_NOT_ACTIVE"; exit 2; }
echo "JAMAICA_HBX_HOTEL_MEDIA_CONNECTOR=ENABLED_WITH_VALID_WRITTEN_GRANT"
echo "JAMAICA_HBX_HOTEL_MEDIA_INTERVAL=DAILY"
echo "JAMAICA_HBX_PHOTO_BYTES_COPIED_TO_ORACLE=0"
echo "JAMAICA_HBX_BOOKING_OR_PAYMENT_OPERATIONS=0"
