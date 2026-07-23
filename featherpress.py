#!/usr/bin/env python3
"""
Featherpress: a dyslexic-first publishing pipeline.

Takes one manuscript (.md, .txt, .docx, .pdf, or .epub) and produces:
  1. An OpenDyslexic PDF (cream or dark theme)
  2. A high-contrast EPUB with embedded OpenDyslexic fonts
  3. Audiobook-ready plain text (TTS-cleaned)
  4. A voiced audiobook (.m4b with chapters, via Piper TTS + ffmpeg)
  5. A standalone accessible HTML reader with live toggles

Usage:
  python featherpress.py manuscript.md -o output/
  python featherpress.py book.docx --title "My Book" --author "PelagicDeep" --theme dark
  python featherpress.py notes.txt --formats pdf,tts
"""

import argparse
import base64
import html as html_mod
import os
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

__version__ = "1.8.0"

SCRIPT_DIR = Path(__file__).resolve().parent
FONT_DIR = SCRIPT_DIR / "fonts"

FONTS = {
    "regular": "OpenDyslexic-Regular.ttf",
    "bold": "OpenDyslexic-Bold.ttf",
    "italic": "OpenDyslexic-Italic.ttf",
    "bolditalic": "OpenDyslexic-Bold-Italic.ttf",
}

THEMES = {
    "cream": {
        "bg": "#FAF4E6", "ink": "#2B2A26", "heading": "#5C4A1E",
        "accent": "#8A6D1F", "quote_bar": "#C9B26B", "muted": "#6B675E",
    },
    "dark": {
        "bg": "#0C1015", "ink": "#E6E3DC", "heading": "#7FDBE8",
        "accent": "#D9B84A", "quote_bar": "#B9A7E8", "muted": "#9A968C",
    },
}


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------

@dataclass
class Block:
    kind: str                 # h1 h2 h3 p quote li-ul li-ol hr table book
    text: str = ""            # inline HTML subset: <b> <i> only
    items: list = field(default_factory=list)  # list items, or table rows


def strip_inline(text: str) -> str:
    """Remove the inline <b>/<i> tags, returning plain text."""
    return re.sub(r"</?(b|i)>", "", text)


# ---------------------------------------------------------------------------
# Input parsers
# ---------------------------------------------------------------------------

MD_INLINE = [
    (re.compile(r"\*\*\*(.+?)\*\*\*"), r"<b><i>\1</i></b>"),
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"__(.+?)__"), r"<b>\1</b>"),
    (re.compile(r"\*(.+?)\*"), r"<i>\1</i>"),
    (re.compile(r"_(.+?)_"), r"<i>\1</i>"),
    (re.compile(r"`(.+?)`"), r"\1"),
    (re.compile(r"\[(.+?)\]\((.+?)\)"), r"\1"),
]


def md_inline(text: str) -> str:
    text = html_mod.escape(text, quote=False)
    for pat, rep in MD_INLINE:
        text = pat.sub(rep, text)
    return text.strip()


def parse_markdown(raw: str) -> list:
    blocks, para, ul, ol = [], [], [], []

    def flush_para():
        if para:
            blocks.append(Block("p", md_inline(" ".join(para))))
            para.clear()

    def flush_lists():
        if ul:
            blocks.append(Block("li-ul", items=[md_inline(i) for i in ul]))
            ul.clear()
        if ol:
            blocks.append(Block("li-ol", items=[md_inline(i) for i in ol]))
            ol.clear()

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_para(); flush_lists(); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para(); flush_lists()
            level = min(len(m.group(1)), 3)
            blocks.append(Block(f"h{level}", md_inline(m.group(2))))
            continue
        if re.match(r"^(\*\s*){3,}$|^(-\s*){3,}$|^(_\s*){3,}$", stripped):
            flush_para(); flush_lists()
            blocks.append(Block("hr")); continue
        if stripped.startswith(">"):
            flush_para(); flush_lists()
            blocks.append(Block("quote", md_inline(stripped.lstrip("> ")))); continue
        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            flush_para()
            ul.append(m.group(1)); continue
        m = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if m:
            flush_para()
            ol.append(m.group(1)); continue
        flush_lists()
        para.append(stripped)
    flush_para(); flush_lists()
    return blocks


def parse_plaintext(raw: str) -> list:
    blocks, para = [], []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            if para:
                blocks.append(Block("p", html_mod.escape(" ".join(para), quote=False)))
                para.clear()
            continue
        para.append(stripped)
    if para:
        blocks.append(Block("p", html_mod.escape(" ".join(para), quote=False)))
    return blocks


def parse_docx(path: Path) -> list:
    from docx import Document
    from docx.table import Table
    from docx.oxml.ns import qn
    from docx.oxml import parse_xml
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    doc = Document(str(path))
    blocks, ul, ol = [], [], []

    # --- footnotes: build id->text map (skip separators), renumber in doc order ---
    fn_text = {}                      # docx id (str) -> body text
    try:
        fpart = doc.part.part_related_by(RT.FOOTNOTES)
    except KeyError:
        fpart = None
    if fpart is not None:
        root = parse_xml(fpart.blob)
        for fn in root.findall(qn("w:footnote")):
            if fn.get(qn("w:type")):          # separator / continuationSeparator
                continue
            fid = fn.get(qn("w:id"))
            raw = "".join(t.text or "" for t in fn.iter(qn("w:t"))).strip()
            # items convention: li-ol items are stored escaped; blocks_to_html
            # interpolates them raw into <li>...</li> and build_pdf feeds them to
            # reportlab's mini-XML Paragraph parser, so an unescaped & or < would
            # corrupt HTML/EPUB and crash the PDF build. Escape at extraction, once.
            fn_text[fid] = html_mod.escape(raw, quote=False)
    fn_seq = []                       # ordered list of note texts, doc order
    fn_num = {}                       # docx id -> assigned 1..N

    def note_marker(fid):
        if fid not in fn_text:        # dangling ref: ignore
            return ""
        if fid not in fn_num:
            fn_seq.append(fn_text[fid])
            fn_num[fid] = len(fn_seq)
        return f"[{fn_num[fid]}]"

    def run_html(par):
        out = []
        for run in par.runs:
            r = run._r
            ref = r.find(qn("w:footnoteReference"))   # check BEFORE text skip
            t = html_mod.escape(run.text, quote=False)
            if t:
                if run.bold and run.italic:
                    t = f"<b><i>{t}</i></b>"
                elif run.bold:
                    t = f"<b>{t}</b>"
                elif run.italic:
                    t = f"<i>{t}</i>"
                out.append(t)
            if ref is not None:
                out.append(note_marker(ref.get(qn("w:id"))))
        return "".join(out).strip()

    def image_alts(par):
        alts = []
        for run in par.runs:
            for dr in run._r.findall(qn("w:drawing")):
                docpr = dr.find(".//" + qn("wp:docPr"))
                alt = None
                if docpr is not None:
                    alt = docpr.get("descr") or docpr.get("name")
                alts.append(alt or "unnamed")
        return alts

    def flush_lists():
        if ul:
            blocks.append(Block("li-ul", items=list(ul))); ul.clear()
        if ol:
            blocks.append(Block("li-ol", items=list(ol))); ol.clear()

    def emit_paragraph(par):
        imgs = image_alts(par)                # collect BEFORE early-out
        text = run_html(par)
        style = (par.style.name or "").lower()
        if text:
            if style.startswith("heading"):
                flush_lists()
                m = re.search(r"(\d+)", style)
                level = min(int(m.group(1)) if m else 1, 3)
                blocks.append(Block(f"h{level}", text))
            elif "quote" in style:
                flush_lists()
                blocks.append(Block("quote", text))
            elif "list bullet" in style:
                ul.append(text)
            elif "list number" in style:
                ol.append(text)
            else:
                flush_lists()
                blocks.append(Block("p", text))
        for alt in imgs:                      # image placeholder p-blocks
            flush_lists()
            blocks.append(Block("p", f"[image: {html_mod.escape(alt, quote=False)}]"))

    def emit_table(tbl):
        flush_lists()
        rows = [[cell.text for cell in row.cells] for row in tbl.rows]
        blocks.append(Block("table", items=rows))

    for item in doc.iter_inner_content():
        if isinstance(item, Table):
            emit_table(item)
        else:  # Paragraph
            emit_paragraph(item)
    flush_lists()

    if fn_seq:                                # endnotes: reuse h2 + li-ol only
        blocks.append(Block("h2", "Notes"))
        blocks.append(Block("li-ol", items=list(fn_seq)))
    return blocks


