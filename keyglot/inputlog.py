"""Detailed input log (off by default): one JSON line per input (a phrase typed into one field, up to Enter, Tab,
Esc, a window change, a click into another field or a pause) with the final text, the context, every key pressed
(edits included) and Keyglot's decisions. Daily files in APP_DIR\\input, deleted after `log_days`. Password fields and windows
that match `log_exclude` (password managers, banks) are never written."""
import json
import os
import re
import time
from collections import Counter

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


IDLE = 60          # seconds without keys that end an input
MAX_KEYS = 4000    # a longer input is written in parts

# keys that are not text, as they appear in the key trace
KEY_NAMES = {0x08: "⌫", 0x2E: "⌦", 0x25: "←", 0x27: "→", 0x26: "↑", 0x28: "↓", 0x24: "[Home]", 0x23: "[End]",
             0x21: "[PgUp]", 0x22: "[PgDn]", 0x2D: "[Ins]", 0x1B: "[Esc]", 0x09: "⇥", 0x0D: "⏎"}


def key_name(vk, shift=False, ctrl=False, alt=False):
    if 0x70 <= vk <= 0x87:
        name = f"F{vk - 0x6F}"
    elif 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        name = chr(vk)
    else:
        name = KEY_NAMES.get(vk, f"vk{vk:02X}")
    mods = ("^" if ctrl else "") + ("Alt+" if alt else "") + ("⇧" if shift and (ctrl or alt or vk in KEY_NAMES) else "")
    if not mods:
        return name
    return f"[{mods}{name.strip('[]')}]"


class Session:
    """One input. `keys` is the trace of what was pressed, in order: characters as the active layout shows them,
    ⌫ Backspace, ⌦ Delete, ← → ↑ ↓ arrows, ⏎ Enter, ⇧⏎ Shift+Enter, ⇥ Tab, [^Z] Ctrl shortcuts, [click] a mouse
    click, [Pause]; {→привет} Keyglot rewrote the word just typed, {a b→c d} it rewrote more than that word,
    {undo} a Backspace undid that rewrite."""

    def __init__(self, hwnd, exe, title, before=""):
        self.t0 = self.t1 = time.time()
        self.hwnd, self.exe, self.title = hwnd, exe, title
        self.before = before            # what Keyglot knows of the field before this input
        self.trace = []
        self.text = ""                  # the text as it ends up (approximate after the caret moved)
        self.erased_before = ""         # Backspace beyond the start of this input
        self.n = Counter()
        self.decisions = []             # words worth a look: fixes, retypes, near misses, edits inside the word
        self.field = self.kind = self.doc = self.conv = None
        self.layouts = []
        self.private = False
        self.moved = False              # the caret moved (arrows, click): `text` is the typed pieces in order
        self.click_at = None            # trace index of the last click: a new field may start there

    def key(self, tok):
        self.trace.append(tok)
        self.t1 = time.time()

    def edit(self, drop, add):
        if drop > len(self.text):
            cut = max(0, len(self.before) - (drop - len(self.text)))
            self.erased_before = self.before[cut:] + self.erased_before
            self.before = self.before[:cut]
            drop = len(self.text)
        self.text = self.text[:len(self.text) - drop] + add

    def context(self, kind, layout, field, doc=None, conv=None):
        if kind == "skip":
            self.private = True
        self.kind = self.kind or kind
        self.field = self.field or field
        if layout and (not self.layouts or self.layouts[-1] != layout):
            self.layouts.append(layout)
        self.doc, self.conv = doc or self.doc, conv or self.conv

    def word(self, typed, out, d=None, bs=0, erased=""):
        self.n["words"] += 1
        d = d or {}
        cands = [[c[3], round(c[0], 1)] for c in d.get("cands", [])[:3]]
        fix = out != typed
        near = bool(not fix and cands and cands[0][0] != typed)
        if fix:
            self.n["fixes"] += 1
        if bs:
            self.n["bs"] += bs
        if erased:
            self.n["retypes"] += 1
        if fix or near or bs or erased:
            e = {"typed": typed, "out": out, "reason": d.get("reason"), "lang": d.get("lang"),
                 "margin": d.get("margin"), "cands": cands, "bs": bs, "erased": erased, "near": near}
            self.decisions.append({k: v for k, v in e.items() if v not in (None, [], "", 0, False)})

    def split_at_click(self):
        """The text after the last click went to another field: return the trace part that belongs to it."""
        if self.click_at is None:
            return []
        rest, self.trace = self.trace[self.click_at:], self.trace[:self.click_at]
        self.click_at = None
        return rest

    def event(self, end):
        ev = {"event": "input", "t0": time.strftime("%H:%M:%S", time.localtime(self.t0)),
              "dur": round(self.t1 - self.t0, 1), "exe": self.exe, "title": (self.title or "")[:80],
              "field": (self.field or "")[:40], "kind": self.kind, "layout": ">".join(self.layouts),
              "doc": self.doc, "conv": self.conv, "end": end, "before": self.before[-60:], "text": self.text.rstrip(),
              "keys": "".join(self.trace), **{k: v for k, v in self.n.items() if v}}
        if self.erased_before:
            ev["erased_before"] = self.erased_before
        if self.moved:
            ev["moved"] = True
        if self.decisions:
            ev["decisions"] = self.decisions
        return {k: v for k, v in ev.items() if v not in (None, "", [])}
