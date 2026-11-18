"""Paths, settings and learned state (all local, per user)."""
import json
import os
import sys
import time

from . import __version__

APP_NAME = "Keyglot"
REPO = "petrovrv/keyglot"
APP_DIR = os.environ.get("KEYGLOT_DIR") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
STATE_FILE = os.path.join(APP_DIR, "state.json")
EVENTS_FILE = os.path.join(APP_DIR, "events.jsonl")
PENDING_FILE = os.path.join(APP_DIR, "pending.json")

DEFAULTS = {
    "enabled": True,
    "correct_on_enter": True,
    "hotkeys": True,              # Shift+Backspace: other layout, Alt+Backspace: typo fix
    "preswitch": True,
    "fix_typos": True,          # typos in words already in the right layout
    "fix_yo": True,             # еще -> ещё
    "fix_spaces": True,         # приветк ак -> привет как, приветкак -> привет как
    "sound": True,
    "log_events": True,
    "log_verbose": False,       # detailed input log: every input (phrase), its context, keys and edits
    "log_days": 14,             # detailed log files older than this are deleted
    # windows never written to the detailed log: substring of exe/title, "re:" = case-sensitive regex on the title
    "log_exclude": ["bitwarden", "keepass", "1password", "home'bank", "homebank", "ing.be", "ing belgi",
                    r"re:\bING\b", "keytrade"],
    "updates": "auto",          # auto | notify | off
    "ui_lang": "auto",          # auto | en | ru | uk | nl
    "rules": {},                # exe -> auto | off | latin
}


def frozen():
    return bool(getattr(sys, "frozen", False))


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULTS)
    cfg.update(_read(CONFIG_FILE, {}))
    cfg["rules"] = dict(cfg.get("rules") or {})
    return cfg


def save_config(cfg):
    _write(CONFIG_FILE, cfg)


def load_state():
    return _read(STATE_FILE, {"apps": {}, "ctx": {}, "exceptions": []})


def save_state(state):
    _write(STATE_FILE, state)


def push_pending(**cmd):
    """Settings window -> running app: commands applied on the next poll."""
    data = _read(PENDING_FILE, [])
    data.append(cmd)
    _write(PENDING_FILE, data)


def pop_pending():
    if not os.path.exists(PENDING_FILE):
        return []
    data = _read(PENDING_FILE, [])
    try:
        os.remove(PENDING_FILE)
    except OSError:
        pass
    return data


def log_event(**ev):
    os.makedirs(APP_DIR, exist_ok=True)
    try:
        if os.path.exists(EVENTS_FILE) and os.path.getsize(EVENTS_FILE) > 2_000_000:
            os.replace(EVENTS_FILE, EVENTS_FILE + ".1")
        ev = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "v": __version__, **ev}
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_events(n=200):
    out = []
    for path in (EVENTS_FILE + ".1", EVENTS_FILE):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
    return out[-n:]
