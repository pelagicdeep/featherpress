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

# ---------------------------------------------------------------------------
# Core conversion, GUI-independent and testable
# ---------------------------------------------------------------------------

def convert(input_path, outdir, title, author, theme, formats, status_cb):
    """Run the pipeline. status_cb(str) receives progress lines.
    Returns the output directory Path on success, raises on failure."""
    import featherpress as fp
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    title = title.strip() or src.stem.replace("-", " ").replace("_", " ").title()
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = fp.re.sub(r"\W+", "-", title.lower()).strip("-") or "book"

    status_cb(f"Reading {src.name} ...")
    blocks = fp.load_manuscript(src)
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
                             progress_cb=status_cb)
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

    root = tk.Tk()
    root.title(f"Featherpress v{VERSION}")
    root.configure(bg=BG)
    root.geometry("560x520")
    root.minsize(480, 480)

    state = {"file": None, "outdir": Path(__file__).resolve().parent / "output"}

    def styled_label(parent, text, **kw):
        return tk.Label(parent, text=text, bg=BG, fg=MUTED, anchor="w", **kw)

    frame = tk.Frame(root, bg=BG, padx=18, pady=14)
    frame.pack(fill="both", expand=True)

    def whats_new():
        path = Path(__file__).resolve().parent / "CHANGELOG.md"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            log("No CHANGELOG.md found next to featherpress_gui.py.")
            return
        section, started = [], False
        for line in lines:
            if line.startswith("## "):
                if started:
                    break
                started = True
            if started and line.strip():
                section.append(line.lstrip("#").strip())
        log("\n".join(section) if section else "CHANGELOG.md has no entries yet.")

    head = tk.Frame(frame, bg=BG); head.pack(fill="x")
    tk.Label(head, text="FEATHERPRESS", bg=BG, fg=CYAN,
             font=("Verdana", 14, "bold")).pack(side="left")
    tk.Label(head, text=f"v{VERSION}", bg=BG, fg=MUTED).pack(
        side="left", padx=(8, 0), pady=(3, 0))
    tk.Button(head, text="What's new", command=whats_new, bg=BG, fg=MUTED,
              activebackground=BG, activeforeground=INK, relief="flat",
              bd=0, cursor="hand2").pack(side="right")
    tk.Label(frame, text="One manuscript in. Five accessible formats out.",
             bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 10))

    # file picker
    file_var = tk.StringVar(value="No file chosen yet")
    def pick_file():
        p = filedialog.askopenfilename(
            title="Choose a manuscript",
            filetypes=[("Manuscripts", "*.md *.markdown *.txt *.docx *.pdf *.epub"), ("All files", "*.*")])
        if p:
            state["file"] = p
            file_var.set(Path(p).name)
    tk.Button(frame, text="Choose manuscript...", command=pick_file,
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

    # status box
    status = tk.Text(frame, height=9, bg=PANEL, fg=INK, relief="flat",
                     state="disabled", wrap="word")
    status.pack(fill="both", expand=True, pady=(12, 8))

    def log(msg):
        status.configure(state="normal")
        status.insert("end", msg + "\n")
        status.see("end")
        status.configure(state="disabled")

    # buttons
    brow = tk.Frame(frame, bg=BG); brow.pack(fill="x")
    go_btn = tk.Button(brow, text="Convert", bg=PANEL, fg=GOLD,
                       activebackground=PANEL, activeforeground=GOLD,
                       relief="flat", padx=20, pady=8, font=("Verdana", 11, "bold"))
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
                                   install_btn.configure(state="normal", text="Install/update requirements")))
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
    tk.Button(brow, text="Open output folder", command=open_output,
              bg=PANEL, fg=MUTED, activebackground=PANEL, activeforeground=INK,
              relief="flat", padx=12, pady=8).pack(side="left", padx=8)
    install_btn = tk.Button(brow, text="Install/update requirements", command=lambda: install_deps(),
              bg=PANEL, fg=MUTED, activebackground=PANEL, activeforeground=INK,
              relief="flat", padx=12, pady=8)
    install_btn.pack(side="left")

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
                convert(state["file"], state["outdir"], title_e.get(), author_e.get(),
                        theme_var.get(), formats, lambda m: root.after(0, log, m))
                root.after(0, open_output)
            except ModuleNotFoundError as e:
                root.after(0, log, f"Missing piece: {e.name}. Press the Install/update requirements button, then Convert again.")
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
