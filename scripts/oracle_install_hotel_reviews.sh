#!/usr/bin/env bash
# Install PRIVATE hotel reviews API on existing Oracle server. Loopback only.
# This does NOT expose a public HTTPS endpoint or enable GitHub Pages form.
# An HTTPS reverse proxy / DNS and verified API connectivity are required next.
set -Eeuo pipefail
umask 077

[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP_ORACLE_UBUNTU_ONLY"; exit 2; }
ROOT="$HOME/.local/share/jamaica-oracle-catalog/site"
[[ -r "$ROOT/backend/hotel_reviews_api.py" &&
   -r "$ROOT/backend/hotel_reviews_store.py" &&
   -r "$ROOT/destination-directory.json" ]] || {
 echo "STOP_ORACLE_CODE_MISSING_SYNC_GITHUB_FIRST"; exit 2; }
for cmd in python3 systemctl loginctl;do
  command -v "$cmd" >/dev/null||{ echo "STOP_MISSING_COMMAND=$cmd"; exit 2; }
done
STATE="$HOME/.local/share/jamaica-hotel-reviews"
CONF="$HOME/.config/jamaica"
mkdir -p "$STATE" "$CONF" "$HOME/.config/systemd/user"
chmod 700 "$STATE" "$CONF"
ENV_FILE="$CONF/reviews.env"
if [[ ! -f "$ENV_FILE" ]];then
  secret="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
  printf 'JAMAICA_REVIEW_HASH_SECRET=%s\n' "$secret" > "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
UNIT="$HOME/.config/systemd/user/jamaica-hotel-reviews-api.service"
cat > "$UNIT" <<EOF
[Unit]
Description=JAMAICA private moderated hotel reviews API (localhost only)
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 -B -m backend.hotel_reviews_api --db $STATE/reviews.sqlite --directory $ROOT/destination-directory.json --port 18778
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
TimeoutStartSec=25

[Install]
WantedBy=default.target
EOF
chmod 600 "$UNIT"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
# The installer can be invoked from any folder via SSH. Python modules must
# resolve against the actual verified repository root.
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python3 -B -m unittest backend.test_hotel_reviews -v
systemctl --user daemon-reload
systemctl --user enable --now jamaica-hotel-reviews-api.service
[[ "$(systemctl --user is-active jamaica-hotel-reviews-api.service)" == "active" ]] || {
 echo "STOP_PRIVATE_REVIEW_API_NOT_ACTIVE"; exit 2; }
python3 -B - <<'PY'
from urllib.request import urlopen
from urllib.error import HTTPError
import json
from pathlib import Path
d=json.loads(Path.home().joinpath(".local/share/jamaica-oracle-catalog/site/destination-directory.json").read_text())
hotel=next(h["id"] for h in d["hotels"] if h.get("id"))
with urlopen("http://127.0.0.1:18778/v1/hotels/"+hotel+"/reviews",timeout=8) as res:
    if res.status!=200:raise RuntimeError("API_LOCAL_GET_FAILED")
    data=json.load(res)
    if data.get("schema")!="jamaica.hotel-reviews.v1":raise RuntimeError("API_SCHEMA_FAILED")
print("JAMAICA_HOTEL_REVIEWS_LOCAL_API_TEST=PASS")
PY
echo "JAMAICA_HOTEL_REVIEWS_PRIVATE_SERVICE=active"
echo "JAMAICA_HOTEL_REVIEWS_DATABASE=PRIVATE_SQLITE"
echo "JAMAICA_HOTEL_REVIEWS_PUBLIC_HTTPS=NOT_CONFIGURED"
echo "JAMAICA_HOTEL_REVIEWS_UI_ENABLED=NO"
echo "NEXT=Configure a verified HTTPS reverse proxy to http://127.0.0.1:18778 and then update hotel-reviews-config.json"