class _EpubHTMLParser(HTMLParser):
    """Convert one XHTML chapter into Blocks, keeping only <b>/<i> inline."""

    SKIP = {"script", "style", "head", "title", "nav", "template", "svg"}
    HEADINGS = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h3", "h5": "h3", "h6": "h3"}
    FLUSHERS = {"p", "div", "section", "article", "figure", "figcaption",
                "table", "tr", "td", "th", "dl", "dt", "dd", "pre", "aside"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.buf = []
        self.kind = "p"
        self.quote = 0
        self.skip = 0
        self.li_depth = 0
        self.lists = []  # stack of (kind, items)

    @staticmethod
    def _balance(text):
        for tag in ("b", "i"):
            opens, closes = text.count(f"<{tag}>"), text.count(f"</{tag}>")
            if opens > closes:
                text += f"</{tag}>" * (opens - closes)
            elif closes > opens:
                text = f"<{tag}>" * (closes - opens) + text
        return text

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf.clear()
        kind, self.kind = self.kind, "p"
        if not text:
            return
        text = self._balance(text)
        if self.li_depth and self.lists:
            self.lists[-1][1].append(text)
        elif kind in ("h1", "h2", "h3"):
            self.blocks.append(Block(kind, text))
        elif self.quote:
            self.blocks.append(Block("quote", text))
        else:
            self.blocks.append(Block("p", text))

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ("b", "strong"):
            self.buf.append("<b>")
        elif tag in ("i", "em", "cite"):
            self.buf.append("<i>")
        elif tag == "br":
            self.buf.append(" ")
        elif tag == "hr":
            self.flush()
            self.blocks.append(Block("hr"))
        elif tag in self.HEADINGS:
            self.flush()
            self.kind = self.HEADINGS[tag]
        elif tag in ("ul", "ol"):
            self.flush()
            self.lists.append(("li-ul" if tag == "ul" else "li-ol", []))
        elif tag == "li":
            self.flush()
            self.li_depth += 1
        elif tag == "blockquote":
            self.flush()
            self.quote += 1
        elif tag in self.FLUSHERS:
            self.flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ("b", "strong"):
            self.buf.append("</b>")
        elif tag in ("i", "em", "cite"):
            self.buf.append("</i>")
        elif tag in self.HEADINGS or tag in self.FLUSHERS:
            self.flush()
        elif tag == "li":
            self.flush()
            self.li_depth = max(0, self.li_depth - 1)
        elif tag in ("ul", "ol"):
            self.flush()
            if self.lists:
                kind, items = self.lists.pop()
                if items:
                    self.blocks.append(Block(kind, items=items))
        elif tag == "blockquote":
            self.flush()
            self.quote = max(0, self.quote - 1)

    def handle_data(self, data):
        if not self.skip and data:
            self.buf.append(html_mod.escape(data, quote=False))


_FRONT_MATTER_RE = re.compile(
    r"copyright|©|all rights reserved|isbn|published by|\bpublishers?\b|publication data|"
    r"\btable of contents\b|\bcontents\b|acknowledg|\btitle page\b|"
    r"\bpraise for\b|\balso by\b|\bbooks by\b|\bcover\b|\bcolophon\b|\bimprint\b",
    re.I)


def _trim_front_matter(doc_blocks):
    """Drop leading spine documents that are publisher furniture.
    A document counts as body once it carries substantial prose; before that,
    empty pages and pages matching front-matter phrases (copyright, contents,
    praise quotes) are dropped. Short pages without those phrases, like
    dedications and epigraphs, are kept."""
    def text_of(blocks):
        parts = []
        for b in blocks:
            parts.append(strip_inline(b.text))
            parts.extend(strip_inline(i) for i in b.items)
        return " ".join(p for p in parts if p).strip()

    kept, body_found = [], False
    for blocks in doc_blocks:
        if body_found:
            kept.append(blocks)
            continue
        text = text_of(blocks)
        if len(text) >= 2500:
            body_found = True
            kept.append(blocks)
        elif text and not _FRONT_MATTER_RE.search(text):
            kept.append(blocks)
    return kept or doc_blocks


_TOC_MARKER_RE = re.compile(r"^(table of\s+)?contents\W{0,3}$", re.I)
_STORY_START_RE = re.compile(
    r"^(prologue\b|prolog\b|chapter\s+(one|1)\b|part\s+(one|1|i)\b)", re.I)


def _cut_at_story_start(blocks):
    """When a leftover in-book contents listing survives (it can share one
    spine document with title and publisher pages, which makes the document
    look substantial), cut everything up to the story's first real heading:
    a short Prologue / Chapter One line with actual prose right behind it.
    The same line inside the contents listing fails the prose check, because
    it is followed by more short listing lines."""
    window = max(20, len(blocks) // 3)
    toc_at = next((i for i, b in enumerate(blocks[:window])
                   if _TOC_MARKER_RE.match(strip_inline(b.text).strip())), None)
    if toc_at is None:
        return blocks
    # a long book's contents listing alone can run hundreds of blocks,
    # so scan well past the marker (but not into the deep body)
    scan_end = min(len(blocks), toc_at + 400)
    for i in range(toc_at + 1, scan_end):
        text = strip_inline(blocks[i].text).strip()
        if not text or len(text) > 80 or not _STORY_START_RE.match(text):
            continue
        if any(len(strip_inline(n.text)) >= 300 for n in blocks[i + 1:i + 4]):
            return blocks[i:]
    return blocks


def _nav_bodymatter_href(nav_text):
    """Find the EPUB3 landmarks link that marks the start of the body text."""
    m = re.search(r"<a\b[^>]*epub:type\s*=\s*[\"'][^\"']*\bbodymatter\b[^\"']*[\"'][^>]*>",
                  nav_text, re.I)
    if not m:
        return None
    m = re.search(r"href\s*=\s*[\"']([^\"']+)[\"']", m.group(0), re.I)
    return m.group(1) if m else None


def parse_epub(path: Path, keep_front_matter: bool = False) -> list:
    """Read an EPUB: chapters in spine order from the OPF, XHTML to Blocks.
    Unless keep_front_matter is set, starts at the book's own start-reading
    marker (guide/landmarks) and drops leading publisher pages."""
    import posixpath
    import zipfile
    from urllib.parse import unquote
    from xml.etree import ElementTree as ET

    CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"
    OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}

    def resolve(base, href):
        return posixpath.normpath(posixpath.join(base, unquote(href.split("#")[0])))

    try:
        zf = zipfile.ZipFile(str(path))
    except zipfile.BadZipFile:
        raise ValueError("This does not look like a valid EPUB (not a zip archive).")

    with zf:
        docs, start = [], None
        try:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            opf_name = container.find(f".//{CONTAINER_NS}rootfile").get("full-path")
            opf = ET.fromstring(zf.read(opf_name))
            base = posixpath.dirname(opf_name)
            manifest = {
                item.get("id"): item
                for item in opf.findall(".//opf:manifest/opf:item", OPF_NS)
            }
            nav_name = next(
                (resolve(base, item.get("href") or "") for item in manifest.values()
                 if "nav" in (item.get("properties") or "").split()), None)
            for itemref in opf.findall(".//opf:spine/opf:itemref", OPF_NS):
                item = manifest.get(itemref.get("idref"))
                if item is None:
                    continue
                if "nav" in (item.get("properties") or "").split():
                    continue  # the EPUB3 table-of-contents page, not book text
                if item.get("media-type") not in ("application/xhtml+xml", "text/html"):
                    continue
                docs.append(resolve(base, item.get("href") or ""))
            if not keep_front_matter:
                # EPUB2 guide: the book's own "start reading here" marker
                for ref in opf.findall(".//opf:guide/opf:reference", OPF_NS):
                    if ref.get("type") in ("text", "bodymatter") and ref.get("href"):
                        start = resolve(base, ref.get("href"))
                        break
                if start is None and nav_name:
                    try:
                        href = _nav_bodymatter_href(
                            zf.read(nav_name).decode("utf-8", errors="replace"))
                        if href:
                            start = resolve(posixpath.dirname(nav_name), href)
                    except KeyError:
                        pass
        except (KeyError, AttributeError, ET.ParseError):
            # no readable OPF: fall back to every HTML file, archive order
            docs = [n for n in zf.namelist()
                    if n.lower().endswith((".xhtml", ".html", ".htm"))
                    and "nav" not in posixpath.basename(n).lower()]

        if start in docs:
            docs = docs[docs.index(start):]

        doc_blocks = []
        for name in docs:
            try:
                raw = zf.read(name).decode("utf-8", errors="replace")
            except KeyError:
                continue
            parser = _EpubHTMLParser()
            parser.feed(raw)
            parser.close()
            parser.flush()
            if parser.blocks:
                doc_blocks.append(parser.blocks)

    if not keep_front_matter:
        doc_blocks = _trim_front_matter(doc_blocks)
    blocks = [b for chunk in doc_blocks for b in chunk]
    if not keep_front_matter:
        blocks = _cut_at_story_start(blocks)
    if not blocks:
        raise ValueError("No readable text found in this EPUB.")
    return blocks


def parse_pdf(path: Path) -> list:
    """Extract a manuscript from a PDF with structure inference.
    Uses font sizes to rebuild headings; falls back to plain extraction."""
    try:
        import pdfplumber
    except ImportError:
        return _parse_pdf_basic(path)
    from collections import Counter

    lines = []
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages):
            try:
                tls = page.extract_text_lines()
            except Exception:
                tls = []
            for tl in tls:
                text = (tl.get("text") or "").strip()
                if not text:
                    continue
                chars = tl.get("chars") or []
                size = (sum(c.get("size", 10) for c in chars) / len(chars)) if chars else 10.0
                lines.append({"text": text, "size": size, "top": tl["top"],
                              "bottom": tl["bottom"], "page": pno})
    if not lines:
        raise ValueError(
            "No text layer found; this PDF looks scanned. "
            "Run OCR first (for example with ocrmypdf) and try again.")

    # drop bare page numbers and headers/footers repeated across pages
    freq = Counter(l["text"] for l in lines)
    npages = max(l["page"] for l in lines) + 1
    def keep(l):
        if re.fullmatch(r"\d{1,4}", l["text"]):
            return False
        if npages >= 3 and len(l["text"]) < 60 and freq[l["text"]] >= max(3, npages // 2):
            return False
        return True
    lines = [l for l in lines if keep(l)]
    if not lines:
        raise ValueError("Nothing but page furniture found in this PDF.")

    sizes = sorted(l["size"] for l in lines)
    body = sizes[len(sizes) // 2]

    # learn the document's normal line-to-line gap so paragraph breaks are
    # detected relative to it (accessible PDFs have generous leading)
    gaps = []
    for a, b in zip(lines, lines[1:]):
        if a["page"] == b["page"]:
            g = b["top"] - a["bottom"]
            if 0 < g < 60:
                gaps.append(g)
    normal_gap = sorted(gaps)[len(gaps) // 4] if gaps else 4.0  # 25th percentile: true line spacing, not paragraph gaps
    break_gap = normal_gap * 1.6 + 1.0

    blocks, para = [], []
    prev = None

    def flush():
        if para:
            blocks.append(Block("p", html_mod.escape(" ".join(para), quote=False)))
            para.clear()

    for l in lines:
        is_head = l["size"] >= body * 1.15 and len(l["text"]) <= 90
        new_page = prev is not None and l["page"] != prev["page"]
        gap = (l["top"] - prev["bottom"]) if (prev and not new_page) else 0
        if is_head:
            flush()
            level = "h1" if l["size"] >= body * 1.35 else "h2"
            blocks.append(Block(level, html_mod.escape(l["text"], quote=False)))
        else:
            if para and prev and not new_page and gap > break_gap:
                flush()
            if para and para[-1].endswith("-"):
                para[-1] = para[-1][:-1] + l["text"]  # de-hyphenate across lines
            else:
                para.append(l["text"])
        prev = l
    flush()
    return blocks


def _parse_pdf_basic(path: Path) -> list:
    """Fallback: plain text extraction via pypdf, no structure inference."""
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    raw = "\n\n".join((p.extract_text() or "") for p in reader.pages).strip()
    if not raw:
        raise ValueError(
            "No text layer found; this PDF looks scanned. "
            "Run OCR first (for example with ocrmypdf) and try again.")
    return parse_plaintext(raw)


_NON_TITLE_HEADING_RE = re.compile(r"^(a\s+)?(novella|novel|short story|found document)\b", re.I)


def strip_book_front_matter(blocks):
    """Drop a single manuscript's own title page — leading title, subtitle,
    epigraph, dedication, rules — keeping everything from the first real
    section heading or first substantial paragraph onward."""
    def is_subtitle(b):
        t = b.text.strip()
        return t.startswith("<i>") and t.endswith("</i>")

    def next_solid(i):
        return next((n for n in blocks[i + 1:] if n.kind != "hr"), None)

    for i, b in enumerate(blocks):
        text = strip_inline(b.text).strip()
        if b.kind == "h1":
            if i > 0:
                return blocks[i:]  # a later h1 is a chapter, not the title
            nxt = next_solid(i)
            if nxt is not None and nxt.kind == "p" and not is_subtitle(nxt) \
                    and len(strip_inline(nxt.text)) >= 120:
                return blocks[i:]  # h1 straight into prose: chapter heading
            continue  # a real title page: strip it
        if b.kind in ("h2", "h3") and not _NON_TITLE_HEADING_RE.match(text):
            return blocks[i:]
        if b.kind in ("li-ul", "li-ol"):
            return blocks[i:]
        if b.kind == "p" and not is_subtitle(b):
            if len(text) >= 200:
                return blocks[i:]
            # a short line right before real prose is an opening, not a dedication
            nxt = next_solid(i)
            if nxt is not None and nxt.kind == "p" and len(strip_inline(nxt.text)) >= 200:
                return blocks[i:]
    return blocks


def load_manuscripts(paths, keep_front_matter: bool = False) -> list:
    """Load one manuscript, or combine several into one continuous stream:
    each book's own title page is stripped and a 'book' marker block sits at
    every seam — an unspoken chapter mark in the audiobook, a top-level
    heading in the visual outputs."""
    paths = [Path(p) for p in paths]
    if len(paths) == 1:
        return load_manuscript(paths[0], keep_front_matter)
    combined = []
    for p in paths:
        blocks = load_manuscript(p, keep_front_matter)
        stripped = strip_book_front_matter(blocks)
        h1 = next((b for b in blocks if b.kind == "h1"), None)
        if h1 is not None and (not stripped or stripped[0] is not h1):
            title = strip_inline(h1.text)  # the stripped title page names the book
        else:
            title = p.stem.replace("-", " ").replace("_", " ").title()
        combined.append(Block("book", title))
        combined.extend(stripped)
    return combined


def _books_as_h1(blocks):
    """For the visual outputs, book seam markers render as top headings."""
    return [Block("h1", b.text) if b.kind == "book" else b for b in blocks]


def load_manuscript(path: Path, keep_front_matter: bool = False) -> list:
    ext = path.suffix.lower()
    if ext == ".docx":
        return parse_docx(path)
    if ext == ".pdf":
        return parse_pdf(path)
    if ext == ".epub":
        return parse_epub(path, keep_front_matter)
    raw = path.read_text(encoding="utf-8", errors="replace")
    if ext in (".md", ".markdown"):
        return parse_markdown(raw)
    return parse_plaintext(raw)


# ---------------------------------------------------------------------------
# Output 1: OpenDyslexic PDF
# ---------------------------------------------------------------------------

def build_pdf(blocks, out_path: Path, title: str, author: str, theme_name: str):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, HRFlowable,
        ListFlowable, ListItem,
    )
    from reportlab.lib.styles import ParagraphStyle

    blocks = _books_as_h1(blocks)
    t = THEMES[theme_name]
    pdfmetrics.registerFont(TTFont("OD", str(FONT_DIR / FONTS["regular"])))
    pdfmetrics.registerFont(TTFont("OD-Bold", str(FONT_DIR / FONTS["bold"])))
    pdfmetrics.registerFont(TTFont("OD-Italic", str(FONT_DIR / FONTS["italic"])))
    pdfmetrics.registerFont(TTFont("OD-BoldItalic", str(FONT_DIR / FONTS["bolditalic"])))
    pdfmetrics.registerFontFamily(
        "OD", normal="OD", bold="OD-Bold", italic="OD-Italic", boldItalic="OD-BoldItalic"
    )

    page_w, page_h = letter
    margin = 1.1 * inch  # wide margins keep line length near 60 characters

    ink, heading, accent = HexColor(t["ink"]), HexColor(t["heading"]), HexColor(t["accent"])

    body = ParagraphStyle(
        "body", fontName="OD", fontSize=12.5, leading=23, textColor=ink,
        alignment=TA_LEFT, spaceAfter=14,
    )
    styles = {
        "p": body,
        "h1": ParagraphStyle("h1", parent=body, fontName="OD-Bold", fontSize=20,
                             leading=30, textColor=heading, spaceBefore=26, spaceAfter=16),
        "h2": ParagraphStyle("h2", parent=body, fontName="OD-Bold", fontSize=16,
                             leading=26, textColor=heading, spaceBefore=20, spaceAfter=12),
        "h3": ParagraphStyle("h3", parent=body, fontName="OD-Bold", fontSize=13.5,
                             leading=24, textColor=accent, spaceBefore=16, spaceAfter=10),
        "quote": ParagraphStyle("quote", parent=body, fontName="OD-Italic",
                                leftIndent=24, textColor=HexColor(t["muted"]),
                                borderColor=HexColor(t["quote_bar"]), borderWidth=0,
                                spaceBefore=6, spaceAfter=14),
        "li": ParagraphStyle("li", parent=body, spaceAfter=8),
        "title": ParagraphStyle("title", parent=body, fontName="OD-Bold", fontSize=26,
                                leading=38, textColor=heading, spaceAfter=10),
        "author": ParagraphStyle("author", parent=body, fontSize=14, leading=24,
                                 textColor=HexColor(t["muted"]), spaceAfter=30),
    }

    def paint_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor(t["bg"]))
        canvas.rect(0, 0, page_w, page_h, stroke=0, fill=1)
        canvas.setFont("OD", 9)
        canvas.setFillColor(HexColor(t["muted"]))
        canvas.drawCentredString(page_w / 2, 0.55 * inch, str(canvas.getPageNumber()))
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(out_path), pagesize=letter, title=title, author=author,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
    )
    frame = Frame(margin, margin, page_w - 2 * margin, page_h - 2 * margin, id="main")
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=paint_page)])

    story = [Paragraph(title, styles["title"])]
    if author:
        story.append(Paragraph(author, styles["author"]))
    story.append(Spacer(1, 6))

    for b in blocks:
        if b.kind == "hr":
            story.append(HRFlowable(width="40%", thickness=1, color=accent,
                                    spaceBefore=14, spaceAfter=14))
        elif b.kind in ("li-ul", "li-ol"):
            bt = "bullet" if b.kind == "li-ul" else "1"
            items = [ListItem(Paragraph(i, styles["li"]), leftIndent=28) for i in b.items]
            story.append(ListFlowable(items, bulletType=bt, bulletColor=accent,
                                      bulletFontName="OD", start="1"))
            story.append(Spacer(1, 8))
        elif b.kind == "table":
            for row in b.items:
                line = "  |  ".join(html_mod.escape(c, quote=False) for c in row)
                story.append(Paragraph(line, body))
            story.append(Spacer(1, 8))
        elif b.kind in styles:
            story.append(Paragraph(b.text, styles[b.kind]))
        else:
            story.append(Paragraph(b.text, body))

    doc.build(story)


