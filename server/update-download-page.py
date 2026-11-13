#!/usr/bin/env python3
"""Adds the Android app + automatic Chrome install notes to the vault Download & Help page.
Run on the vault server:  sudo python3 /opt/vaultwarden/update-download-page.py
Safe to run again. Updates download-page/ (source) and branding/download/ (live copy)."""
import os
import shutil
import time

ANDROID = (
    '<div class="card"><h2>NXS Vault for Android</h2>'
    "<p>On your Android phone (Android 10 or newer): tap the button, open the downloaded file and "
    "allow &quot;Install unknown apps&quot; once if asked. Then log in with your work email, master "
    "password and 2FA code.</p>"
    '<p><a class="btn" href="/ext/nxs-vault.apk">Download Android app</a></p>'
    "<p>Turn on autofill: phone Settings &gt; Passwords &gt; Autofill service &gt; NXS Vault.</p></div>\n"
)
CHROME_NOTE = (
    "<p><b>Work Chrome:</b> nothing to install. Sign in to Chrome with your @nxsinfotech.com "
    "account and NXS Vault installs itself and stays updated. The download below is only for "
    "other browsers or testing.</p>"
)
HELP = '<div class="card"><h2>Help</h2>'
CHROME_H2 = "<h2>Install the NXS Vault extension (Chrome / Edge)</h2>"

for path in ["/opt/vaultwarden/download-page/index.html", "/opt/vaultwarden/branding/download/index.html"]:
    try:
        s = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        continue
    orig = s
    if "/ext/nxs-vault.apk" not in s:
        if HELP not in s:
            raise SystemExit(f"Help card not found in {path}")
        s = s.replace(HELP, ANDROID + HELP, 1)
    if "Work Chrome:" not in s and CHROME_H2 in s:
        s = s.replace(CHROME_H2, CHROME_H2 + CHROME_NOTE, 1)
    if s != orig:
        os.makedirs("/opt/vaultwarden/page-backups", exist_ok=True)
        shutil.copy2(path, "/opt/vaultwarden/page-backups/" + path.split("/")[-2] + "-index.html." + time.strftime("%Y%m%d%H%M"))
        open(path, "w", encoding="utf-8").write(s)
        print("updated", path)
    else:
        print("already up to date", path)
