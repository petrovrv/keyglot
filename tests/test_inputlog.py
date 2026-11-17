import json
import os
import time
import types

import pytest

from keyglot import config as C
from keyglot import inputlog as IL
from keyglot import runner as R
from keyglot.engine import Engine
from keyglot.layouts import Layouts
from keyglot.lexicon import LanguageModel

VK_SPACE, VK_BACK, VK_RETURN, VK_TAB, VK_LEFT = 0x20, 0x08, 0x0D, 0x09, 0x25


@pytest.fixture(scope="module")
def eng():
    return Engine(Layouts(static=True), LanguageModel())


class FakeContext:
    uia_ok = False

    def __init__(self, *a):
        pass

    def request(self, hwnd):
        pass

    def get(self, hwnd, max_age=10.0):
        return None


@pytest.fixture
def run(eng, monkeypatch, tmp_path):
    title = ["Messaging | LinkedIn - Microsoft Edge"]
    monkeypatch.setattr(IL, "INPUT_DIR", str(tmp_path))
    monkeypatch.setattr(C, "log_event", lambda **ev: None)
    monkeypatch.setattr(R, "ContextProvider", FakeContext)
    monkeypatch.setattr(R.W, "user32", types.SimpleNamespace(GetForegroundWindow=lambda: 1, GetKeyState=lambda vk: 0))
    monkeypatch.setattr(R.W, "key_down", lambda vk: False)
    monkeypatch.setattr(R.W, "window_exe", lambda h: "msedge.exe")
    monkeypatch.setattr(R.W, "window_title", lambda h: title[0])
    monkeypatch.setattr(R.W, "window_class", lambda h: "Chrome_WidgetWin_1")
    monkeypatch.setattr(R.W, "window_hkl", lambda h: 0x04090409)
    monkeypatch.setattr(R.W, "thread_hkl", lambda h: 0x04090409)
    monkeypatch.setattr(R.W, "focus_is_win32_password", lambda h: False)
    monkeypatch.setattr(R.W, "request_layout", lambda h, k: None)
    cfg = dict(C.DEFAULTS)
    cfg.update(log_verbose=True, rules={})
    r = R.Runner(eng, cfg)

    def typ(text):
        for word in text.split(" "):
            for vk, shift, caps in eng.L.keys_for(word, "lat"):
                r.on_key(vk, True, False, 0)
            r.on_key(VK_SPACE, True, False, 0)

    def lines():
        out = []
        for name in sorted(os.listdir(tmp_path)):
            with open(os.path.join(tmp_path, name), encoding="utf-8") as f:
                out += [json.loads(x) for x in f]
        return out

    return types.SimpleNamespace(r=r, typ=typ, lines=lines, title=title, dir=tmp_path)


def enter(run):
    run.r.on_key(VK_RETURN, True, False, 0)


def test_one_line_per_input(run):
    run.typ("hello ghbdtn")
    enter(run)
    ev = run.lines()
    assert len(ev) == 1
    e = ev[0]
    assert e["event"] == "input" and e["end"] == "enter"
    assert e["text"] == "hello привет"
    assert e["keys"] == "hello ghbdtn{→привет} ⏎"
    assert e["words"] == 2 and e["fixes"] == 1
    assert e["exe"] == "msedge.exe" and e["kind"] == "prose" and e["layout"] == "en"
    assert e["decisions"] == [{"typed": "ghbdtn", "out": "привет", "reason": e["decisions"][0]["reason"],
                               "lang": "ru", "margin": e["decisions"][0]["margin"],
                               "cands": e["decisions"][0]["cands"]}]


def test_retype_records_erased_text(run):
    run.typ("hello")
    for _ in range(6):
        run.r.on_key(VK_BACK, True, False, 0)
    run.typ("help")
    enter(run)
    e = run.lines()[-1]
    assert e["keys"] == "hello ⌫⌫⌫⌫⌫⌫help ⏎"
    assert e["text"] == "help" and e["retypes"] == 1
    assert e["decisions"][0]["typed"] == "help" and e["decisions"][0]["erased"] == "hello "


def test_backspace_inside_word_counted(run):
    for vk, shift, caps in run.r.E.L.keys_for("helo", "lat"):
        run.r.on_key(vk, True, False, 0)
    run.r.on_key(VK_BACK, True, False, 0)
    run.typ("lo")
    enter(run)
    e = run.lines()[-1]
    assert e["keys"] == "helo⌫lo ⏎" and e["text"] == "hello" and e["bs"] == 1


def test_undo_in_trace(run):
    run.typ("hello ghbdtn")
    run.r.on_key(VK_BACK, True, False, 0)
    enter(run)
    e = run.lines()[-1]
    assert e["keys"] == "hello ghbdtn{→привет} ⌫{undo}⏎"
    assert e["text"] == "hello ghbdtn" and e["undo"] == 1


def test_nav_keys_and_tab_end(run):
    run.typ("hello")
    run.r.on_key(VK_LEFT, True, False, 0)
    run.typ("x")
    run.r.on_key(VK_TAB, True, False, 0)
    e = run.lines()[-1]
    assert e["keys"] == "hello ←x ⇥" and e["end"] == "tab" and e["moved"] is True


