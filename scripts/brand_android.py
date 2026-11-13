#!/usr/bin/env python3
"""
NXS Vault branding for the open-source Bitwarden Android app (Password Manager).

Usage: python3 scripts/brand_android.py <path-to-bitwarden-android-source>
Env:   BUILD_NUMBER = GitHub run number (goes into the version)

What it changes:
1. Package id com.nxsinfotech.vault (never clashes with Bitwarden's own app) + our version
2. Server: every built-in region (US / EU / FedRAMP) points to https://vault.nxsinfotech.com
3. All texts in every language: "Bitwarden" -> "NXS Vault" (app name, autofill service, etc.)
4. Help / marketing links to bitwarden.com -> our vault Download & Help page
5. Logos and icons -> NXS logo (launcher icon, splash, in-app logo, notification icon)
6. Audit list of anything still mentioning Bitwarden (printed in the build log)

Safety: if an expected piece of code is missing (e.g. after a Bitwarden version change),
the script stops with "PATCH FAILED" so a broken app is never built.
"""
import os
import re
import sys
from pathlib import Path

NAME = "NXS Vault"
VAULT = "https://vault.nxsinfotech.com"
PKG = "com.nxsinfotech.vault"
LINK = VAULT + "/download/"
BUILD = int(os.environ.get("BUILD_NUMBER", "0") or 0)

SRC = Path(sys.argv[1]).resolve()
SKIP_PARTS = {"test", "androidTest", "testFixtures", "testharness", "authenticator", "build", ".git"}


def fail(msg):
    sys.exit("PATCH FAILED: " + msg)


def must_exist(rel):
    p = SRC / rel
    if not p.exists():
        fail(f"file not found: {rel}")
    return p


def patch(rel, old, new, count=1):
    p = must_exist(rel)
    t = p.read_text(encoding="utf-8")
    if old not in t:
        fail(f"pattern not found in {rel}: {old[:70]!r}")
    p.write_text(t.replace(old, new, count), encoding="utf-8")
    print("patched", rel)


def patch_re(rel, pattern, repl, min_count=1):
    p = must_exist(rel)
    t = p.read_text(encoding="utf-8")
    t2, n = re.subn(pattern, repl, t, flags=re.S | re.M)
    if n < min_count:
        fail(f"pattern found {n}x (need {min_count}) in {rel}: {pattern[:70]!r}")
    p.write_text(t2, encoding="utf-8")
    print(f"patched {rel} ({n}x)")


def source_files(suffixes):
    for f in SRC.rglob("*"):
        if f.is_file() and f.suffix in suffixes and not (set(f.relative_to(SRC).parts) & SKIP_PARTS):
            yield f


# 1. Package id + version --------------------------------------------------------------
patch("app/build.gradle.kts", 'applicationId = "com.x8bit.bitwarden"', f'applicationId = "{PKG}"')
toml = must_exist("gradle/libs.versions.toml")
t = toml.read_text(encoding="utf-8")
m_code = re.search(r'(appVersionCode\s*=\s*")(\d+)(")', t)
m_name = re.search(r'(appVersionName\s*=\s*")([^"]+)(")', t)
if not m_code or not m_name:
    fail("appVersionCode / appVersionName not found in gradle/libs.versions.toml")
code = int(m_code.group(2)) * 1000 + (BUILD % 1000)
vname = f"{m_name.group(2)} (NXS build {BUILD})"
t = t.replace(m_code.group(0), f"{m_code.group(1)}{code}{m_code.group(3)}", 1)
t = t.replace(m_name.group(0), f"{m_name.group(1)}{vname}{m_name.group(3)}", 1)
toml.write_text(t, encoding="utf-8")
print(f"version: {vname} (code {code}), package {PKG}")

# 2. Server: all built-in regions -> our vault -------------------------------------------
ENV = "data/src/main/kotlin/com/bitwarden/data/repository/util/EnvironmentExtensions.kt"
ours = {
    "API": VAULT + "/api",
    "EVENTS": VAULT + "/events",
    "IDENTITY": VAULT + "/identity",
    "WEB_VAULT": VAULT,
    "WEB_SEND": VAULT + "/#/send/",
    "ICON": VAULT + "/icons",
}
for kind, url in ours.items():
    patch_re(
        ENV,
        rf'(private const val DEFAULT_(?:US|EU|FED_RAMP)_{kind}_URL: String = )"[^"]*"',
        rf'\1"{url}"',
    )
