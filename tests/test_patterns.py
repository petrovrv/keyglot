"""0.3.7: rules over word cores (keep / fix pair / ctx triplet), learned from undo and retyping."""
import pytest

from keyglot.engine import Ctx, Engine, empty_state, simulate
from keyglot.layouts import Layouts
from keyglot.lexicon import LanguageModel
from keyglot.patterns import LEARN_N, Patterns, core

from test_inputlog import FakeContext, run as _run  # noqa: F401
import test_inputlog

VK_SPACE, VK_BACK = 0x20, 0x08


@pytest.fixture(scope="module")
def lm():
    return LanguageModel()


@pytest.fixture
def eng(lm):
    return Engine(Layouts(static=True), lm, empty_state())


def test_core_strips_endings():
    assert core("скамом", "ru") == core("скам", "ru") == core("скама", "ru") == "скам"
    assert core("хочет", "ru") == core("хочу", "ru") == "хоч"
    assert core("кот", "ru") == "кот"  # never shorter than three letters


def test_shipped_keep_rule_covers_all_forms(eng):
    for w in ("скам", "скамом", "скама", "скамер"):
        assert simulate(eng, f"это был {w}", "ru", Ctx(), polish={}) == f"это был {w}"


def test_shipped_keep_rule_for_a_company_name(eng):
    # 0.3.9: Thorizon (a company) was "fixed" to Horizon
    for w in ("Thorizon", "Thorizon,", "thorizon."):
        assert simulate(eng, f"about {w}", "lat", Ctx(), polish={}) == f"about {w}"


def test_keep_learned_after_two_rejections(lm):
    p = Patterns({}, shipped={})
    assert p.reject("тесом", "ru") is None and not p.keeps("тесами", "ru")
    assert p.reject("теса", "ru") == "ru:тес"
    assert p.keeps("тесами", "ru")
    assert Patterns({"patterns": p.learned}, shipped={}).keeps("тесу", "ru")  # persisted in state


def test_fix_pair_learned_from_retyping_and_used_for_other_forms(eng):
    P = eng.P
    assert P.retyped("зочет", "хочет", "ru") is None
    assert P.retyped("зочет", "хочет", "ru") == "ru:зоч>хоч"
    assert simulate(eng, "он зочу", "ru", Ctx(), polish={}) == "он хочу"


def test_fix_pair_needs_close_words():
    p = Patterns({}, shipped={})
    for _ in range(LEARN_N):
        assert p.retyped("стол", "кресло", "ru") is None  # the user changed the word, not a typo


def test_ctx_triplet_stops_space_fix(eng):
    before = simulate(eng, "сейча св", "ru", Ctx(), polish={})
    assert before == "сейчас в"
    for _ in range(LEARN_N):
        eng.P.reject_space("сейча", "св", "ru")
    assert simulate(eng, "сейча св", "ru", Ctx(), polish={}) == "сейчас св"  # only the typo fix is left


def test_undo_in_runner_counts_for_keep(lm, monkeypatch, tmp_path):
    e = Engine(Layouts(static=True), lm, empty_state())
    r = test_inputlog.run.__wrapped__(e, monkeypatch, tmp_path)
    r.typ("the problme")
    assert r.r.last_corr and r.r.last_corr["new"] == "problem"
    r.r.on_key(VK_BACK, True, False, 0)
    assert e.state["patterns"]["keep"]["en:problme"]["n"] == 1


def test_fix_erased_and_typed_again_is_kept(lm, monkeypatch, tmp_path):
    e = Engine(Layouts(static=True), lm, empty_state())
    r = test_inputlog.run.__wrapped__(e, monkeypatch, tmp_path)
    r.typ("the problme")
    r.r.on_key(VK_SPACE, True, False, 0)  # a space after the fix: no Backspace undo any more
    for _ in range(len("problem  ")):
        r.r.on_key(VK_BACK, True, False, 0)
    r.r.jobs.queue.clear()
    r.typ("problme")
    assert r.r.jobs.empty()  # not fixed a second time
    assert e.state["patterns"]["keep"]["en:problme"]["n"] == 1


def test_word_erased_and_retyped_by_hand_counts_for_fix_pair(lm, monkeypatch, tmp_path):
    e = Engine(Layouts(static=True), lm, empty_state())
    r = test_inputlog.run.__wrapped__(e, monkeypatch, tmp_path)
    r.typ("it is wrkoing")
    for _ in range(len("wrkoing ")):
        r.r.on_key(VK_BACK, True, False, 0)
    r.typ("working")
    (k,) = e.state["patterns"]["fix"]
    assert k.startswith("en:wrko") and e.state["patterns"]["fix"][k]["n"] == 1


@pytest.mark.parametrize("text", [
    "колко,", "обучишься", "неумеренно", "призакрыл",
    '"приоткрытие"', "сопоставь", "приоткрытыми",
])
def test_review_nov19_words_are_not_split(eng, text):
    assert simulate(eng, text, "ru", Ctx(), polish={}) == text


@pytest.mark.parametrize("text", ["Sonoff", "Sonoff,", "sonoff."])
def test_review_nov20_device_brand_is_not_split(eng, text):
    assert simulate(eng, text, "lat", Ctx(), polish={}) == text
