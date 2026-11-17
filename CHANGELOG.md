# Changelog

## 0.3.4 — 2026-11-17

- Ctrl+Enter (send in CO Desktop, WhatsApp Web …) now fixes the last word like Enter does. Keyglot holds the
  key back, releases Ctrl for its Backspaces (so they do not become Ctrl+Backspace), types the fix and sends Ctrl+Enter.
- After a click, arrows, Home/End, Delete or a Ctrl shortcut the next word may continue text left of the caret:
  it gets no typo, ё or space fix and is no anchor for the next word (a click into `помо|` then `жет ему` became
  `же тему`). When the field shows a space or nothing left of the caret, the word is fixed as usual.
- Text without letters is never converted: `:-)` stays (was `Ж-)`), a lone `.` or `,` stays (was `ю`, `б`).
- A stray first letter is removed only when it is a neighbour key (`дописывает` is no longer `описывает`).
- A letter typed twice around a space is dropped once (`хочуя я` → `хочу я`, was `хочу яя`).

## 0.3.3 — 2026-11-16

- Fix: typing in Edge, WhatsApp Web, CO Desktop and other Chromium/Electron windows lagged at the start of a phrase —
  letters appeared only after a second or two. Keyglot read the visible conversation through UI Automation
  (`GetVisibleRanges`), which Chromium answers in 2+ s on its UI thread, and the window did not draw the keys
  meanwhile. Now it reads up to 3000 characters just before the field (or at the end of the document) in ~10–50 ms,
  and keeps it for 60 s.

## 0.3.2 — 2026-11-16

- The detailed input log writes one line per input instead of one per word. An input is what you type into one
  field until Enter, Tab, Esc, a window or browser-tab change, a click into another field or a minute's pause.
  The line has the final text, the text before it, the program, window, field, layouts, language of the text and
  conversation, and `keys`: every key in order — characters as the layout showed them, `⌫` Backspace, `⌦` Delete,
  arrows, `[^Z]` and other Ctrl shortcuts, `[click]`, `[Pause]`, `{→привет}` where Keyglot rewrote a word,
  `{undo}` where Backspace undid it. Words worth a look (fixes, near misses, retyped words, Backspace inside a word)
  are listed in `decisions` with the candidates and scores.
- A password field anywhere in the input drops the whole input; excluded windows are checked by title at every word.
- Pause on a word still being typed now keeps the converted word in the context Keyglot reads.
- `tools/log_digest.py` reads both formats and shows the edited inputs with their keys.

## 0.3.1 — 2026-11-16

- Detailed input log (Settings → General, off by default): one line per word with what was typed, what Keyglot
  decided and why (candidates, margin), the program, field, layout and the language of the text and conversation,
  plus your own edits — Backspace after a fix, Pause, and text you erased and typed again. Daily files in
  `%LOCALAPPDATA%\Keyglot\input`, deleted after 14 days (`log_days`). Password fields are never written, nor windows
  that match the exclusion list (password managers; ING, Keytrade by default — editable in Settings).
- The corrections log skips the excluded windows too.
- `tools/log_digest.py`: a Markdown digest of one day of the detailed log (undone fixes, retyped words, near misses).
- Fewer false fixes: a missing space is restored only when one part is a common word (`валидна` is no longer
  `вали дна`), never after a compound head (`автокоррекции` stays); a one-letter typo beats a split
  (`моели` → `модели`, not `моё ли`); case forms of a known noun are not typos (`имейла` stays).

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
