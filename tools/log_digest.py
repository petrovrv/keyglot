"""Digest of the detailed input log for tuning: inputs the user edited, undos, near misses, fixes, missed switches.
    python tools/log_digest.py [--date YYYY-MM-DD | --days N] [--dir %LOCALAPPDATA%\\Keyglot] [--json]
Prints Markdown (or JSON). Read-only."""
import argparse
import collections
import datetime as dt
import json
import os
import sys


def load(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(os.environ.get("LOCALAPPDATA", ""), "Keyglot"))
    ap.add_argument("--date", help="one day (default: yesterday)")
    ap.add_argument("--days", type=int, help="the last N days instead of one")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=60, help="max rows per section")
    a = ap.parse_args()
    today = dt.date.today()
    if a.days:
        days = [(today - dt.timedelta(days=i)).isoformat() for i in range(a.days - 1, -1, -1)]
    else:
        days = [a.date or (today - dt.timedelta(days=1)).isoformat()]
    rows = []
    for d in days:
        rows += load(os.path.join(a.dir, "input", d + ".jsonl"))
    events = [e for e in load(os.path.join(a.dir, "events.jsonl")) + load(os.path.join(a.dir, "events.jsonl.1"))
              if e.get("t", "")[:10] in days]

    inputs = [e for e in rows if e.get("event") == "input"]
    # 0.3.1 wrote one line per word; from 0.3.2 the words are inside the input lines
    words = [e for e in rows if e.get("event") == "word"]
    flat = [dict(d, exe=e.get("exe"), kind=e.get("kind"), layout=e.get("layout"), doc=e.get("doc"),
                 conv=e.get("conv"), input=e) for e in inputs for d in e.get("decisions", [])]
    for e in words:
        if e.get("action") == "fix" or e.get("erased") or e.get("cands") and e["cands"][0][0] != e.get("typed"):
            flat.append(dict(e, near=e.get("action") == "keep"))
    fixed = lambda e: e.get("out") not in (None, e.get("typed"))
    rep = {
        "days": days,
        "versions": sorted({e.get("v") for e in rows if e.get("v")}),
        "inputs": len(inputs),
        "words": len(words) + sum(e.get("words", 0) for e in inputs),
        "fixes": [e for e in flat if fixed(e)],
        "retypes": [e for e in flat if e.get("erased")],
        # inputs with the user's own corrections: Backspace after a fix, Pause, erased text, Ctrl+Z
        "undos": [e for e in inputs if e.get("undo")] + [e for e in rows if e.get("event") == "undo"],
        "manual": [e for e in inputs if e.get("manual")] + [e for e in rows if e.get("event") == "manual"],
        "edited": [e for e in inputs if any(k in e.get("keys", "") for k in ("⌫", "⌦", "[^Z]"))
                   and not e.get("undo")],
        # the engine liked another reading but kept the word: a possible missed fix
        "near_miss": [e for e in flat if e.get("near")],
        "patterns": [e for e in events if e.get("event") == "pattern"],
        "switch_missed": [e for e in events if e.get("event") == "switch_missed"],
        "errors": [e for e in events if e.get("event") == "error"],
        "by_app": collections.Counter(e.get("exe") for e in inputs + words).most_common(15),
    }
    if a.json:
        json.dump(rep, sys.stdout, ensure_ascii=False, indent=1, default=str)
        return 0
    p = print
    p(f"# Keyglot input digest {days[0]}" + (f" … {days[-1]}" if len(days) > 1 else ""))
    p(f"versions {', '.join(rep['versions']) or '-'}; inputs {rep['inputs']}; words {rep['words']}; "
      f"fixes {len(rep['fixes'])}; undos {len(rep['undos'])}; retypes {len(rep['retypes'])}; "
      f"manual (Pause) {len(rep['manual'])}; edited inputs {len(rep['edited'])}; "
      f"near misses {len(rep['near_miss'])}; switch_missed {len(rep['switch_missed'])}; errors {len(rep['errors'])}")
    p("\nBy program: " + ", ".join(f"{k} {v}" for k, v in rep["by_app"]))

    def sect(title, items, fmt):
        p(f"\n## {title} ({len(items)})")
        for e in items[-a.limit:]:
            p("- " + fmt(e))

    ctx = lambda e: f"[{e.get('exe')}/{e.get('kind')} {e.get('layout', '')} doc {e.get('doc', '-')} conv {e.get('conv', '-')}]"

    def inp(e):
        """An input: the final text, then what was pressed (⌫ Backspace, {→x} Keyglot's rewrite, {undo} ...)."""
        return (f"{e.get('t0', e.get('t', ''))} {ctx(e)} field {e.get('field', '-')!r}, end {e.get('end')}\n"
                f"    text: {e.get('text', '')!r}\n    keys: {e.get('keys', '')!r}"
                + (f"\n    erased before: {e['erased_before']!r}" if e.get("erased_before") else ""))

    def old(e):  # 0.3.1 per-word events
        return f"{e.get('frm')!r} -> {e.get('to')!r} after {e.get('before', '')!r} [{e.get('exe')}]"

    sect("Undone fixes (Backspace right after a fix)", rep["undos"], lambda e: inp(e) if "keys" in e else old(e))
    sect("Pause (manual convert)", rep["manual"], lambda e: inp(e) if "keys" in e else old(e))
    sect("Inputs the user edited (Backspace, Delete, Ctrl+Z)", rep["edited"], inp)
    sect("Words erased and typed again", rep["retypes"], lambda e: f"erased {e['erased']!r}, typed {e.get('typed')!r}"
         f" -> {e.get('out')!r} ({e.get('reason')}) {ctx(e)}")
    sect("Near misses (kept, another reading scored higher)", rep["near_miss"],
         lambda e: f"{e.get('typed')!r} kept ({e.get('reason')}); cands {e.get('cands')} {ctx(e)}"
                   + (f" in {e['input'].get('text', '')[-80:]!r}" if e.get("input") else ""))
    sect("Fixes", rep["fixes"], lambda e: f"{e.get('typed')!r} -> {e.get('out')!r} ({e.get('reason')}) {ctx(e)}")
    sect("Layout switch did not take", rep["switch_missed"],
         lambda e: f"{e.get('t')} {e.get('exe')} want {e.get('want')} got {e.get('got')}")
    sect("Learned core rules turned on (keep / fix pair / ctx triplet)", rep["patterns"],
         lambda e: f"{e.get('t')} {e.get('rule')} ({e.get('how')}) [{e.get('exe')}]")
    state = load_json(os.path.join(a.dir, "state.json")).get("patterns") or {}
    pending = [(kind, k, v) for kind, t in state.items() for k, v in t.items() if v.get("n", 0) == 1]
    sect("Core rules seen once (on at the second time)", pending,
         lambda e: f"{e[0]} {e[1]} ({e[2].get('word') or e[2].get('words', '')})")
    sect("Errors", rep["errors"], lambda e: f"{e.get('t')} {e.get('where')}: {e.get('error')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
