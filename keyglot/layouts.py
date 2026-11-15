"""Key -> character tables of the installed layouts, grouped as lat / ru / uk."""
import ctypes

GROUP_LANGS = {"lat": ("en", "nl"), "ru": ("ru",), "uk": ("uk",)}
LANG_GROUP = {"en": "lat", "nl": "lat", "ru": "ru", "uk": "uk"}

WORD_VKS = set(range(0x41, 0x5B)) | {0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xDB, 0xDC, 0xDD, 0xDE, 0xE2}
DIGIT_VKS = set(range(0x30, 0x3A))
TRAIL_PUNCT_VKS = {0xBC, 0xBE, 0xBF, 0xBA, 0xDE}  # , . / ; '  -> letters in Cyrillic layouts

# Built-in tables (used for tests and when Win32 is not available).
_VK_ORDER = [0xC0] + list(range(0x31, 0x3A)) + [0x30, 0xBD, 0xBB] + [ord(c) for c in "QWERTYUIOP"] + \
    [0xDB, 0xDD, 0xDC] + [ord(c) for c in "ASDFGHJKL"] + [0xBA, 0xDE] + [ord(c) for c in "ZXCVBNM"] + \
    [0xBC, 0xBE, 0xBF, 0xE2]
_STATIC = {
    "lat": ("`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./\\",
            "~!@#$%^&*()_+QWERTYUIOP{}|ASDFGHJKL:\"ZXCVBNM<>?|"),
    "ru": ("ё1234567890-=йцукенгшщзхъ\\фывапролджэячсмитьбю.\\",
           "Ё!\"№;%:?*()_+ЙЦУКЕНГШЩЗХЪ/ФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,/"),
    "uk": ("'1234567890-=йцукенгшщзхї\\фівапролджєячсмитьбю.ґ",
           "₴!\"№;%:?*()_+ЙЦУКЕНГШЩЗХЇ/ФІВАПРОЛДЖЄЯЧСМИТЬБЮ,Ґ"),
}
_STATIC_HKL = {"en": 0x04090409, "nl": 0x04130413, "ru": 0x04190419, "uk": 0x04220422}


class Layouts:
    def __init__(self, static=False):
        self.hkls = {}      # lang -> hkl
        self.tables = {}    # group -> {(vk, shift, caps): (char, dead)}
        self.compose = {}   # group -> {(dead_vk, dead_shift, vk, shift): text}
        if static:
            self._build_static()
            return
        from . import winapi
        self._w = winapi
        for hkl in winapi.installed_layouts():
            lang = winapi.hkl_lang(hkl)
            if lang and lang not in self.hkls:
                self.hkls[lang] = hkl
        for group, langs in GROUP_LANGS.items():
            hkl = next((self.hkls[l] for l in langs if l in self.hkls), None)
            if hkl:
                self.tables[group] = self._table(hkl)
                self.compose[group] = self._compose(hkl, self.tables[group])

    def _build_static(self):
        self.hkls = dict(_STATIC_HKL)
        for group, (lo, up) in _STATIC.items():
            t = {}
            for vk, a, b in zip(_VK_ORDER, lo, up):
                for caps in (0, 1):
                    for shift, ch in ((0, a), (1, b)):
                        if caps and ch.isalpha():
                            ch = ch.swapcase()
                        t[(vk, shift, caps)] = (ch, False)
            self.tables[group] = t
            self.compose[group] = {}

    def _char(self, vk, shift, caps, hkl, flags=4):
        u = self._w.user32
        state = (ctypes.c_char * 256)()
        if shift:
            state[0x10] = b"\x80"
        if caps:
            state[0x14] = b"\x01"
        buf = ctypes.create_unicode_buffer(8)
        sc = u.MapVirtualKeyExW(vk, 0, hkl)
        r = u.ToUnicodeEx(vk, sc, state, buf, 8, flags, hkl)
        if r < 0:
            return buf.value[:1], True
        return buf.value[:r], False

    def _table(self, hkl):
        t = {}
        for vk in WORD_VKS | DIGIT_VKS:
            for shift in (0, 1):
                for caps in (0, 1):
                    t[(vk, shift, caps)] = self._char(vk, shift, caps, hkl)
        return t

    def _compose(self, hkl, table):
        # Dead key + letter (US-International: ' + e = é), computed on our own thread's key state.
        out = {}
        deads = [(vk, s) for (vk, s, c), (ch, dead) in table.items() if dead and not c]
        for dvk, ds in deads:
            for vk in WORD_VKS:
                for s in (0, 1):
                    self._char(dvk, ds, 0, hkl, flags=0)
                    text, _ = self._char(vk, s, 0, hkl, flags=0)
                    out[(dvk, ds, vk, s)] = text
                    self._char(0x20, 0, 0, hkl, flags=0)
        return out

    def render(self, keys, group, composed=False):
        """Text the keys produce in group; composed=True applies dead-key composition,
        i.e. what the application really shows when this group is active."""
        t = self.tables[group]
        out, pending = [], None
        for vk, shift, caps in keys:
            ch, dead = t.get((vk, shift, caps), ("", False))
            if composed and pending:
                out.append(self.compose[group].get((pending[0], pending[1], vk, shift), pending[2] + ch))
                pending = None
                continue
            if composed and dead:
                pending = (vk, shift, ch)
                continue
            out.append(ch)
        if pending:
            out.append(pending[2])
        return "".join(out)

    def is_dead(self, key, group):
        return self.tables[group].get(key, ("", False))[1]

    def has_dead(self, keys, group):
        return any(self.is_dead(k, group) for k in keys)

    def keys_for(self, text, group):
        """Reverse mapping for simulations: text typed with group active -> keys."""
        rev = {}
        for (vk, shift, caps), (ch, dead) in sorted(self.tables[group].items()):
            if not caps and ch and ch not in rev:
                rev[ch] = (vk, shift, 0)
        return [rev[c] for c in text]
