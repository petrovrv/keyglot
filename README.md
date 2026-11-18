<p align="center"><img src="assets/keyglot.png" width="96" alt="Keyglot"></p>

<h1 align="center">Keyglot</h1>
<p align="center"><b>Types in the language you meant.</b><br>
A context-aware keyboard layout switcher for Windows — English, Dutch, Russian, Ukrainian.</p>

---

You type `ghbdtn` and meant `привет`. Classic switchers look at one word and guess; they miss short words,
break passwords and commands, and cannot tell Russian from Ukrainian. Keyglot reads the situation the way you do:

| Signal | Example |
|---|---|
| **Words** | Frequency dictionaries of 120–220k words per language and a letter model for unknown words |
| **The field** | Terminal, code editor, path, e-mail field, address bar or a normal text box — each has its own rules |
| **Text before the caret** | You are writing a Russian e-mail: a short ambiguous word becomes Russian |
| **The conversation** | The visible chat or mail thread tells which language you answer in |
| **Your habits** | Keyglot learns which language you use in which program and window |
| **Your intent** | A layout you switched by hand wins; Backspace after a fix undoes it and is remembered |

A real word of another language is left alone: `deadline` stays `deadline` inside Russian text.
In a terminal only Cyrillic garbage that is a command becomes Latin (`пше ыефегы` → `git status`), never the other way.

In normal text Keyglot also fixes clear typos (`програама` → `программа`, `wrold` → `world`), puts ё into
Russian words (`еще` → `ещё`, but `все` stays: it can be either), and repairs a space typed a letter too late or
too early or missed (`приветк ак` / `приве ткак` / `приветкак` → `привет как`). Only words that are unknown in every
language of their alphabet are touched, and Backspace undoes any fix.

## Install

Download **Keyglot-Setup-x.y.z.exe** from [Releases](https://github.com/petrovrv/keyglot/releases/latest) and run it.
No administrator rights needed. Keyglot updates itself from this page.

> Windows SmartScreen may warn about an unknown publisher (the installer is not code-signed yet): *More info → Run anyway*.

## Use

Just type. The tray icon shows the language of the active window.

| Key | Action |
|---|---|
| **Backspace** right after a correction | Undo it and remember the word |
| **Shift+Backspace** | Convert the last word to the other layout (press again: next option, then back) |
| **Alt+Backspace** | Treat the last word as a typo and fix it (press again: next suggestion, then back) |
| **Pause** | Same as Shift+Backspace |
| **Shift+Pause** | Turn Keyglot off/on |

Settings (tray icon → Settings): correction on Enter, typos, ё, spaces, layout pre-switch per window, per-program mode
(*auto*, *off*, *Latin only*), exceptions, updates, interface language (English, Русский, Українська, Nederlands).

## Privacy

Everything runs on your computer. Keyglot keeps per-program language counts, your exceptions and a log of corrections
(`%LOCALAPPDATA%\Keyglot`, can be switched off). Password fields are never read or changed.
An optional detailed input log (off by default) records every input — the phrase typed into one field up to Enter,
Tab, a window change or a pause — with its context, every key pressed (Backspace, arrows, Ctrl+Z, Pause, Keyglot's own
rewrites and their undo) and Keyglot's decisions, for tuning;
it stays in `%LOCALAPPDATA%\Keyglot\input`, is deleted after 14 days and skips password fields and excluded windows
(password managers and banks by default). `python tools/log_digest.py` summarises a day of it.
The only network access is the update check against GitHub.

Windows does not let a normal program see keys typed into windows running as administrator; Keyglot does nothing there.

## Build

```powershell
pip install -r requirements-build.txt
./build.ps1            # language data, tests, PyInstaller bundle, Inno Setup installer in dist\
python -m keyglot      # run from source
python -m keyglot --explain "ghbdtn rfr ltkf"   # see how a phrase is decided
```

Releases are built by GitHub Actions on a `v*` tag.

## License

MIT. Word frequencies come from [wordfreq](https://github.com/rspeer/wordfreq) (data CC BY-SA 4.0).
