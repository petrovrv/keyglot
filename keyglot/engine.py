"""Decision logic: which layout did the user mean? Pure Python, no Win32 calls (testable)."""
import math
from dataclasses import dataclass, field

from .layouts import GROUP_LANGS, LANG_GROUP, TRAIL_PUNCT_VKS
from .lexicon import LANGS, TECH_WORDS, split_core, valid_core
from .spell import Speller, match_case

# Field kinds where text is mostly Latin: only Cyrillic garbage -> Latin is corrected there.
LATIN_KINDS = {"terminal", "code", "path", "address"}


@dataclass
class Ctx:
    exe: str = ""
    kind: str = "prose"      # prose | url | terminal | code | path | address | skip
    key: str = ""            # learned-habit key: exe + window/field identity
    doc: dict = field(default_factory=dict)   # language shares of the text before the caret
    doc_n: int = 0
    conv: dict = field(default_factory=dict)  # language shares of the conversation/document around
    conv_n: int = 0
    sticky: str = None       # language of the previous word in this window
    user_switched: bool = False
    url_like: bool = False   # url field already holds a domain-like text


def empty_state():
    return {"apps": {}, "ctx": {}, "exceptions": []}


class Engine:
    def __init__(self, layouts, lm, state=None):
        self.L = layouts
        self.lm = lm
        self.state = state or empty_state()
        self.state.setdefault("apps", {})
        self.state.setdefault("ctx", {})
        self.exceptions = set(self.state.setdefault("exceptions", []))
        self.S = Speller(lm)

    # ------------------------------------------------------------ prior ---
    @staticmethod
    def _habit(counts, lang, cap=1.5):
        n = sum(counts.values())
        if not n:
            return 0.0
        v = math.log10((counts.get(lang, 0) + 1) / (n + len(LANGS))) - math.log10(1 / len(LANGS))
        return max(-cap, min(cap, v))

    def prior(self, ctx, active_group):
        apps = self.state["apps"].get(ctx.exe, {})
        place = self.state["ctx"].get(ctx.key, {}) if ctx.key else {}
        pr = {}
        for lang in LANGS:
            g = LANG_GROUP[lang]
            p = self._habit(apps, lang, 1.0) + self._habit(place, lang, 1.5)
            if ctx.doc_n:
                p += 1.5 * ctx.doc.get(lang, 0.0) * min(1.0, ctx.doc_n / 5)
            if ctx.conv_n:
                p += 1.0 * ctx.conv.get(lang, 0.0) * min(1.0, ctx.conv_n / 8)
            if ctx.sticky:
                if lang == ctx.sticky:
                    p += 0.8
                elif g == LANG_GROUP.get(ctx.sticky):
                    p += 0.4
            if ctx.kind == "url" and g == "lat" and ctx.url_like:
                p += 1.5
            if g == active_group:
                p += 3.0 if ctx.user_switched else 1.0
            pr[lang] = p
        return pr

    # ------------------------------------------------------- candidates ---
    def candidates(self, keys):
        """[(group, lang, text, core, word_score, known)]"""
        out = []
        n = len(keys)
        for group in self.L.tables:
            variants = [self.L.render(keys, group)]
            # trailing punctuation typed on Latin positions while a Cyrillic layout was meant
            if group != "lat" and "lat" in self.L.tables:
                m = 0
                while m < min(2, n - 1) and keys[n - 1 - m][0] in TRAIL_PUNCT_VKS:
                    m += 1
                    variants.append(self.L.render(keys[:n - m], group) + self.L.render(keys[n - m:], "lat"))
            full_core = split_core(variants[0])[1].lower()
            if len(variants) > 1 and valid_core(full_core, group) and \
                    max(self.lm.known(full_core, l) for l in GROUP_LANGS[group]) >= 2.0:
                variants = variants[:1]  # "гараж" is a word: the last key is a letter, not ';'
            for k, text in enumerate(variants):
                _, core, _ = split_core(text)
                if not valid_core(core, group):
                    continue
                for lang in GROUP_LANGS[group]:
                    s, known = self.lm.score(core.lower(), lang)
                    if k:
                        s -= 1.0  # cost of the punctuation hypothesis
                    out.append((group, lang, text, core, s, known))
        return out

    def key_id(self, keys):
        return self.L.render(keys, "lat").lower() if "lat" in self.L.tables else ""

    # ----------------------------------------------------------- decide ---
    def decide(self, keys, active_group, ctx=None):
        ctx = ctx or Ctx()
        res = {"action": "keep", "reason": "", "kind": ctx.kind}
        if not keys or active_group not in self.L.tables:
            res["reason"] = "no keys / unknown layout"
            return res
        if ctx.kind == "skip":
            res["reason"] = "field skipped"
            return res
        typed = self.L.render(keys, active_group, composed=True)
        res["typed"] = typed
        kid = self.key_id(keys)
        res["key_id"] = kid
        if kid in self.exceptions:
            res["reason"] = "exception"
            return res
        if self.L.is_dead(keys[-1], active_group):
            res["reason"] = "ends with a dead key"
            return res
        cands = self.candidates(keys)
        if not cands:
            res["reason"] = "no word candidates"
            return res
        if ctx.kind in LATIN_KINDS:
            return self._decide_latin_field(res, cands, typed, active_group, ctx)

        pr = self.prior(ctx, active_group)
        scored = sorted(((s + pr[lang], g, lang, text, core, s, known) for g, lang, text, core, s, known in cands),
                        reverse=True)
        if split_core(typed)[1][:1] == typed[:1]:
            # the word starts with a letter: never turn its first letters into punctuation ('эьл' -> "'mk")
            scored = [c for c in scored if c[3] == typed or split_core(c[3])[0] == ""]
        res["cands"] = scored[:6]
        best = scored[0]
        if best[3] == typed:
            res.update(reason="typed text is best", lang=best[2], known=best[6])
            if best[1] != active_group:
                # same text, other layout wins (Russian word typed on the Ukrainian layout): switch only
                res.update(action="switch", group=best[1], reason="same text, layout switch")
            return res
        same = [c for c in scored if c[3] == typed]
        cur = same[0] if same else (-30.0, active_group, None, typed, split_core(typed)[1], -30.0, False)
        res["lang"] = cur[2]
        margin = best[0] - cur[0]
        need = 1.5
        if len(best[4]) <= 2:
            need = 2.0
            if self.lm.known(best[4].lower(), best[2]) < 3.0:
                res["reason"] = "short word, target not common"
                return res
        if not best[6]:
            need = max(need, 9.0)  # unknown target word: only very clear cases
        if cur[6] and cur[2] and self.lm.known(cur[4].lower(), cur[2]) >= 3.0:
            need += 2.0  # the typed text is itself a common word: maybe the other language is meant here
        res["margin"] = round(margin, 2)
        if margin < need:
            res["reason"] = f"margin {margin:.2f} < {need}"
            return res
        res.update(action="rewrite", text=best[3], group=best[1], lang=best[2], known=True,
                   reason=f"margin {margin:.2f}")
        return res

    def _decide_latin_field(self, res, cands, typed, active_group, ctx):
        """Terminals, code, paths, addresses: only Cyrillic garbage -> Latin, never the other way."""
        if active_group == "lat":
            res.update(reason=f"{ctx.kind}: Latin stays", lang="en")
            return res
        tcore = split_core(typed)[1].lower()
        if tcore and max(self.lm.known(tcore, l) for l in GROUP_LANGS[active_group]) >= 2.5:
            res.update(reason=f"{ctx.kind}: real {active_group} word", lang=GROUP_LANGS[active_group][0])
            return res
        lat = [c for c in cands if c[0] == "lat" and c[1] == "en"]
        if not lat:
            res["reason"] = f"{ctx.kind}: no Latin candidate"
            return res
        g, lang, text, core, s, known = lat[0]
        low = core.lower()
        ok = low in TECH_WORDS or self.lm.known(low, "en") >= (3.5 if ctx.kind in ("terminal", "code") else 2.5)
        if not ok and ctx.kind in ("path", "address"):
            ok = self.lm.tri_avg(low, "en") > self.lm.ref["en"] - 0.6 and len(low) >= 3
        if not ok:
            res["reason"] = f"{ctx.kind}: Latin target not recognised"
            return res
        res.update(action="rewrite", text=text, group="lat", lang="en", known=True, reason=f"{ctx.kind}: to Latin")
        return res

    def recheck_previous(self, keys, active_group, target_lang):
        """After word N+1 switched to target, should word N follow?"""
        tg = LANG_GROUP[target_lang]
        if not keys or tg == active_group or tg not in self.L.tables or active_group not in self.L.tables:
            return None
        typed = self.L.render(keys, active_group, composed=True)
        kid = self.key_id(keys)
        if kid in self.exceptions or self.L.has_dead(keys, active_group):
            return None
        new = self.L.render(keys, tg)
        core_new = split_core(new)[1]
        core_old = split_core(typed)[1]
        if not valid_core(core_new, tg):
            return None
        s_new, known = self.lm.score(core_new.lower(), target_lang)
        if not known:
            return None
        s_old = max([self.lm.score(core_old.lower(), l)[0] for l in GROUP_LANGS[active_group]]
                    if valid_core(core_old, active_group) else [-30.0])
        if s_new + 1.0 >= s_old + 0.5:
            return {"typed": typed, "text": new, "key_id": kid}
        return None

    # ----------------------------------------------- typos, ё, spaces ---
    def polish(self, text, lang, prev_text=None, opts=None, kid="", prev_kid=""):
        """After the layout decision: misplaced space with the previous word, missing space, typo, ё.
        prev_text is the previous word as typed (before its own typo fix), so "приветк ак" is still seen.
        Returns {"prev": new previous word or None, "text": new word, "reason": ...} or None."""
        opts = opts or {}
        if not text or lang not in LANG_GROUP or kid in self.exceptions:
            return None
        pre, core, post = split_core(text)
        if not core or not core.isalpha() or (len(core) > 1 and core.isupper()) or \
                any(c.isupper() for c in core[1:]):
            return None  # abbreviations, iPhone-style names, words with digits or inner punctuation
        low = core.lower()
        group = LANG_GROUP[lang]
        name_like = core[0].isupper() and prev_text and not prev_text.rstrip().endswith((".", "!", "?", "…"))
        reason = []
        new_prev, words = None, [low]
        if opts.get("spaces", True) and prev_text and not pre and not name_like:
            ppre, pcore, ppost = split_core(prev_text)
            pair = f"{prev_kid} {kid}"
            if pcore and pcore.isalpha() and not ppost and pair not in self.exceptions:
                r = self.S.respace(pcore.lower(), low, lang)
                if r:
                    if len(r) == 1:
                        new_prev, words = ppre + match_case(pcore, r[0]), None
                    else:
                        new_prev, words = ppre + match_case(pcore, r[0]), [r[1]]
                    reason.append("space " + " ".join(r))
        if new_prev is None and not name_like:
            typo = self.S.correct(low, group, {lang: 0.3}) if opts.get("typos", True) else None
            split = self.S.split(low, lang) if opts.get("spaces", True) else None
            if typo and (typo[3] <= 0.8 or not split):
                words = [typo[0]]
                reason.append(typo[2])
            elif split:
                words = list(split)
                reason.append("split " + " ".join(split))
        if opts.get("yo", True) and lang == "ru":
            if words:
                for i, wd in enumerate(words):
                    y = self.S.yo(wd)
                    if y:
                        words[i] = y
                        reason.append("yo " + y)
            if new_prev:
                pp, pc, pq = split_core(new_prev)
                y = self.S.yo(pc.lower())
                if y:
                    new_prev = pp + match_case(pc, y) + pq
                    reason.append("yo " + y)
        if not reason:
            return None
        out = ""
        if words:
            out = pre + " ".join([match_case(core, words[0])] + words[1:]) + post
        elif new_prev:
            new_prev += post
        return {"prev": new_prev, "text": out, "reason": "; ".join(reason)}

    # --------------------------------------------------------- learning ---
    def learn(self, ctx, lang):
        if not lang:
            return
        for table, k, limit in ((self.state["apps"], ctx.exe, 2000), (self.state["ctx"], ctx.key, 500)):
            if not k:
                continue
            c = table.setdefault(k, {})
            c[lang] = c.get(lang, 0) + 1
            if sum(c.values()) > limit:  # keep habits recent
                for x in c:
                    c[x] *= 0.9
        if len(self.state["ctx"]) > 800:
            for k in sorted(self.state["ctx"], key=lambda k: sum(self.state["ctx"][k].values()))[:100]:
                del self.state["ctx"][k]

    def add_exception(self, kid):
        if kid:
            self.exceptions.add(kid)
            self.state["exceptions"] = sorted(self.exceptions)

    def remove_exception(self, kid):
        self.exceptions.discard(kid)
        self.state["exceptions"] = sorted(self.exceptions)

    def preferred_lang(self, key, exe, min_words=40, share=0.85):
        for table, k in ((self.state["ctx"], key), (self.state["apps"], exe)):
            c = table.get(k or "", {})
            n = sum(c.values())
            if n >= min_words:
                lang, v = max(c.items(), key=lambda kv: kv[1])
                return lang if v / n >= share else None
        return None


