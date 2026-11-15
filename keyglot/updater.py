"""Auto-update from GitHub Releases: latest tag, installer asset, SHA-256 check, silent Inno Setup run."""
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request

from . import __version__
from .config import REPO

API = f"https://api.github.com/repos/{REPO}/releases/latest"
UA = {"User-Agent": f"Keyglot/{__version__}", "Accept": "application/vnd.github+json"}


def _ver(s):
    s = s.lstrip("vV")
    out = []
    for part in s.split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num or 0))
    return tuple(out + [0] * (3 - len(out)))


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check():
    """Return dict(version, url, sha256, notes) if a newer release exists, else None."""
    rel = json.loads(_get(API))
    tag = rel.get("tag_name", "")
    if rel.get("draft") or rel.get("prerelease") or _ver(tag) <= _ver(__version__):
        return None
    asset = next((a for a in rel.get("assets", []) if a["name"].lower().startswith("keyglot-setup")
                  and a["name"].lower().endswith(".exe")), None)
    if not asset:
        return None
    sha = (asset.get("digest") or "").removeprefix("sha256:")
    if not sha:
        sums = next((a for a in rel["assets"] if a["name"].upper() == "SHA256SUMS.TXT"), None)
        if sums:
            for line in _get(sums["browser_download_url"]).decode().splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == asset["name"]:
                    sha = parts[0]
    return {"version": tag.lstrip("vV"), "url": asset["browser_download_url"], "sha256": sha.lower(),
            "name": asset["name"], "notes": rel.get("body", "")}


def download(info):
    data = _get(info["url"], timeout=120)
    digest = hashlib.sha256(data).hexdigest()
    if not info["sha256"] or digest != info["sha256"]:
        raise ValueError(f"checksum mismatch for {info['name']}")
    path = os.path.join(tempfile.gettempdir(), info["name"])
    with open(path, "wb") as f:
        f.write(data)
    return path


def run_installer(path):
    """Start the silent installer detached; it closes this app and starts the new version."""
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     creationflags=flags, close_fds=True)
