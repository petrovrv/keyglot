"""Tray icon (shows the layout of the active window), menu, update loop."""
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

import pystray
from PIL import Image, ImageDraw, ImageFont

from . import __version__
from . import config as C
from . import updater
from . import winapi as W
from .i18n import t

COLORS = {"en": (37, 99, 235), "nl": (234, 88, 12), "ru": (124, 58, 237), "uk": (13, 148, 136)}
GRAY = (120, 120, 120)


def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def badge(lang, paused=False, size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = GRAY if paused or lang not in COLORS else COLORS[lang]
    d.rounded_rectangle((2, 6, size - 3, size - 7), radius=12, fill=color + (255,))
    text = (lang or "··").upper()[:2]
    f = _font(int(size * 0.5))
    box = d.textbbox((0, 0), text, font=f)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    d.text((x, y), text, font=f, fill=(255, 255, 255, 255))
    if paused:
        d.line((10, size - 12, size - 10, 12), fill=(255, 255, 255, 255), width=5)
    return img


def self_command(*args):
    if C.frozen():
        return [sys.executable, *args]
    return [sys.executable, "-m", "keyglot", *args]


def report_url():
    evs = [e for e in C.read_events(300) if e.get("event") in ("fix", "undo", "manual", "error")][-15:]
    lines = [f"Keyglot {__version__}, Windows {platform.version()}", "", "What happened:", "", "",
             "Last events (check before sending, remove anything private):", "```"]
    for e in evs:
        lines.append(f"{e.get('t')} {e.get('event')} {e.get('exe', '')} {e.get('kind', '')} "
                     f"{e.get('frm', '')!r} -> {e.get('to', '')!r} {e.get('error', '')}")
    lines.append("```")
    q = urllib.parse.urlencode({"title": "Problem: ", "body": "\n".join(lines)[:6000]})
    return f"https://github.com/{C.REPO}/issues/new?{q}"


class Tray:
    def __init__(self, runner):
        self.R = runner
        self.lang = None
        self.icon = pystray.Icon("Keyglot", badge(None), f"Keyglot {__version__}", menu=self._menu())
        runner.on_state_change = self.refresh
        self._stop = False

    def _menu(self):
        M = pystray.MenuItem
        return pystray.Menu(
            M(f"Keyglot {__version__}", None, enabled=False),
            M(t("enabled"), lambda: self.R.set_enabled(not self.R.enabled), checked=lambda i: self.R.enabled),
            M(t("correct_on_enter"), self._toggle("correct_on_enter"),
              checked=lambda i: self.R.cfg.get("correct_on_enter", True)),
            pystray.Menu.SEPARATOR,
            M(t("settings"), self.open_settings, default=True),
            M(t("open_log"), lambda: os.startfile(C.EVENTS_FILE) if os.path.exists(C.EVENTS_FILE) else None),
            M(t("check_updates"), lambda: threading.Thread(target=self.update_once, args=(True,), daemon=True).start()),
            M(t("report"), lambda: webbrowser.open(report_url())),
            pystray.Menu.SEPARATOR,
            M(t("exit"), self.quit),
        )

    def _toggle(self, key):
        def f():
            self.R.cfg[key] = not self.R.cfg.get(key, True)
            C.save_config(self.R.cfg)
        return f

    def open_settings(self):
        subprocess.Popen(self_command("--settings"), creationflags=0x08000000)  # CREATE_NO_WINDOW

    def refresh(self):
        paused = not self.R.enabled
        self.icon.icon = badge(self.lang, paused)
        self.icon.title = f"Keyglot {__version__} — {(self.lang or '').upper()}" + (f" ({t('paused')})" if paused else "")
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _watch_layout(self):
        while not self._stop:
            try:
                hwnd = W.user32.GetForegroundWindow()
                lang = W.hkl_lang(W.window_hkl(hwnd)) if hwnd else None
                if lang and lang != self.lang:
                    self.lang = lang
                    self.refresh()
            except Exception:
                pass
            time.sleep(0.3)

    def update_once(self, manual=False):
        if not C.frozen():
            if manual:
                self.icon.notify("Dev build: updates come through git", "Keyglot")
            return
        try:
            info = updater.check()
        except Exception as e:
            C.log_event(event="update_error", error=repr(e))
            if manual:
                self.icon.notify(t("update_failed"), "Keyglot")
            return
        if not info:
            if manual:
                self.icon.notify(t("up_to_date"), "Keyglot")
            return
        mode = self.R.cfg.get("updates", "auto")
        if mode == "auto" or manual:
            try:
                path = updater.download(info)
                self.icon.notify(t("update_installing", v=info["version"]), "Keyglot")
                C.log_event(event="update", to=info["version"])
                time.sleep(2)
                self.R.stop()
                updater.run_installer(path)
                self.quit()
            except Exception as e:
                C.log_event(event="update_error", error=repr(e))
        elif mode == "notify":
            self.icon.notify(t("update_found", v=info["version"]), "Keyglot")

    def _update_loop(self):
        time.sleep(60)
        while not self._stop:
            if self.R.cfg.get("updates", "auto") != "off":
                self.update_once()
            time.sleep(6 * 3600)

    def quit(self):
        self._stop = True
        self.R.stop()
        self.icon.stop()

    def run(self):
        threading.Thread(target=self._watch_layout, daemon=True).start()
        threading.Thread(target=self._update_loop, daemon=True).start()
        self.icon.run()
