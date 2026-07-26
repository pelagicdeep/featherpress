# Featherpress

A dyslexic-first publishing pipeline. One manuscript in, five accessible formats out.

Drop in a `.md`, `.txt`, `.docx`, `.pdf`, or `.epub` file and get:

1. **OpenDyslexic PDF**: cream or dark theme, 12.5pt body, 1.8x line spacing, wide margins, left-aligned ragged right, page numbers.
2. **Accessible EPUB**: OpenDyslexic fonts embedded, high-contrast CSS, chapters split automatically at every `# Heading 1`.
3. **Audiobook-ready text**: formatting stripped, abbreviations expanded (Dr. becomes Doctor, e.g. becomes for example), symbols spoken (% becomes percent), chapter announcements added. Ready to feed straight into Piper or any TTS engine.
4. **Voiced audiobook**: the narration text read aloud and stitched into an `.m4b` with chapter markers, title, and author metadata. Voices come from Microsoft's Edge neural catalog by default (natural-sounding, 300+ voices across dozens of languages, needs internet) with Piper as the fully offline fallback. Speech speed is adjustable. Opt-in (`--formats audio` or the AUDIO checkbox) because voicing a whole book takes a while.
5. **Standalone HTML reader**: a single self-contained file with fonts embedded, live dark/cream theme toggle, a Dyslexic/Standard font toggle, font size and line spacing controls, keyboard accessible, reduced-motion aware.

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
| `--voice` | Audiobook voice, Edge or Piper (see below) | `en-US-AndrewMultilingualNeural` |
| `--rate` | Speech speed in percent, negative = slower | `0` |
| `--keep-front-matter` | Keep EPUB cover/copyright/contents pages | skipped |

### The voiced audiobook

Two engines, chosen automatically from the voice name:

- **Edge neural voices** (default) — names like `en-US-AriaNeural`: Microsoft's neural TTS via the free `edge-tts` package. Natural prosody, solid pronunciation of foreign words, 300+ voices across dozens of languages. Needs an internet connection while voicing. The GUI's "Choose voice..." window lists the whole catalog with search, language and gender filters, and a per-voice sample button.
- **Piper voices** — names like `en_US-lessac-medium`: fully offline after a one-time ~60 MB model download into `voices/`. More robotic, but nothing leaves your machine. Catalog at [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).

**ffmpeg** is needed for the chaptered `.m4b` (`winget install Gyan.FFmpeg` on Windows). Without it you still get audio: one plain `.wav` (Piper) or per-chapter `.mp3` files (Edge).

The narration holds real pauses where the manuscript asks for them: a beat at every `---` scene break, around section headings, after quotes, and a breath at chapter and book turns — so contemplative passages land instead of being steamrolled.

Long books voice in resumable parts: progress prints as each part finishes, and if the run is interrupted, running the same conversion again picks up where it left off (the `.<name>_work` folder next to the output holds the finished parts until assembly).

For playback, anything that understands audiobooks will show the chapter list and remember your position: VLC on the desktop, or Smart AudioBook Player / BookPlayer on phones. Most players also have their own speed control on top of `--rate`.

## Input handling

- **Markdown**: headings (h1 to h3), bold, italic, bullet and numbered lists, blockquotes, horizontal rules. Links keep their text, URLs are dropped.
- **Word (.docx)**: Heading styles, bold/italic runs, List Bullet and List Number styles, Quote styles. Footnotes become renumbered `[N]` markers with a "Notes" section at the end, tables carry through to every output, and inline images leave an `[image: alt text]` placeholder so nothing silently disappears.
- **Plain text**: paragraphs split on blank lines.
- **EPUB**: chapters are read in reading order from the book's own spine, headings, bold/italic, lists, and blockquotes carry across, and the table-of-contents page is skipped. Deep heading levels fold into h3. Images and tables are dropped (table text survives as plain paragraphs). Front matter is skipped automatically: conversion starts at the book's own "start reading" marker when it declares one, otherwise leading cover, copyright, praise-quote, and contents pages are dropped (dedications and epigraphs are kept). Pass `--keep-front-matter` to keep everything.
- **PDF**: text is extracted with structure inference. Font sizes rebuild the headings, the document's own line spacing is measured so paragraphs group correctly, hyphenation across line breaks is repaired, and repeated headers, footers, and bare page numbers are stripped. Honest limitations: bullets flatten into plain lines (their glyphs may appear as stray characters), bold and italic are lost, and scanned PDFs have no text layer at all, so the tool will tell you to OCR them first (ocrmypdf works well). PDF is the lossiest input; when you have the original .docx or .md, prefer it.

Chapters are detected at h1 boundaries for the EPUB table of contents and the TTS chapter announcements.

### Combining a series

Pass several manuscripts in reading order (or multi-select in the GUI) and they merge into one continuous book:

```bash
python featherpress.py book1.md book2.md book3.md --title "The Trilogy" --formats tts,audio
```

Each volume's own title page (title, subtitle, epigraph, dedication) is stripped so the story flows straight through. In the audiobook, every seam becomes a *silent* chapter marker — the book's title shows in your player's chapter list, but nothing extra is spoken. In the PDF, EPUB, and HTML outputs the book titles appear as top-level headings.

Any volume can have its own narrator — useful when a book inside a series is told by a different voice. On the CLI, `--book-voice MATCH=VOICE` (repeatable) matches against filenames: `--book-voice feather=en-GB-RyanNeural`. In the GUI, the "Narrators..." button lists the selected books with a voice picker for each. Per-book narrators need Edge voices throughout.

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

**The GUI.** Double-click `featherpress_gui.bat`. A small dark window: choose your file, optionally set title and author, pick a theme, a narration voice ("Choose voice..." opens the full searchable catalog; "Hear sample" speaks a preview line before you commit to a whole book), and a speech speed, press Convert. The interface itself is accessible: toggle between the OpenDyslexic and standard fonts, and between Normal and Large text (the window scales with it); both choices are remembered. The "Version history" button shows the full changelog in-app. The output folder opens when it finishes. Built on tkinter, which ships with Python, so there is nothing extra to install.

Both use the exact same pipeline underneath; the terminal remains the power-user door for custom output paths and format selection.

## Version history

Current version: **1.10.0**. The full history lives in [CHANGELOG.md](CHANGELOG.md)
and is browsable in-app via the GUI's "Version history" button.
`python featherpress.py --version` prints the version on the command line.
The working plan (done, decided, next, gaps) lives in [PLAN.md](PLAN.md).

## Fonts

OpenDyslexic by Abbie Gonzalez, SIL Open Font License. The TTFs here were converted from the official OTF releases (CFF to TrueType) so ReportLab can embed them.

## Prefer studio-grade narration?

The voices here are free and get the job done, but they are not human. For the most natural AI narration around, try [ElevenReader](https://elevenreader.io) — ElevenLabs' reading app with their studio-grade voices. It reads EPUBs directly, so the accessible EPUB that Featherpress produces drops straight in.

<!-- affiliate: replace the link above with your ElevenLabs affiliate URL -->

---

By PelagicDeep. Claude was the feather.
