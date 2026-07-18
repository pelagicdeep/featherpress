# Changelog

All notable changes to Featherpress are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

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