patch_re(
    "data/src/main/kotlin/com/bitwarden/data/repository/model/Environment.kt",
    r'override val label: String get\(\) = "[^"]*"',
    'override val label: String get() = "vault.nxsinfotech.com"',
)
patch_re(
    "data/src/main/kotlin/com/bitwarden/data/datasource/disk/model/EnvironmentUrlDataJson.kt",
    r'(val DEFAULT_US: EnvironmentUrlDataJson =\s*EnvironmentUrlDataJson\(base = )"[^"]*"',
    rf'\1"{VAULT}"',
)

# 3. Texts in every language ---------------------------------------------------------------
word_rx = re.compile(r"Bitwarden(?![.\-](com|eu|net|pw|gov))")
link_rx = re.compile(
    r"https://(?:www\.)?bitwarden\.com"
    r"(?!/(?:[a-z-]*callback|redirect-connector|\.well-known))"
    r"(?:/[^\s\"'<>\\)]*)?"
)
ntexts = nfiles = 0
for f in source_files({".xml"}):
    if "/res/values" not in f.as_posix() or not f.name.startswith("strings"):
        continue
    t = f.read_text(encoding="utf-8")

    def fix_text(m):
        global ntexts
        inner = m.group(1)
        new = link_rx.sub(LINK, word_rx.sub(NAME, inner))
        if new != inner:
            ntexts += 1
        return ">" + new + "<"

    t2 = re.sub(r">([^<]*)<", fix_text, t)
    if t2 != t:
        f.write_text(t2, encoding="utf-8")
        nfiles += 1
print(f"texts changed: {ntexts} in {nfiles} string files")
if ntexts < 50:
    fail("too few texts changed - string files moved?")

# 4. Links in code -> our Download & Help page ------------------------------------------------
nlinks = 0
for f in source_files({".kt"}):
    t = f.read_text(encoding="utf-8", errors="ignore")
    t2, k = link_rx.subn(LINK, t)
    if k:
        f.write_text(t2, encoding="utf-8")
        nlinks += k
print(f"bitwarden.com links in code redirected to {LINK}: {nlinks}")

# 5. Logos and icons (vector drawables) -----------------------------------------------------
# NXS logo = two triangles (from the 512x512 NXS icon), point-symmetric.
TRI_LEFT = [(134, 114), (134, 490), (306, 314)]
TRI_RIGHT = [(376, 20), (376, 396), (206, 196)]
BOX = (134, 20, 376, 490)  # x0, y0, x1, y1


def tri_path(pts, scale, dx, dy):
    p = [(round(x * scale + dx, 3), round(y * scale + dy, 3)) for x, y in pts]
    return f"M{p[0][0]},{p[0][1]} L{p[1][0]},{p[1][1]} L{p[2][0]},{p[2][1]} Z"


def logo_paths(size_h, cx, cy, colors, names=("", "")):
    """Return <path> xml for the NXS logo, height size_h, centred on (cx, cy)."""
    s = size_h / (BOX[3] - BOX[1])
    w = (BOX[2] - BOX[0]) * s
    dx = cx - w / 2 - BOX[0] * s
    dy = cy - size_h / 2 - BOX[1] * s
    out = []
    for pts, col, nm in [(TRI_LEFT, colors[0], names[0]), (TRI_RIGHT, colors[1], names[1])]:
        name_attr = f' android:name="{nm}"' if nm else ""
        out.append(
            f'    <path{name_attr} android:fillColor="{col}" android:pathData="{tri_path(pts, s, dx, dy)}" />'
        )
    return "\n".join(out), w


def vector(w, h, body, vw=None, vh=None):
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!-- NXS Vault logo -->\n'
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
        f'    android:width="{w}dp" android:height="{h}dp"\n'
        f'    android:viewportWidth="{vw or w}" android:viewportHeight="{vh or h}">\n'
        f"{body}\n</vector>\n"
    )


