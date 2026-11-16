# Changelog

## 0.3.0 — 2026-11-16

- Typo fixes in words already typed in the right layout: one wrong, missing, extra or swapped letter
  (neighbour keys and doubled letters count as likely), two edits for longer words (`програама` → `программа`).
  Only words unknown in all languages of their alphabet; forms that look like a real inflection stay.
- ё in Russian words (`еще` → `ещё`, `пришел` → `пришёл`); words that are different words with е (`все`, `небо`) stay.
- A misplaced space: one letter too late or too early (`приветк ак`, `приве ткак` → `привет как`), a missing
  space (`приветкак`), a stray space inside a word.
- Fix: the first letters of a word are never turned into punctuation (`эьл` became `'mk`).
- The layout is read from the thread that has the keyboard focus, and the switch request also goes to the focused
  window (Chromium/Electron apps such as Edge, LinkedIn, CO Desktop).
- The log records the layout of each fix and `switch_missed` when a requested layout switch did not take.
- Settings: Fix typos, Put ё, Fix spaces (all on by default).

## 0.2.0 — 2026-11-16

First public build.

- Corrects words typed in the wrong layout (English/Dutch, Russian, Ukrainian) at Space or Enter, switches the layout.
- Decides by context, not by one word: the program and window, the kind of field, the text before the caret,
  the visible conversation or document, the previous word, a manual layout switch, learned habits.
- Field kinds: terminals and code (only Cyrillic garbage → Latin commands and keywords; comments and strings are prose),
  paths and Run dialog, e-mail/login fields, browser address bar (domain vs search), password fields are never touched.
- A word in another language that is a real word stays: `deadline` in a Russian text is kept.
- Fixes the previous short word too (`b ghbdtn` → `и привет`) and punctuation typed on Latin positions (`приветю` → `привет.`).
- Backspace right after a correction restores the original and remembers it. Pause converts the last word by hand, Shift+Pause turns Keyglot off/on.
- Picks the layout in advance when you switch to a window where you nearly always write one language.
- Tray icon with the current language, settings window (per-program modes, exceptions), English/Russian/Ukrainian/Dutch UI.
- Per-user installer, start with Windows, automatic updates from GitHub Releases (SHA-256 checked).