# ---------------------------------------------------------------------------
# Output 2: high-contrast EPUB
# ---------------------------------------------------------------------------

EPUB_CSS = """
@font-face {{
  font-family: "OpenDyslexic";
  src: url(fonts/OpenDyslexic-Regular.ttf);
  font-weight: normal; font-style: normal;
}}
@font-face {{
  font-family: "OpenDyslexic";
  src: url(fonts/OpenDyslexic-Bold.ttf);
  font-weight: bold; font-style: normal;
}}
@font-face {{
  font-family: "OpenDyslexic";
  src: url(fonts/OpenDyslexic-Italic.ttf);
  font-weight: normal; font-style: italic;
}}
body {{
  font-family: "OpenDyslexic", sans-serif;
  background: {bg}; color: {ink};
  line-height: 1.8; text-align: left;
  margin: 4% 6%;
}}
h1, h2 {{ color: {heading}; line-height: 1.4; }}
h3 {{ color: {accent}; }}
p {{ margin: 0 0 1em 0; }}
blockquote {{
  border-left: 4px solid {quote_bar};
  margin-left: 0; padding-left: 1em;
  color: {muted}; font-style: italic;
}}
li {{ margin-bottom: 0.5em; }}
hr {{ border: none; border-top: 1px solid {accent}; width: 40%; margin: 2em auto; }}
"""


