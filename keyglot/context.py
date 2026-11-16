"""Where is the user typing? Field kind, password flag, text before the caret and the visible
conversation/document, read through UI Automation on a background thread (never in the hook)."""
import re
import threading
import time
from dataclasses import dataclass

from . import winapi as W
from .engine import Ctx

TERMINAL_EXE = {"windowsterminal.exe", "conhost.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "wsl.exe",
                "putty.exe", "mintty.exe", "wezterm-gui.exe", "alacritty.exe", "kitty.exe", "tabby.exe",
                "mobaxterm.exe", "kitty_portable.exe", "openconsole.exe"}
CODE_EXE = {"code.exe", "cursor.exe", "windsurf.exe", "devenv.exe", "pycharm64.exe", "idea64.exe", "rider64.exe",
            "webstorm64.exe", "clion64.exe", "notepad++.exe", "sublime_text.exe", "spyder.exe", "zed.exe"}
SKIP_EXE = {"keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe", "mstsc.exe", "vmconnect.exe",
            "vmware.exe", "virtualboxvm.exe", "parsecd.exe", "steam.exe"}
BROWSER_EXE = {"msedge.exe", "chrome.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe", "arc.exe"}
TERMINAL_CLASSES = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "TermControl", "xterm-helper-textarea")
RUN_TITLES = {"run", "выполнить", "виконати", "uitvoeren"}
ADDRESS_NAMES = re.compile(r"^(to|cc|bcc|aan|kopie|кому|копия|копія|e-?mail|email address|адрес эл.*|"
                           r"username|user name|login|логин|логін|gebruikersnaam)\b", re.I)
PROSE_FILE = re.compile(r"\.(md|txt|rst|tex|org|adoc)\b", re.I)
COMMENT = re.compile(r"(#|//|--|/\*|<!--)")


@dataclass
class FieldInfo:
    hwnd: int = 0
    t: float = 0.0
    exe: str = ""
    title: str = ""
    wclass: str = ""
    password: bool = False
    name: str = ""
    eclass: str = ""
    aid: str = ""
    ctrl: int = 0
    before: str = ""
    visible: str = ""
    uia: bool = False


def classify(fi, rules):
    """Field kind for the engine."""
    rule = rules.get(fi.exe, "auto")
    if rule == "off" or fi.exe in SKIP_EXE or fi.password:
        return "skip"
    if rule == "latin":
        return "path"
    if fi.exe in TERMINAL_EXE or any(c in fi.wclass or c in fi.eclass for c in TERMINAL_CLASSES) or \
            (fi.exe in CODE_EXE and fi.name.lower().startswith("terminal")):
        return "terminal"
    if fi.exe in CODE_EXE:
        if PROSE_FILE.search(fi.title):
            return "prose"
        line = fi.before.rsplit("\n", 1)[-1]
        if COMMENT.search(line) or line.count('"') % 2 == 1:
            return "prose"  # a comment or a string literal: people write prose there
        return "code"
    if fi.exe in BROWSER_EXE and (fi.eclass == "OmniboxViewViews" or fi.aid == "urlbar-input" or
                                  "address and search" in fi.name.lower() or "адресн" in fi.name.lower()):
        return "url"
    if fi.wclass == "#32770" and fi.title.strip().lower() in RUN_TITLES:
        return "path"
    if fi.exe == "explorer.exe" and fi.name.lower().startswith(("address", "адрес", "adres")):
        return "path"
    if ADDRESS_NAMES.match(fi.name.strip()) or re.search(r"email|login|username", fi.aid, re.I):
        return "address"
    return "prose"


def habit_key(fi):
    title = re.sub(r"\(\d+\)|\d+|[•●*]", "", fi.title)
    title = re.sub(r"\s+-\s+(Microsoft​? Edge|Google Chrome|Mozilla Firefox|Brave|Opera|Vivaldi)$", "", title)
    title = re.sub(r"\s+-\s+(Personal|Profile.*|Work)\s*$", "", title)
    return f"{fi.exe}|{title.strip()[:60]}|{fi.name.strip()[:30]}"