def simulate(engine, text, layout, ctx=None, verbose=False, polish=None):
    """Type text word by word as if layout were active (physical keys stay, layout may change).
    polish: None = layout only, or options for typos/ё/spaces ({} = all on)."""
    ctx = ctx or Ctx()
    out, prev, active, raw = [], None, layout, None
    for word in text.split(" "):
        if not word:
            continue
        keys = engine.L.keys_for(word, layout)
        ctx.sticky = prev["lang"] if prev else None
        d = engine.decide(keys, active, ctx)
        if verbose:
            print(f"  {word!r}: {d['action']} {d.get('text', '')!r} ({d['reason']})")
            for c in d.get("cands", [])[:4]:
                print(f"      {c[0]:7.2f}  {c[2]}  {c[3]!r}{'' if c[6] else '  (oov)'}")
        if d["action"] == "switch":
            active = d["group"]
        if d["action"] == "rewrite":
            if prev and prev["group"] == active and ctx.kind not in LATIN_KINDS:
                r = engine.recheck_previous(prev["keys"], active, d["lang"])
                if r:
                    out[-1] = r["text"]
            out.append(d["text"])
            active = d["group"]
            prev = {"keys": keys, "lang": d["lang"], "group": d["group"]}
        else:
            out.append(d.get("typed", word))
            prev = {"keys": keys, "lang": d.get("lang"), "group": active}
        cur_raw = out[-1]
        if polish is not None and ctx.kind == "prose" and d.get("reason") != "exception" and prev["lang"]:
            pt = raw if len(out) > 1 else None
            p = engine.polish(out[-1], prev["lang"], pt, polish)
            if verbose and p:
                print(f"      polish: {p}")
            if p:
                if p["prev"] is not None:
                    out[-2] = p["prev"]
                    cur_raw = None  # both words were rebuilt: no third-word look-back
                out[-1] = p["text"]
                if not out[-1]:
                    out.pop()
        raw = cur_raw
    return " ".join(w for w in out if w)
