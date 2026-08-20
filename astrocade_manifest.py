#!/usr/bin/env python3
# ==================================================================
# astrocade_manifest.py
#
# Run this INSIDE the parent folder of your project. It walks that
# folder and every sub-folder, catalogues every file, and writes
# astrocade-manifest.json into the SAME parent folder.
#
# Zero dependencies. Python 3.7+.
#
#   python astrocade_manifest.py                 # catalogue "."
#   python astrocade_manifest.py ./wolf3d        # catalogue a sub-folder
#   python astrocade_manifest.py --out=manifest.json
#   python astrocade_manifest.py --no-hash       # faster, skip sha256
# ==================================================================

import os
import sys
import json
import hashlib
import subprocess
import datetime
import urllib.parse

FALLBACK_REPO_URL = "https://github.com/OWNER/REPO"
FALLBACK_BRANCH = "main"

OUT_NAME = "astrocade-manifest.json"
NO_HASH = False
TARGET = "."

for arg in sys.argv[1:]:
    if arg.startswith("--out="):
        OUT_NAME = arg.split("=", 1)[1]
    elif arg in ("--no-hash", "--hash=off"):
        NO_HASH = True
    elif not arg.startswith("-"):
        TARGET = arg

ROOT = os.path.abspath(TARGET)
OUT_PATH = os.path.join(ROOT, OUT_NAME)   # manifest lands in the same parent folder

SKIP_DIRS = {".git", "node_modules", ".github", ".vscode", ".idea",
             ".cache", "dist", "build", "coverage", "__pycache__", ".venv", "venv"}
SKIP_FILES = {".DS_Store", "Thumbs.db", OUT_NAME}
MAX_HASH_BYTES = 64 * 1024 * 1024

MIME = {
    ".html": "text/html", ".htm": "text/html",
    ".js": "application/javascript", ".mjs": "application/javascript",
    ".ts": "application/typescript", ".json": "application/json",
    ".css": "text/css", ".md": "text/markdown", ".txt": "text/plain",
    ".py": "text/x-python",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav",
    ".m4a": "audio/mp4", ".mid": "audio/midi",
    ".mp4": "video/mp4", ".webm": "video/webm",
    ".ttf": "font/ttf", ".otf": "font/otf",
    ".woff": "font/woff", ".woff2": "font/woff2",
    ".zip": "application/zip", ".wasm": "application/wasm",
}
DEFAULT_MIME = "application/octet-stream"

CATEGORIES = [
    ({".html", ".htm"}, "entry-html"),
    ({".js", ".mjs", ".ts", ".wasm", ".py"}, "code"),
    ({".css"}, "style"),
    ({".json", ".xml", ".csv"}, "data"),
    ({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}, "image"),
    ({".mp3", ".ogg", ".wav", ".m4a", ".mid"}, "audio"),
    ({".mp4", ".webm"}, "video"),
    ({".ttf", ".otf", ".woff", ".woff2"}, "font"),
    ({".wad", ".wl6", ".wl1", ".sod", ".sdm", ".vswap", ".gamemaps",
      ".audiot", ".vgagraph", ".vgadict", ".vgahead", ".maphead",
      ".dat", ".bin", ".pk3", ".zip"}, "game-data"),
    ({".md", ".txt", ".license"}, "doc"),
]


def category_of(ext, stem):
    if stem.lower() in ("license", "readme"):
        return "doc"
    for exts, name in CATEGORIES:
        if ext in exts:
            return name
    return "other"


def git(*args):
    try:
        out = subprocess.check_output(("git",) + args, cwd=ROOT,
                                      stderr=subprocess.DEVNULL)
        return out.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def parse_remote(url):
    if not url:
        return None
    import re
    m = re.search(r"github\.com[:/]+([^/]+)/(.+?)(?:\.git)?$", url, re.I)
    if not m:
        return None
    return {"owner": m.group(1), "name": m.group(2)}


def sha256_of(path, size):
    if NO_HASH or size > MAX_HASH_BYTES:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- walk ---------------------------------------------------------
dirs = []
files = []