class ContextProvider:
    def __init__(self, lm, rules_getter):
        self.lm = lm
        self.rules = rules_getter
        self.current = None
        self._hwnd = None
        self._event = threading.Event()
        self._uia = None
        self._UIA = None
        self._conv_cache = {}
        self.uia_ok = False
        threading.Thread(target=self._run, name="keyglot-context", daemon=True).start()

    def request(self, hwnd):
        self._hwnd = hwnd
        self._event.set()

    def get(self, hwnd, max_age=10.0):
        c = self.current
        if c and c.hwnd == hwnd and time.time() - c.t < max_age:
            return c
        return None

    # ---------------------------------------------------------- thread ---
    def _init_uia(self):
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            try:
                from comtypes.gen import UIAutomationClient as UIA
            except ImportError:
                UIA = comtypes.client.GetModule("UIAutomationCore.dll")
            self._UIA = UIA
            self._uia = comtypes.client.CreateObject(UIA.CUIAutomation._reg_clsid_, interface=UIA.IUIAutomation)
            try:
                u2 = self._uia.QueryInterface(UIA.IUIAutomation2)
                u2.ConnectionTimeout = 1500
                u2.TransactionTimeout = 1500
            except Exception:
                pass
            self.uia_ok = True
        except Exception:
            self._uia = None

    def _run(self):
        self._init_uia()
        while True:
            self._event.wait()
            self._event.clear()
            hwnd = self._hwnd
            try:
                self.current = self.probe(hwnd)
            except Exception:
                self.current = self.basic(hwnd)

    def basic(self, hwnd):
        return FieldInfo(hwnd=hwnd, t=time.time(), exe=W.window_exe(hwnd), title=W.window_title(hwnd),
                         wclass=W.window_class(hwnd), password=W.focus_is_win32_password(hwnd))

    def probe(self, hwnd):
        fi = self.basic(hwnd)
        if not self._uia or fi.exe in SKIP_EXE or fi.password:
            return fi
        UIA = self._UIA
        el = self._uia.GetFocusedElement()
        if not el:
            return fi
        fi.uia = True
        fi.password = fi.password or bool(el.CurrentIsPassword)
        if fi.password:
            return fi
        fi.name = el.CurrentName or ""
        fi.eclass = el.CurrentClassName or ""
        fi.aid = el.CurrentAutomationId or ""
        fi.ctrl = el.CurrentControlType
        fi.before = self._text_before(el)
        key = (hwnd, fi.title)
        cached = self._conv_cache.get(key)
        if cached and time.time() - cached[0] < 60:
            fi.visible = cached[1]
        else:
            fi.visible = self._visible_text(el)
            self._conv_cache = {k: v for k, v in self._conv_cache.items() if time.time() - v[0] < 60}
            self._conv_cache[key] = (time.time(), fi.visible)
        return fi

    def _pattern(self, el, pid, iface):
        try:
            p = el.GetCurrentPattern(pid)
            return p.QueryInterface(iface) if p else None
        except Exception:
            return None

    def _text_before(self, el):
        UIA = self._UIA
        tp = self._pattern(el, 10014, UIA.IUIAutomationTextPattern)
        if tp:
            try:
                sel = tp.GetSelection()
                if sel and sel.Length:
                    r = sel.GetElement(0).Clone()
                    r.MoveEndpointByUnit(0, 0, -400)  # Start, Character
                    return r.GetText(600) or ""
            except Exception:
                pass
        vp = self._pattern(el, 10002, UIA.IUIAutomationValuePattern)
        if vp:
            try:
                return (vp.CurrentValue or "")[-400:]
            except Exception:
                pass
        return ""

    def _visible_text(self, el):
        """Text of the nearest document just before the field (chat history, mail thread), up to 3000 characters.
        Never GetVisibleRanges: Chromium computes it for the whole page (2+ s on a chat), and while it answers,
        its window does not draw the letters being typed. Moving a range back from the field takes ~50 ms."""
        UIA = self._UIA
        walker = self._uia.ControlViewWalker
        node = el
        for _ in range(14):
            try:
                if node.CurrentControlType == 50030:  # Document
                    tp = self._pattern(node, 10014, UIA.IUIAutomationTextPattern)
                    if tp:
                        return self._text_back(tp, el)
                node = walker.GetParentElement(node)
                if not node:
                    break
            except Exception:
                break
        return ""

    @staticmethod
    def _text_back(tp, el):
        for anchor in ("field", "end"):
            try:
                if anchor == "field":
                    r = tp.RangeFromChild(el)
                    r.MoveEndpointByRange(1, r, 0)  # End = Start: the text before the field
                else:
                    r = tp.DocumentRange
                    r.MoveEndpointByRange(0, r, 1)  # Start = End
                r.MoveEndpointByUnit(0, 0, -3000)   # Start, Character
                text = r.GetText(4000) or ""
                if len(text.strip()) > 20:
                    return text[-3000:]
            except Exception:
                continue
        return ""

    # ----------------------------------------------------------- build ---
    def build_ctx(self, fi, rules):
        kind = classify(fi, rules)
        before = fi.before
        # drop the word being typed (it may already be in the field)
        before_words = before.rsplit(None, 1)[0] if " " in before.strip() else ""
        doc, doc_n = self.lm.text_languages(before_words) if before_words else ({}, 0)
        conv, conv_n = self.lm.text_languages(fi.visible, 150) if fi.visible else ({}, 0)
        url_like = False
        if kind == "url":
            head = before.strip()
            url_like = not head or (" " not in head and bool(re.search(r"[./:]", head)))
        return Ctx(exe=fi.exe, kind=kind, key=habit_key(fi), doc=doc, doc_n=doc_n, conv=conv, conv_n=conv_n,
                   url_like=url_like)
