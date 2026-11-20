#!/usr/bin/env bash
# User-local 15-minute refresh timer. No root, no changes to existing timers.
# Laptop must remain online; timer does not bypass operator rate limits.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="rosak8-lgtm/jamaica-ai-tour-hunter-site"
KEY="$HOME/.ssh/jamaica-oracle.key"
UNIT="jamaica-tour-catalog-refresh"
command -v systemctl >/dev/null || { echo "STOP_SYSTEMD_MISSING"; exit 2; }
command -v flock >/dev/null || { echo "STOP_FLOCK_MISSING"; exit 2; }
command -v gh >/dev/null || { echo "STOP_GH_MISSING"; exit 2; }
test -r "$KEY" || { echo "STOP_ORACLE_SSH_KEY_MISSING"; exit 2; }
test "$(gh api user --jq .login)" = "rosak8-lgtm" || {
 echo "STOP_GITHUB_WRONG_USER"; exit 2;
}
test -f "$ROOT/scripts/sync_tour_previews_from_lenovo.sh" || {
 echo "STOP_JAMAICA_SYNC_SCRIPT_MISSING"; exit 2;
}
command -v ssh >/dev/null || { echo "STOP_SSH_MISSING"; exit 2; }
systemctl --user status >/dev/null 2>&1 || {
 echo "STOP_SYSTEMD_USER_MANAGER_UNAVAILABLE"; exit 2;
}
mkdir -p "$HOME/.config/systemd/user"
SERVICE="$HOME/.config/systemd/user/$UNIT.service"
TIMER="$HOME/.config/systemd/user/$UNIT.timer"
cat > "$SERVICE" <<EOF
[Unit]
Description=JAMAICA verified source price list refresh and GitHub Pages catalog
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
ExecStart=/bin/bash "$ROOT/scripts/run_catalog_refresh_locked.sh"
TimeoutStartSec=12min
EOF
cat > "$TIMER" <<EOF
[Unit]
Description=Check and publish JAMAICA tour listings every 15 minutes

[Timer]
OnCalendar=*-*-* *:00/15:00
AccuracySec=1min
Persistent=true
Unit=$UNIT.service

[Install]
WantedBy=timers.target
EOF
chmod 600 "$SERVICE" "$TIMER"
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT.timer"
echo "JAMAICA_PRICE_REFRESH_SCHEDULE=15_MINUTES"
echo "JAMAICA_REFRESH_TIMER_ACTIVE=$(systemctl --user is-active "$UNIT.timer")"
systemctl --user list-timers --all "$UNIT.timer"
echo "JAMAICA_REFRESH_HOST=LENOVO"
echo "JAMAICA_REFRESH_WHEN_OFFLINE=NOT_POSSIBLE"
echo "JAMAICA_REFRESH_NOTE=User systemd manager must remain active; verify loginctl show-user."
