"""Entry point: tray app (default), settings window, offline explain."""
import argparse
import os
import sys

from . import __version__


def main(argv=None):
    ap = argparse.ArgumentParser(prog="Keyglot", description="Context-aware keyboard layout auto-correction.")
    ap.add_argument("--settings", action="store_true", help="open the settings window")
    ap.add_argument("--explain", metavar="TEXT", help="show decisions for TEXT typed in --layout (offline)")
    ap.add_argument("--layout", default="lat", choices=["lat", "ru", "uk"])
    ap.add_argument("--kind", default="prose", help="field kind for --explain")
    ap.add_argument("--selfcheck", action="store_true", help="check data, layouts and UI Automation; write selfcheck.txt")
    ap.add_argument("--accept-injected", action="store_true", help="also process injected keys (tests)")
    ap.add_argument("--version", action="version", version=f"Keyglot {__version__}")
    a = ap.parse_args(argv)

    if a.settings:
        from .settings_ui import main as settings_main
        return settings_main()

    from .engine import Ctx, Engine, simulate
    from .layouts import Layouts
    from .lexicon import LanguageModel
    from . import config as C

    if a.selfcheck:
        return selfcheck()

    if a.explain:
        eng = Engine(Layouts(), LanguageModel())
        print("->", simulate(eng, a.explain, a.layout, Ctx(kind=a.kind), verbose=True))
        return 0

    from . import winapi as W
    if not W.single_instance("Local\\KeyglotSingleInstance"):
        return 0
    from .i18n import set_lang
    from .runner import Runner
    from .tray import Tray
    cfg = C.load_config()
    set_lang(cfg.get("ui_lang"))
    os.makedirs(C.APP_DIR, exist_ok=True)
    eng = Engine(Layouts(), LanguageModel(), C.load_state())
    runner = Runner(eng, cfg, accept_injected=a.accept_injected)
    runner.start()
    Tray(runner).run()
    return 0


def selfcheck():
    """Load everything the app needs without hooking the keyboard; report to a file (works in the windowed exe)."""
    import time
    import traceback
    from . import config as C
    lines, ok = [f"Keyglot {__version__} selfcheck {time.strftime('%Y-%m-%d %H:%M:%S')}"], True
    try:
        from .engine import Engine, simulate
        from .layouts import Layouts
        from .lexicon import LanguageModel
        t0 = time.time()
        eng = Engine(Layouts(), LanguageModel())
        lines.append(f"data loaded in {time.time() - t0:.2f}s, layouts {sorted(eng.L.hkls)}, groups {sorted(eng.L.tables)}")
        if "lat" in eng.L.tables and "ru" in eng.L.tables:
            got = simulate(eng, "ghbdtn rfr ltkf", "lat")
            lines.append(f"decision: {got}")
            ok &= got == "привет как дела"
        from .context import ContextProvider
        cp = ContextProvider(eng.lm, lambda: {})
        for _ in range(30):
            if cp.uia_ok:
                break
            time.sleep(0.1)
        lines.append(f"ui automation: {cp.uia_ok}")
        ok &= cp.uia_ok
        import pystray  # noqa: F401
        lines.append("tray: ok")
    except Exception:
        ok = False
        lines.append(traceback.format_exc())
    lines.append("RESULT: " + ("OK" if ok else "FAIL"))
    os.makedirs(C.APP_DIR, exist_ok=True)
    with open(os.path.join(C.APP_DIR, "selfcheck.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
