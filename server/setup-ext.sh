#!/usr/bin/env bash
# One-time setup: self-hosted NXS Vault extension updates on vault.nxsinfotech.com
# Run on the vault server:  sudo bash /opt/vaultwarden/setup-ext.sh
# Safe to run again (each change is skipped if already done). Backups: *.bak-ext-<time>
set -euo pipefail
VW=/opt/vaultwarden
cd "$VW"
TS=$(date +%Y%m%d%H%M)

echo "== 1. Download publisher script"
curl -fsSL -o ext-update.py https://raw.githubusercontent.com/vijaynxs/nxs-vault-extension/main/server/ext-update.py
chmod 700 ext-update.py
mkdir -p ext ext-key
chmod 700 ext-key

echo "== 2. Mount ./ext into Caddy (docker-compose.yml)"
if ! grep -q '/srv/ext' docker-compose.yml; then
  cp -a docker-compose.yml "docker-compose.yml.bak-ext-$TS"
  sed -i 's#^\([[:space:]]*\)- ./branding:/srv/branding:ro#&\n\1- ./ext:/srv/ext:ro#' docker-compose.yml
fi
grep -n '/srv/ext' docker-compose.yml

echo "== 3. Serve https://vault.nxsinfotech.com/ext/ (Caddyfile)"
if ! grep -q 'handle_path /ext/' Caddyfile; then
  cp -a Caddyfile "Caddyfile.bak-ext-$TS"
  python3 - <<'PY'
import re
p = "/opt/vaultwarden/Caddyfile"
s = open(p).read()
m = re.search(r"^[ \t]*redir /download", s, re.M) or re.search(r"^[ \t]*reverse_proxy", s, re.M)
block = ("\thandle_path /ext/* {\n"
         "\t\troot * /srv/ext\n"
         "\t\theader Cache-Control \"no-cache\"\n"
         "\t\theader /nxs-vault.crx Content-Type application/x-chrome-extension\n"
         "\t\tfile_server\n"
         "\t}\n\n")
with open(p, "w") as f:  # same file (inode) so the Caddy bind mount sees it
    f.write(s[:m.start()] + block + s[m.start():])
PY
fi
grep -n -A5 'handle_path /ext/' Caddyfile

echo "== 4. Include signing key in the encrypted daily backup"
if ! grep -q 'ext-key' backup.sh; then
  cp -a backup.sh "backup.sh.bak-ext-$TS"
  sed -i 's#^tar -czf#cp -a "$VW_DIR/ext-key" "$TMP/" 2>/dev/null || true\n&#' backup.sh
fi
grep -n 'ext-key' backup.sh

echo "== 5. Point the download page to the new zip location"
for f in download-page/index.html branding/download/index.html; do
  [ -f "$f" ] && sed -i 's#/download/nxs-vault-chrome\.zip#/ext/nxs-vault-chrome.zip#g' "$f" && grep -c '/ext/nxs-vault-chrome.zip' "$f" || true
done

echo "== 6. Publish latest build (creates signing key on first run)"
python3 ext-update.py --force
cat ext/info.json; echo

echo "== 7. Check for new builds every hour"
if ! crontab -l 2>/dev/null | grep -q ext-update.py; then
  (crontab -l 2>/dev/null; echo "15 * * * * /usr/bin/python3 $VW/ext-update.py >> $VW/ext-update.log 2>&1") | crontab -
fi
crontab -l | grep ext-update

echo "== 8. Restart Caddy with the new folder"
docker compose up -d caddy
sleep 5
curl -fsS https://vault.nxsinfotech.com/ext/updates.xml
curl -fsSI https://vault.nxsinfotech.com/ext/nxs-vault.crx | grep -iE 'HTTP|content-type|content-length'
echo "== DONE"
