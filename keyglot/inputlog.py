"""Detailed input log (off by default): one JSON line per typed word with the decision and its context,
plus the user's own edits. Daily files in APP_DIR\\input, deleted after `log_days`. Password fields and windows
that match `log_exclude` (password managers, banks) are never written."""
import json
import os
import re
import time

from . import __version__
from . import config as C

INPUT_DIR = os.path.join(C.APP_DIR, "input")


def excluded(patterns, exe, title):
    """Plain patterns: case-insensitive substring of the program (exe) or the window title.
    "re:" patterns: a case-sensitive regular expression on the title ("re:\\bING\\b" is the bank, not "meeting")."""
    low = f"{exe}\n{title}".lower()
    for p in patterns or ():
        if not p:
            continue
        if p.startswith("re:"):
            try:
                if re.search(p[3:], title or ""):
                    return True
            except re.error:
                continue
        elif p.lower() in low:
            return True
    return False


def day_file(t=None):
    return os.path.join(INPUT_DIR, time.strftime("%Y-%m-%d", time.localtime(t)) + ".jsonl")


def write(**ev):
    try:
        os.makedirs(INPUT_DIR, exist_ok=True)
        ev = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "v": __version__, **ev}
        with open(day_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError:
        pass


def prune(days):
    """Delete day files older than `days` days."""
    if not os.path.isdir(INPUT_DIR):
        return 0
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - max(1, int(days)) * 86400))
    n = 0
    for name in os.listdir(INPUT_DIR):
        if name.endswith(".jsonl") and name[:10] < cutoff:
            try:
                os.remove(os.path.join(INPUT_DIR, name))
                n += 1
            except OSError:
                pass
    return n
