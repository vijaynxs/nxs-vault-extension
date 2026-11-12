#!/usr/bin/env python3
"""
NXS Vault branding for the open-source Bitwarden browser extension.

Usage:  python scripts/brand.py <path-to-bitwarden-clients-source>

What it changes:
  1. Server is locked to our own vault (re-applied on every start if changed)
  2. Install welcome page opens our vault instead of bitwarden.com
  3. Manifest: short name, author, homepage, toolbar title
  4. All interface texts (all languages): "Bitwarden" -> "NXS Vault" (web addresses untouched)
  5. All toolbar / extension icons -> NXS icon (normal, gray = logged out, locked)

Safety: if an expected piece of code is missing (e.g. after a Bitwarden version change),
the script stops with "PATCH FAILED" so a broken extension is never built.
"""
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

NAME = "NXS Vault"
VAULT = "https://vault.nxsinfotech.com"
ICON_URL = "https://nxsinfotech.com/wp-content/uploads/2023/06/NXS-infotech-icon.webp"

SRC = Path(sys.argv[1]).resolve()
APP = SRC / "apps" / "browser"


def patch(rel, old, new):
    p = SRC / rel
    text = p.read_text(encoding="utf-8")
    if old not in text:
        sys.exit(f"PATCH FAILED: pattern not found in {rel}: {old[:70]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched", rel)


# 1. Lock the server to our vault -------------------------------------------
patch(
    "apps/browser/src/platform/services/browser-environment.service.ts",
    "getManagedEnvironment(): Promise<GroupPolicyEnvironment> {",
    "getManagedEnvironment(): Promise<GroupPolicyEnvironment> {\n"
    "    // NXS Vault: the server is always our own vault\n"
    f'    return Promise.resolve({{ base: "{VAULT}" }} as GroupPolicyEnvironment);\n'
    "  }\n\n"
    "  originalGetManagedEnvironment(): Promise<GroupPolicyEnvironment> {",
)
patch(
    "apps/browser/src/background/runtime.background.ts",
    "void this.autofillService.loadAutofillScriptsOnInstall();",
    "void this.autofillService.loadAutofillScriptsOnInstall();\n\n"
    "      // NXS Vault: put our server back if it was changed\n"
    "      if (await this.environmentService.settingsHaveChanged()) {\n"
    "        await this.environmentService.setUrlsToManagedEnvironment();\n"
    "      }",
)

# 2. Welcome page ---------------------------------------------------------------
patch(
    "apps/browser/src/platform/services/browser-initial-install.service.ts",
    '"https://bitwarden.com/browser-start/"',
    f'"{VAULT}/"',
)

# 3. Manifest ---------------------------------------------------------------------
for mf in ["manifest.json", "manifest.v3.json"]:
    p = APP / "src" / mf
    if not p.exists():
        continue
    m = json.loads(p.read_text(encoding="utf-8"))
    m["short_name"] = NAME
    m["author"] = "NXS Infotech"
    m["homepage_url"] = VAULT
    for key in ["action", "browser_action", "__firefox__sidebar_action", "__opera__sidebar_action"]:
        if isinstance(m.get(key), dict):
            m[key]["default_title"] = NAME
    p.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("patched manifest", mf)

# 4. Interface texts (all languages) -----------------------------------------------
rx = re.compile(r"Bitwarden(?![.](com|eu|net))")
changed = 0
for f in sorted((APP / "src" / "_locales").glob("*/messages.json")):
    data = json.loads(f.read_text(encoding="utf-8"))
    for key, val in data.items():
        if isinstance(val, dict) and isinstance(val.get("message"), str):
            new = NAME if key == "extName" else rx.sub(NAME, val["message"])
            if new != val["message"]:
                val["message"] = new
                changed += 1
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("texts changed:", changed)

# 5. Icons ------------------------------------------------------------------------------
raw = urllib.request.urlopen(ICON_URL, timeout=60).read()
src = Image.open(io.BytesIO(raw)).convert("RGBA")
box = src.getchannel("A").point(lambda a: 255 if a > 10 else 0).getbbox() or src.getbbox()
src = src.crop(box)
w, h = src.size
s = int(max(w, h) * 1.05)
square = Image.new("RGBA", (s, s), (0, 0, 0, 0))
square.paste(src, ((s - w) // 2, (s - h) // 2), src)


def make_gray(img):
    g = ImageOps.grayscale(img.convert("RGB")).convert("RGBA")
    g.putalpha(img.getchannel("A"))
    return ImageEnhance.Brightness(g).enhance(0.75)


def add_lock(img):
    img = img.copy()
    d = ImageDraw.Draw(img)
    W = img.size[0]
    r = W * 0.45
    x0, y0 = W - r, W - r
    col = (40, 40, 40, 255)
    d.rounded_rectangle([x0, y0 + r * 0.42, W - 1, W - 1], radius=max(1, int(r * 0.15)), fill=col)
    d.arc([x0 + r * 0.22, y0, W - 1 - r * 0.22, y0 + r * 0.8], 180, 360, fill=col, width=max(1, int(r * 0.16)))
    return img


count = 0
for f in sorted((APP / "src" / "images").glob("icon*.png")):
    m = re.match(r"icon(\d+)(_gray|_locked)?(_gray)?(_beta)?\.png$", f.name)
    if not m:
        continue
    size = Image.open(f).size[0]
    icon = square.resize((size, size), Image.LANCZOS)
    if "_gray" in f.name:
        icon = make_gray(icon)
    if "_locked" in f.name:
        icon = add_lock(icon)
    icon.save(f)
    count += 1
print("icons replaced:", count)
print("NXS Vault branding applied OK")
