# Changelog

All notable changes to Featherpress are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

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
