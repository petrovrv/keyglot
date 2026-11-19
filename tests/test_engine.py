import pytest

from keyglot.engine import Ctx, Engine, simulate
from keyglot.layouts import Layouts
from keyglot.lexicon import LanguageModel


@pytest.fixture(scope="module")
def eng():
    return Engine(Layouts(static=True), LanguageModel())


PROSE = [
    ("ghbdtn rfr ltkf", "lat", "привет как дела"),
    ("b ghbdtn", "lat", "и привет"),
    ("руддщ цщкдв", "ru", "hello world"),
    ("hello world", "lat", "hello world"),
    ("привет как дела", "ru", "привет как дела"),
    ("ghbdsn ckfdf erhf]ys", "lat", "привіт слава україні"),
    ("привыт", "ru", "привіт"),
    ("ghbdsn", "lat", "привіт"),
    ("ltrfzhw", "lat", "ltrfzhw"),
    ("ytn ,jkmit", "lat", "нет больше"),
    ("приветю", "ru", "привет."),
    ("пщувуьщкпут", "ru", "goedemorgen"),
    ("vjq gfhjkm", "lat", "мой пароль"),
    ("ghbdtn, rfr ltkf&", "lat", "привет, как дела?"),
    ("Rjhjkm vfnthbfkjd ns", "lat", "Король материалов ты"),
    ("ghbdtnn", "lat", "приветт"),
    ("qwrtpx", "lat", "qwrtpx"),
    ("ntcn", "lat", "тест"),
    ("dank je wel", "lat", "dank je wel"),
    ("ufhf;", "lat", "гараж"),
    ("CO", "lat", "CO"),
    ("ok", "lat", "ok"),
    ("hr", "lat", "hr"),
    ("люблю хлеб", "ru", "люблю хлеб"),
    # 0.3.4: tokens without letters are never converted (':-)' became 'Ж-)', a lone '.' became 'ю')
    ("ok :-)", "lat", "ok :-)"),
    ("the end . next", "lat", "the end . next"),
    ("one , two", "lat", "one , two"),
    # 0.3.9: a last б/ю that is a neighbour slip of ь makes a word, not "word,"
    ("поставб для", "ru", "поставь для"),
    ("делатб это", "ru", "делать это"),
    ("Поставб", "ru", "Поставь"),
    ("такб", "ru", "так,"),
    ("делб", "ru", "дел,"),
    ("хлеб", "ru", "хлеб"),
]


@pytest.mark.parametrize("text,layout,want", PROSE)
def test_prose(eng, text, layout, want):
    assert simulate(eng, text, layout) == want


@pytest.mark.parametrize("text,layout,kind,want", [
    ("пше ыефегы", "ru", "terminal", "git status"),
    ("ячсм", "ru", "terminal", "ячсм"),              # not a command
    ("привет", "ru", "terminal", "привет"),           # real word stays
    ("ghbdtn", "lat", "terminal", "ghbdtn"),          # never Latin -> Cyrillic in a terminal
    ("вуа", "ru", "code", "def"),
    ("ghbdtn", "lat", "code", "ghbdtn"),
    ("ьфшд", "ru", "address", "mail"),
])
def test_latin_fields(eng, text, layout, kind, want):
    assert simulate(eng, text, layout, Ctx(kind=kind)) == want


def test_skip_field(eng):
    assert simulate(eng, "ghbdtn", "lat", Ctx(kind="skip")) == "ghbdtn"


def test_document_language_tips_short_word(eng):
    # "lf" is ambiguous alone; inside a Russian conversation it is "да"
    alone = simulate(eng, "lf", "lat")
    ru_doc = simulate(eng, "lf", "lat", Ctx(doc={"ru": 1.0}, doc_n=10, conv={"ru": 1.0}, conv_n=20))
    assert alone == "lf" or alone == "да"
    assert ru_doc == "да"