def blocks_to_html(chunk) -> str:
    out = []
    for b in chunk:
        if b.kind == "hr":
            out.append("<hr/>")
        elif b.kind == "li-ul":
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in b.items) + "</ul>")
        elif b.kind == "li-ol":
            out.append("<ol>" + "".join(f"<li>{i}</li>" for i in b.items) + "</ol>")
        elif b.kind == "quote":
            out.append(f"<blockquote><p>{b.text}</p></blockquote>")
        elif b.kind in ("h1", "h2", "h3"):
            out.append(f"<{b.kind}>{b.text}</{b.kind}>")
        elif b.kind == "table":
            rows = []
            for row in b.items:
                cells = "".join(f"<td>{html_mod.escape(c, quote=False)}</td>" for c in row)
                rows.append(f"<tr>{cells}</tr>")
            out.append("<table>" + "".join(rows) + "</table>")
        else:
            out.append(f"<p>{b.text}</p>")
    return "\n".join(out)


def split_chapters(blocks):
    """Split the document at h1 boundaries. Returns [(title, blocks), ...]."""
    chapters, current, title = [], [], None
    for b in blocks:
        if b.kind == "h1":
            if current or title is not None:
                chapters.append((title or "Untitled", current))
            title, current = strip_inline(b.text), [b]
        else:
            current.append(b)
    if current:
        chapters.append((title or "Untitled", current))
    if not chapters:
        chapters = [("Full text", blocks)]
    return chapters


