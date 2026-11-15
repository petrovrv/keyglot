"""Build Keyglot's language data from wordfreq: compact word lists and trigram models.

    python tools/build_data.py [--out keyglot/data]
"""
import argparse
import gzip
import json
import math
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from keyglot.lexicon import ALPHABET, INNER_OK, LANGS  # noqa: E402

SIZES = {"en": 120000, "nl": 120000, "ru": 220000, "uk": 220000}


def build(lang, out):
    from wordfreq import get_frequency_dict
    alpha = ALPHABET[lang]
    freqs = get_frequency_dict(lang, wordlist="best")
    items = [(w, f) for w, f in freqs.items()
             if w and w[0] in alpha and all(c in alpha or c in INNER_OK for c in w)]
    items.sort(key=lambda kv: -kv[1])
    items = items[:SIZES[lang]]
    rows = []
    for w, f in items:
        z = max(1, min(90, round((math.log10(f) + 9) * 10)))
        rows.append((w, z))
    rows.sort()
    with gzip.open(os.path.join(out, f"words-{lang}.txt.gz"), "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write("".join(f"{w}\t{z}\n" for w, z in rows))

    cnt, ctx = Counter(), Counter()
    for w, f in items[:80000]:
        wgt = math.sqrt(f) * 1e4
        s = "^^" + w + "$"
        for i in range(2, len(s)):
            cnt[s[i - 2:i + 1]] += wgt
            ctx[s[i - 2:i]] += wgt
    v = len(alpha) + 2
    p = {g: round(math.log10((c + 0.1) / (ctx[g[:2]] + 0.1 * v)), 3) for g, c in cnt.items()}
    p["__ctx__"] = {k: round(math.log10(0.1 / (c + 0.1 * v)), 3) for k, c in ctx.items()}

    def avg(word):
        s = "^^" + word + "$"
        tot = 0.0
        for i in range(2, len(s)):
            g = s[i - 2:i + 1]
            tot += p[g] if g in p else p["__ctx__"].get(g[:2], math.log10(1.0 / v)) - 1.0
        return tot / (len(s) - 2)
    sample = [w for w, _ in items[:3000] if len(w) >= 4 and all(c in alpha for c in w)][:1500]
    avgs = sorted(avg(w) for w in sample)
    ref = avgs[len(avgs) // 2]
    with open(os.path.join(out, f"tri-{lang}.json"), "w", encoding="utf-8") as fh:
        json.dump({"p": p, "ref": ref}, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{lang}: {len(rows)} words, {len(p)} trigrams, ref {ref:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "keyglot", "data"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for lang in LANGS:
        build(lang, a.out)


if __name__ == "__main__":
    main()
