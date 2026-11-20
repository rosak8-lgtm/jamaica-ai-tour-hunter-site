#!/usr/bin/env bash
# Replaced by the independent Oracle server-side 5 minute publisher.
# Do not enable local Lenovo timers again. Existing timer is stopped by the
# one-time Oracle installer only after server first import succeeds.
set -Eeuo pipefail
echo "JAMAICA_LENOVO_REFRESH_INSTALLER=DEPRECATED"
echo "The production schedule belongs to Oracle every 5 minutes."
echo "Run once from the existing Lenovo checkout:"
echo "  bash scripts/deploy_oracle_5min_from_lenovo_once.sh"
echo "Existing Lenovo timer remains until Oracle installation is verified."
exit 2
