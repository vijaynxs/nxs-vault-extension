#!/usr/bin/env python3
"""NXS Vault extension publisher (runs on the vault server).

Fetches the latest NXS Vault build from GitHub, signs it as a Chrome .crx
with our own key and writes updates.xml, so Chrome (managed by Google
Workspace) installs and auto-updates the extension from our server.

Location: /opt/vaultwarden/ext-update.py   (run as root)
Cron:     15 * * * * /usr/bin/python3 /opt/vaultwarden/ext-update.py >> /opt/vaultwarden/ext-update.log 2>&1
Manual:   sudo python3 /opt/vaultwarden/ext-update.py --force

Signing key: /opt/vaultwarden/ext-key/nxs-vault.pem  (created on first run,
included in the encrypted daily backup). If this key is lost, the extension
gets a new ID and must be re-added in Google Admin.
"""
import hashlib, io, json, os, struct, subprocess, sys, tempfile, urllib.request, zipfile

REPO = "vijaynxs/nxs-vault-extension"
VW = "/opt/vaultwarden"
OUT = os.environ.get("EXT_OUT", VW + "/ext")
KEYDIR = os.environ.get("EXT_KEYDIR", VW + "/ext-key")
KEY = KEYDIR + "/nxs-vault.pem"
BASE_URL = "https://vault.nxsinfotech.com/ext"
UA = {"User-Agent": "nxs-vault-updater"}


def log(msg):
    print(subprocess.run(["date", "+%F %T"], capture_output=True, text=True).stdout.strip(), msg, flush=True)


def fetch(url, accept=None):
    h = dict(UA)
    if accept:
        h["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
        return r.read()


def varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            return out + bytes([b])


def field(num, data):  # length-delimited protobuf field
    return varint((num << 3) | 2) + varint(len(data)) + data


def ensure_key():
    os.makedirs(KEYDIR, mode=0o700, exist_ok=True)
    if not os.path.exists(KEY):
        subprocess.run(["openssl", "genrsa", "-out", KEY, "2048"], check=True, capture_output=True)
        os.chmod(KEY, 0o600)
        log("created new signing key " + KEY)


def public_der():
    return subprocess.run(["openssl", "rsa", "-in", KEY, "-pubout", "-outform", "DER"],
                          check=True, capture_output=True).stdout


def ext_id(pub):
    return "".join("abcdefghijklmnop"[int(c, 16)] for c in hashlib.sha256(pub).hexdigest()[:32])


def make_crx(zip_bytes, pub):
    crx_id = hashlib.sha256(pub).digest()[:16]
    signed_data = field(1, crx_id)
    msg = b"CRX3 SignedData\x00" + struct.pack("<I", len(signed_data)) + signed_data + zip_bytes
    with tempfile.NamedTemporaryFile() as f:
        f.write(msg)
        f.flush()
        sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", KEY, f.name],
                             check=True, capture_output=True).stdout
    header = field(2, field(1, pub) + field(2, sig)) + field(10000, signed_data)
    return b"Cr24" + struct.pack("<II", 3, len(header)) + header + zip_bytes


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main():
    force = "--force" in sys.argv
    local_zip = next((a for a in sys.argv[1:] if a.endswith(".zip")), None)
    os.makedirs(OUT, exist_ok=True)
    ensure_key()
    pub = public_der()
    eid = ext_id(pub)

    if local_zip:
        tag, zip_bytes = "local", open(local_zip, "rb").read()
    else:
        rel = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases/latest",
                               "application/vnd.github+json"))
        tag = rel["tag_name"]
        stamp = os.path.join(OUT, "release.txt")
        if not force and os.path.exists(stamp) and open(stamp).read().strip() == tag:
            return  # nothing new
        asset = next(a for a in rel["assets"]
                     if a["name"].startswith("nxs-vault-chrome") and a["name"].endswith(".zip"))
        zip_bytes = fetch(asset["browser_download_url"])

    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = z.namelist()
    prefix = ""
    if "manifest.json" not in names:  # zip has a top-level folder
        m = [n for n in names if n.endswith("/manifest.json") and n.count("/") == 1]
        if not m:
            raise SystemExit("manifest.json not found in release zip")
        prefix = m[0][: -len("manifest.json")]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as nz:
            for n in names:
                if n.startswith(prefix) and not n.endswith("/"):
                    nz.writestr(n[len(prefix):], z.read(n))
        zip_bytes = buf.getvalue()
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    manifest = json.loads(z.read("manifest.json").decode("utf-8-sig"))
    version = manifest["version"]

    write_atomic(os.path.join(OUT, "nxs-vault.crx"), make_crx(zip_bytes, pub))
    write_atomic(os.path.join(OUT, "nxs-vault-chrome.zip"), zip_bytes)
    xml = ("<?xml version='1.0' encoding='UTF-8'?>\n"
           "<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>\n"
           f"  <app appid='{eid}'>\n"
           f"    <updatecheck codebase='{BASE_URL}/nxs-vault.crx?v={version}' version='{version}' />\n"
           "  </app>\n</gupdate>\n")
    write_atomic(os.path.join(OUT, "updates.xml"), xml.encode())
    write_atomic(os.path.join(OUT, "info.json"),
                 json.dumps({"id": eid, "version": version, "release": tag,
                             "update_url": BASE_URL + "/updates.xml"}, indent=1).encode())
    write_atomic(os.path.join(OUT, "release.txt"), (tag + "\n").encode())
    log(f"published {tag} version {version} id {eid}")


if __name__ == "__main__":
    main()
