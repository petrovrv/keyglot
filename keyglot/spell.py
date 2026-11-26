"""Typos, ё and misplaced spaces in words that are already in the right layout. Pure Python (testable).

Precision first: a word is changed only when it is unknown in every language of its alphabet and one
correction is clearly better than the others. Backspace right after a fix undoes it and remembers the word.
"""
import time

from .lexicon import ALPHABET, LANGS

# Keyboard rows (unshifted) for neighbour-key typos; x offsets follow the usual row stagger.
_ROWS = {
    "lat": ("qwertyuiop", "asdfghjkl", "zxcvbnm"),
    "ru": ("йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю"),
    "uk": ("йцукенгшщзхї", "фівапролджє", "ячсмитьбю"),
}
_STAGGER = (0.0, 0.25, 0.75)
LANG_GROUP = {"en": "lat", "nl": "lat", "ru": "ru", "uk": "uk"}
GROUP_LANGS = {"lat": ("en", "nl"), "ru": ("ru",), "uk": ("uk",)}

# One-letter words that may stand alone after a space is moved or inserted.
ONE_LETTER = {"en": set("ai"), "nl": set(), "ru": set("ивскуоая"), "uk": set("іївзуоай")}

# е-forms that are words of their own (все/всё, небо/нёбо ...): never turned into ё.
YO_AMBIGUOUS = set("""
все небо осел лен мел берет слез слезы узнаем совершенный совершенно падеж нес вед звезды сестры жены
озера села весла гнезда ведра стекла зерна черт мед нем передохнем поем плачем истекший признанный
опека опеки определенный определенно мертвый решетка заем подаем отдаем издаем сдаем продаем встаем
даем узнает тек тем чем лет
""".split())

# ш next to щ: a typo of ещё that the word list also knows as a word, so it is never "ешё".
YO_TYPO = {"еше": "ещё"}

COST_FIRST = 0.6     # extra cost of an edit at the first letter (people rarely miss it)

# Endings used to recognise inflected forms that are missing from the word list.
_RU_END = """а я о е и ы у ю ь й ой ей ий ый ая яя ое ее ые ие ого его ому ему ом ем им ым ам ям ами ями ах ях ов ев
ть ла ло ли л ет ит ут ют ат ят ешь ишь ете ите ал ял ил ыл ать ять ить еть ую юю ость ости ся сь""".split()
_UK_END = """а я о е и і у ю ь й ий ій ої ою ою ого ому ім ом ем ам ям ами ями ах ях ів їв
ти ла ло ли в ла є ить ать ять ути ують ую юю ість ості ся сь""".split()
INFLECTED = {"ru": _RU_END, "uk": _UK_END}
# Case endings of nouns: a known stem ending in a consonant + one of these is a form (имейл -> имейла)
NOUN_END = {"ru": ("а", "у", "ом", "е", "ы", "ов", "ам", "ами", "ах"),
            "uk": ("а", "у", "ом", "і", "и", "ів", "ам", "ами", "ах")}
VOWELS = set("аеёиоуыэюяіїєaeiouy")
# First parts of compounds: автокоррекция is one word, not "авто коррекция"
COMPOUND_HEADS = tuple("""авто аудио видео фото кино теле радио микро макро мега мини макси супер гипер анти псевдо
полу само нео эко био гео агро авиа вело мото электро термо гидро аэро медиа мульти квази пост пред""".split())


def _neighbours():
    out = {}
    for group, rows in _ROWS.items():
        pos = {}
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                pos[ch] = (r, c + _STAGGER[r])
        nb = {}
        for a, (ra, xa) in pos.items():
            nb[a] = {b for b, (rb, xb) in pos.items() if b != a and abs(ra - rb) <= 1 and abs(xa - xb) <= 1.3}
        out[group] = nb
    return out


NEIGHBOURS = _neighbours()


