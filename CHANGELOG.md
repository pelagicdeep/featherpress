# Changelog

All notable changes to Featherpress are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [1.14.0] - 2026-07-28

### Added
- Simplify mode (`--simplify`, or the "Simplify references" checkbox in the
  GUI): a reading aid for reference-heavy documents like academic papers
  and technical reports. Strips inline citations (`[12]`, `[1,2,5]`,
  `[17-28]`, and author-year forms), expands acronyms the document defines
  itself (learns "water holding capacity (WHC)" and expands every later
  "WHC"), drops the reference list, and removes journal furniture (DOIs,
  copyright and publisher notices, running headers).

### Fixed
- PDF word-spacing recovery: some PDFs (many academic journals) encode
  spacing as glyph position rather than space characters, so extraction
  jammed words together ("Improvingsoilwater"). Featherpress now rebuilds
  word boundaries from character positions when a line comes out jammed.

## [1.13.1] - 2026-07-28

### Changed
- License: MIT to GPL-3.0-or-later. Featherpress's core engines
  (EbookLib, piper-tts, edge-tts) are AGPL/GPL already, so the combined
  work was effectively copyleft; the project license now says so
  honestly, and improvements to this accessibility tool stay open for
  the readers it serves. Releases up to v1.13.0 remain MIT. Fonts stay
  under their own SIL Open Font License.

## [1.13.0] - 2026-07-27

### Added
- Atkinson Hyperlegible and Lexend ship bundled (SIL OFL, license texts
  in fonts/) and become named choices: `--font atkinson` / `--font
  lexend` on the CLI, radio options in the GUI's Book font rows. The
  PDF, EPUB, and HTML reader embed them like any custom family, and the
  reader's toggle is labeled with the actual font name. Lexend has no
  italic faces upstream, so italics render in regular there.

## [1.12.0] - 2026-07-27

### Added
- Bring your own font: `--font` now also accepts a path to a .ttf/.otf
  file or a folder of them, and the GUI's Book font row gains a
  "Custom..." picker. Give it one file and the Bold/Italic/BoldItalic
  siblings are found by name; missing variants fall back to regular.
  The PDF embeds the family (and is named after it), the EPUB embeds
  every variant with proper @font-face weights and styles, and the HTML
  reader embeds it with its toggle honestly labeled "Font: Custom".
  Clear errors for missing files and CFF-flavored .otf in the PDF path.

## [1.11.0] - 2026-07-26

### Added
- The output font is now a choice: `--font dyslexic` (default) or
  `--font standard` on the CLI, and a "Book font" selector in the GUI.
  OpenDyslexic remains the dyslexia-first default; standard mode gives
  non-dyslexic readers a conventional book. In standard mode the PDF
  uses clean built-in Helvetica (named `*_standard_<theme>.pdf`), the
  EPUB embeds no fonts so the reading system's own font and the
  reader's overrides rule, and the HTML reader simply starts on the
  Standard side of its live font toggle.

## [1.10.1] - 2026-07-26

### Fixed
- With OpenDyslexic or Large text enabled, the Convert / Open output /
  Install buttons could be pushed off the window edge and become
  unclickable. The button row is now pinned to the bottom with packing
  priority (it can never be clipped), the voice buttons moved to their
  own row so long voice names cannot shove them off the right edge,
  utility button labels shortened, and the Large window grew.

## [1.10.0] - 2026-07-26

### Added
- Full version history in the app: the GUI's "Version history" button
  (formerly "What's new") opens the complete changelog in a scrollable
  window, so the running list of changes is visible without leaving the
  tool.
- Interface accessibility for the GUI itself: a font toggle between
  OpenDyslexic (bundled, loaded privately, no install needed) and the
  standard system font, plus a Normal/Large text size toggle for low
  vision. Sizes are driven by named fonts so every widget, list row, and
  window scales together; the window and pickers grow with the text so
  nothing clips. Choices persist in gui_settings.json (gitignored).
- The standalone HTML reader gains the same font choice: a Font
  Dyslexic/Standard toggle beside the theme button.
- PLAN.md: the living working plan (shipped, decisions, next up, gaps),
  updated as work lands so an interrupted session costs nothing.

## [1.9.0] - 2026-07-25

### Added
- Per-book narrators in combine mode ("different instruments"): give any
  volume its own Edge voice while the rest read in the main voice. CLI:
  repeatable `--book-voice MATCH=VOICE`, where MATCH is a filename
  fragment (e.g. `--book-voice feather=en-GB-RyanNeural`). GUI: the
  "Narrators..." button lists the selected books, each with its own
  full-catalog voice picker. Mixing Piper into a multi-narrator book is
  rejected with a clear error.

## [1.8.0] - 2026-07-22

### Added
- Dramatic pauses in the voiced audiobook (Edge + ffmpeg): the narration
  now holds real silence where the manuscript asks for a beat — 1.5s at
  scene breaks (`---`), around section headings, after quotes, and a 2s
  breath at every chapter and book turn. Adjacent pauses merge, capped at
  2.5s. The TTS text output is unchanged.

## [1.7.0] - 2026-07-22

