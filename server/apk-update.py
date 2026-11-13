#!/usr/bin/env python3
"""NXS Vault Android publisher (runs on the vault server).

Fetches the newest NXS Vault Android build (unsigned APK) from GitHub, signs it with
our own key and publishes it at https://vault.nxsinfotech.com/ext/nxs-vault.apk

Location: /opt/vaultwarden/apk-update.py   (run as root)
Cron:     20 * * * * /usr/bin/python3 /opt/vaultwarden/apk-update.py >> /opt/vaultwarden/apk-update.log 2>&1
Manual:   sudo python3 /opt/vaultwarden/apk-update.py --force

Signing key: /opt/vaultwarden/ext-key/nxs-android.jks (+ .pass), created on first run and
included in the encrypted daily backup. If this key is lost, phones cannot get updates
(the app would have to be removed and installed again on every phone).
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import urllib.request

REPO = "vijaynxs/nxs-vault-extension"
VW = "/opt/vaultwarden"
OUT = VW + "/ext"
KEYDIR = VW + "/ext-key"
KS = KEYDIR + "/nxs-android.jks"
KSPASS = KEYDIR + "/nxs-android.pass"
ALIAS = "nxsvault"
ASSET = "nxs-vault-android-unsigned.apk"
UA = {"User-Agent": "nxs-vault-updater", "Accept": "application/vnd.github+json"}


def log(msg):
    print(subprocess.run(["date", "+%F %T"], capture_output=True, text=True).stdout.strip(), msg, flush=True)


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        return r.read()


def ensure_key():
    os.makedirs(KEYDIR, mode=0o700, exist_ok=True)
    if os.path.exists(KS):
        return
    pw = secrets.token_urlsafe(32)
    with open(KSPASS, "w") as f:
        f.write(pw + "\n")
    os.chmod(KSPASS, 0o600)
    subprocess.run(
        ["keytool", "-genkeypair", "-keystore", KS, "-storetype", "PKCS12", "-alias", ALIAS,
         "-keyalg", "RSA", "-keysize", "4096", "-validity", "36500",
         "-dname", "CN=NXS Vault, O=NXS Infotech Private Limited, C=IN",
         "-storepass:file", KSPASS, "-keypass:file", KSPASS],
        check=True, capture_output=True,
    )
    os.chmod(KS, 0o600)
    log("created new Android signing key " + KS)


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    ensure_key()
    releases = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases?per_page=30"))
    rel = next(
        (r for r in releases
         if r["tag_name"].startswith("android-") and not r.get("draft")
         and any(a["name"] == ASSET for a in r["assets"])),
        None,
    )
    if not rel:
        log("no Android release found yet")
        return
    tag = rel["tag_name"]
    stamp = os.path.join(OUT, "android-release.txt")
    if not force and os.path.exists(stamp) and open(stamp).read().strip() == tag:
        return  # nothing new
    url = next(a["browser_download_url"] for a in rel["assets"] if a["name"] == ASSET)
    with tempfile.TemporaryDirectory() as d:
        unsigned = os.path.join(d, "unsigned.apk")
        signed = os.path.join(d, "signed.apk")
        with open(unsigned, "wb") as f:
            f.write(fetch(url))
        subprocess.run(
            ["apksigner", "sign", "--ks", KS, "--ks-key-alias", ALIAS,
             "--ks-pass", "file:" + KSPASS, "--key-pass", "file:" + KSPASS,
             "--out", signed, unsigned],
            check=True,
        )
        subprocess.run(["apksigner", "verify", signed], check=True)
        badging = subprocess.run(["apksigner", "verify", "--print-certs", signed],
                                 capture_output=True, text=True).stdout
        sha = next((ln.split(":", 1)[1].strip() for ln in badging.splitlines()
                    if "SHA-256 digest" in ln), "")
        write_atomic(os.path.join(OUT, "nxs-vault.apk"), open(signed, "rb").read())
    info = {"release": tag, "apk": "https://vault.nxsinfotech.com/ext/nxs-vault.apk",
            "signing_cert_sha256": sha}
    write_atomic(os.path.join(OUT, "android-info.json"), json.dumps(info, indent=1).encode())
    write_atomic(stamp, (tag + "\n").encode())
    log(f"published Android {tag}")


if __name__ == "__main__":
    main()
