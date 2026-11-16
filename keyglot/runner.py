"""Keyboard hook, word buffer, corrections, Backspace undo. SendInput runs on a worker thread."""
import ctypes
import os
import queue
import threading
import time
from ctypes import wintypes as w

from . import config as C
from . import inputlog as IL
from . import winapi as W
from .context import ContextProvider, SKIP_EXE, TERMINAL_EXE, classify, FieldInfo
from .engine import Ctx, LATIN_KINDS
from .layouts import DIGIT_VKS, LANG_GROUP, WORD_VKS

MODIFIER_VKS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, W.VK_CAPITAL}


class Runner:
    def __init__(self, engine, cfg, accept_injected=False):
        self.E = engine
        self.cfg = cfg
        self.accept_injected = accept_injected
        self.ctxp = ContextProvider(engine.lm, lambda: self.cfg["rules"])
        self.keys = []
        self.nonword = False
        self.prev = None
        self.last_corr = None
        self.hwnd = None
        self.exe = ""
        self.last_hkl = None
        self.our_switch_hkl = None
        self.expect = None            # (hwnd, hkl) we asked for: checked at the next word
        self.blocked_up = set()
        self.jobs = queue.Queue()
        self.dirty = False
        self.thread_id = None
        self.on_state_change = None   # callback for the tray (enabled flag)
        self._cfg_mtime = 0
        self._prune_t = 0
        self.tail = ""                # text typed in this field so far (for the detailed log)
        self.erased = ""              # what the user erased with Backspace before the current word
        self.bs_word = 0              # Backspaces inside the current word
        self.sess = None              # the current input of the detailed log (inputlog.Session)
        self.vgroup = None            # layout group the trace renders keys in

    # ------------------------------------------------------------ utils ---
    @property
    def enabled(self):
        return self.cfg.get("enabled", True)

    def set_enabled(self, value):
        self.cfg["enabled"] = bool(value)
        C.save_config(self.cfg)
        self._cfg_mtime = _mtime(C.CONFIG_FILE)
        if self.cfg.get("sound"):
            W.kernel32.Beep(880 if value else 440, 90)
        if self.on_state_change:
            self.on_state_change()

    def reset(self, keep_prev=False):
        self.keys = []
        self.nonword = False
        self.bs_word = 0
        if not keep_prev:
            self.prev = None
            self.last_corr = None
            self.tail = ""
            self.erased = ""

    def switch_layout(self, hwnd, lang):
        hkl = self.E.L.hkls.get(lang)
        if hkl:
            self.our_switch_hkl = hkl
            self.expect = (hwnd, hkl)
            W.request_layout(hwnd, hkl)

    def event(self, **ev):
        if self.cfg.get("log_events", True):
            C.log_event(**ev)

    def private(self, hwnd):
        return IL.excluded(self.cfg.get("log_exclude"), self.exe, W.window_title(hwnd) if hwnd else "")

    # -------------------------------------------------------- input log ---
    def _sess(self, hwnd):
        """The current input of the detailed log; a new one starts on the first key."""
        if not self.cfg.get("log_verbose"):
            self.sess = None
            return None
        s = self.sess
        if s:
            idle = time.time() - s.t1 > IL.IDLE
            if s.hwnd != hwnd or idle or len(s.trace) > IL.MAX_KEYS:
                self.flush("window" if s.hwnd != hwnd else "idle" if idle else "long")
                s = None
        if s is None:
            s = self.sess = IL.Session(hwnd, self.exe, W.window_title(hwnd) if hwnd else "", self.tail[-60:])
            self.vgroup = LANG_GROUP.get(W.hkl_lang(W.window_hkl(hwnd)))
        return s

    def vkey(self, hwnd, tok):
        s = self._sess(hwnd)
        if s:
            s.key(tok)
        return s

    def _vctx(self, hwnd, kind, layout, ctx=None):
        """Field context of the input; text typed after a click into another field starts a new input."""
        s = self.sess
        if not s:
            return None
        fi = self.ctxp.get(hwnd)
        field = fi.name if fi else None
        title = W.window_title(hwnd)
        new_field = s.click_at is not None and s.field and field and field != s.field
        if new_field or title != s.title:  # another field, or another tab of the browser
            rest = s.split_at_click() if s.click_at is not None else []
            self.flush("click" if new_field else "title")
            s = self._sess(hwnd)
            s.trace, s.before = rest + s.trace, ""
        s.click_at = None
        s.context(kind, layout, field, _top(ctx.doc) if ctx else None, _top(ctx.conv) if ctx else None)
        return s

    def flush(self, end, on_hook=True):
        """Write the current input, unless it was a password field or an excluded window."""
        s, self.sess = self.sess, None
        if not s or not s.trace:
            return
        if on_hook and self.keys and self.vgroup:
            s.text += self.E.L.render(self.keys, self.vgroup, composed=True)  # a word not ended by a space
        if s.kind is None:  # no word ended, e.g. a password and Tab
            if on_hook:
                kind = self._ctx(s.hwnd).kind
            else:
                fi = self.ctxp.get(s.hwnd, 600)
                kind = classify(fi, self.cfg["rules"]) if fi else "skip"
            s.private = s.private or kind == "skip"
            s.kind = kind
        excl = self.cfg.get("log_exclude")
        if s.private or IL.excluded(excl, s.exe, s.title) or IL.excluded(excl, s.exe, W.window_title(s.hwnd)):
            return
        IL.write(**s.event(end))

    def _tail(self, drop, add):
        """Edit the text known before the caret (and the current input's text)."""
        self.tail = (self.tail[:max(0, len(self.tail) - drop)] + add)[-200:]
        if self.sess:
            self.sess.edit(drop, add)

    # ----------------------------------------------------------- worker ---
    def _worker(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            try:
                _, hwnd, n_back, text, bvk, lang = job
                if lang:
                    self.switch_layout(hwnd, lang)
                W.send_rewrite(n_back, text, bvk)
            except Exception as e:
                self.event(event="error", where="worker", error=repr(e))

    def _housekeeping(self):
        while True:
            time.sleep(2)
            try:
                m = _mtime(C.CONFIG_FILE)
                if m and m != self._cfg_mtime:
                    self._cfg_mtime = m
                    self.cfg.update(C.load_config())
                    if self.on_state_change:
                        self.on_state_change()
                for cmd in C.pop_pending():
                    if cmd.get("op") == "remove_exception":
                        self.E.remove_exception(cmd.get("key", ""))
                        self.dirty = True
                    elif cmd.get("op") == "forget_app":
                        self.E.state["apps"].pop(cmd.get("exe", ""), None)
                        self.dirty = True
                if self.dirty:
                    self.dirty = False
                    C.save_state(self.E.state)
                s = self.sess
                if s and time.time() - s.t1 > IL.IDLE:
                    self.flush("idle", on_hook=False)
                if time.time() - self._prune_t > 3600:
                    self._prune_t = time.time()
                    IL.prune(self.cfg.get("log_days", 14))
            except Exception as e:
                self.event(event="error", where="housekeeping", error=repr(e))

    # ------------------------------------------------------------- hook ---
    def on_key(self, vk, down, injected, extra):
        """Return True to swallow the key."""
        if extra == W.MAGIC or (injected and not self.accept_injected):
            return False
        if not down:
            if vk in self.blocked_up:
                self.blocked_up.discard(vk)
                return True
            return False
        if vk in MODIFIER_VKS:
            return False
        shift = 1 if W.key_down(W.VK_SHIFT) else 0
        if vk == W.VK_PAUSE:
            self.blocked_up.add(vk)
            if shift:
                self.flush("off")
                self.set_enabled(not self.enabled)
            else:
                self.manual_convert()
            return True
        ctrl, alt = W.key_down(W.VK_CONTROL), W.key_down(W.VK_MENU)
        if not self.enabled or ctrl or alt or W.key_down(W.VK_LWIN) or W.key_down(W.VK_RWIN):
            s = self.sess
            if s and self.enabled and (ctrl or alt) and W.user32.GetForegroundWindow() == s.hwnd:
                s.key(IL.key_name(vk, shift, ctrl, alt))  # Ctrl+Backspace, Ctrl+Z, Ctrl+V ...
                s.click_at = len(s.trace)                  # Ctrl+Tab, Ctrl+L ... may leave the field
                if vk == W.VK_RETURN:
                    self.flush("enter")
            self.reset()
            return False
        hwnd = W.user32.GetForegroundWindow()
        if hwnd != self.hwnd:
            self.flush("window")
            self.hwnd = hwnd
            self.exe = W.window_exe(hwnd)
            self.reset()
        if self.exe in SKIP_EXE or self.cfg["rules"].get(self.exe) == "off":
            return False

        if vk == W.VK_BACK:
            if self.last_corr and not self.keys:
                return self.undo()
            self.last_corr = None
            s = self.vkey(hwnd, "⌫")
            if self.keys:
                self.keys.pop()
                self.bs_word += 1
            else:
                self.prev = None
                if self.tail:
                    self.erased = self.tail[-1] + self.erased
                    self.tail = self.tail[:-1]
                if s and not s.moved:
                    s.edit(1, "")
            return False
        self.last_corr = None

        if vk in WORD_VKS or vk in DIGIT_VKS:
            if not self.keys:
                self.ctxp.request(hwnd)  # read the field while the word is being typed
            caps = W.user32.GetKeyState(W.VK_CAPITAL) & 1
            self.keys.append((vk, shift, caps))
            if self.cfg.get("log_verbose"):
                s = self._sess(hwnd)
                if len(self.keys) == 1:  # the user may have switched the layout since the last word
                    self.vgroup = LANG_GROUP.get(W.hkl_lang(W.window_hkl(hwnd))) or self.vgroup
                s.key(self.E.L.render([(vk, shift, caps)], self.vgroup) if self.vgroup else "?")
            if vk in DIGIT_VKS and not shift:
                self.nonword = True
            return False
        if vk == W.VK_SPACE or (vk == W.VK_RETURN and self.cfg.get("correct_on_enter", True)):
            r = self.on_boundary(vk)
            if vk == W.VK_RETURN and not shift:
                self.flush("enter")
            return r
        s = self.vkey(hwnd, IL.key_name(vk, shift)) if self.cfg.get("log_verbose") else None
        if s and vk in (W.VK_RETURN, W.VK_TAB, 0x1B) and not (vk == W.VK_RETURN and shift):
            self.flush({W.VK_RETURN: "enter", W.VK_TAB: "tab"}.get(vk, "esc"))
        elif s and vk in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28):
            s.moved = True
        self.reset()  # arrows, Home, End, Delete, Esc, Tab, F-keys ...
        return False

    def _ctx(self, hwnd):
        fi = self.ctxp.get(hwnd)
        if fi is None:
            fi = FieldInfo(hwnd=hwnd, exe=self.exe, title=W.window_title(hwnd), wclass=W.window_class(hwnd),
                           password=W.focus_is_win32_password(hwnd))
            ctx = Ctx(exe=self.exe, kind=classify(fi, self.cfg["rules"]))
        else:
            ctx = self.ctxp.build_ctx(fi, self.cfg["rules"])
        return ctx

    def on_boundary(self, bvk):
        keys, self.keys = self.keys, []
        bs, self.bs_word = self.bs_word, 0
        erased, self.erased = self.erased, ""
        bch = "\n" if bvk == W.VK_RETURN else " "
        btok = " " if bvk == W.VK_SPACE else IL.key_name(bvk, W.key_down(W.VK_SHIFT))
        if not keys:
            self.prev = None
            self.vkey(self.hwnd, btok)
            self._tail(0, bch)
            return False
        hwnd = self.hwnd
        hkl = W.window_hkl(hwnd)
        active_lang = W.hkl_lang(hkl)
        active_group = LANG_GROUP.get(active_lang)
        user_switched = bool(self.last_hkl and hkl != self.last_hkl and hkl != self.our_switch_hkl)
        self.last_hkl = hkl
        if self.expect and self.expect[0] == hwnd:
            if hkl != self.expect[1]:
                self.event(event="switch_missed", exe=self.exe, want=_hex(self.expect[1]), got=_hex(hkl),
                           top=_hex(W.thread_hkl(hwnd)))
            self.expect = None
        if self.nonword or not active_group:
            self.nonword = False
            self.prev = None
            s = self.vkey(hwnd, btok)
            if active_group and s:
                typed = self.E.L.render(keys, active_group, composed=True)
                kind = self._ctx(hwnd).kind
                s = self._vctx(hwnd, kind, active_lang)
                if kind != "skip":
                    s.word(typed, typed, {"reason": "has digits"}, bs, erased)
                    self._tail(0, typed + bch)
                    return False
            self.tail = ""
            return False
        ctx = self._ctx(hwnd)
        ctx.user_switched = user_switched
        s = self._vctx(hwnd, ctx.kind, active_lang, ctx)
        self.vgroup = active_group
        if self.prev and self.prev["hwnd"] == hwnd and time.time() - self.prev["t"] < 60:
            ctx.sticky = self.prev["lang"]
        d = self.E.decide(keys, active_group, ctx)

        if d["action"] == "switch":
            self.switch_layout(hwnd, d["lang"])
            self.our_switch_hkl = self.E.L.hkls.get(d["lang"])
            self.last_hkl = self.our_switch_hkl
            self.event(event="switch", exe=ctx.exe, kind=ctx.kind, to=d["lang"], word=d.get("typed"))
            d["action"] = "keep"
        lang = d.get("lang")
        if d["action"] != "rewrite":
            if lang and d.get("known") and ctx.kind not in LATIN_KINDS:
                self.E.learn(ctx, lang)
                self.dirty = True
            typed = d.get("typed", "")
            n_back, out, orig, kids, switch_to, reason = len(typed), typed, typed, [d.get("key_id", "")], None, ""
        else:
            typed, new = d["typed"], d["text"]
            n_back, out, orig, kids, switch_to, reason = len(typed), new, typed, [d["key_id"]], d["lang"], d["reason"]
        p = self.prev
        prev_ok = bool(p and p["hwnd"] == hwnd and p["boundary"] == W.VK_SPACE and time.time() - p["t"] < 30
                       and ctx.kind not in LATIN_KINDS)
        if d["action"] == "rewrite" and prev_ok:
            r = self.E.recheck_previous(p["keys"], p["group"], d["lang"])
            if r:
                n_back += len(r["typed"]) + 1
                out = r["text"] + " " + new
                orig = r["typed"] + " " + typed
                kids.append(r["key_id"])
                prev_ok = False
        head, word = (out.rsplit(" ", 1) + [""])[:2] if " " in out else ("", out)
        pol = None
        if ctx.kind == "prose" and lang and d.get("reason") != "exception" and word and \
                (self.cfg.get("fix_typos", True) or self.cfg.get("fix_yo", True) or self.cfg.get("fix_spaces", True)):
            opts = {"typos": self.cfg.get("fix_typos", True), "yo": self.cfg.get("fix_yo", True),
                    "spaces": self.cfg.get("fix_spaces", True)}
            pr = p.get("raw") if prev_ok and p.get("raw") else None
            pol = self.E.polish(word, lang, pr, opts, kid=kids[0], prev_kid=p.get("kid", "") if pr else "")
        two = len(kids) > 1
        if pol:
            if pol["prev"] is not None:
                n_back += len(p["shown"]) + 1
                orig = p["shown"] + " " + orig
                out = pol["prev"] + (" " + pol["text"] if pol["text"] else "")
                kids = [f'{p.get("kid", "")} {kids[0]}']
                two = True
            else:
                out = (head + " " if head else "") + pol["text"]
            reason = (reason + "; " if reason else "") + pol["reason"]
        if out == orig:
            if s:
                s.key(btok)
            if ctx.kind == "skip":
                self.tail = ""
            else:
                if s:
                    s.word(orig, out, d, bs, erased)
                self._tail(0, out + bch)
            self.prev = {"keys": keys, "hwnd": hwnd, "group": d.get("group", active_group), "boundary": bvk,
                         "lang": lang or ctx.sticky, "t": time.time(), "raw": typed, "shown": typed,
                         "kid": d.get("key_id", "")}
            return False

        self.blocked_up.add(bvk)
        self.jobs.put(("rewrite", hwnd, n_back, out, bvk, switch_to))
        if switch_to:
            self.last_hkl = self.E.L.hkls.get(switch_to)
        self.E.learn(ctx, lang)
        self.dirty = True
        if not self.private(hwnd):
            self.event(event="fix", exe=ctx.exe, kind=ctx.kind, frm=orig, to=out, reason=reason,
                       doc=_top(ctx.doc), conv=_top(ctx.conv), key=ctx.key, hkl=_hex(hkl))
        d["reason"] = reason
        if s:
            s.word(orig, out, d, bs, erased)
            s.key(("{→" if orig == typed else "{" + orig + "→") + out + "}" + btok)
            if switch_to:
                self.vgroup = LANG_GROUP.get(switch_to, self.vgroup)
        self._tail(n_back - len(typed), out + bch)
        self.last_corr = None if bvk == W.VK_RETURN else {
            "orig": orig, "new": out, "bvk": bvk, "hwnd": hwnd, "lang": active_lang, "kids": kids,
            "exe": ctx.exe, "kind": ctx.kind, "key": ctx.key}
        shown = out.rsplit(" ", 1)[-1]
        self.prev = None if two else {
            "keys": keys, "hwnd": hwnd, "group": d.get("group", active_group), "boundary": bvk, "lang": lang,
            "t": time.time(), "raw": new if d["action"] == "rewrite" else typed, "shown": shown,
            "kid": kids[0]}
        return True

    def undo(self):
        c, self.last_corr = self.last_corr, None
        self.blocked_up.add(W.VK_BACK)
        self.jobs.put(("rewrite", c["hwnd"], len(c["new"]) + 1, c["orig"], c["bvk"], c["lang"]))
        for k in c["kids"]:
            self.E.add_exception(k)
        self.dirty = True
        self.prev = None
        if not self.private(c["hwnd"]):
            self.event(event="undo", exe=c["exe"], kind=c["kind"], frm=c["new"], to=c["orig"], key=c["key"])
        bch = "\n" if c["bvk"] == W.VK_RETURN else " "
        s = self.vkey(c["hwnd"], "⌫{undo}")
        if s:
            s.n["undo"] += 1
            if s.text.endswith(c["new"] + bch):
                s.text = s.text[:-(len(c["new"]) + 1)] + c["orig"] + bch
            self.vgroup = LANG_GROUP.get(c["lang"], self.vgroup)
        if self.tail.endswith(c["new"] + bch):
            self.tail = self.tail[:-(len(c["new"]) + 1)] + c["orig"] + bch
        return True

    def manual_convert(self):
        """Pause: convert the current (or just finished) word to the best other layout."""
        hwnd = self.hwnd or W.user32.GetForegroundWindow()
        ag = LANG_GROUP.get(W.hkl_lang(W.window_hkl(hwnd)))
        if not ag:
            return
        if self.keys:
            keys, tail, bvk = self.keys, 0, None
        elif self.prev and self.prev["hwnd"] == hwnd:
            keys, tail, bvk = self.prev["keys"], 1, self.prev["boundary"]
            ag = self.prev["group"] or ag
        else:
            return
        typed = self.E.L.render(keys, ag, composed=True)
        best = None
        for g, lang, text, core, s, known in self.E.candidates(keys):
            if g != ag and (best is None or s > best[1]):
                best = (text, s, lang)
        if not best:
            return
        self.jobs.put(("rewrite", hwnd, len(typed) + tail, best[0], bvk if tail else None, best[2]))
        if not self.private(hwnd):
            self.event(event="manual", exe=self.exe, frm=typed, to=best[0])
        bch = "\n" if bvk == W.VK_RETURN else " "
        s = self.vkey(hwnd, "[Pause]{" + typed + "→" + best[0] + "}")
        if s:
            s.n["manual"] += 1
            self.vgroup = LANG_GROUP.get(best[2], self.vgroup)
        if not tail:
            self._tail(0, best[0])  # the word in progress, now converted
        else:
            if self.tail.endswith(typed + bch):
                self.tail = self.tail[:-(len(typed) + 1)] + best[0] + bch
            if s and s.text.endswith(typed + bch):
                s.text = s.text[:-(len(typed) + 1)] + best[0] + bch
        self.keys = []
        self.prev = None

    def on_foreground(self, hwnd):
        if not self.cfg.get("preswitch") or not self.enabled or not hwnd:
            return
        exe = W.window_exe(hwnd)
        if exe in SKIP_EXE or exe in TERMINAL_EXE or self.cfg["rules"].get(exe, "auto") != "auto":
            return
        fi = FieldInfo(exe=exe, title=W.window_title(hwnd))
        from .context import habit_key
        lang = self.E.preferred_lang(habit_key(fi), exe)
        if not lang:
            return
        cur = W.hkl_lang(W.window_hkl(hwnd))
        if cur and LANG_GROUP.get(cur) != LANG_GROUP[lang]:
            self.switch_layout(hwnd, lang)
            self.event(event="preswitch", exe=exe, to=lang)

    # -------------------------------------------------------------- run ---
    def start(self):
        threading.Thread(target=self._worker, name="keyglot-worker", daemon=True).start()
        threading.Thread(target=self.E.S.warm, name="keyglot-warm", daemon=True).start()
        threading.Thread(target=self._housekeeping, name="keyglot-house", daemon=True).start()
        ready = threading.Event()
        threading.Thread(target=self._hook_thread, args=(ready,), name="keyglot-hook", daemon=True).start()
        ready.wait(5)

    def stop(self):
        if self.thread_id:
            W.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)  # WM_QUIT
        try:
            C.save_state(self.E.state)
        except OSError:
            pass

    def _hook_thread(self, ready):
        self.thread_id = W.kernel32.GetCurrentThreadId()

        @W.HOOKPROC
        def kb_proc(code, wparam, lparam):
            if code == 0:
                k = ctypes.cast(lparam, ctypes.POINTER(W.KBDLLHOOKSTRUCT)).contents
                try:
                    if self.on_key(k.vkCode, wparam in (0x100, 0x104), bool(k.flags & 0x10), k.dwExtraInfo):
                        return 1
                except Exception as e:
                    self.event(event="error", where="hook", error=repr(e))
                    self.reset()
            return W.user32.CallNextHookEx(None, code, wparam, lparam)

        @W.HOOKPROC
        def mouse_proc(code, wparam, lparam):
            if code == 0 and wparam in (0x201, 0x204, 0x207):  # a click may move the caret
                s = self.sess
                if s:
                    s.key("[click]")
                    s.moved = True
                    s.click_at = len(s.trace)
                self.reset()
            return W.user32.CallNextHookEx(None, code, wparam, lparam)

        @W.WINEVENTPROC
        def fg_proc(hook, event, hwnd, obj, child, thread, t):
            try:
                self.on_foreground(hwnd)
            except Exception as e:
                self.event(event="error", where="foreground", error=repr(e))

        self._procs = (kb_proc, mouse_proc, fg_proc)
        h1 = W.user32.SetWindowsHookExW(13, kb_proc, None, 0)
        h2 = W.user32.SetWindowsHookExW(14, mouse_proc, None, 0)
        W.user32.SetWinEventHook(3, 3, None, fg_proc, 0, 0, 0)
        self.event(event="start", layouts=sorted(self.E.L.hkls), uia=self.ctxp.uia_ok, hook=bool(h1))
        ready.set()
        msg = w.MSG()
        while W.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            W.user32.TranslateMessage(ctypes.byref(msg))
            W.user32.DispatchMessageW(ctypes.byref(msg))
        W.user32.UnhookWindowsHookEx(h1)
        W.user32.UnhookWindowsHookEx(h2)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def _hex(hkl):
    return f"{(hkl or 0) & 0xFFFFFFFF:08x}"


def _top(shares):
    if not shares:
        return None
    k = max(shares, key=shares.get)
    return f"{k}:{shares[k]:.0%}"