### Changed
- Edge audiobook synthesis is now chunked, concurrent, and resumable.
  Chapters split into ~4000-character parts, four parts voice at once
  (roughly 4x faster on a long book), every part reports progress, and a
  dropped connection retries that part instead of stalling the whole run.
  Parts persist in a `.<name>_work` folder next to the output, so an
  interrupted conversion picks up where it stopped instead of starting
  over; the folder is removed once the audiobook is assembled.

## [1.6.0] - 2026-07-21

### Added
- Word (.docx) edge cases, ported from the July 6 workshop fork: footnotes
  become renumbered `[N]` markers with a "Notes" endnote section, tables
  carry through to every output (rows in the PDF, real `<table>` in
  EPUB/HTML, "Table." announcements in narration), and inline images leave
  an `[image: alt text]` placeholder. `tests/make_fixtures.py` generates
  the docx fixture exercising all three.

### Fixed
- A stale local copy of Featherpress (which had none of the audio
  features) now forwards its launchers to this repo, so old shortcuts
  open the current version.

## [1.5.0] - 2026-07-21

### Added
- Combine mode: pass several manuscripts to the CLI (in reading order), or
  multi-select in the GUI's file picker, and they merge into one continuous
  book. Each volume's own title page — title, subtitle, epigraph,
  dedication — is stripped so the narration flows without interruption;
  every seam becomes a silent chapter marker in the audiobook (the book's
  title in the player's chapter list, nothing spoken) and a top-level
  heading in the PDF/EPUB/HTML outputs. Manuscripts whose first heading is
  a chapter rather than a title page are detected and kept whole.

## [1.4.0] - 2026-07-18

### Added
- Edge neural voices are now the default audiobook engine (via the free
  `edge-tts` package): natural prosody, much better pronunciation of foreign
  words, 300+ voices across dozens of languages. Needs internet while
  voicing; Piper remains as the fully offline engine, chosen automatically
  when the voice name looks like `en_US-lessac-medium`.
- Full voice-picker window in the GUI: the entire Edge catalog plus the
  offline Piper voices, with search, language and gender filters, per-voice
  samples, and double-click to select.
- Speech speed control: `--rate` on the CLI (percent, negative = slower)
  and a speed slider in the GUI. Works with both engines and is applied to
  voice samples too.
- Without ffmpeg, Edge voicing now writes per-chapter numbered `.mp3` files.
- README pointer to ElevenReader for studio-grade narration of the
  Featherpress EPUB.

### Changed
- Default voice is now `en-US-AndrewMultilingualNeural`.

## [1.3.0] - 2026-07-17

### Added
- Voice picker in the GUI: a dropdown of eight curated English Piper voices
  (US and British, male and female) with a "Hear sample" button that speaks
  a short preview line in the chosen voice. Samples are synthesized once and
  cached in `voices/samples/`; the first listen of a new voice downloads its
  model (~60 MB). The chosen voice is used for the audiobook conversion.

## [1.2.0] - 2026-07-17

### Added
- Voiced audiobook output (`--formats audio`, or the AUDIO checkbox in the
  GUI): each chapter is narrated locally by Piper TTS and stitched into an
  `.m4b` audiobook with chapter markers, book title, and author metadata.
  Needs ffmpeg for the `.m4b`; without it a plain `.wav` is written instead.
  Voicing runs fully offline; the voice model (~60 MB) downloads on first
  use into `voices/`.
- `--voice` flag to pick any Piper voice (default `en_US-lessac-medium`).
- MIT license.

### Changed
- The TTS text builder now shares a chapterized narration script with the
  audiobook builder; chapters in the text file are separated by blank lines.

## [1.1.0] - 2026-07-17

### Added
- EPUB input support: chapters are read in reading order from the book's own
  spine, with headings, bold/italic, lists, and blockquotes carried across.
  Deep heading levels fold into h3; the table-of-contents page is skipped.
- Front matter is skipped automatically for EPUBs. Conversion starts at the
  book's own "start reading" marker (EPUB2 guide / EPUB3 landmarks) when one
  is declared; otherwise leading cover, copyright, praise, publisher, and
  contents pages are dropped while dedications and epigraphs are kept. A
  leftover in-book contents listing is also detected and skipped through to
  the first Prologue / Chapter One heading with real prose behind it.
- `--keep-front-matter` flag to keep everything.
- `--version` flag on the CLI; the GUI shows its version in the header and a
  "What's new" button that prints the latest changes.

### Fixed
- Dropping an `.epub` on the converter no longer produces garbled symbols.
  An EPUB is a zip archive, and it was being read as plain text.

## [1.0.0] - 2026-07-02

### Added
- Initial release: one manuscript in (`.md`, `.txt`, `.docx`, `.pdf`), four
  accessible formats out — OpenDyslexic PDF, high-contrast EPUB with embedded
  fonts, audiobook-ready TTS text, and a standalone HTML reader with live
  theme, font size, and line spacing toggles.
- Cream and dark themes shared by every output format.
- PDF input with structure inference: headings rebuilt from font sizes,
  paragraphs grouped by measured line spacing, de-hyphenation across line
  breaks, repeated headers/footers and bare page numbers stripped.
- The exhausted-evening interfaces: drag-and-drop converter
  (`featherpress_drop.bat`) and tkinter GUI (`featherpress_gui.py`).