def test_foreign_word_in_document_stays(eng):
    # an English word typed on purpose inside a Russian text is kept
    assert simulate(eng, "deadline", "lat", Ctx(doc={"ru": 1.0}, doc_n=20)) == "deadline"


def test_learning_and_exception(eng):
    e = Engine(eng.L, eng.lm)
    keys = e.L.keys_for("ghbdtn", "lat")
    assert e.decide(keys, "lat")["action"] == "rewrite"
    e.add_exception(e.key_id(keys))
    assert e.decide(keys, "lat")["action"] == "keep"
    ctx = Ctx(exe="telegram.exe", key="telegram.exe|Sofia")
    for _ in range(50):
        e.learn(ctx, "ru")
    assert e.preferred_lang(ctx.key, ctx.exe) == "ru"


def test_wordlist_lookup(eng):
    assert eng.lm.known("привет", "ru") > 4
    assert eng.lm.known("groet", "nl") > 3
    assert eng.lm.known("ghbdtn", "en") == 0
    shares, n = eng.lm.text_languages("Привет, как дела? Я сегодня дома.")
    assert n >= 4 and shares.get("ru", 0) > 0.7


@pytest.mark.parametrize("text,layout,want", [
    ("и еще хотелось бы", "ru", "и ещё хотелось бы"),
    ("Еще одна програама", "ru", "Ещё одна программа"),
    ("чтобые вместо", "ru", "чтобы вместо"),
    ("приветк ак дела", "ru", "привет как дела"),
    ("приве ткак дела", "ru", "привет как дела"),
    ("приветкак дела", "ru", "привет как дела"),
    ("ghbdtnr fr ltkf", "lat", "привет как дела"),
    ("hello wrold", "lat", "hello world"),
    ("goedemorgne", "lat", "goedemorgen"),
    ("все хорошо", "ru", "все хорошо"),            # все/всё is ambiguous: left alone
    ("ее нет", "ru", "её нет"),
    ("Иван Петров пришел", "ru", "Иван Петров пришёл"),
    ("строящей порхал", "ru", "строящей порхал"),  # real forms missing from the word list stay
    ("NATO SCK", "lat", "NATO SCK"),
    ("yflj jngbcfnmcz", "lat", "надо отписаться"),
    # false fixes of 0.3.0 seen in the log
    ("отдавать поток крупной моели", "ru", "отдавать поток крупной модели"),
    ("проблемы автокоррекции существуют", "ru", "проблемы автокоррекции существуют"),
    ("ссылка валидна.", "ru", "ссылка валидна."),
    ("в тексте имейла", "ru", "в тексте имейла"),
    ("мояработа это", "ru", "моя работа это"),
    ("этоправда", "ru", "это правда"),
    # 0.3.4, seen in the log
    ("сам дописывает текст", "ru", "сам дописывает текст"),   # a stray first letter only if it is a neighbour
    ("не хочуя я спать", "ru", "не хочу я спать"),            # letter typed twice around the space, not "яя"
    # 0.3.6, seen in the log
    ("что там в брико продают", "ru", "что там в брико продают"),  # a word before the space stays, not "вб рико"
    ("голвы под крышей", "ru", "голвы под крышей"),                # a missed letter (головы), not "гол вы"
])
def test_polish(eng, text, layout, want):
    assert simulate(eng, text, layout, polish={}) == want


def test_polish_options_off(eng):
    off = {"typos": False, "yo": False, "spaces": False}
    assert simulate(eng, "и еще програама", "ru", polish=off) == "и еще програама"


def test_letters_never_become_leading_punctuation(eng):
    assert simulate(eng, "эьл", "ru") == "эьл"


def test_typo_exception(eng):
    e = Engine(eng.L, eng.lm)
    keys = e.L.keys_for("програама", "ru")
    e.add_exception(e.key_id(keys))
    assert e.polish("програама", "ru", kid=e.key_id(keys)) is None
