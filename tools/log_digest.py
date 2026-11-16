"""Digest of the detailed input log for tuning: user edits, undos, near misses, fixes, missed switches.
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

    words = [e for e in rows if e.get("event") == "word"]
    rep = {
        "days": days,
        "versions": sorted({e.get("v") for e in rows if e.get("v")}),
        "words": len(words),
        "fixes": [e for e in words if e.get("action") == "fix"],
        "retypes": [e for e in words if e.get("erased")],
        "undos": [e for e in rows if e.get("event") == "undo"],
        "manual": [e for e in rows if e.get("event") == "manual"],
        # the engine liked another reading but kept the word: a possible missed fix
        "near_miss": [e for e in words if e.get("action") == "keep" and e.get("cands") and
                      e["cands"][0][0] != e.get("typed")],
        "switch_missed": [e for e in events if e.get("event") == "switch_missed"],
        "errors": [e for e in events if e.get("event") == "error"],
        "by_app": collections.Counter(e.get("exe") for e in words).most_common(15),
    }
    if a.json:
        json.dump(rep, sys.stdout, ensure_ascii=False, indent=1)
        return 0
    p = print
    p(f"# Keyglot input digest {days[0]}" + (f" … {days[-1]}" if len(days) > 1 else ""))
    p(f"versions {', '.join(rep['versions']) or '-'}; words {rep['words']}; fixes {len(rep['fixes'])}; "
      f"undos {len(rep['undos'])}; retypes {len(rep['retypes'])}; manual (Pause) {len(rep['manual'])}; "
      f"near misses {len(rep['near_miss'])}; switch_missed {len(rep['switch_missed'])}; errors {len(rep['errors'])}")
    p("\nBy program: " + ", ".join(f"{k} {v}" for k, v in rep["by_app"]))

    def sect(title, items, fmt):
        p(f"\n## {title} ({len(items)})")
        for e in items[-a.limit:]:
            p("- " + fmt(e))

    ctx = lambda e: f"[{e.get('exe')}/{e.get('kind')} {e.get('layout', '')} doc {e.get('doc', '-')} conv {e.get('conv', '-')}]"
    sect("Undone fixes (Backspace)", rep["undos"], lambda e: f"{e.get('frm')!r} -> back to {e.get('to')!r} "
         f"after {e.get('before', '')!r} [{e.get('exe')}]")
    sect("User erased and retyped", rep["retypes"], lambda e: f"erased {e['erased']!r}, typed {e.get('typed')!r}"
         f" -> {e.get('out')!r} ({e.get('reason')}) after {e.get('before', '')!r} {ctx(e)}")
    sect("Pause (manual convert)", rep["manual"], lambda e: f"{e.get('frm')!r} -> {e.get('to')!r} [{e.get('exe')}]")
    sect("Near misses (kept, another reading scored higher)", rep["near_miss"],
         lambda e: f"{e.get('typed')!r} kept ({e.get('reason')}); cands {e.get('cands')} after "
                   f"{e.get('before', '')!r} {ctx(e)}")
    sect("Fixes", rep["fixes"], lambda e: f"{e.get('typed')!r} -> {e.get('out')!r} ({e.get('reason')}) {ctx(e)}")
    sect("Layout switch did not take", rep["switch_missed"],
         lambda e: f"{e.get('t')} {e.get('exe')} want {e.get('want')} got {e.get('got')}")
    sect("Errors", rep["errors"], lambda e: f"{e.get('t')} {e.get('where')}: {e.get('error')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
