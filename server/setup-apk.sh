#!/usr/bin/env bash
# One-time setup: sign and publish the NXS Vault Android app from vault.nxsinfotech.com
# Run on the vault server:  sudo bash /opt/vaultwarden/setup-apk.sh
# Safe to run again (each change is skipped if already done).
set -euo pipefail
VW=/opt/vaultwarden
cd "$VW"
TS=$(date +%Y%m%d%H%M)

echo "== 1. Install apksigner (free Android signing tool)"
if ! command -v apksigner >/dev/null; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq apksigner >/dev/null
fi
apksigner --version

echo "== 2. Download publisher script"
curl -fsSL -o apk-update.py https://raw.githubusercontent.com/vijaynxs/nxs-vault-extension/main/server/apk-update.py
chmod 700 apk-update.py

echo "== 3. Serve .apk files with the Android file type"
if ! grep -q 'nxs-vault.apk' Caddyfile; then
  cp -a Caddyfile "Caddyfile.bak-apk-$TS"
  python3 - <<'PY'
p = "/opt/vaultwarden/Caddyfile"
s = open(p).read()
old = "\t\theader /nxs-vault.crx Content-Type application/x-chrome-extension\n"
if old not in s:
    raise SystemExit("crx header line not found in Caddyfile")
new = old + "\t\theader /nxs-vault.apk Content-Type application/vnd.android.package-archive\n"
with open(p, "w") as f:  # same file (inode) so the Caddy bind mount sees it
    f.write(s.replace(old, new, 1))
PY
  docker exec caddy caddy reload --config /etc/caddy/Caddyfile
fi
grep -n 'nxs-vault.apk' Caddyfile

echo "== 4. Check for new Android builds every hour"
if ! crontab -l 2>/dev/null | grep -q apk-update.py; then
  (crontab -l 2>/dev/null; echo "20 * * * * /usr/bin/python3 $VW/apk-update.py >> $VW/apk-update.log 2>&1") | crontab -
fi
crontab -l | grep apk-update

echo "== 5. Create signing key (first run) and publish the newest build"
python3 apk-update.py --force
ls -l ext/ ext-key/
cat ext/android-info.json 2>/dev/null; echo
curl -fsSI https://vault.nxsinfotech.com/ext/nxs-vault.apk | grep -iE 'HTTP|content-type|content-length' || true
echo "== DONE"
