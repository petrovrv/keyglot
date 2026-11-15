"""UI strings in English, Russian, Ukrainian and Dutch."""
import ctypes
import locale

S = {
    "enabled": ("Enabled", "Включено", "Увімкнено", "Ingeschakeld"),
    "correct_on_enter": ("Correct on Enter too", "Исправлять и на Enter", "Виправляти й на Enter", "Ook bij Enter corrigeren"),
    "preswitch": ("Pick layout when switching windows", "Ставить раскладку при смене окна",
                  "Ставити розкладку при зміні вікна", "Indeling kiezen bij vensterwissel"),
    "sound": ("Sound on on/off", "Звук при вкл./выкл.", "Звук при увімк./вимк.", "Geluid bij aan/uit"),
    "log_events": ("Keep a log of corrections", "Вести журнал исправлений", "Вести журнал виправлень",
                   "Logboek van correcties bijhouden"),
    "settings": ("Settings…", "Настройки…", "Налаштування…", "Instellingen…"),
    "open_log": ("Open log", "Открыть журнал", "Відкрити журнал", "Logboek openen"),
    "check_updates": ("Check for updates", "Проверить обновления", "Перевірити оновлення", "Controleren op updates"),
    "report": ("Report a problem…", "Сообщить о проблеме…", "Повідомити про проблему…", "Probleem melden…"),
    "exit": ("Exit", "Выход", "Вихід", "Afsluiten"),
    "paused": ("paused", "на паузе", "на паузі", "gepauzeerd"),
    "up_to_date": ("Keyglot is up to date", "Keyglot последней версии", "Keyglot останньої версії",
                   "Keyglot is up-to-date"),
    "update_found": ("Update {v} is available", "Доступно обновление {v}", "Доступне оновлення {v}",
                     "Update {v} beschikbaar"),
    "update_installing": ("Installing update {v}…", "Устанавливаю обновление {v}…", "Встановлюю оновлення {v}…",
                          "Update {v} wordt geïnstalleerd…"),
    "update_failed": ("Update check failed", "Не удалось проверить обновления", "Не вдалося перевірити оновлення",
                      "Updatecontrole mislukt"),
    "general": ("General", "Общие", "Загальні", "Algemeen"),
    "apps": ("Applications", "Приложения", "Застосунки", "Programma's"),
    "exceptions": ("Exceptions", "Исключения", "Винятки", "Uitzonderingen"),
    "about": ("About", "О программе", "Про програму", "Over"),
    "updates": ("Updates", "Обновления", "Оновлення", "Updates"),
    "upd_auto": ("Install automatically", "Ставить автоматически", "Встановлювати автоматично",
                 "Automatisch installeren"),
    "upd_notify": ("Only notify", "Только сообщать", "Лише повідомляти", "Alleen melden"),
    "upd_off": ("Do not check", "Не проверять", "Не перевіряти", "Niet controleren"),
    "autostart": ("Start with Windows", "Запускать с Windows", "Запускати з Windows", "Starten met Windows"),
    "language": ("Interface language", "Язык интерфейса", "Мова інтерфейсу", "Interfacetaal"),
    "save": ("Save", "Сохранить", "Зберегти", "Opslaan"),
    "close": ("Close", "Закрыть", "Закрити", "Sluiten"),
    "remove": ("Remove", "Удалить", "Видалити", "Verwijderen"),
    "app": ("Program", "Программа", "Програма", "Programma"),
    "words": ("Words", "Слов", "Слів", "Woorden"),
    "languages": ("Languages", "Языки", "Мови", "Talen"),
    "mode": ("Mode", "Режим", "Режим", "Modus"),
    "mode_auto": ("auto", "авто", "авто", "auto"),
    "mode_off": ("off", "выкл.", "вимк.", "uit"),
    "mode_latin": ("Latin only", "только латиница", "лише латиниця", "alleen Latijns"),
    "add_app": ("Add program (exe)…", "Добавить программу (exe)…", "Додати програму (exe)…", "Programma toevoegen (exe)…"),
    "exceptions_hint": ("Words you undid with Backspace. Keyglot leaves them as typed.",
                        "Слова, которые вы откатили Backspace. Keyglot оставляет их как набраны.",
                        "Слова, які ви відкотили Backspace. Keyglot залишає їх як набрані.",
                        "Woorden die u met Backspace ongedaan maakte. Keyglot laat ze zoals getypt."),
    "keys_hint": ("Backspace right after a fix: undo · Pause: convert last word · Shift+Pause: on/off",
                  "Backspace сразу после исправления: отмена · Pause: перевести последнее слово · Shift+Pause: вкл./выкл.",
                  "Backspace одразу після виправлення: скасувати · Pause: перекласти останнє слово · Shift+Pause: увімк./вимк.",
                  "Backspace direct na een correctie: ongedaan maken · Pause: laatste woord omzetten · Shift+Pause: aan/uit"),
    "tagline": ("Types in the language you meant.", "Печатает на том языке, на котором вы хотели.",
                "Друкує тією мовою, якою ви хотіли.", "Typt in de taal die u bedoelde."),
    "open_data": ("Open data folder", "Открыть папку данных", "Відкрити теку даних", "Gegevensmap openen"),
    "privacy": ("Everything stays on this computer. Nothing is sent anywhere, except the update check on GitHub.",
                "Всё остаётся на этом компьютере. В сеть уходит только проверка обновлений на GitHub.",
                "Усе залишається на цьому комп'ютері. У мережу йде лише перевірка оновлень на GitHub.",
                "Alles blijft op deze computer. Alleen de updatecontrole gaat naar GitHub."),
}
_IDX = {"en": 0, "ru": 1, "uk": 2, "nl": 3}
_lang = "en"


def system_lang():
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x19: "ru", 0x22: "uk", 0x13: "nl"}.get(lid, "en")
    except Exception:
        code = (locale.getdefaultlocale()[0] or "en")[:2]
        return code if code in _IDX else "en"


def set_lang(lang):
    global _lang
    _lang = system_lang() if lang in (None, "", "auto") else (lang if lang in _IDX else "en")


def t(key, **kw):
    row = S.get(key)
    if not row:
        return key
    s = row[_IDX[_lang]]
    return s.format(**kw) if kw else s