def build_epub(blocks, out_path: Path, title: str, author: str, theme_name: str):
    from ebooklib import epub

    blocks = _books_as_h1(blocks)
    t = THEMES[theme_name]
    book = epub.EpubBook()
    book.set_identifier(re.sub(r"\W+", "-", title.lower()) or "featherpress-book")
    book.set_title(title)
    book.set_language("en")
    if author:
        book.add_author(author)

    for key in ("regular", "bold", "italic"):
        fname = FONTS[key]
        book.add_item(epub.EpubItem(
            uid=f"font-{key}", file_name=f"fonts/{fname}",
            media_type="font/ttf", content=(FONT_DIR / fname).read_bytes(),
        ))

    css = epub.EpubItem(
        uid="style", file_name="style/main.css", media_type="text/css",
        content=EPUB_CSS.format(**t).encode(),
    )
    book.add_item(css)

    chapters = []
    for idx, (ch_title, chunk) in enumerate(split_chapters(blocks), 1):
        ch = epub.EpubHtml(title=ch_title, file_name=f"chapter_{idx:02d}.xhtml", lang="en")
        ch.content = f"<html><body>{blocks_to_html(chunk)}</body></html>"
        ch.add_item(css)
        book.add_item(ch)
        chapters.append(ch)

    book.toc = chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters
    epub.write_epub(str(out_path), book)


# ---------------------------------------------------------------------------
# Output 3: audiobook-ready text
# ---------------------------------------------------------------------------

TTS_ABBREV = [
    # (pattern, replacement, flags)
    (r"\bDr\.", "Doctor", 0), (r"\bMr\.", "Mister", 0), (r"\bMrs\.", "Missus", 0),
    (r"\bMs\.", "Miz", 0), (r"\bSt\.", "Saint", 0), (r"\bvs\.?\b", "versus", re.I),
    (r"\be\.g\.", "for example", re.I), (r"\bi\.e\.", "that is", re.I),
    (r"\betc\.", "et cetera", re.I), (r"\bapprox\.", "approximately", re.I),
    (r"\bno\.\s*(\d)", r"number \1", re.I), (r"\bft\.?\b", "feet", 0),
]

TTS_SYMBOLS = [
    ("&", " and "), ("%", " percent"), ("+", " plus "), ("=", " equals "),
    ("~", " about "), ("#", " number "), ("@", " at "),
    ("\u2014", ", "), ("\u2013", " to "), ("\u2026", "..."),
    ("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"),
]


def tts_clean(text: str) -> str:
    text = strip_inline(text)
    text = html_mod.unescape(text)
    for pat, rep, flags in TTS_ABBREV:
        text = re.sub(pat, rep, text, flags=flags)
    for sym, rep in TTS_SYMBOLS:
        text = text.replace(sym, rep)
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[-1] not in ".!?:\"'":
        text += "."
    return text


PAUSE_RE = re.compile(r"^<<pause:([\d.]+)>>$")


def tts_script(blocks, title: str, author: str, pauses: bool = False):
    """Chapterized narration script: [(chapter_title, lines), ...].
    Shared by the TTS text file and the voiced audiobook. With pauses=True,
    `<<pause:seconds>>` sentinel lines mark where the audiobook should hold
    a beat: scene breaks, heading turns, quotes."""
    opening = [tts_clean(title)]
    if author:
        opening.append(f"Written by {tts_clean(author)}")
    chapters = [[tts_clean(title).rstrip("."), opening]]
    chapter_n = 0

    def pause(sec):
        if pauses:
            chapters[-1][1].append(f"<<pause:{sec}>>")

    for b in blocks:
        if b.kind == "book":
            # a seam between combined books: an audiobook chapter mark that
            # carries the book's title but speaks nothing, so the text flows
            chapters.append([tts_clean(b.text).rstrip(".!?"), []])
            continue
        if b.kind == "h1":
            chapter_n += 1
            heading = f"Chapter {chapter_n}. {tts_clean(b.text)}"
            chapters.append([heading.rstrip(".!?"), [heading, ""]])
            pause(1.0)
            continue
        lines = chapters[-1][1]
        if b.kind in ("h2", "h3"):
            pause(0.8)
            lines += ["", tts_clean(b.text), ""]
            pause(1.0)
        elif b.kind == "quote":
            lines += [f"Quote. {tts_clean(b.text)} End quote.", ""]
            pause(0.5)
        elif b.kind in ("li-ul", "li-ol"):
            for n, item in enumerate(b.items, 1):
                prefix = f"{n}. " if b.kind == "li-ol" else ""
                lines.append(f"{prefix}{tts_clean(item)}")
            lines.append("")
        elif b.kind == "hr":
            # a scene break in the manuscript is a beat for the listener
            lines.append("")
            pause(1.5)
        elif b.kind == "table":
            lines.append("Table.")
            for row in b.items:
                lines.append(tts_clean(", ".join(row)))
            lines.append("")
        else:
            lines += [tts_clean(b.text), ""]
    return [(t, lines) for t, lines in chapters
            if any(l.strip() and not PAUSE_RE.match(l.strip()) for l in lines)]


def _segments(lines):
    """Fold narration lines into [text, pause_after_seconds] segments."""
    segs, cur = [], []

    def flush():
        text = "\n".join(x for x in cur if x.strip())
        cur.clear()
        return text

    for l in lines:
        m = PAUSE_RE.match(l.strip())
        if m:
            text = flush()
            if text:
                segs.append([text, float(m.group(1))])
            elif segs:
                # merge adjacent pauses, capped so stacks don't gape
                segs[-1][1] = min(segs[-1][1] + float(m.group(1)), 2.5)
        else:
            cur.append(l)
    text = flush()
    if text:
        segs.append([text, 0.0])
    return segs


