# Featherpress

A dyslexic-first publishing pipeline. One manuscript in, five accessible formats out.

Drop in a `.md`, `.txt`, `.docx`, `.pdf`, or `.epub` file and get:

1. **OpenDyslexic PDF**: cream or dark theme, 12.5pt body, 1.8x line spacing, wide margins, left-aligned ragged right, page numbers.
2. **Accessible EPUB**: OpenDyslexic fonts embedded, high-contrast CSS, chapters split automatically at every `# Heading 1`.
3. **Audiobook-ready text**: formatting stripped, abbreviations expanded (Dr. becomes Doctor, e.g. becomes for example), symbols spoken (% becomes percent), chapter announcements added. Ready to feed straight into Piper or any TTS engine.
4. **Voiced audiobook**: the narration text read aloud by Piper TTS, fully offline, stitched into an `.m4b` with chapter markers, title, and author metadata. Opt-in (`--formats audio` or the AUDIO checkbox) because voicing a whole book takes a while.
5. **Standalone HTML reader**: a single self-contained file with fonts embedded, live dark/cream theme toggle, font size and line spacing controls, keyboard accessible, reduced-motion aware.

## Setup

Requires Python 3.9+.

```bash
pip install -r requirements.txt
```

The `fonts/` folder ships with the pipeline. Keep it next to `featherpress.py`.

## Usage

```bash
# Everything, default cream theme
python featherpress.py manuscript.md -o output/

# Dark theme, with metadata
python featherpress.py book.docx --title "My Book" --author "PelagicDeep" --theme dark

# Just the formats you want
python featherpress.py notes.txt --formats pdf,tts
```

| Flag | What it does | Default |
|------|--------------|---------|
| `-o, --outdir` | Output directory | `featherpress_output` |
| `--title` | Book title | Derived from filename |
| `--author` | Author name | none |
| `--theme` | `cream` or `dark` (PDF and EPUB) | `cream` |
| `--formats` | Any of `pdf,epub,tts,html,audio` | `pdf,epub,tts,html` |
| `--voice` | Piper voice for the audiobook | `en_US-lessac-medium` |
| `--keep-front-matter` | Keep EPUB cover/copyright/contents pages | skipped |

### The voiced audiobook

`--formats audio` needs two extra pieces:

- **Piper TTS** (`pip install piper-tts`, already in requirements.txt). The voice model (~60 MB) downloads once into `voices/` on first use, then everything runs offline. Browse other voices at [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) and pass the name with `--voice`.
- **ffmpeg** for the chaptered `.m4b` (`winget install Gyan.FFmpeg` on Windows). Without it you still get audio, just as one plain `.wav` with no chapter marks.

## Input handling

- **Markdown**: headings (h1 to h3), bold, italic, bullet and numbered lists, blockquotes, horizontal rules. Links keep their text, URLs are dropped.
- **Word (.docx)**: Heading styles, bold/italic runs, List Bullet and List Number styles, Quote styles.
- **Plain text**: paragraphs split on blank lines.
- **EPUB**: chapters are read in reading order from the book's own spine, headings, bold/italic, lists, and blockquotes carry across, and the table-of-contents page is skipped. Deep heading levels fold into h3. Images and tables are dropped (table text survives as plain paragraphs). Front matter is skipped automatically: conversion starts at the book's own "start reading" marker when it declares one, otherwise leading cover, copyright, praise-quote, and contents pages are dropped (dedications and epigraphs are kept). Pass `--keep-front-matter` to keep everything.
- **PDF**: text is extracted with structure inference. Font sizes rebuild the headings, the document's own line spacing is measured so paragraphs group correctly, hyphenation across line breaks is repaired, and repeated headers, footers, and bare page numbers are stripped. Honest limitations: bullets flatten into plain lines (their glyphs may appear as stray characters), bold and italic are lost, and scanned PDFs have no text layer at all, so the tool will tell you to OCR them first (ocrmypdf works well). PDF is the lossiest input; when you have the original .docx or .md, prefer it.

Chapters are detected at h1 boundaries for the EPUB table of contents and the TTS chapter announcements.

## Design choices, on purpose

- Left-aligned text, never justified. Justified text creates rivers of white space that make tracking harder.
- Line length held near 60 characters via wide margins.
- Line spacing at 1.8x, generous paragraph gaps.
- Cream background as the print default; pure white increases glare and visual stress.
- The dark theme uses near-black with warm off-white ink, cyan headings, and gold accents.

## Extending it

- Add TTS abbreviations in `TTS_ABBREV`, one regex per line.
- Add or adjust themes in the `THEMES` dict at the top; every output picks them up.
- The `Block` model is deliberately simple. New input formats just need a `parse_*` function that returns a list of Blocks.


## The exhausted-evening interfaces

Terminal optional. Two other doors:

**Drag and drop.** Drag any manuscript (or several at once) onto `featherpress_drop.bat` in File Explorer. Everything converts with defaults (dark theme, all formats, title from the filename) and the output folder opens itself. If something fails, the window stays open so you can read why.

**The GUI.** Double-click `featherpress_gui.bat`. A small dark window: choose your file, optionally set title and author, pick a theme and a narration voice (the "Hear sample" button speaks a preview line in the chosen voice before you commit to a whole book), press Convert. The output folder opens when it finishes. Built on tkinter, which ships with Python, so there is nothing extra to install.

Both use the exact same pipeline underneath; the terminal remains the power-user door for custom output paths and format selection.

## Version history

Current version: **1.3.0**. The full history lives in [CHANGELOG.md](CHANGELOG.md).
The GUI shows its version in the header, and its "What's new" button prints the latest changes.
`python featherpress.py --version` does the same on the command line.

## Fonts

OpenDyslexic by Abbie Gonzalez, SIL Open Font License. The TTFs here were converted from the official OTF releases (CFF to TrueType) so ReportLab can embed them.

---

By PelagicDeep. Claude was the feather.
