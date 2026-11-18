"""Shift+Backspace (other layout), Alt+Backspace (typo), Pause — on the current or just finished word."""
import pytest

from keyglot import runner as R
from test_inputlog import FakeContext, eng, run  # noqa: F401  (fixtures)

VK_SPACE, VK_BACK, VK_LSHIFT, VK_LMENU, VK_A, VK_PAUSE = 0x20, 0x08, 0xA0, 0xA4, 0x41, 0x13


@pytest.fixture
def held(monkeypatch):
    keys = set()
    alias = {0x10: (0xA0, 0xA1), 0x12: (0xA4, 0xA5), 0x11: (0xA2, 0xA3)}
    monkeypatch.setattr(R.W, "key_down", lambda vk: vk in keys or any(k in keys for k in alias.get(vk, ())))
    return keys


def press(run, held, mod, vk=VK_BACK):
    held.add(mod)
    run.r.on_key(mod, True, False, 0)
    r = run.r.on_key(vk, True, False, 0)
    held.discard(mod)
    return r


def jobs(run):
    out = []
    while not run.r.jobs.empty():
        out.append(run.r.jobs.get_nowait())
    return out


def test_alt_backspace_fixes_typo_of_last_word(run, held):
    run.typ("teh")
    assert press(run, held, VK_LMENU)
    (job,) = jobs(run)
    assert job[2:5] == (4, "the", VK_SPACE) and job[6] == (VK_LMENU,)


def test_alt_backspace_cycles_and_returns_to_the_word(run, held):
    run.typ("teh")
    seen = []
    for _ in range(8):
        press(run, held, VK_LMENU)
        seen.append(jobs(run)[0][3])
    assert seen[0] == "the" and "teh" in seen
    i = seen.index("teh")
    assert seen[i + 1] == "the"  # around again


def test_shift_backspace_converts_word_in_progress(run, held):
    for vk, shift, caps in run.r.E.L.keys_for("ghbdtn", "lat")[:-1]:
        run.r.on_key(vk, True, False, 0)
    assert press(run, held, VK_LSHIFT)
    (job,) = jobs(run)
    assert job[2] == 5 and job[3].startswith("приве") and job[4] is None and job[5] in ("ru", "uk")


def test_shift_backspace_undoes_auto_switch(run, held):
    run.typ("ghbdtn")  # auto-converted to привет
    jobs(run)
    assert press(run, held, VK_LSHIFT)
    (job,) = jobs(run)
    assert job[2] == 7 and job[3] != "привет" and job[4] == VK_SPACE


def test_shift_held_for_capitals_keeps_backspace(run, held):
    run.typ("hello")
    held.add(VK_LSHIFT)
    run.r.on_key(VK_LSHIFT, True, False, 0)
    run.r.on_key(VK_A, True, False, 0)        # a capital A typed with Shift
    assert not run.r.on_key(VK_BACK, True, False, 0)  # still held: a plain Backspace
    assert jobs(run) == []


def test_alt_backspace_without_word_passes(run, held):
    assert not press(run, held, VK_LMENU)
    assert jobs(run) == []


def test_pause_still_converts(run, held):
    run.typ("hello")
    run.r.on_key(VK_PAUSE, True, False, 0)
    (job,) = jobs(run)
    assert job[3] != "hello" and job[4] == VK_SPACE


def test_hotkey_in_trace(run, held):
    run.typ("teh")
    press(run, held, VK_LMENU)
    run.r.on_key(0x0D, True, False, 0)
    e = run.lines()[-1]
    assert "[Alt+⌫]{teh→the}" in e["keys"] and e["text"].startswith("the") and e["manual"] == 1


def test_typo_options(eng):  # noqa: F811
    assert eng.typo_options("зочет", "ru", "ru")[0] == "хочет"
    assert eng.typo_options("Кносьерж,", "ru", "ru")[0] == "Консьерж,"
    assert eng.typo_options("помошь", "ru", "ru")[0] == "помощь"
    assert eng.typo_options("dangerousl", "lat", "en")[:2] == ["dangerous", "dangerously"]
    assert eng.typo_options("еще", "ru", "ru")[0] == "ещё"
    assert eng.typo_options(":-)", "lat") == []
