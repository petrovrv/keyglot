"""Settings window (separate process). Writes config.json; the running app picks it up."""
import os
import tkinter as tk
import webbrowser
import winreg
from tkinter import messagebox, simpledialog, ttk

from . import __version__
from . import config as C
from .i18n import set_lang, t
from .tray import report_url, self_command

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_get():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "Keyglot")
            return True
    except OSError:
        return False


def autostart_set(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            cmd = " ".join(f'"{p}"' for p in self_command())
            winreg.SetValueEx(k, "Keyglot", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, "Keyglot")
            except OSError:
                pass


class SettingsWindow:
    MODES = ("auto", "off", "latin")

    def __init__(self):
        self.cfg = C.load_config()
        set_lang(self.cfg.get("ui_lang"))
        self.state = C.load_state()
        self.root = tk.Tk()
        self.root.title(f"Keyglot {__version__}")
        self.root.geometry("640x470")
        self.root.minsize(560, 420)
        try:
            self.root.iconbitmap(self._icon())
        except tk.TclError:
            pass
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        nb.add(self._general(nb), text=t("general"))
        nb.add(self._apps(nb), text=t("apps"))
        nb.add(self._exceptions(nb), text=t("exceptions"))
        nb.add(self._about(nb), text=t("about"))
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(bar, text=t("keys_hint"), foreground="#666", wraplength=420).pack(side="left")
        ttk.Button(bar, text=t("close"), command=self.root.destroy).pack(side="right")
        ttk.Button(bar, text=t("save"), command=self.save).pack(side="right", padx=6)

    @staticmethod
    def _icon():
        import sys
        base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(__file__), ".."))
        return os.path.join(base, "assets", "keyglot.ico")

    # ---------------------------------------------------------- general ---
    def _general(self, parent):
        f = ttk.Frame(parent, padding=14)
        self.vars = {}
        for key in ("enabled", "correct_on_enter", "preswitch", "sound", "log_events"):
            v = tk.BooleanVar(value=self.cfg.get(key, True))
            self.vars[key] = v
            ttk.Checkbutton(f, text=t(key), variable=v).pack(anchor="w", pady=2)
        self.autostart = tk.BooleanVar(value=autostart_get())
        ttk.Checkbutton(f, text=t("autostart"), variable=self.autostart).pack(anchor="w", pady=2)
        ttk.Separator(f).pack(fill="x", pady=10)
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text=t("updates") + ":", width=20).pack(side="left")
        self.upd = tk.StringVar(value=self.cfg.get("updates", "auto"))
        for val, key in (("auto", "upd_auto"), ("notify", "upd_notify"), ("off", "upd_off")):
            ttk.Radiobutton(row, text=t(key), value=val, variable=self.upd).pack(side="left", padx=4)
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=6)
        ttk.Label(row, text=t("language") + ":", width=20).pack(side="left")
        self.ui_lang = tk.StringVar(value=self.cfg.get("ui_lang", "auto"))
        ttk.Combobox(row, textvariable=self.ui_lang, values=["auto", "en", "ru", "uk", "nl"], width=8,
                     state="readonly").pack(side="left")
        return f

    # ------------------------------------------------------------- apps ---
    def _apps(self, parent):
        f = ttk.Frame(parent, padding=10)
        cols = ("app", "words", "languages", "mode")
        tv = ttk.Treeview(f, columns=cols, show="headings", height=12)
        for c, wdt in zip(cols, (190, 60, 210, 110)):
            tv.heading(c, text=t(c))
            tv.column(c, width=wdt, anchor="w")
        tv.pack(fill="both", expand=True)
        self.tv = tv
        self.rules = dict(self.cfg.get("rules", {}))
        self._fill_apps()
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(8, 0))
        for m in self.MODES:
            ttk.Button(row, text=t("mode_" + m), command=lambda m=m: self._set_mode(m)).pack(side="left", padx=(0, 6))
        ttk.Button(row, text=t("add_app"), command=self._add_app).pack(side="right")
        return f

    def _fill_apps(self):
        self.tv.delete(*self.tv.get_children())
        apps = self.state.get("apps", {})
        names = sorted(set(apps) | set(self.rules), key=lambda e: -sum(apps.get(e, {}).values()))
        for exe in names:
            c = apps.get(exe, {})
            n = sum(c.values())
            langs = "  ".join(f"{k} {v / n:.0%}" for k, v in sorted(c.items(), key=lambda kv: -kv[1])) if n else ""
            self.tv.insert("", "end", iid=exe, values=(exe, int(n), langs, t("mode_" + self.rules.get(exe, "auto"))))

    def _set_mode(self, mode):
        for exe in self.tv.selection():
            if mode == "auto":
                self.rules.pop(exe, None)
            else:
                self.rules[exe] = mode
        self._fill_apps()

    def _add_app(self):
        exe = simpledialog.askstring("Keyglot", "program.exe", parent=self.root)
        if exe:
            self.rules[exe.strip().lower()] = "off"
            self._fill_apps()

    # ------------------------------------------------------- exceptions ---
    def _exceptions(self, parent):
        f = ttk.Frame(parent, padding=10)
        ttk.Label(f, text=t("exceptions_hint"), wraplength=560).pack(anchor="w", pady=(0, 6))
        self.lb = tk.Listbox(f, height=14, selectmode="extended")
        self.lb.pack(fill="both", expand=True)
        for e in self.state.get("exceptions", []):
            self.lb.insert("end", e)
        ttk.Button(f, text=t("remove"), command=self._remove_exc).pack(anchor="e", pady=(8, 0))
        return f

    def _remove_exc(self):
        for i in reversed(self.lb.curselection()):
            C.push_pending(op="remove_exception", key=self.lb.get(i))
            self.lb.delete(i)

    # ------------------------------------------------------------ about ---
    def _about(self, parent):
        f = ttk.Frame(parent, padding=18)
        ttk.Label(f, text=f"Keyglot {__version__}", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(f, text=t("tagline"), font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 10))
        ttk.Label(f, text=t("privacy"), wraplength=560, foreground="#444").pack(anchor="w", pady=(0, 12))
        link = ttk.Label(f, text=f"github.com/{C.REPO}", foreground="#2563eb", cursor="hand2")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(f"https://github.com/{C.REPO}"))
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=14)
        ttk.Button(row, text=t("report"), command=lambda: webbrowser.open(report_url())).pack(side="left")
        ttk.Button(row, text=t("open_data"), command=lambda: os.startfile(C.APP_DIR)).pack(side="left", padx=6)
        return f

    def save(self):
        for k, v in self.vars.items():
            self.cfg[k] = bool(v.get())
        self.cfg["updates"] = self.upd.get()
        self.cfg["ui_lang"] = self.ui_lang.get()
        self.cfg["rules"] = self.rules
        C.save_config(self.cfg)
        try:
            if self.autostart.get() != autostart_get():
                autostart_set(self.autostart.get())
        except OSError as e:
            messagebox.showerror("Keyglot", str(e))
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    SettingsWindow().run()
