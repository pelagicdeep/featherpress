#!/usr/bin/env python3
"""
Featherpress GUI: the exhausted-evening interface.
Double-click featherpress_gui.bat (Windows) or run: python featherpress_gui.py
No dependencies beyond Featherpress itself; tkinter ships with Python.
"""

import threading
import traceback
from pathlib import Path

try:
    from featherpress import __version__ as VERSION
except Exception:
    VERSION = "unknown"

# offline Piper voices, listed in the picker alongside the Edge catalog
OFFLINE_VOICES = [
    ("en_US-lessac-medium", "Female"),
    ("en_US-amy-medium", "Female"),
    ("en_US-hfc_female-medium", "Female"),
    ("en_US-hfc_male-medium", "Male"),
    ("en_US-joe-medium", "Male"),
    ("en_US-ryan-high", "Male"),
    ("en_GB-alba-medium", "Female"),
    ("en_GB-alan-medium", "Male"),
]

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"

SETTINGS_PATH = Path(__file__).resolve().parent / "gui_settings.json"
DEFAULT_SETTINGS = {"dyslexic_font": True, "large_text": False}


def load_settings():
    import json
    try:
        return {**DEFAULT_SETTINGS,
                **json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    import json
    try:
        SETTINGS_PATH.write_text(json.dumps(settings), encoding="utf-8")
    except OSError:
        pass


def _register_fonts():
    """Make the bundled OpenDyslexic faces available to tkinter.
    Windows: loaded as private process fonts, no install needed."""
    import sys
    fonts = Path(__file__).resolve().parent / "fonts"
    if sys.platform == "win32" and fonts.is_dir():
        import ctypes
        FR_PRIVATE = 0x10
        for f in fonts.glob("OpenDyslexic-*.ttf"):
            ctypes.windll.gdi32.AddFontResourceExW(str(f), FR_PRIVATE, 0)


def play_media(path):
    """Play a short clip without blocking."""
    import os
    import sys
    path = str(path)
    if sys.platform == "win32":
        if path.lower().endswith(".wav"):
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            os.startfile(path)  # noqa: S606 - hand mp3s to the default player
    else:
        import subprocess
        player = "afplay" if sys.platform == "darwin" else "aplay"
        subprocess.Popen([player, path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

# ---------------------------------------------------------------------------
# Core conversion, GUI-independent and testable
# ---------------------------------------------------------------------------

def convert(input_path, outdir, title, author, theme, formats, status_cb,
            voice=DEFAULT_VOICE, rate=0, book_voices=None):
    """Run the pipeline. status_cb(str) receives progress lines.
    Returns the output directory Path on success, raises on failure."""
    import featherpress as fp
    paths = ([Path(input_path)] if isinstance(input_path, (str, Path))
             else [Path(p) for p in input_path])
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError("File not found: " + ", ".join(str(m) for m in missing))
    title = title.strip() or paths[0].stem.replace("-", " ").replace("_", " ").title()
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = fp.re.sub(r"\W+", "-", title.lower()).strip("-") or "book"

    if len(paths) == 1:
        status_cb(f"Reading {paths[0].name} ...")
    else:
        status_cb(f"Combining {len(paths)} manuscripts in this order:")
        for i, p in enumerate(paths):
            narrator = (f"  (narrator: {book_voices[i]})"
                        if book_voices and book_voices[i] else "")
            status_cb(f"  + {p.name}{narrator}")
    blocks = fp.load_manuscripts(paths, voices=book_voices)
    status_cb(f"Parsed {len(blocks)} blocks.")

    if "pdf" in formats:
        p = outdir / f"{stem}_opendyslexic_{theme}.pdf"
        fp.build_pdf(blocks, p, title, author, theme)
        status_cb(f"PDF written: {p.name}")
    if "epub" in formats:
        p = outdir / f"{stem}_accessible.epub"
        fp.build_epub(blocks, p, title, author, theme)
        status_cb(f"EPUB written: {p.name}")
    if "tts" in formats:
        p = outdir / f"{stem}_audiobook_text.txt"
        fp.build_tts(blocks, p, title, author)
        status_cb(f"Audiobook text written: {p.name}")
    if "html" in formats:
        p = outdir / f"{stem}_reader.html"
        fp.build_html(blocks, p, title, author)
        status_cb(f"HTML reader written: {p.name}")
    if "audio" in formats:
        status_cb("Voicing audiobook (a full book can take a while) ...")
        out = fp.build_audio(blocks, outdir / f"{stem}_audiobook", title, author,
                             voice_name=voice, rate=rate, progress_cb=status_cb)
        status_cb(f"Audiobook written: {out.name}")
    status_cb("Done.")
    return outdir


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def main():
    import tkinter as tk
    from tkinter import filedialog, ttk
    import os
    import subprocess
    import sys

    BG, PANEL, INK, CYAN, GOLD, MUTED = "#0c1015", "#141a22", "#e6e3dc", "#3fe0d0", "#d9b84a", "#9a968c"

    import tkinter.font as tkfont

    root = tk.Tk()
    root.title(f"Featherpress v{VERSION}")
    root.configure(bg=BG)

    settings = load_settings()
    _register_fonts()
    dys_ok = "OpenDyslexic" in set(tkfont.families(root))
    body_font = tkfont.Font(root=root)
    bold_font = tkfont.Font(root=root, weight="bold")
    head_font = tkfont.Font(root=root, weight="bold")
    root.option_add("*Font", body_font)

    def apply_typography():
        fam = "OpenDyslexic" if (settings["dyslexic_font"] and dys_ok) else "Segoe UI"
        base = 13 if settings["large_text"] else 10
        body_font.configure(family=fam, size=base)
        bold_font.configure(family=fam, size=base + 1)
        head_font.configure(family=fam, size=base + 5)
        style = ttk.Style(root)
        style.configure(".", font=body_font)
        style.configure("Treeview", font=body_font,
                        rowheight=int(body_font.metrics("linespace") * 1.35))
        style.configure("Treeview.Heading", font=body_font)
        # the window grows with the text so nothing clips at any size
        if settings["large_text"]:
            root.minsize(700, 780)
            if root.winfo_width() < 700:
                root.geometry("720x800")
        else:
            root.minsize(520, 640)

    root.geometry("560x660")
    apply_typography()

    state = {"file": None, "outdir": Path(__file__).resolve().parent / "output",
             "book_voices": {}}

    def styled_label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=BG, fg=MUTED, anchor="w", **kw)

    frame = tk.Frame(root, bg=BG, padx=18, pady=14)
    frame.pack(fill="both", expand=True)

    def show_history():
        path = Path(__file__).resolve().parent / "CHANGELOG.md"
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            log("No CHANGELOG.md found next to featherpress_gui.py.")
            return
        win = tk.Toplevel(root)
        win.title("Featherpress version history")
        win.configure(bg=BG)
        win.geometry("840x680" if settings["large_text"] else "660x560")
        win.transient(root)
        wrap = tk.Frame(win, bg=BG, padx=10, pady=10)
        wrap.pack(fill="both", expand=True)
        txt = tk.Text(wrap, bg=PANEL, fg=INK, relief="flat", wrap="word",
                      padx=14, pady=12, font=body_font)
        sc = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sc.set)
        txt.insert("1.0", content)
        txt.configure(state="disabled")
        txt.pack(side="left", fill="both", expand=True)
        sc.pack(side="left", fill="y")

    head = tk.Frame(frame, bg=BG); head.pack(fill="x")
    tk.Label(head, text="FEATHERPRESS", bg=BG, fg=CYAN,
             font=head_font).pack(side="left")
    tk.Label(head, text=f"v{VERSION}", bg=BG, fg=MUTED).pack(
        side="left", padx=(8, 0), pady=(3, 0))
    tk.Button(head, text="Version history", command=show_history, bg=BG, fg=MUTED,
              activebackground=BG, activeforeground=INK, relief="flat",
              bd=0, cursor="hand2").pack(side="right")
    tk.Label(frame, text="One manuscript in. Five accessible formats out.",
             bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 6))

    # interface preferences: dyslexic or standard font, normal or large text
    irow = tk.Frame(frame, bg=BG); irow.pack(fill="x", pady=(0, 8))
    styled_label(irow, "Interface:").pack(side="left")

    def toggle_font():
        settings["dyslexic_font"] = not settings["dyslexic_font"]
        save_settings(settings)
        apply_typography()
        refresh_toggle_labels()

    def toggle_size():
        settings["large_text"] = not settings["large_text"]
        save_settings(settings)
        apply_typography()
        refresh_toggle_labels()

    font_btn = tk.Button(irow, command=toggle_font, bg=PANEL, fg=INK,
                         activebackground=PANEL, activeforeground=INK,
                         relief="flat", padx=10, pady=2)
    font_btn.pack(side="left", padx=(6, 4))
    size_btn = tk.Button(irow, command=toggle_size, bg=PANEL, fg=INK,
                         activebackground=PANEL, activeforeground=INK,
                         relief="flat", padx=10, pady=2)
    size_btn.pack(side="left")

    def refresh_toggle_labels():
        font_btn.configure(text="Font: " + (
            "OpenDyslexic" if settings["dyslexic_font"] and dys_ok else "Standard"))
        size_btn.configure(text="Text: " + (
            "Large" if settings["large_text"] else "Normal"))

    if not dys_ok:
        font_btn.configure(state="disabled")
    refresh_toggle_labels()

    # file picker (select several files to combine them into one book)
    file_var = tk.StringVar(value="No file chosen yet")
    def pick_file():
        picked = filedialog.askopenfilenames(
            title="Choose one manuscript, or several to combine",
            filetypes=[("Manuscripts", "*.md *.markdown *.txt *.docx *.pdf *.epub"), ("All files", "*.*")])
        if picked:
            state["file"] = list(picked)
            state["book_voices"] = {}
            if len(picked) == 1:
                file_var.set(Path(picked[0]).name)
            else:
                file_var.set(f"{len(picked)} manuscripts (combined into one book)")
                log("Combining in this order (set Title yourself for combined books):")
                for p in picked:
                    log(f"  + {Path(p).name}")
    tk.Button(frame, text="Choose manuscript(s)...", command=pick_file,
              bg=PANEL, fg=CYAN, activebackground=PANEL, activeforeground=CYAN,
              relief="flat", padx=12, pady=6).pack(anchor="w")
    tk.Label(frame, textvariable=file_var, bg=BG, fg=INK).pack(anchor="w", pady=(2, 10))

    # title / author
    row = tk.Frame(frame, bg=BG); row.pack(fill="x")
    styled_label(row, "Title (optional)").grid(row=0, column=0, sticky="w")
    styled_label(row, "Author (optional)").grid(row=0, column=1, sticky="w", padx=(10, 0))
    title_e = tk.Entry(row, bg=PANEL, fg=INK, insertbackground=INK, relief="flat")
    author_e = tk.Entry(row, bg=PANEL, fg=INK, insertbackground=INK, relief="flat")
    title_e.grid(row=1, column=0, sticky="ew", ipady=4)
    author_e.grid(row=1, column=1, sticky="ew", padx=(10, 0), ipady=4)
    row.columnconfigure(0, weight=1); row.columnconfigure(1, weight=1)

    # theme
    theme_var = tk.StringVar(value="dark")
    trow = tk.Frame(frame, bg=BG); trow.pack(fill="x", pady=(10, 0))
    styled_label(trow, "Theme:").pack(side="left")
    for val, lab in (("dark", "Dark"), ("cream", "Cream")):
        tk.Radiobutton(trow, text=lab, value=val, variable=theme_var,
                       bg=BG, fg=INK, selectcolor=PANEL,
                       activebackground=BG, activeforeground=INK).pack(side="left", padx=6)

    # voice + speed (for the audiobook format)
    voice_state = {"name": DEFAULT_VOICE}
    vrow = tk.Frame(frame, bg=BG); vrow.pack(fill="x", pady=(6, 0))
    styled_label(vrow, "Voice:").pack(side="left")
    voice_lbl = tk.Label(vrow, text=voice_state["name"], bg=BG, fg=INK)
    voice_lbl.pack(side="left", padx=(6, 10))
    # the voice buttons live on their own row so long voice names and wide
    # fonts can never push them off the window edge
    vbtns = tk.Frame(frame, bg=BG); vbtns.pack(fill="x", pady=(2, 0))

    def set_voice(name):
        voice_state["name"] = name
        voice_lbl.configure(text=name)
        log(f"Voice set to {name}.")

    srow = tk.Frame(frame, bg=BG); srow.pack(fill="x")
    styled_label(srow, "Speed:").pack(side="left")
    rate_var = tk.IntVar(value=0)
    tk.Scale(srow, from_=-40, to=40, resolution=5, orient="horizontal",
             variable=rate_var, bg=BG, fg=INK, highlightthickness=0,
             troughcolor=PANEL, length=190).pack(side="left", padx=(6, 4))
    styled_label(srow, "% (negative = slower)").pack(side="left")

    def sample_task(name, rate, btn):
        def task():
            try:
                import featherpress as fp
                sample = fp.voice_sample(name, rate)
                play_media(sample)
                root.after(0, log, f"Playing sample: {name} at {rate:+d}%")
            except Exception as e:
                root.after(0, log, f"Could not play sample: {e}")
            finally:
                root.after(0, lambda: btn.configure(state="normal", text="Hear sample"))
        btn.configure(state="disabled", text="Loading...")
        threading.Thread(target=task, daemon=True).start()

    def open_voice_picker(on_pick=None):
        on_pick = on_pick or set_voice
        import featherpress as fp
        win = tk.Toplevel(root)
        win.title("Choose a voice")
        win.configure(bg=BG)
        win.geometry("860x640" if settings["large_text"] else "680x540")
        win.transient(root)

        style = ttk.Style(win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=INK)
        style.configure("Treeview.Heading", background=BG, foreground=MUTED)
        apply_typography()  # reassert fonts and row height after theme switch

        top = tk.Frame(win, bg=BG, padx=10, pady=8); top.pack(fill="x")
        tk.Label(top, text="Search:", bg=BG, fg=MUTED).pack(side="left")
        search_var = tk.StringVar()
        tk.Entry(top, textvariable=search_var, bg=PANEL, fg=INK,
                 insertbackground=INK, relief="flat", width=22).pack(
            side="left", padx=(4, 10), ipady=3)
        lang_var = tk.StringVar(value="All languages")
        lang_box = ttk.Combobox(top, textvariable=lang_var, state="readonly",
                                values=["All languages"], width=14)
        lang_box.pack(side="left", padx=(0, 10))
        gender_var = tk.StringVar(value="Any gender")
        ttk.Combobox(top, textvariable=gender_var, state="readonly",
                     values=["Any gender", "Female", "Male"], width=11).pack(side="left")

        mid = tk.Frame(win, bg=BG); mid.pack(fill="both", expand=True, padx=10)
        cols = ("voice", "language", "gender", "engine")
        tree = ttk.Treeview(mid, columns=cols, show="headings")
        heads = {"voice": ("Voice", 280), "language": ("Language", 90),
                 "gender": ("Gender", 80), "engine": ("Engine", 120)}
        for c in cols:
            tree.heading(c, text=heads[c][0])
            tree.column(c, width=heads[c][1], anchor="w")
        scroll = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")

        rows = [(n, n.split("-")[0].replace("_", "-"), g, "Piper (offline)")
                for n, g in OFFLINE_VOICES]

        count_lbl = tk.Label(win, text="Loading the Edge voice catalog ...",
                             bg=BG, fg=MUTED)

        def apply_filter(*_):
            q = search_var.get().lower().strip()
            lang, gen = lang_var.get(), gender_var.get()
            tree.delete(*tree.get_children())
            shown = 0
            for name, loc, g, eng in rows:
                if q and q not in name.lower() and q not in loc.lower():
                    continue
                if lang != "All languages" and loc != lang:
                    continue
                if gen != "Any gender" and g != gen:
                    continue
                tree.insert("", "end", values=(name, loc, g, eng))
                shown += 1
            count_lbl.configure(text=f"{shown} voices")

        def catalog_loaded(edge_rows):
            rows.extend(edge_rows)
            locales = sorted({loc for _, loc, _, _ in rows})
            lang_box.configure(values=["All languages"] + locales)
            apply_filter()

        def load_catalog():
            try:
                edge = fp.list_edge_voices()
                edge_rows = [(v["name"], v["locale"], v["gender"], "Edge (online)")
                             for v in edge]
                root.after(0, catalog_loaded, edge_rows)
            except Exception as e:
                root.after(0, log, f"Could not load Edge voices (offline?): {e}")
                root.after(0, apply_filter)

        search_var.trace_add("write", apply_filter)
        for w in top.winfo_children():
            if isinstance(w, ttk.Combobox):
                w.bind("<<ComboboxSelected>>", apply_filter)

        def selected_name():
            sel = tree.selection()
            return str(tree.item(sel[0])["values"][0]) if sel else None

        bottom = tk.Frame(win, bg=BG, padx=10, pady=8); bottom.pack(fill="x")
        count_lbl.pack(in_=bottom, side="left")
        pick_btn = tk.Button(bottom, text="Use this voice", bg=PANEL, fg=GOLD,
                             activebackground=PANEL, activeforeground=GOLD,
                             relief="flat", padx=14, pady=4)
        pick_btn.pack(side="right")
        hear2_btn = tk.Button(bottom, text="Hear sample", bg=PANEL, fg=INK,
                              activebackground=PANEL, activeforeground=INK,
                              relief="flat", padx=14, pady=4)
        hear2_btn.pack(side="right", padx=8)

        def use_selected(*_):
            name = selected_name()
            if name:
                on_pick(name)
                win.destroy()

        pick_btn.configure(command=use_selected)
        hear2_btn.configure(
            command=lambda: selected_name() and sample_task(
                selected_name(), rate_var.get(), hear2_btn))
        tree.bind("<Double-1>", use_selected)

        apply_filter()
        threading.Thread(target=load_catalog, daemon=True).start()

    tk.Button(vbtns, text="Choose voice...", command=open_voice_picker,
              bg=PANEL, fg=CYAN, activebackground=PANEL, activeforeground=CYAN,
              relief="flat", padx=10, pady=2).pack(side="left", padx=(0, 6))
    hear_btn = tk.Button(vbtns, text="Hear sample", bg=PANEL, fg=INK,
                         activebackground=PANEL, activeforeground=INK,
                         relief="flat", padx=10, pady=2)
    hear_btn.configure(command=lambda: sample_task(
        voice_state["name"], rate_var.get(), hear_btn))
    hear_btn.pack(side="left")

    def open_narrators():
        files = state["file"] if isinstance(state["file"], list) else None
        if not files or len(files) < 2:
            log("Choose several manuscripts first: per-book narrators "
                "apply to combined books.")
            return
        win = tk.Toplevel(root)
        win.title("Narrators per book")
        win.configure(bg=BG)
        win.transient(root)
        tk.Label(win, text="Each book reads in the main voice unless changed here.",
                 bg=BG, fg=MUTED, padx=12, pady=8).pack(anchor="w")
        rows = tk.Frame(win, bg=BG, padx=12); rows.pack(fill="both", expand=True)
        labels = {}

        def set_book_voice(path, name):
            state["book_voices"][path] = name
            labels[path].configure(text=name)
            log(f"Narrator for {Path(path).name}: {name}")

        def clear_book_voice(path):
            state["book_voices"].pop(path, None)
            labels[path].configure(text="(main voice)")

        for p in files:
            row = tk.Frame(rows, bg=BG); row.pack(fill="x", pady=2)
            tk.Label(row, text=Path(p).name, bg=BG, fg=INK, anchor="w",
                     width=34).pack(side="left")
            lbl = tk.Label(row, text=state["book_voices"].get(p) or "(main voice)",
                           bg=BG, fg=MUTED, anchor="w")
            lbl.pack(side="left", padx=8)
            labels[p] = lbl
            tk.Button(row, text="Change...", bg=PANEL, fg=CYAN,
                      activebackground=PANEL, activeforeground=CYAN, relief="flat",
                      padx=8, pady=1,
                      command=lambda path=p: open_voice_picker(
                          lambda name, path=path: set_book_voice(path, name))
                      ).pack(side="right", padx=(4, 0))
            tk.Button(row, text="Reset", bg=PANEL, fg=MUTED,
                      activebackground=PANEL, activeforeground=INK, relief="flat",
                      padx=8, pady=1,
                      command=lambda path=p: clear_book_voice(path)).pack(side="right")
        tk.Button(win, text="Done", command=win.destroy, bg=PANEL, fg=GOLD,
                  activebackground=PANEL, activeforeground=GOLD, relief="flat",
                  padx=16, pady=4).pack(pady=10)

    tk.Button(vbtns, text="Narrators...", command=open_narrators,
              bg=PANEL, fg=MUTED, activebackground=PANEL, activeforeground=INK,
              relief="flat", padx=10, pady=2).pack(side="left", padx=(6, 0))

    # formats
    frow = tk.Frame(frame, bg=BG); frow.pack(fill="x", pady=(6, 0))
    styled_label(frow, "Formats:").pack(side="left")
    fmt_vars = {}
    for f in ("pdf", "epub", "tts", "html", "audio"):
        v = tk.BooleanVar(value=(f != "audio"))
        fmt_vars[f] = v
        tk.Checkbutton(frow, text=f.upper(), variable=v, bg=BG, fg=INK,
                       selectcolor=PANEL, activebackground=BG,
                       activeforeground=INK).pack(side="left", padx=4)

    # status box: created here, packed after the button row below so the
    # buttons keep their space when a wide font shrinks the free area
    status = tk.Text(frame, height=8, bg=PANEL, fg=INK, relief="flat",
                     state="disabled", wrap="word")

    def log(msg):
        status.configure(state="normal")
        status.insert("end", msg + "\n")
        status.see("end")
        status.configure(state="disabled")

    # buttons: pinned to the bottom and packed before the status box, so
    # they are always visible and clickable no matter the font or size
    brow = tk.Frame(frame, bg=BG); brow.pack(side="bottom", fill="x", pady=(8, 0))
    go_btn = tk.Button(brow, text="Convert", bg=PANEL, fg=GOLD,
                       activebackground=PANEL, activeforeground=GOLD,
                       relief="flat", padx=20, pady=8, font=bold_font)
    go_btn.pack(side="left")

    def install_deps():
        req = Path(__file__).resolve().parent / "requirements.txt"
        go_btn.configure(state="disabled")
        install_btn.configure(state="disabled", text="Installing...")
        def task():
            import subprocess
            cmds = [
                [sys.executable, "-m", "pip", "install", "-r", str(req)],
                [sys.executable, "-m", "pip", "install", "-r", str(req), "--user"],
            ]
            ok = False
            for cmd in cmds:
                root.after(0, log, "Running: " + " ".join(cmd[-4:]))
                try:
                    p = subprocess.run(cmd, capture_output=True, text=True)
                    tail = (p.stdout or "").strip().splitlines()[-2:]
                    for line in tail:
                        root.after(0, log, line)
                    if p.returncode == 0:
                        ok = True
                        break
                    root.after(0, log, (p.stderr or "").strip().splitlines()[-1] if p.stderr else "pip failed, retrying with --user")
                except Exception as e:
                    root.after(0, log, f"pip could not run: {e}")
            root.after(0, log, "Everything installed. Press Convert again." if ok
                       else "Install failed. Open a terminal here and run: python -m pip install -r requirements.txt")
            root.after(0, lambda: (go_btn.configure(state="normal"),
                                   install_btn.configure(state="normal", text="Install requirements")))
        threading.Thread(target=task, daemon=True).start()

    def open_output():
        out = state["outdir"]
        out.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(out)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(out)])
        else:
            subprocess.Popen(["xdg-open", str(out)])
    tk.Button(brow, text="Open output", command=open_output,
              bg=PANEL, fg=MUTED, activebackground=PANEL, activeforeground=INK,
              relief="flat", padx=10, pady=8).pack(side="left", padx=6)
    install_btn = tk.Button(brow, text="Install requirements", command=lambda: install_deps(),
              bg=PANEL, fg=MUTED, activebackground=PANEL, activeforeground=INK,
              relief="flat", padx=10, pady=8)
    install_btn.pack(side="left")
    status.pack(fill="both", expand=True, pady=(12, 0))

    def run():
        if not state["file"]:
            log("Choose a manuscript first.")
            return
        formats = {f for f, v in fmt_vars.items() if v.get()}
        if not formats:
            log("Pick at least one format.")
            return
        go_btn.configure(state="disabled", text="Working...")
        def task():
            try:
                files = state["file"]
                bv = None
                if isinstance(files, list) and len(files) > 1 and state["book_voices"]:
                    bv = [state["book_voices"].get(p) for p in files]
                convert(files, state["outdir"], title_e.get(), author_e.get(),
                        theme_var.get(), formats, lambda m: root.after(0, log, m),
                        voice=voice_state["name"], rate=rate_var.get(),
                        book_voices=bv)
                root.after(0, open_output)
            except ModuleNotFoundError as e:
                root.after(0, log, f"Missing piece: {e.name}. Press the Install requirements button, then Convert again.")
            except Exception as e:
                root.after(0, log, f"Failed: {e}")
                traceback.print_exc()
            finally:
                root.after(0, lambda: go_btn.configure(state="normal", text="Convert"))
        threading.Thread(target=task, daemon=True).start()

    go_btn.configure(command=run)
    log("Ready. Choose a manuscript and press Convert.")
    root.mainloop()


if __name__ == "__main__":
    main()