for cur_abs, subdirs, filenames in os.walk(ROOT):
    subdirs[:] = sorted(d for d in subdirs
                        if d not in SKIP_DIRS
                        and not os.path.islink(os.path.join(cur_abs, d)))
    rel_dir = os.path.relpath(cur_abs, ROOT).replace(os.sep, "/")
    if rel_dir == ".":
        rel_dir = ""
    else:
        dirs.append(rel_dir)

    for name in sorted(filenames):
        if name in SKIP_FILES:
            continue
        abs_path = os.path.join(cur_abs, name)
        if os.path.islink(abs_path) or not os.path.isfile(abs_path):
            continue
        try:
            st = os.stat(abs_path)
        except OSError:
            continue

        rel_path = (rel_dir + "/" + name) if rel_dir else name
        stem, ext = os.path.splitext(name)
        ext = ext.lower()

        files.append({
            "path": rel_path,
            "dir": rel_dir or ".",
            "name": name,
            "ext": ext,
            "depth": rel_path.count("/") + 1,
            "bytes": st.st_size,
            "modified": datetime.datetime.utcfromtimestamp(st.st_mtime)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "mime": MIME.get(ext, DEFAULT_MIME),
            "category": category_of(ext, stem),
            "sha256": sha256_of(abs_path, st.st_size),
        })

dirs.sort()
files.sort(key=lambda f: f["path"])

# ---- repository identity -----------------------------------------
remote = (parse_remote(git("config", "--get", "remote.origin.url"))
          or parse_remote(FALLBACK_REPO_URL)
          or {"owner": "OWNER", "name": "REPO"})
branch = git("rev-parse", "--abbrev-ref", "HEAD") or FALLBACK_BRANCH or "main"
commit = git("rev-parse", "HEAD") or None
repo_url = "https://github.com/%s/%s" % (remote["owner"], remote["name"])
raw_base = "https://raw.githubusercontent.com/%s/%s/%s/" % (
    remote["owner"], remote["name"], commit or branch)

for f in files:
    f["url"] = raw_base + "/".join(urllib.parse.quote(p) for p in f["path"].split("/"))

# ---- entry point detection ---------------------------------------
html_files = [f for f in files if f["category"] == "entry-html"]
html_files.sort(key=lambda f: (0 if f["name"].lower() in ("index.html", "index.htm") else 1,
                               f["depth"], f["path"]))

by_category = {}
for f in files:
    by_category.setdefault(f["category"], []).append(f["path"])

total_bytes = sum(f["bytes"] for f in files)

manifest = {
    "schemaVersion": 1,
    "generator": "astrocade_manifest.py",
    "generatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "game": {
        "title": "Wolfenstein 3D (HTML5)",
        "engine": "html5-canvas",
        "entryHtml": html_files[0]["path"] if html_files else None,
        "entryCandidates": [f["path"] for f in html_files],
    },
    "repository": {
        "url": repo_url,
        "owner": remote["owner"],
        "name": remote["name"],
        "branch": branch,
        "commit": commit,
        "rawBase": raw_base,
        "cloneCommand": "git clone --depth 1 -b %s %s.git" % (branch, repo_url),
        "archiveZip": "%s/archive/refs/heads/%s.zip" % (repo_url, branch),
    },
    "root": os.path.basename(ROOT),
    "totals": {
        "directories": len(dirs),
        "files": len(files),
        "bytes": total_bytes,
        "megabytes": round(total_bytes / 1048576.0, 3),
    },
    "directories": dirs,
    "byCategory": by_category,
    "download": {
        "order": ["entry-html", "code", "style", "data", "game-data",
                  "image", "audio", "font", "video", "doc", "other"],
        "note": ("Fetch every entry in files[] from its url. Verify bytes/sha256. "
                 "Preserve the relative path so the game can resolve its own references."),
    },
    "files": files,
}

with open(OUT_PATH, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2)
    fh.write("\n")

# ---- console summary ---------------------------------------------
print("astrocade-manifest  ->  " + OUT_PATH)
print("  root        : " + ROOT)
print("  repository  : %s @ %s" % (repo_url, branch))
print("  entry html  : " + (manifest["game"]["entryHtml"] or "NOT FOUND"))
print("  directories : %d" % len(dirs))
print("  files       : %d  (%s MB)" % (len(files), manifest["totals"]["megabytes"]))
for k in sorted(by_category):
    print("    - %-12s %d" % (k, len(by_category[k])))