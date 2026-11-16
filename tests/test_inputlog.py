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

VK_SPACE, VK_BACK = 0x20, 0x08


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


def test_words_and_fix_logged(run):
    run.typ("hello ghbdtn")
    ev = [e for e in run.lines() if e["event"] == "word"]
    assert [(e["typed"], e["out"], e["action"]) for e in ev] == [("hello", "hello", "keep"),
                                                                 ("ghbdtn", "привет", "fix")]
    assert ev[1]["before"] == "hello " and ev[1]["exe"] == "msedge.exe" and ev[1]["kind"] == "prose"


def test_retype_records_erased_text(run):
    run.typ("hello")
    for _ in range(6):
        run.r.on_key(VK_BACK, True, False, 0)
    run.typ("help")
    ev = run.lines()[-1]
    assert ev["typed"] == "help" and ev["erased"] == "hello " and ev.get("before") is None


def test_backspace_inside_word_counted(run):
    for vk, shift, caps in run.r.E.L.keys_for("helo", "lat"):
        run.r.on_key(vk, True, False, 0)
    run.r.on_key(VK_BACK, True, False, 0)
    run.typ("lo")
    assert run.lines()[-1]["bs"] == 1


def test_excluded_windows_not_logged(run):
    run.title[0] = "ING Home'Bank - Microsoft Edge"
    run.typ("hello world")
    run.title[0] = "Keytrade Bank - Microsoft Edge"
    run.typ("hello world")
    assert run.lines() == []
    run.title[0] = "Meeting notes - Word"
    run.typ("hello")
    assert len(run.lines()) == 1


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