def build_tts(blocks, out_path: Path, title: str, author: str):
    parts = ["\n".join(lines).strip() for _, lines in tts_script(blocks, title, author)]
    out_path.write_text("\n\n\n".join(parts) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Output 4: voiced audiobook (Edge TTS online, Piper TTS offline)
# ---------------------------------------------------------------------------

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"   # Edge neural voice
DEFAULT_PIPER_VOICE = "en_US-lessac-medium"        # offline fallback
VOICE_DIR = SCRIPT_DIR / "voices"


def is_piper_voice(name: str) -> bool:
    """Piper voices look like en_US-lessac-medium; Edge like en-US-AriaNeural."""
    return bool(re.match(r"^[a-z]+_[A-Z]{2}-", name))


def _find_ffmpeg():
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # winget installs land here but only reach PATH in new shells
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if root.is_dir():
        hits = sorted(root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
        if hits:
            return str(hits[0])
    return None


def _load_voice(voice_name: str):
    try:
        from piper import PiperVoice
    except ImportError:
        raise ValueError(
            "The audiobook format needs Piper. Install it with: "
            "python -m pip install piper-tts")
    VOICE_DIR.mkdir(exist_ok=True)
    onnx = VOICE_DIR / f"{voice_name}.onnx"
    if not onnx.exists():
        from piper.download_voices import download_voice
        print(f"    downloading voice {voice_name} (one time, ~60 MB) ...")
        download_voice(voice_name, VOICE_DIR)
    return PiperVoice.load(onnx)


def _synth_piper(voice, text: str, out_path: Path, rate: int = 0):
    """Piper synthesis to wav. rate is percent, negative = slower."""
    import wave
    syn_config = None
    if rate:
        try:
            from piper import SynthesisConfig
            syn_config = SynthesisConfig(length_scale=1.0 / (1.0 + rate / 100.0))
        except (ImportError, TypeError):
            pass
    with wave.open(str(out_path), "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=syn_config)


def _synth_edge(text: str, voice_name: str, out_path: Path, rate: int = 0):
    """Edge TTS synthesis to mp3. Needs internet; rate as for Piper."""
    try:
        import edge_tts
    except ImportError:
        raise ValueError(
            "Edge voices need the edge-tts package. Install it with: "
            "python -m pip install edge-tts")
    import asyncio

    async def run():
        com = edge_tts.Communicate(text, voice=voice_name, rate=f"{rate:+d}%")
        await com.save(str(out_path))
    asyncio.run(run())


def list_edge_voices(refresh: bool = False):
    """The Edge voice catalog: [{name, locale, gender}, ...], cached on disk."""
    import json
    cache = VOICE_DIR / "edge_voices.json"
    if cache.exists() and not refresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    import asyncio
    import edge_tts
    voices = asyncio.run(edge_tts.list_voices())
    data = sorted(
        ({"name": v["ShortName"], "locale": v["Locale"], "gender": v["Gender"]}
         for v in voices), key=lambda v: v["name"])
    VOICE_DIR.mkdir(exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


SAMPLE_TEXT = ("This is the voice of Featherpress. "
               "A quiet story, read gently, one page at a time.")


def voice_sample(voice_name: str, rate: int = 0) -> Path:
    """Synthesize (once) and return a short preview clip for a voice.
    Returns a wav when possible (Piper always; Edge when ffmpeg can convert),
    otherwise an mp3."""
    samples = VOICE_DIR / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    stem = f"{voice_name}_{rate:+d}"
    if is_piper_voice(voice_name):
        out = samples / f"{stem}.wav"
        if not out.exists():
            _synth_piper(_load_voice(voice_name), SAMPLE_TEXT, out, rate)
        return out
    wav, mp3 = samples / f"{stem}.wav", samples / f"{stem}.mp3"
    if wav.exists():
        return wav
    if not mp3.exists():
        _synth_edge(SAMPLE_TEXT, voice_name, mp3, rate)
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        import subprocess
        subprocess.run([ffmpeg, "-y", "-i", str(mp3), str(wav)],
                       check=True, capture_output=True)
        return wav
    return mp3


def _ffmeta_escape(text: str) -> str:
    return re.sub(r"([=;#\\\n])", r"\\\1", text)


def _chunk_text(text: str, target: int = 4000):
    """Split narration text into chunks near the target size, on paragraph
    boundaries, so each Edge request stays short-lived and retryable."""
    paras = [p for p in text.split("\n") if p.strip()]
    chunks, cur, size = [], [], 0
    for p in paras:
        if cur and size + len(p) > target:
            chunks.append("\n".join(cur)); cur, size = [], 0
        cur.append(p); size += len(p) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks or [text]


def _synth_edge_many(jobs, rate: int, progress_cb, concurrency: int = 4):
    """Synthesize many (text, voice, out_path) jobs concurrently with retries.
    Each job is one bounded websocket session, so a dropped connection costs
    one chunk, not the whole book."""
    try:
        import edge_tts
    except ImportError:
        raise ValueError(
            "Edge voices need the edge-tts package. Install it with: "
            "python -m pip install edge-tts")
    import asyncio

    done = [0]

    async def one(sem, text, voice, out):
        async with sem:
            for attempt in range(1, 4):
                try:
                    com = edge_tts.Communicate(text, voice=voice, rate=f"{rate:+d}%")
                    await asyncio.wait_for(com.save(str(out)),
                                           timeout=max(120, len(text) // 15))
                    done[0] += 1
                    progress_cb(f"    voiced part {done[0]}/{len(jobs)}")
                    return
                except Exception as e:
                    if attempt == 3:
                        raise
                    progress_cb(f"    part failed ({type(e).__name__}), "
                                f"retry {attempt}/2 ...")
                    await asyncio.sleep(5 * attempt)

    async def run():
        sem = asyncio.Semaphore(concurrency)
        await asyncio.gather(*(one(sem, t, v, o) for t, v, o in jobs))
    asyncio.run(run())


def _media_duration(path: Path, ffmpeg: str) -> float:
    """Duration in seconds via the ffprobe that ships beside ffmpeg."""
    import json
    import subprocess
    ffprobe = str(Path(ffmpeg).with_name(Path(ffmpeg).name.replace("ffmpeg", "ffprobe")))
    p = subprocess.run(
        [ffprobe, "-v", "quiet", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True)
    return float(json.loads(p.stdout)["format"]["duration"])


def build_audio(blocks, out_path: Path, title: str, author: str,
                voice_name: str = DEFAULT_VOICE, rate: int = 0,
                progress_cb=print) -> Path:
    """Voice the manuscript into a real audiobook.

    Edge voices (like en-US-AndrewMultilingualNeural) use Microsoft's neural
    TTS over the network; Piper voices (like en_US-lessac-medium) run fully
    offline. rate is a percent speed adjustment, negative = slower.
    Writes an .m4b with chapter markers when ffmpeg is available; without
    ffmpeg, Piper falls back to one .wav and Edge to per-chapter .mp3 files."""
    import hashlib
    import json
    import shutil

    piper = is_piper_voice(voice_name)
    voice = _load_voice(voice_name) if piper else None
    ffmpeg = _find_ffmpeg()

    if piper:
        chapters = tts_script(blocks, title, author)
        return _build_audio_piper(chapters, out_path, title, author, voice,
                                  rate, ffmpeg, progress_cb)

    # Edge path: chunked, concurrent, resumable. Chunks live in a persistent
    # work folder so an interrupted run picks up where it stopped. Pause
    # sentinels become real silence between chunks (needs ffmpeg).
    chapters = tts_script(blocks, title, author, pauses=bool(ffmpeg))
    ch_segs = [(ch_title, _segments(lines)) for ch_title, lines in chapters]
    fingerprint = "\n".join(f"{text}|{p}" for _, segs in ch_segs for text, p in segs)
    manifest = {"voice": voice_name, "rate": rate, "version": 2,
                "hash": hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]}
    work = out_path.parent / f".{out_path.name}_work"
    mpath = work / "manifest.json"
    stale = True
    if mpath.exists():
        try:
            stale = json.loads(mpath.read_text(encoding="utf-8")) != manifest
        except json.JSONDecodeError:
            pass
    if stale:
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest), encoding="utf-8")

    def silence(seconds):
        p = work / f"silence_{int(seconds * 1000)}.mp3"
        if not p.exists():
            import subprocess
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                 "-t", f"{seconds}", "-c:a", "libmp3lame", "-b:a", "48k", str(p)],
                check=True, capture_output=True)
        return p

    files = []          # (chapter_index, path) in final play order
    jobs = []
    voiced_total = 0
    for i, (_, segs) in enumerate(ch_segs):
        if ffmpeg and i > 0:
            files.append((i, silence(2.0)))  # a breath at every book/chapter turn
        for s, (text, pause_after) in enumerate(segs):
            for j, chunk in enumerate(_chunk_text(text)):
                part = work / f"ch{i:03d}_s{s:03d}_{j:03d}.mp3"
                files.append((i, part))
                voiced_total += 1
                if not (part.exists() and part.stat().st_size > 0):
                    jobs.append((chunk, voice_name, part))
            if ffmpeg and pause_after:
                files.append((i, silence(pause_after)))
    if len(jobs) < voiced_total:
        progress_cb(f"    resuming: {voiced_total - len(jobs)}/{voiced_total} "
                    "parts already voiced")
    progress_cb(f"    voicing {len(jobs)} parts across {len(ch_segs)} chapters ...")
    _synth_edge_many(jobs, rate, progress_cb)

    if ffmpeg:
        durs = [_media_duration(p, ffmpeg) for _, p in files]
        concat = work / "concat.txt"
        concat.write_text(
            "".join(f"file '{p.as_posix()}'\n" for _, p in files), encoding="utf-8")
        meta = [";FFMETADATA1", f"title={_ffmeta_escape(title)}",
                f"artist={_ffmeta_escape(author or '')}"]
        t = 0.0
        for i, (ch_title, _) in enumerate(ch_segs):
            dur = sum(d for (ci, _), d in zip(files, durs) if ci == i)
            meta += ["[CHAPTER]", "TIMEBASE=1/1000",
                     f"START={int(t * 1000)}", f"END={int((t + dur) * 1000)}",
                     f"title={_ffmeta_escape(ch_title)}"]
            t += dur
        (work / "meta.txt").write_text("\n".join(meta) + "\n", encoding="utf-8")
        out = out_path.with_suffix(".m4b")
        progress_cb(f"    assembling {out.name} ({t / 3600:.1f} hours) ...")
        import subprocess
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
             "-i", str(work / "meta.txt"), "-map_metadata", "1",
             "-c:a", "aac", "-b:a", "64k", str(out)],
            check=True, capture_output=True)
        shutil.rmtree(work, ignore_errors=True)
        return out

    # no ffmpeg: merge each chapter's chunk mp3 bytes into one numbered mp3
    progress_cb("    ffmpeg not found: writing per-chapter mp3 files")
    out = out_path
    out.mkdir(parents=True, exist_ok=True)
    for i, (ch_title, _) in enumerate(ch_segs):
        safe = re.sub(r"[^\w\- ]+", "", ch_title)[:60].strip() or f"part {i}"
        with open(out / f"{i:03d} - {safe}.mp3", "wb") as dst:
            for ci, p in files:
                if ci == i:
                    dst.write(p.read_bytes())
    shutil.rmtree(work, ignore_errors=True)
    return out