def match_case(src, word):
    """Give word the case pattern of src (lower, Capitalised, UPPER)."""
    if src.isupper() and len(src) > 1:
        return word.upper()
    if src[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


class Speller:
    def __init__(self, lm):
        self.lm = lm
        self._ranges = {}
        self._freq = {}

    # ------------------------------------------------------------ utils ---
    def z(self, word, lang):
        return self.lm.known(word, lang)

    def best_z(self, word, langs):
        return max(self.z(word, l) for l in langs)

    def known_anywhere(self, word):
        return any(self.z(word, l) > 0 for l in LANGS if all(c in ALPHABET[l] or c in "'-’" for c in word))

    def _range(self, lang, first):
        """Index range of words that start with `first` in the sorted word list."""
        key = (lang, first)
        if key not in self._ranges:
            wl = self.lm.words[lang]
            text, off = wl.text, wl.off

            def lower_bound(s):
                lo, hi = 0, wl.n
                while lo < hi:
                    mid = (lo + hi) // 2
                    if text[off[mid]:off[mid + 1] - 1] < s:
                        lo = mid + 1
                    else:
                        hi = mid
                return lo
            self._ranges[key] = (lower_bound(first), lower_bound(first + "￿"))
        return self._ranges[key]

    def warm(self):
        """Build the per-letter caches in the background so the first typo costs no lookup time."""
        for lang in LANGS:
            for first in sorted(ALPHABET[lang]):
                self._frequent(lang, first, 0, 3.5)

    # ------------------------------------------------------------ typos ---
    def _sub_cost(self, a, b, group):
        if b in NEIGHBOURS[group].get(a, ()):
            return 0.8
        return 2.2

    def edits1(self, word, group):
        """{candidate: cost} for one delete / insert / substitute / transpose."""
        alpha = sorted(c for c in ALPHABET[GROUP_LANGS[group][0]] if c.isalpha()) if group != "lat" \
            else sorted(ALPHABET["en"])
        out = {}

        def put(w, cost, i):
            if i == 0:
                cost += COST_FIRST
            if w and (w not in out or cost < out[w]):
                out[w] = cost
        n = len(word)
        for i in range(n):
            ch = word[i]
            # extra letter: doubled or a neighbour of the letter next to it is the usual slip
            near = (i > 0 and (word[i - 1] == ch or ch in NEIGHBOURS[group].get(word[i - 1], ()))) or \
                   (i + 1 < n and (word[i + 1] == ch or ch in NEIGHBOURS[group].get(word[i + 1], ())))
            if i or near:  # a stray first letter is a neighbour slip; "дописывает" is not "описывает"
                put(word[:i] + word[i + 1:], 0.7 if near else 1.0, i)
            if i + 1 < n and word[i] != word[i + 1]:
                put(word[:i] + word[i + 1] + ch + word[i + 2:], 0.7, i)
            for c in alpha:
                if c != ch:
                    put(word[:i] + c + word[i + 1:], self._sub_cost(ch, c, group), i)
        for i in range(n + 1):
            for c in alpha:
                doubled = (i > 0 and word[i - 1] == c) or (i < n and word[i] == c)
                put(word[:i] + c + word[i:], 0.7 if doubled else 1.0, i)
        out.pop(word, None)
        return out

    def _dist(self, a, b, group, limit):
        """Weighted Damerau-Levenshtein distance with the same costs, None if above limit."""
        la, lb = len(a), len(b)
        INF = 99.0
        prev2 = None
        prev = [j * 1.0 for j in range(lb + 1)]
        for i in range(1, la + 1):
            cur = [i * 1.0] + [INF] * lb
            lo = INF
            for j in range(1, lb + 1):
                ca, cb = a[i - 1], b[j - 1]
                first = COST_FIRST if (i == 1 or j == 1) else 0.0
                if ca == cb:
                    v = prev[j - 1]
                else:
                    v = prev[j - 1] + self._sub_cost(ca, cb, group) + first
                dl = 0.7 if (i > 1 and a[i - 2] == ca) else 1.0
                ins = 0.7 if (j > 1 and b[j - 2] == cb) else 1.0
                v = min(v, prev[j] + dl + (COST_FIRST if i == 1 else 0.0),
                        cur[j - 1] + ins + (COST_FIRST if j == 1 else 0.0))
                if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb and ca != cb:
                    v = min(v, prev2[j - 2] + 0.7)
                cur[j] = v
                lo = min(lo, v)
            if lo > limit:
                return None
            prev2, prev = prev, cur
        return prev[lb] if prev[lb] <= limit else None

    def _frequent(self, lang, first, length, min_z):
        """Frequent words (zipf >= min_z) of one first letter and length, cached."""
        key = (lang, first, length, min_z)
        got = self._freq.get(key)
        if got is None:
            if (lang, first, min_z) not in self._freq:
                wl = self.lm.words[lang]
                text, off, zs = wl.text, wl.off, wl.z
                lo, hi = self._range(lang, first)
                zmin = int(min_z * 10)
                by_len = {}
                for k in range(lo, hi):
                    if zs[k] >= zmin:
                        cand = text[off[k]:off[k + 1] - 1]
                        by_len.setdefault(len(cand), []).append((cand, frozenset(cand)))
                self._freq[(lang, first, min_z)] = True
                for ln, lst in by_len.items():
                    self._freq[(lang, first, ln, min_z)] = lst
            got = self._freq.get(key, [])
        return got

    def edits2(self, word, lang, group, min_z=3.5, limit=2.0, budget=0.04):
        """Frequent words within weighted distance `limit` that start with the same letter."""
        n = len(word)
        letters = frozenset(word)
        out = {}
        t_end = time.perf_counter() + budget
        for ln in sorted(range(n - 2, n + 3), key=lambda x: abs(x - n)):
            for cand, cl in self._frequent(lang, word[0], ln, min_z):
                if len(letters ^ cl) > 4:
                    continue
                d = self._dist(word, cand, group, limit)
                if d is not None and cand != word:
                    out[cand] = d
            if time.perf_counter() > t_end:
                break
        return out

    def inflected(self, word, lang):
        """Looks like a real form of a known word (строящей, порхал): another ending gives known words."""
        if lang not in INFLECTED or len(word) < 5:
            return False
        found = set()
        for k in (1, 2, 3):
            stem = word[:-k]
            if len(stem) < 4:
                break
            for e in INFLECTED[lang]:
                v = stem + e
                if v != word and v not in found and self.z(v, lang) >= 2.0:
                    found.add(v)
                    if len(found) >= 2:
                        return True
        return False

    def noun_form(self, word, lang):
        """A case form of a known noun missing from the word list: имейла, имейлом."""
        for e in NOUN_END.get(lang, ()):
            stem = word[:-len(e)]
            if word.endswith(e) and len(stem) >= 4 and stem[-1] not in VOWELS and self.z(stem, lang) >= 2.0:
                return True
        return False

    def correct(self, word, group, prior=None):
        """Typo fix for a lowercase word typed in `group`: (new_word, lang, info, cost) or None."""
        langs = GROUP_LANGS[group]
        n = len(word)
        if n < 3 or not word.isalpha() or self.known_anywhere(word) or \
                any(self.inflected(word, l) or self.noun_form(word, l) for l in langs):
            return None
        prior = prior or {}
        cands = {}
        for lang in langs:
            for c, cost in self.edits1(word, group).items():
                zc = self.z(c, lang)
                if zc:
                    cands[(c, lang)] = (zc - 2.0 * cost + prior.get(lang, 0.0), zc, cost)
        best = max(cands.items(), key=lambda kv: kv[1][0], default=None)
        if (best is None or best[1][0] < 1.5) and n >= 5:
            for lang in langs:
                for c, cost in self.edits2(word, lang, group).items():
                    zc = self.z(c, lang)
                    s = zc - 2.0 * cost + prior.get(lang, 0.0)
                    if (c, lang) not in cands or cands[(c, lang)][0] < s:
                        cands[(c, lang)] = (s, zc, cost)
        if not cands:
            return None
        ranked = sorted(cands.items(), key=lambda kv: -kv[1][0])
        # the same word in two languages of a group is one candidate
        (c, lang), (s, zc, cost) = ranked[0]
        rivals = [v[0] for (c2, _), v in ranked[1:] if c2 != c]
        margin = s - (rivals[0] if rivals else -99.0)
        need_z = 3.0 if n >= 5 else 4.5
        if n == 3:
            need_z = 5.0
        if zc < need_z or s < 0.5 or margin < 1.0:
            return None
        if zc < 4.0 and self.lm.tri_avg(word, lang) - self.lm.ref[lang] > -0.2:
            return None  # the typed text looks like a normal word of its own (a rare form, a name)
        return c, lang, f"typo {word}->{c} cost {cost:.1f} z {zc:.1f} margin {margin:.1f}", cost

    def suggest(self, word, group, prior=None, n=5):
        """Alt+Backspace: the user says the word is wrong — ranked fixes without the auto-fix thresholds,
        also for words that exist (зочет) and with two edits or a missing space. Lowercase input."""
        langs = GROUP_LANGS[group]
        prior = prior or {}
        cands = {}

        def put(c, s):
            if c != word and s > cands.get(c, -99.0):
                cands[c] = s
        for lang in langs:
            for c, cost in self.edits1(word, group).items():
                zc = self.z(c, lang)
                if zc:
                    put(c, zc - 2.0 * cost + prior.get(lang, 0.0))
            if len(word) >= 4:
                for c, cost in self.edits2(word, lang, group, min_z=2.5, limit=2.6, budget=0.15).items():
                    put(c, self.z(c, lang) - 2.0 * cost + prior.get(lang, 0.0))
            for i in range(1, len(word)):
                a, b = word[:i], word[i:]
                if self._ok_part(a, lang, 3.0) and self._ok_part(b, lang, 3.0):
                    put(a + " " + b, min(self.z(a, lang) or 5.0, self.z(b, lang) or 5.0) - 2.0)
            y = self.yo(word) if lang == "ru" else None
            if y:
                put(y, self.z(y, lang))
        return [c for c, _ in sorted(cands.items(), key=lambda kv: -kv[1])[:n]]

    # --------------------------------------------------------------- ё ---
    def yo(self, word):
        """еще -> ещё for Russian words whose ё-form is clearly the same word."""
        if word in YO_TYPO:
            return YO_TYPO[word]
        if "е" not in word or "ё" in word or word in YO_AMBIGUOUS:
            return None
        z0 = self.z(word, "ru")
        best = None
        for i, ch in enumerate(word):
            if ch == "е":
                v = word[:i] + "ё" + word[i + 1:]
                zv = self.z(v, "ru")
                if zv >= 2.0 and zv >= z0 - 1.2 and (best is None or zv > best[1]):
                    best = (v, zv)
        return best[0] if best else None

    # ----------------------------------------------------------- spaces ---
    def _ok_part(self, w, lang, min_z=3.0):
        if len(w) == 1:
            return w in ONE_LETTER[lang]
        return self.z(w, lang) >= min_z

    def _missing_letter(self, word, lang, min_z=3.5):
        """A known word that is this one with one letter added (голвы -> головы)."""
        letters = set("".join(_ROWS[LANG_GROUP[lang]]))
        for i in range(1, len(word)):
            for ch in letters:
                if self.z(word[:i] + ch + word[i:], lang) >= min_z:
                    return True
        return False

    def split(self, word, lang):
        """Missing space: приветкак -> (привет, как)."""
        if len(word) < 5 or self.known_anywhere(word) or word.startswith(COMPOUND_HEADS):
            return None
        if self._missing_letter(word, lang):
            return None  # голвы is головы with a letter missed, not "гол вы"
        best = None
        for i in range(1, len(word) - 1):
            a, b = word[:i], word[i:]
            if len(b) < 2:
                continue  # приветк is a late space or a typo, not "привет к"
            if self._ok_part(a, lang, 5.0 if len(a) == 2 else 3.5) and \
                    self._ok_part(b, lang, 5.0 if len(b) == 2 else 3.5):
                s = min(self.z(a, lang), self.z(b, lang))
                if max(self.z(a, lang), self.z(b, lang)) < 5.0:
                    continue  # one part should be a common word (как, это, на): валидна is not "вали дна"
                if best is None or s > best[2]:
                    best = (a, b, s)
        return best[:2] if best else None

    def respace(self, prev, cur, lang):
        """Space typed one letter too late or too early, or a stray space inside a word:
        приветк ак -> привет как, приве ткак -> привет как, прив ет -> привет. Lowercase input."""
        zp, zc = self.z(prev, lang), self.z(cur, lang)
        p_ok = self._ok_part(prev, lang, 1.0) or zp > 0
        c_ok = self._ok_part(cur, lang, 1.0) or zc > 0
        if p_ok and c_ok:
            return None
        opts = []
        if len(prev) >= 2:
            # "хочуя я": the letter was typed twice, around the space — drop the stray one, not "хочу яя"
            a, b = prev[:-1], cur if cur == prev[-1] else prev[-1] + cur
            if self._ok_part(a, lang) and self._ok_part(b, lang):
                opts.append(((a, b), min(self.z(a, lang) or 5.0, self.z(b, lang))))
        if len(cur) >= 2:
            a, b = prev + cur[0], cur[1:]
            # "в брико" is not "вб рико": a previous word that is already a word changes only into a common one
            if self._ok_part(a, lang, 4.5 if p_ok else 3.0) and self._ok_part(b, lang):
                opts.append(((a, b), min(self.z(a, lang), self.z(b, lang) or 5.0)))
        if not p_ok and not c_ok:
            j = prev + cur
            if self.z(j, lang) >= 3.0:
                opts.append(((j,), self.z(j, lang)))
        if not opts:
            return None
        opts.sort(key=lambda o: -o[1])
        if len(opts) > 1 and opts[0][1] - opts[1][1] < 0.5:
            return None
        return opts[0][0]