def test_window_change_ends_input(run, monkeypatch):
    run.typ("hello")
    monkeypatch.setattr(R.W, "user32", types.SimpleNamespace(GetForegroundWindow=lambda: 2, GetKeyState=lambda vk: 0))
    run.typ("world")
    enter(run)
    ev = run.lines()
    assert [(e["text"], e["end"]) for e in ev] == [("hello", "window"), ("world", "enter")]


def test_idle_flush(run):
    run.typ("hello")
    run.r.sess.t1 -= 120
    run.r.flush("idle", on_hook=False)
    assert run.lines()[-1]["end"] == "idle" and run.r.sess is None


def test_password_field_not_logged(run, monkeypatch):
    monkeypatch.setattr(R.W, "focus_is_win32_password", lambda h: True)
    run.typ("secret123")
    run.r.on_key(VK_TAB, True, False, 0)
    run.typ("hunter")
    enter(run)
    assert run.lines() == []


def test_excluded_windows_not_logged(run):
    run.title[0] = "ING Home'Bank - Microsoft Edge"
    run.typ("hello world")
    run.title[0] = "Keytrade Bank - Microsoft Edge"
    run.typ("hello world")
    run.title[0] = "Meeting notes - Word"
    run.typ("hello")
    enter(run)
    ev = run.lines()
    assert len(ev) == 1 and ev[0]["text"] == "hello" and ev[0]["title"] == "Meeting notes - Word"


def test_verbose_off_writes_nothing(run):
    run.r.cfg["log_verbose"] = False
    run.typ("hello ghbdtn")
    enter(run)
    assert run.lines() == []


def test_key_names():
    assert IL.key_name(0x5A, ctrl=True) == "[^Z]"
    assert IL.key_name(0x08, ctrl=True) == "[^⌫]"
    assert IL.key_name(0x0D, shift=True) == "[⇧⏎]"
    assert IL.key_name(0x25) == "←"


def test_excluded_patterns():
    p = C.DEFAULTS["log_exclude"]
    assert IL.excluded(p, "bitwarden.exe", "")
    assert IL.excluded(p, "msedge.exe", "Bitwarden Web vault - Microsoft Edge")
    assert IL.excluded(p, "msedge.exe", "ING Belgium - Home'Bank")
    assert not IL.excluded(p, "msedge.exe", "Meeting - Booking.com")


def test_prune(tmp_path, monkeypatch):
    monkeypatch.setattr(IL, "INPUT_DIR", str(tmp_path))
    old = time.strftime("%Y-%m-%d", time.localtime(time.time() - 20 * 86400))
    new = time.strftime("%Y-%m-%d")
    for d in (old, new):
        (tmp_path / f"{d}.jsonl").write_text("{}\n")
    assert IL.prune(14) == 1
    assert os.listdir(tmp_path) == [f"{new}.jsonl"]


def keys(run, word):
    for vk, shift, caps in run.r.E.L.keys_for(word, "lat"):
        run.r.on_key(vk, True, False, 0)


def jobs(run):
    out = []
    while not run.r.jobs.empty():
        out.append(run.r.jobs.get())
    return out


def test_typo_fixed_without_caret_move(run):
    run.typ("hello wrold")
    assert [j[3] for j in jobs(run)] == ["world"]


def test_no_typo_or_space_fix_after_caret_move(run):
    # after a click or arrows the word may continue text left of the caret ("помо|жет" became "же")
    run.typ("hello")
    run.r.on_key(VK_LEFT, True, False, 0)
    run.typ("wrold")
    assert jobs(run) == []
    run.typ("hellow orld")          # without a move the space is put back where it belongs
    assert [j[3] for j in jobs(run)][-1] == "hello world"
    run.r.on_key(VK_LEFT, True, False, 0)
    run.typ("hellow orld")          # but not across a move: the first word is no anchor for the second
    assert all(" " not in j[3] for j in jobs(run))
    run.typ("wrold")                # the move is over: words after it are fixed again
    assert [j[3] for j in jobs(run)] == ["world"]


def test_word_start_after_move():
    assert R._at_word_start("", "wrold")
    assert R._at_word_start("Hello, w", "wrold")
    assert R._at_word_start("one two ", "wrold")
    assert not R._at_word_start("помож", "жет")
    assert not R._at_word_start("помо", "жет")


def test_ctrl_enter_fixes_last_word(run, monkeypatch):
    VK_CONTROL, VK_LCONTROL = 0x11, 0xA2
    run.typ("hello")
    keys(run, "wrold")
    monkeypatch.setattr(R.W, "key_down", lambda vk: vk in (VK_CONTROL, VK_LCONTROL))
    assert run.r.on_key(VK_RETURN, True, False, 0) is True   # Enter held back until the word is fixed
    (job,) = jobs(run)
    _, hwnd, n_back, text, bvk, lang, held = job
    assert (n_back, text, bvk, held) == (5, "world", VK_RETURN, (VK_LCONTROL,))  # Ctrl released for Backspace
    e = run.lines()[-1]
    assert e["end"] == "enter" and e["text"] == "hello world" and e["keys"].endswith("{→world}[^⏎]")


def test_ctrl_enter_passes_when_nothing_to_fix(run, monkeypatch):
    run.typ("hello")
    keys(run, "world")
    monkeypatch.setattr(R.W, "key_down", lambda vk: vk in (0x11, 0xA2))
    assert run.r.on_key(VK_RETURN, True, False, 0) is False
    assert jobs(run) == [] and run.lines()[-1]["text"] == "hello world"