def _build_audio_piper(chapters, out_path: Path, title: str, author: str,
                       voice, rate: int, ffmpeg, progress_cb) -> Path:
    """Offline Piper synthesis, one wav per chapter (CPU-bound, sequential)."""
    import subprocess
    import tempfile
    import wave

    with tempfile.TemporaryDirectory(prefix="featherpress_audio_") as td:
        tdir = Path(td)
        parts = []
        for i, (ch_title, lines) in enumerate(chapters):
            text = "\n".join(l for l in lines if l.strip())
            part = tdir / f"ch_{i:03d}.wav"
            _synth_piper(voice, text, part, rate)
            with wave.open(str(part), "rb") as wf:
                dur = wf.getnframes() / wf.getframerate()
            parts.append((ch_title, part, dur))
            progress_cb(f"    voiced {i + 1}/{len(chapters)}: {ch_title[:46]} ({dur:.0f}s)")

        if ffmpeg:
            concat = tdir / "concat.txt"
            concat.write_text(
                "".join(f"file '{p.as_posix()}'\n" for _, p, _ in parts), encoding="utf-8")
            meta = [";FFMETADATA1", f"title={_ffmeta_escape(title)}",
                    f"artist={_ffmeta_escape(author or '')}"]
            t = 0.0
            for ch_title, _, dur in parts:
                meta += ["[CHAPTER]", "TIMEBASE=1/1000",
                         f"START={int(t * 1000)}", f"END={int((t + dur) * 1000)}",
                         f"title={_ffmeta_escape(ch_title)}"]
                t += dur
            (tdir / "meta.txt").write_text("\n".join(meta) + "\n", encoding="utf-8")
            out = out_path.with_suffix(".m4b")
            subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                 "-i", str(tdir / "meta.txt"), "-map_metadata", "1",
                 "-c:a", "aac", "-b:a", "64k", str(out)],
                check=True, capture_output=True)
            return out

        # no ffmpeg: stitch the chapter WAVs together losslessly instead
        progress_cb("    ffmpeg not found: writing plain .wav without chapter marks")
        out = out_path.with_suffix(".wav")
        with wave.open(str(out), "wb") as dst:
            for i, (_, p, _) in enumerate(parts):
                with wave.open(str(p), "rb") as src:
                    if i == 0:
                        dst.setparams(src.getparams())
                    dst.writeframes(src.readframes(src.getnframes()))
        return out


# ---------------------------------------------------------------------------
# Output 5: standalone accessible HTML reader
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
@font-face { font-family:'OpenDyslexic'; font-weight:normal; font-style:normal;
  src:url(data:font/ttf;base64,__FONT_REG__) format('truetype'); }
@font-face { font-family:'OpenDyslexic'; font-weight:bold; font-style:normal;
  src:url(data:font/ttf;base64,__FONT_BOLD__) format('truetype'); }
