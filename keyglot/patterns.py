"""Rules over word cores (stems) for special cases, learned from the user's own corrections without a model.

A core is the word without its inflectional ending (скамом -> скам, зочет -> зоч), so one rule covers
all forms of a word. Three kinds of rules:
  keep  one core:              words of this core are never typo-fixed or re-spaced (слэнг, names, terms)
  fix   a pair of cores:       typed core -> meant core (зоч -> хоч: зочет -> хочет, зочу -> хочу)
  ctx   a triplet of cores:    previous core | this core: no space fix between them (в | брик)

Shipped rules live in SHIPPED below (always on). Learned ones live in state["patterns"] with a
counter and turn on at LEARN_N observations:
  - a typo/split fix undone (Backspace) or erased and the original retyped -> keep
  - a space fix undone or erased and retyped                              -> ctx
  - an unknown word erased and retyped as a known word close to it        -> fix
"""
import time

LEARN_N = 2          # observations before a learned rule is used
MAX_RULES = 3000

ENDINGS = {
    "ru": """ями ами ого его ому ему ыми ими ешь ишь ете ите ться тся ая яя ое ее ые ие ых их ую юю ой ей
             ом ем ам ям ах ях ов ев ет ит ют ут ат ят ть ла ло ли сь ся а я о е ы и у ю ь й""",
    "uk": """ями ами ого ому ими ові еві ють уть ати яти ить ете ите ться ая ою ею ій ий ої ом ем ам ям ах ях
             ів їв ує ть ла ло ли сь ся а я о е и і ї у ю є ь й""",
    "en": "ing ies ied ed es s",
    "nl": "en es ste st te de s e",
}
ENDINGS = {k: sorted(v.split(), key=len, reverse=True) for k, v in ENDINGS.items()}
MIN_CORE = 3


def core(word, lang):
    """Word without its longest inflectional ending, at least MIN_CORE letters."""
    w = word.lower()
    for e in ENDINGS.get(lang, ()):
        if w.endswith(e) and len(w) - len(e) >= MIN_CORE:
            return w[:-len(e)]
    return w


def distance(a, b, limit=3):
    """Damerau-Levenshtein distance (adjacent swap = 1), capped at limit."""
    if abs(len(a) - len(b)) >= limit:
        return limit
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return min(prev[-1], limit)


# lang -> cores; fix: lang -> {typed core: meant core}; ctx: lang -> ["prev core|core"]
SHIPPED = {
    "keep": {"ru": ["скам"]},
    "fix": {},
    "ctx": {},
}


class Patterns:
    def __init__(self, state=None, shipped=None):
        self.state = state if state is not None else {}
        self.learned = self.state.setdefault("patterns", {})
        for k in ("keep", "fix", "ctx"):
            self.learned.setdefault(k, {})
        sh = SHIPPED if shipped is None else shipped
        self.keep_on = {f"{lang}:{c}" for lang, cs in (sh.get("keep") or {}).items() for c in cs}
        self.fix_on = {}
        for lang, pairs in (sh.get("fix") or {}).items():
            for a, b in pairs.items():
                self.fix_on[f"{lang}:{a}"] = b
        self.ctx_on = {f"{lang}:{t}" for lang, ts in (sh.get("ctx") or {}).items() for t in ts}
        for k, v in self.learned["keep"].items():
            if v.get("n", 0) >= LEARN_N:
                self.keep_on.add(k)
        for k, v in self.learned["fix"].items():
            if v.get("n", 0) >= LEARN_N:
                a, b = k.split(">", 1)
                self.fix_on[a] = b
        for k, v in self.learned["ctx"].items():
            if v.get("n", 0) >= LEARN_N:
                self.ctx_on.add(k)

    # ------------------------------------------------------------ lookup ---
    def keeps(self, word, lang):
        c = core(word, lang)
        if f"{lang}:{c}" in self.keep_on:
            return True
        # derived forms keep the rule too (скам -> скамер), short cores only exactly
        for n in (1, 2):
            if len(c) - n >= 4 and f"{lang}:{c[:-n]}" in self.keep_on:
                return True
        return False

    def fix(self, word, lang):
        """Meant word for a typed one by a fix rule (the caller checks it is a real word), or None."""
        c = core(word, lang)
        to = self.fix_on.get(f"{lang}:{c}")
        if to is None:
            return None
        return to + word.lower()[len(c):]

    def ctx(self, prev, word, lang):
        return f"{lang}:{core(prev, lang)}|{core(word, lang)}" in self.ctx_on

    # ---------------------------------------------------------- learning ---
    def _bump(self, kind, key, on, **info):
        table = self.learned[kind]
        r = table.setdefault(key, {"n": 0})
        r["n"] += 1
        r["t"] = time.strftime("%Y-%m-%d %H:%M:%S")
        r.update(info)
        if len(table) > MAX_RULES:
            weak = sorted((k for k in table if table[k].get("n", 0) < LEARN_N), key=lambda k: table[k].get("t", ""))
            for k in weak[:len(table) - MAX_RULES]:
                del table[k]
        if r["n"] >= LEARN_N:
            on()
            return key
        return None

    def reject(self, orig, lang):
        """The user turned a typo fix of `orig` back: keep its core. Returns the rule if it is now on."""
        w = orig.lower()
        if len(w) < 3 or not w.isalpha():
            return None
        key = f"{lang}:{core(w, lang)}"
        return self._bump("keep", key, lambda: self.keep_on.add(key), word=w)

    def reject_space(self, prev, word, lang):
        p, w = prev.lower(), word.lower()
        if not (p.isalpha() and w.isalpha()):
            return None
        key = f"{lang}:{core(p, lang)}|{core(w, lang)}"
        return self._bump("ctx", key, lambda: self.ctx_on.add(key), words=f"{p} {w}")

    def retyped(self, typo, meant, lang):
        """The user erased an unknown word and typed a known one close to it: learn the core pair."""
        a, b = typo.lower(), meant.lower()
        if a == b or len(a) < 4 or not (a.isalpha() and b.isalpha()) or distance(a, b) > 2:
            return None
        ca, cb = core(a, lang), core(b, lang)
        if a[len(ca):] != b[len(cb):]:
            ca, cb = a, b  # different endings: the pair holds for this form only
        if ca == cb:
            return None
        k = f"{lang}:{ca}"
        key = f"{k}>{cb}"

        def on():
            self.fix_on[k] = cb
        return self._bump("fix", key, on, words=f"{a}>{b}")

    def summary(self):
        """Rules in use, for the log digest: {kind: [key, ...]}."""
        out = {"keep": sorted(self.keep_on), "ctx": sorted(self.ctx_on),
               "fix": sorted(f"{a}>{b}" for a, b in self.fix_on.items())}
        return out