def write_drawable(name, content):
    hits = [
        f for f in SRC.rglob(f"{name}.xml")
        if "/res/drawable" in f.as_posix() and not (set(f.relative_to(SRC).parts) & SKIP_PARTS)
    ]
    if not hits:
        fail(f"drawable {name}.xml not found")
    for f in hits:
        f.write_text(content, encoding="utf-8")
        print("logo replaced", f.relative_to(SRC))


IN_APP = ("#7D848D", "#A9AFB7")   # visible on light and dark screens
LAUNCH = ("#A7ADB5", "#E1E4E8")   # on dark launcher background
LAUNCHER_BG = "#1E2329"

# 5a. square app icon (autofill suggestions, credential export, etc.)
body, _ = logo_paths(860, 512, 512, IN_APP)
write_drawable("logo_bitwarden_icon", vector(1024, 1024, body))

# 5b. splash / shield icon (108dp adaptive area: keep inside the safe centre)
body, _ = logo_paths(60, 54, 54, LAUNCH)
write_drawable("logo_shield_icon", vector(108, 108, body))

# 5c. launcher icon foreground + monochrome (themed icons on Android 13+)
body, _ = logo_paths(58, 54, 54, LAUNCH)
write_drawable("ic_launcher_foreground", vector(108, 108, body))
body, _ = logo_paths(58, 54, 54, ("#000000", "#000000"))
write_drawable("ic_launcher_monochrome", vector(108, 108, body))
nbg = 0
for f in source_files({".xml"}):
    if "/res/values" not in f.as_posix():
        continue
    t = f.read_text(encoding="utf-8")
    t2, k = re.subn(r'(<color name="ic_launcher_background">)[^<]*(</color>)', rf"\1{LAUNCHER_BG}\2", t)
    if k:
        f.write_text(t2, encoding="utf-8")
        nbg += k
print("launcher background colour set:", nbg)

# 5d. notification icon (white silhouette, 24dp)
body, _ = logo_paths(20, 12, 12, ("#FFFFFF", "#FFFFFF"))
write_drawable("ic_notification", vector(24, 24, body))

# 5e. wordmark "NXS Vault" (login screen) - text drawn as glyph outlines
from fontTools.pens.svgPathPen import SVGPathPen  # noqa: E402
from fontTools.pens.transformPen import TransformPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

FONT = next(
    (p for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ] if Path(p).exists()),
    None,
)
if not FONT:
    fail("no bold font found for the wordmark")
font = TTFont(FONT)
glyphs = font.getGlyphSet()
cmap = font.getBestCmap()
upm = font["head"].unitsPerEm
H = 34
em = 27.0
scale = em / upm
x = 24.0
baseline = 26.0
cmds = []
for ch in NAME:
    g = glyphs[cmap[ord(ch)]]
    pen = SVGPathPen(glyphs)
    g.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
    c = pen.getCommands()
    if c:
        cmds.append(c)
    x += g.width * scale
W = int(x + 2)
icon_body, _ = logo_paths(32, 9.5, 17, IN_APP)
text_body = f'    <path android:name="logo" android:fillColor="#175DDC" android:pathData="{" ".join(cmds)}" />'
write_drawable("logo_bitwarden", vector(W, H, icon_body + "\n" + text_body))
print(f"wordmark drawn with {Path(FONT).name}, {W}x{H}")

# 6. Audit (review in the build log) ------------------------------------------------------------
print("---- audit: default-language texts still containing 'Bitwarden' ----")
shown = 0
for f in source_files({".xml"}):
    if not f.as_posix().endswith("/res/values/strings.xml"):
        continue
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r">[^<]*Bitwarden[^<]*<", line) and shown < 40:
            print(f"{f.relative_to(SRC)}:{i}: {line.strip()[:140]}")
            shown += 1
print("---- audit: code literals mentioning bitwarden.com / x8bit package ----")
shown = 0
for f in source_files({".kt"}):
    for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if re.search(r'"[^"]*(bitwarden\.com|"com\.x8bit\.bitwarden")[^"]*"', line) and shown < 60:
            print(f"{f.relative_to(SRC)}:{i}: {line.strip()[:140]}")
            shown += 1
print("---- end of audit ----")
print("NXS Vault Android branding complete")