:root {
  --bg:#0C1015; --ink:#E6E3DC; --heading:#7FDBE8; --accent:#D9B84A;
  --quote:#B9A7E8; --muted:#9A968C; --panel:#141A22;
  --fontsize:1.05rem; --lineheight:1.9; --spacing:0.01em;
}
body.cream {
  --bg:#FAF4E6; --ink:#2B2A26; --heading:#5C4A1E; --accent:#8A6D1F;
  --quote:#C9B26B; --muted:#6B675E; --panel:#F1E8D2;
}
* { box-sizing:border-box; }
body {
  margin:0; background:var(--bg); color:var(--ink);
  font-family:'OpenDyslexic', sans-serif;
  font-size:var(--fontsize); line-height:var(--lineheight);
  letter-spacing:var(--spacing);
  transition:background .3s, color .3s;
}
main { max-width:42rem; margin:0 auto; padding:5.5rem 1.4rem 4rem; }
h1,h2 { color:var(--heading); line-height:1.4; }
h3 { color:var(--accent); }
p { margin:0 0 1.1em; }
blockquote { border-left:4px solid var(--quote); margin:1em 0; padding:0 0 0 1em;
  color:var(--muted); font-style:italic; }
li { margin-bottom:.55em; }
hr { border:none; border-top:1px solid var(--accent); width:40%; margin:2.2em auto; }
#toolbar {
  position:fixed; top:0; left:0; right:0; display:flex; flex-wrap:wrap; gap:.5rem;
  align-items:center; padding:.6rem 1rem; background:var(--panel);
  border-bottom:1px solid var(--accent); z-index:10;
}
#toolbar button, #toolbar label {
  font-family:inherit; font-size:.85rem; color:var(--ink);
  background:transparent; border:1px solid var(--muted); border-radius:8px;
  padding:.35rem .7rem; cursor:pointer;
}
#toolbar button:focus-visible { outline:3px solid var(--heading); outline-offset:2px; }
#toolbar .grow { flex:1; }
@media (prefers-reduced-motion:reduce) { body { transition:none; } }
</style>
</head>
<body>
<nav id="toolbar" aria-label="Reading settings">
  <button id="themeBtn" aria-pressed="false">Theme: Dark</button>
  <button data-size="-1" aria-label="Smaller text">A-</button>
  <button data-size="1" aria-label="Larger text">A+</button>
  <button data-lh="-1" aria-label="Tighter lines">Lines-</button>
  <button data-lh="1" aria-label="Looser lines">Lines+</button>
  <span class="grow"></span>
</nav>
<main>
__CONTENT__
</main>
<script>
(function(){
  var size=1.05, lh=1.9, body=document.body;
  document.getElementById('themeBtn').addEventListener('click', function(){
    body.classList.toggle('cream');
    var cream = body.classList.contains('cream');
    this.textContent = 'Theme: ' + (cream ? 'Cream' : 'Dark');
    this.setAttribute('aria-pressed', cream);
  });
  document.querySelectorAll('[data-size]').forEach(function(btn){
    btn.addEventListener('click', function(){
      size = Math.min(1.6, Math.max(.85, size + .07 * (+btn.dataset.size)));
      body.style.setProperty('--fontsize', size + 'rem');
    });
  });
  document.querySelectorAll('[data-lh]').forEach(function(btn){
    btn.addEventListener('click', function(){
      lh = Math.min(2.6, Math.max(1.4, lh + .15 * (+btn.dataset.lh)));
      body.style.setProperty('--lineheight', lh);
    });
  });
})();
</script>
</body>
</html>
"""


def build_html(blocks, out_path: Path, title: str, author: str):
    blocks = _books_as_h1(blocks)
    font_reg = base64.b64encode((FONT_DIR / FONTS["regular"]).read_bytes()).decode()
    font_bold = base64.b64encode((FONT_DIR / FONTS["bold"]).read_bytes()).decode()
    content = [f"<h1>{html_mod.escape(title, quote=False)}</h1>"]
    if author:
        content.append(f'<p style="color:var(--muted)">{html_mod.escape(author, quote=False)}</p>')
    content.append(blocks_to_html(blocks))
    page = (HTML_TEMPLATE
            .replace("__TITLE__", html_mod.escape(title, quote=False))
            .replace("__FONT_REG__", font_reg)
            .replace("__FONT_BOLD__", font_bold)
            .replace("__CONTENT__", "\n".join(content)))
    out_path.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Featherpress: dyslexic-first publishing pipeline")
    ap.add_argument("input", nargs="+",
                    help="Manuscript file(s) (.md, .txt, .docx, .pdf, or .epub). "
                         "Several files combine, in the order given, into one "
                         "continuous book with each volume's title page stripped.")
    ap.add_argument("-o", "--outdir", default="featherpress_output", help="Output directory")
    ap.add_argument("--title", default=None, help="Book title (default: derived from filename)")
    ap.add_argument("--author", default="", help="Author name")
    ap.add_argument("--theme", choices=list(THEMES), default="cream",
                    help="PDF and EPUB color theme (default: cream)")
    ap.add_argument("--formats", default="pdf,epub,tts,html",
                    help="Comma list of outputs: pdf,epub,tts,html,audio "
                         "(audio is opt-in; voicing a whole book takes a while)")
    ap.add_argument("--voice", default=DEFAULT_VOICE,
                    help="Audiobook voice: an Edge neural voice like en-US-AriaNeural "
                         "(online, natural) or a Piper voice like en_US-lessac-medium "
                         f"(offline). Default: {DEFAULT_VOICE}")
    ap.add_argument("--rate", type=int, default=0, metavar="PCT",
                    help="Speech speed adjustment in percent; negative is slower "
                         "(for example -15). Default: 0")
    ap.add_argument("--version", action="version", version=f"Featherpress {__version__}")
    ap.add_argument("--keep-front-matter", action="store_true",
                    help="Keep EPUB front matter (cover, copyright, contents pages) "
                         "instead of starting at the story")
    args = ap.parse_args()

    srcs = [Path(p) for p in args.input]
    missing = [s for s in srcs if not s.exists()]
    if missing:
        sys.exit("Input not found: " + ", ".join(str(m) for m in missing))

    title = args.title or srcs[0].stem.replace("-", " ").replace("_", " ").title()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"\W+", "-", title.lower()).strip("-") or "book"

    if len(srcs) == 1:
        print(f"Reading {srcs[0].name} ...")
    else:
        print(f"Combining {len(srcs)} manuscripts:")
        for s in srcs:
            print(f"  + {s.name}")
    blocks = load_manuscripts(srcs, args.keep_front_matter)
    print(f"  parsed {len(blocks)} blocks")

    wanted = {f.strip() for f in args.formats.lower().split(",")}
    if "pdf" in wanted:
        p = outdir / f"{stem}_opendyslexic_{args.theme}.pdf"
        build_pdf(blocks, p, title, args.author, args.theme)
        print(f"  PDF   -> {p}")
    if "epub" in wanted:
        p = outdir / f"{stem}_accessible.epub"
        build_epub(blocks, p, title, args.author, args.theme)
        print(f"  EPUB  -> {p}")
    if "tts" in wanted:
        p = outdir / f"{stem}_audiobook_text.txt"
        build_tts(blocks, p, title, args.author)
        print(f"  TTS   -> {p}")
    if "html" in wanted:
        p = outdir / f"{stem}_reader.html"
        build_html(blocks, p, title, args.author)
        print(f"  HTML  -> {p}")
    if "audio" in wanted:
        print("  voicing audiobook ...")
        out = build_audio(blocks, outdir / f"{stem}_audiobook", title,
                          args.author, args.voice, args.rate)
        print(f"  AUDIO -> {out}")
    print("Done.")


if __name__ == "__main__":
    main()
