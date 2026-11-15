"""Compact word-frequency lists and character trigram models (built by tools/build_data.py).

Each word list is one sorted newline-joined string plus an offset array, so 200k words
take a few MB instead of a 100 MB dict. Lookup is a binary search.
"""
import gzip
import json
import math
import os
import sys
from array import array

LANGS = ("en", "nl", "ru", "uk")
ALPHABET = {
    "en": set("abcdefghijklmnopqrstuvwxyz"),
    "nl": set("abcdefghijklmnopqrstuvwxyzáàâäéèêëíìîïóòôöúùûüç"),
    "ru": set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя"),
    "uk": set("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"),
}
GROUP_ALPHABET = {"lat": ALPHABET["en"] | ALPHABET["nl"], "ru": ALPHABET["ru"], "uk": ALPHABET["uk"]}
INNER_OK = set("'-’")

# Words of terminals and source code: the only Latin targets accepted there.
TECH_WORDS = set("""
git cd ls ll dir cls clear exit echo cat type more less grep find findstr sed awk sort head tail touch
mkdir rmdir rm del cp copy mv move ren chmod chown sudo su apt yum dnf brew winget choco scoop pip pip3
python python3 py node npm npx yarn pnpm deno bun go cargo rustc gcc make cmake dotnet java javac mvn gradle
docker compose kubectl helm ssh scp rsync curl wget ping tracert ipconfig netstat nslookup tasklist taskkill
systemctl journalctl service code vim nano notepad explorer start set export source alias history man help
status commit push pull fetch merge rebase checkout switch branch log diff add reset restore stash tag clone
init remote show config install uninstall update upgrade list run build test serve dev lint format version
def class return import from as if elif else for while try except finally with lambda yield pass break
continue raise print self none true false null undefined function const let var new this async await
public private static void int str float bool string char long double struct enum interface package
select insert delete where join order group by having limit values into create table drop alter index
""".split())


def data_dir():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "keyglot", "data")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class WordList:
    def __init__(self, path):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            lines = f.read().split("\n")
        words, zs = [], bytearray()
        for ln in lines:
            if ln:
                wd, z = ln.split("\t")
                words.append(wd)
                zs.append(int(z))
        self.text = "\n".join(words) + "\n"
        off = array("I", [0])
        pos = 0
        for wd in words:
            pos += len(wd) + 1
            off.append(pos)
        self.off = off
        self.z = bytes(zs)
        self.n = len(words)

    def zipf(self, word):
        lo, hi = 0, self.n
        text, off = self.text, self.off
        while lo < hi:
            mid = (lo + hi) // 2
            cur = text[off[mid]:off[mid + 1] - 1]
            if cur < word:
                lo = mid + 1
            elif cur > word:
                hi = mid
            else:
                return self.z[mid] / 10.0
        return 0.0


class LanguageModel:
    def __init__(self, directory=None):
        d = directory or data_dir()
        self.words, self.tri, self.ref = {}, {}, {}
        for lang in LANGS:
            self.words[lang] = WordList(os.path.join(d, f"words-{lang}.txt.gz"))
            with open(os.path.join(d, f"tri-{lang}.json"), encoding="utf-8") as f:
                t = json.load(f)
            self.tri[lang], self.ref[lang] = t["p"], t["ref"]

    def known(self, word, lang):
        return self.words[lang].zipf(word)

    def tri_avg(self, word, lang):
        p = self.tri[lang]
        ctxp = p["__ctx__"]
        v = len(ALPHABET[lang]) + 2
        s = "^^" + word + "$"
        tot = 0.0
        for i in range(2, len(s)):
            g = s[i - 2:i + 1]
            if g in p:
                tot += p[g]
            else:
                tot += ctxp.get(g[:2], math.log10(1.0 / v)) - 1.0
        return tot / (len(s) - 2)

    def score(self, word, lang):
        """(log10 probability-like score of a lowercase word, known?)"""
        z = self.known(word, lang)
        if z > 0:
            return z - 9.0, True
        return -9.5 + 1.5 * (self.tri_avg(word, lang) - self.ref[lang]) * len(word), False

    def text_languages(self, text, max_words=60):
        """Share of each language among recognisable words of a text: ({lang: share}, n_words)."""
        counts = dict.fromkeys(LANGS, 0.0)
        n = 0
        for raw in text.split()[-max_words:]:
            wd = raw.strip(".,;:!?()[]{}\"«»„“”'`*_-–—/\\|<>").lower()
            if len(wd) < 2 or not wd.isalpha():
                continue
            best, bz = None, 2.5
            for lang in LANGS:
                if all(c in ALPHABET[lang] for c in wd):
                    z = self.known(wd, lang)
                    if z > bz:
                        best, bz = lang, z
            if best:
                counts[best] += 1
                n += 1
        if not n:
            return {}, 0
        return {k: v / n for k, v in counts.items() if v}, n


def split_core(text):
    """Leading punctuation, core word, trailing punctuation."""
    i, j = 0, len(text)
    while i < j and not text[i].isalpha():
        i += 1
    while j > i and not text[j - 1].isalpha():
        j -= 1
    return text[:i], text[i:j], text[j:]


def valid_core(core, group):
    alpha = GROUP_ALPHABET[group]
    low = core.lower()
    return bool(low) and low[0] in alpha and all(c in alpha or c in INNER_OK for c in low)
