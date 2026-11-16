"""Keyboard hook, word buffer, corrections, Backspace undo. SendInput runs on a worker thread."""
import ctypes
import os
import queue
import threading
import time
from ctypes import wintypes as w

from . import config as C
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
        if not keep_prev:
            self.prev = None
            self.last_corr = None

    def switch_layout(self, hwnd, lang):
        hkl = self.E.L.hkls.get(lang)
        if hkl:
            self.our_switch_hkl = hkl
            self.expect = (hwnd, hkl)
            W.request_layout(hwnd, hkl)

    def event(self, **ev):
        if self.cfg.get("log_events", True):
            C.log_event(**ev)

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
                self.set_enabled(not self.enabled)
            else:
                self.manual_convert()
            return True
        if not self.enabled or W.key_down(W.VK_CONTROL) or W.key_down(W.VK_MENU) or \
                W.key_down(W.VK_LWIN) or W.key_down(W.VK_RWIN):
            self.reset()
            return False
        hwnd = W.user32.GetForegroundWindow()
        if hwnd != self.hwnd:
            self.hwnd = hwnd
            self.exe = W.window_exe(hwnd)
            self.reset()
        if self.exe in SKIP_EXE or self.cfg["rules"].get(self.exe) == "off":
            return False

        if vk == W.VK_BACK:
            if self.last_corr and not self.keys:
                return self.undo()
            self.last_corr = None
            if self.keys:
                self.keys.pop()
            else:
                self.prev = None
            return False
        self.last_corr = None

        if vk in WORD_VKS or vk in DIGIT_VKS:
            if not self.keys:
                self.ctxp.request(hwnd)  # read the field while the word is being typed
            caps = W.user32.GetKeyState(W.VK_CAPITAL) & 1
            self.keys.append((vk, shift, caps))
            if vk in DIGIT_VKS and not shift:
                self.nonword = True
            return False
        if vk == W.VK_SPACE or (vk == W.VK_RETURN and self.cfg.get("correct_on_enter", True)):
            return self.on_boundary(vk)
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
        if not keys:
            self.prev = None
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
            return False
        ctx = self._ctx(hwnd)
        ctx.user_switched = user_switched
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
        self.event(event="fix", exe=ctx.exe, kind=ctx.kind, frm=orig, to=out, reason=reason,
                   doc=_top(ctx.doc), conv=_top(ctx.conv), key=ctx.key, hkl=_hex(hkl))
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
        self.event(event="undo", exe=c["exe"], kind=c["kind"], frm=c["new"], to=c["orig"], key=c["key"])
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
        self.event(event="manual", exe=self.exe, frm=typed, to=best[0])
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
