# Changelog

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
