"""
Prompt Generator — Desktop GUI
Antigravity CLI · Gemini 3.1 Pro High · Batch Engine

Launch:  python gui.py
"""

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

# Ensure src is on path
_REPO_ROOT = Path(__file__).resolve().parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from prompt_generator.gui_account_manager import (
    Account,
    AccountManager,
    QuotaInfo,
    fetch_quota,
)
from prompt_generator.gui_worker import EventType, GenerationWorker, LogLevel

# ─────────────────────────────────────────────────────────────────────────────
# THEME
# ─────────────────────────────────────────────────────────────────────────────

C = {
    "bg":          "#0d0d14",
    "surface":     "#13131f",
    "surface2":    "#1a1a2e",
    "border":      "#2a2a42",
    "accent":      "#7c6ff7",
    "accent_dim":  "#4a4580",
    "accent_glow": "#9d94ff",
    "text":        "#e2e2f0",
    "text_dim":    "#7a7a9a",
    "text_muted":  "#4a4a6a",
    "ok":          "#22c55e",
    "warn":        "#f59e0b",
    "error":       "#ef4444",
    "resume":      "#38bdf8",
    "info":        "#94a3b8",
    "progress_bg": "#1e1e35",
    "progress_fg": "#7c6ff7",
    "btn_bg":      "#7c6ff7",
    "btn_hover":   "#6b5fe6",
    "btn_text":    "#ffffff",
    "btn_stop_bg": "#b91c1c",
    "btn_stop_h":  "#991b1b",
    "input_bg":    "#181828",
    "input_border":"#333355",
}

LEVEL_COLORS = {
    LogLevel.OK:     C["ok"],
    LogLevel.INFO:   C["info"],
    LogLevel.WARN:   C["warn"],
    LogLevel.ERROR:  C["error"],
    LogLevel.RESUME: C["resume"],
}
LEVEL_PREFIXES = {
    LogLevel.OK:     "✓",
    LogLevel.INFO:   "·",
    LogLevel.WARN:   "⚠",
    LogLevel.ERROR:  "✗",
    LogLevel.RESUME: "↩",
}

FONT_FAMILY = "Segoe UI"
FONT_MONO   = "Consolas"

logging.basicConfig(level=logging.INFO)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def quota_color(pct: Optional[float]) -> str:
    if pct is None:
        return C["text_dim"]
    if pct > 50:
        return C["ok"]
    if pct > 15:
        return C["warn"]
    return C["error"]


def _btn(parent, text, command, bg=None, hover_bg=None, fg=None,
         font_size=10, pad_x=18, pad_y=8, width=None, **kwargs):
    bg = bg or C["btn_bg"]
    hover_bg = hover_bg or C["btn_hover"]
    fg = fg or C["btn_text"]
    b = tk.Label(
        parent, text=text, bg=bg, fg=fg,
        font=(FONT_FAMILY, font_size, "bold"),
        cursor="hand2", padx=pad_x, pady=pad_y,
        **kwargs,
    )
    if width:
        b.config(width=width)
    b.bind("<Button-1>", lambda e: command())
    b.bind("<Enter>",    lambda e: b.config(bg=hover_bg))
    b.bind("<Leave>",    lambda e: b.config(bg=bg))
    return b


def _label(parent, text, size=10, color=None, bold=False, **kw):
    font = (FONT_FAMILY, size, "bold" if bold else "normal")
    return tk.Label(parent, text=text, bg=C["bg"], fg=color or C["text"],
                    font=font, **kw)


def _sep(parent, color=None, pad_y=6):
    f = tk.Frame(parent, bg=color or C["border"], height=1)
    f.pack(fill="x", pady=pad_y)
    return f


# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNT SWITCHER MODAL
# ─────────────────────────────────────────────────────────────────────────────

class AccountSwitcherModal(tk.Toplevel):
    def __init__(self, parent, manager: AccountManager, on_switch_callback):
        super().__init__(parent)
        self.manager = manager
        self.on_switch = on_switch_callback
        self._account_rows = {}  # name → frame

        self.title("Switch Account")
        self.configure(bg=C["surface"])
        self.resizable(False, False)
        self.grab_set()

        # Center over parent
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = 440, 520
        self.geometry(f"{w}x{h}+{px + (pw - w)//2}+{py + (ph - h)//2}")

        self._build()
        self._refresh_accounts()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=C["surface"], pady=18)
        hdr.pack(fill="x", padx=24)
        tk.Label(hdr, text="⚡  Switch Account", bg=C["surface"],
                 fg=C["text"], font=(FONT_FAMILY, 13, "bold")).pack(side="left")
        tk.Label(hdr, text="✕", bg=C["surface"], fg=C["text_dim"],
                 font=(FONT_FAMILY, 14), cursor="hand2").pack(side="right")
        hdr.winfo_children()[-1].bind("<Button-1>", lambda e: self.destroy())

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        # Accounts scroll area
        self._list_frame = tk.Frame(self, bg=C["surface"])
        self._list_frame.pack(fill="both", expand=True, padx=16, pady=12)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        # Bottom buttons
        btm = tk.Frame(self, bg=C["surface"], pady=16)
        btm.pack(fill="x", padx=20)

        save_btn = _btn(btm, "💾  Save Current Session", self._save_current,
                        bg=C["accent_dim"], hover_bg=C["accent"], pad_x=14, pad_y=7, font_size=9)
        save_btn.pack(side="left")

        login_btn = _btn(btm, "🔓  New Login", self._launch_login,
                         bg=C["surface2"], hover_bg=C["border"], pad_x=14, pad_y=7, font_size=9)
        login_btn.pack(side="right")

    def _refresh_accounts(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._account_rows.clear()

        accounts = self.manager.list_accounts()

        if not accounts:
            tk.Label(self._list_frame, text="No saved accounts yet.\nSave the current session to get started.",
                     bg=C["surface"], fg=C["text_dim"],
                     font=(FONT_FAMILY, 10), justify="center").pack(pady=40)
            return

        for acc in accounts:
            self._add_account_row(acc)

    def _add_account_row(self, acc: Account):
        is_active = acc.is_active
        row_bg = C["surface2"] if is_active else C["surface"]
        border_color = C["accent"] if is_active else C["border"]

        outer = tk.Frame(self._list_frame, bg=border_color, pady=1, padx=1)
        outer.pack(fill="x", pady=4)

        row = tk.Frame(outer, bg=row_bg, padx=14, pady=12)
        row.pack(fill="x")

        # Left: avatar + info
        left = tk.Frame(row, bg=row_bg)
        left.pack(side="left", fill="y")

        avatar_text = acc.label[0].upper() if acc.label else "?"
        avatar = tk.Label(left, text=avatar_text, bg=C["accent"], fg="white",
                          font=(FONT_FAMILY, 13, "bold"), width=2, height=1)
        avatar.pack(side="left", padx=(0, 10))

        info = tk.Frame(left, bg=row_bg)
        info.pack(side="left")

        tk.Label(info, text=acc.label, bg=row_bg, fg=C["text"],
                 font=(FONT_FAMILY, 10, "bold")).pack(anchor="w")

        date_str = ""
        if acc.created_at:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(acc.created_at.replace("Z", "+00:00"))
                date_str = f"Saved {dt.strftime('%b %d, %Y')}"
            except Exception:
                date_str = acc.created_at[:10]

        tk.Label(info, text=date_str, bg=row_bg, fg=C["text_dim"],
                 font=(FONT_FAMILY, 8)).pack(anchor="w")

        # Right: badge + switch + delete
        right = tk.Frame(row, bg=row_bg)
        right.pack(side="right", fill="y")

        if is_active:
            tk.Label(right, text="✓ Active", bg=C["ok"], fg="white",
                     font=(FONT_FAMILY, 8, "bold"), padx=8, pady=3).pack(side="right", padx=(6, 0))
        else:
            def make_switch(name=acc.name):
                return lambda: self._switch_to(name)

            sw_btn = _btn(right, "Switch →", make_switch(),
                          bg=C["accent"], hover_bg=C["accent_glow"],
                          pad_x=10, pad_y=4, font_size=9)
            sw_btn.pack(side="right", padx=(4, 0))

            def make_del(name=acc.name):
                return lambda: self._delete_account(name)

            del_btn = tk.Label(right, text="🗑", bg=row_bg, fg=C["error"],
                               font=(FONT_FAMILY, 12), cursor="hand2")
            del_btn.pack(side="right", padx=(0, 4))
            del_btn.bind("<Button-1>", lambda e, n=acc.name: self._delete_account(n))

        self._account_rows[acc.name] = outer

    def _switch_to(self, name: str):
        success = self.manager.switch_account(name)
        if success:
            self._refresh_accounts()
            self.on_switch()
            # Show brief confirmation
            self._show_toast(f"Switched to account '{name}'")
        else:
            messagebox.showerror("Switch Failed",
                                 f"Could not restore snapshot for '{name}'.\n"
                                 "The account data may be missing.",
                                 parent=self)

    def _delete_account(self, name: str):
        if messagebox.askyesno("Delete Account",
                               f"Delete the saved account '{name}'?\n"
                               "This only removes the snapshot, not your actual account.",
                               parent=self):
            self.manager.delete_account(name)
            self._refresh_accounts()

    def _save_current(self):
        dialog = _SaveAccountDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            name, label = dialog.result
            try:
                self.manager.save_current_as_account(name, label)
                self._refresh_accounts()
                self._show_toast(f"Saved as '{label}'")
            except Exception as e:
                messagebox.showerror("Save Failed", str(e), parent=self)

    def _launch_login(self):
        self.manager.launch_login_terminal()
        self._show_toast("Opened terminal for login. Save the session after signing in.")

    def _show_toast(self, msg: str):
        toast = tk.Label(self, text=msg, bg=C["accent"], fg="white",
                         font=(FONT_FAMILY, 9), padx=12, pady=6)
        toast.place(relx=0.5, rely=0.97, anchor="s")
        self.after(2500, toast.destroy)


class _SaveAccountDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("Save Account")
        self.configure(bg=C["surface"])
        self.resizable(False, False)
        self.grab_set()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = 360, 220
        self.geometry(f"{w}x{h}+{px + (pw - w)//2}+{py + (ph - h)//2}")
        self._build()

    def _build(self):
        tk.Label(self, text="Save Current Session As", bg=C["surface"],
                 fg=C["text"], font=(FONT_FAMILY, 11, "bold")).pack(pady=(20, 12))

        frm = tk.Frame(self, bg=C["surface"], padx=24)
        frm.pack(fill="x")

        tk.Label(frm, text="Account Label (e.g. email):", bg=C["surface"],
                 fg=C["text_dim"], font=(FONT_FAMILY, 9)).pack(anchor="w")
        self._label_var = tk.StringVar()
        label_entry = tk.Entry(frm, textvariable=self._label_var,
                               bg=C["input_bg"], fg=C["text"],
                               insertbackground=C["text"],
                               relief="flat", font=(FONT_FAMILY, 10),
                               bd=0, highlightthickness=1,
                               highlightbackground=C["input_border"],
                               highlightcolor=C["accent"])
        label_entry.pack(fill="x", pady=(4, 12), ipady=6, ipadx=6)
        label_entry.focus_set()

        btns = tk.Frame(self, bg=C["surface"])
        btns.pack(fill="x", padx=24, pady=12)

        _btn(btns, "Save", self._on_save, bg=C["accent"], hover_bg=C["accent_glow"],
             pad_x=20, pad_y=7).pack(side="left")
        _btn(btns, "Cancel", self.destroy,
             bg=C["surface2"], hover_bg=C["border"], pad_x=20, pad_y=7).pack(side="right")

    def _on_save(self):
        label = self._label_var.get().strip()
        if not label:
            messagebox.showwarning("Input Required", "Please enter an account label.", parent=self)
            return
        # Sanitize name
        import re
        name = re.sub(r"[^a-zA-Z0-9_.-]", "_", label)[:40]
        self.result = (name, label)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APPLICATION WINDOW
# ─────────────────────────────────────────────────────────────────────────────

class PromptGeneratorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Prompt Generator — Antigravity CLI")
        self.configure(bg=C["bg"])
        self.minsize(820, 640)
        self.geometry("900x700")

        # State
        self._worker: Optional[GenerationWorker] = None
        self._start_time: Optional[float] = None
        self._timer_job = None
        self._quota_job = None
        self._account_manager = AccountManager()
        self._quota_info: Optional[QuotaInfo] = None
        self._output_path: Optional[Path] = None

        # Build UI
        self._build_header()
        self._build_account_bar()
        _sep(self)
        self._build_file_panel()
        _sep(self)
        self._build_progress_panel()
        _sep(self)
        self._build_log_panel()
        self._build_footer()

        # Initial async loads
        self.after(200, self._async_load_quota)
        self.after(100, self._async_load_account_info)

    # ─────────────────────────────────────────────────────────────────── #
    # HEADER
    # ─────────────────────────────────────────────────────────────────── #

    def _build_header(self):
        hdr = tk.Frame(self, bg=C["bg"], pady=16, padx=24)
        hdr.pack(fill="x")

        # Logo + title
        logo_frame = tk.Frame(hdr, bg=C["bg"])
        logo_frame.pack(side="left")

        tk.Label(logo_frame, text="🔮", bg=C["bg"], font=(FONT_FAMILY, 20)).pack(side="left", padx=(0, 10))

        title_frame = tk.Frame(logo_frame, bg=C["bg"])
        title_frame.pack(side="left")
        tk.Label(title_frame, text="Prompt Generator", bg=C["bg"], fg=C["text"],
                 font=(FONT_FAMILY, 16, "bold")).pack(anchor="w")
        tk.Label(title_frame, text="Antigravity CLI · Gemini 3.1 Pro High · Batch Engine",
                 bg=C["bg"], fg=C["text_dim"], font=(FONT_FAMILY, 8)).pack(anchor="w")

        # Right side — account switch button
        right = tk.Frame(hdr, bg=C["bg"])
        right.pack(side="right")

        self._acc_btn = _btn(right, "⚡  Switch Account", self._open_account_switcher,
                             bg=C["surface2"], hover_bg=C["surface"],
                             pad_x=14, pad_y=7, font_size=9)
        self._acc_btn.pack()

    # ─────────────────────────────────────────────────────────────────── #
    # ACCOUNT / QUOTA BAR
    # ─────────────────────────────────────────────────────────────────── #

    def _build_account_bar(self):
        self._bar = tk.Frame(self, bg=C["surface"], pady=10, padx=24)
        self._bar.pack(fill="x")

        # Account pill
        acc_frame = tk.Frame(self._bar, bg=C["surface"])
        acc_frame.pack(side="left")

        self._acc_dot = tk.Label(acc_frame, text="●", bg=C["surface"],
                                  fg=C["text_muted"], font=(FONT_FAMILY, 8))
        self._acc_dot.pack(side="left")

        self._acc_label = tk.Label(acc_frame, text="Loading session…",
                                    bg=C["surface"], fg=C["text_dim"],
                                    font=(FONT_FAMILY, 9))
        self._acc_label.pack(side="left", padx=(4, 0))

        # Divider
        tk.Label(self._bar, text="│", bg=C["surface"], fg=C["border"],
                 font=(FONT_FAMILY, 10)).pack(side="left", padx=12)

        # Model badge
        tk.Label(self._bar, text="gemini-3.1-pro-high",
                 bg=C["accent_dim"], fg=C["accent_glow"],
                 font=(FONT_FAMILY, 8, "bold"), padx=8, pady=3).pack(side="left")

        # Divider
        tk.Label(self._bar, text="│", bg=C["surface"], fg=C["border"],
                 font=(FONT_FAMILY, 10)).pack(side="left", padx=12)

        # Quota section
        quota_frame = tk.Frame(self._bar, bg=C["surface"])
        quota_frame.pack(side="left")

        tk.Label(quota_frame, text="Quota:", bg=C["surface"], fg=C["text_dim"],
                 font=(FONT_FAMILY, 8)).pack(side="left")

        self._quota_label = tk.Label(quota_frame, text="—",
                                      bg=C["surface"], fg=C["text_dim"],
                                      font=(FONT_FAMILY, 9, "bold"))
        self._quota_label.pack(side="left", padx=(4, 0))

        self._quota_dot = tk.Label(quota_frame, text="●",
                                    bg=C["surface"], fg=C["text_muted"],
                                    font=(FONT_FAMILY, 8))
        self._quota_dot.pack(side="left", padx=(4, 0))

        # Refresh quota btn
        refresh_btn = tk.Label(self._bar, text="↻", bg=C["surface"], fg=C["text_dim"],
                                font=(FONT_FAMILY, 12), cursor="hand2")
        refresh_btn.pack(side="left", padx=6)
        refresh_btn.bind("<Button-1>", lambda e: self._async_load_quota())

    # ─────────────────────────────────────────────────────────────────── #
    # FILE PANEL
    # ─────────────────────────────────────────────────────────────────── #

    def _build_file_panel(self):
        pnl = tk.Frame(self, bg=C["bg"], padx=24, pady=14)
        pnl.pack(fill="x")

        tk.Label(pnl, text="FILES", bg=C["bg"], fg=C["text_dim"],
                 font=(FONT_FAMILY, 8, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        # Input file
        tk.Label(pnl, text="Input Script", bg=C["bg"], fg=C["text_dim"],
                 font=(FONT_FAMILY, 9), width=12, anchor="w").grid(row=1, column=0, sticky="w", pady=4)

        self._input_var = tk.StringVar()
        input_entry = tk.Entry(pnl, textvariable=self._input_var,
                               bg=C["input_bg"], fg=C["text"],
                               insertbackground=C["text"], relief="flat",
                               font=(FONT_FAMILY, 10), bd=0,
                               highlightthickness=1,
                               highlightbackground=C["input_border"],
                               highlightcolor=C["accent"])
        input_entry.grid(row=1, column=1, sticky="ew", padx=(8, 8), ipady=6, ipadx=6)
        input_entry.bind("<FocusIn>", lambda e: input_entry.config(highlightbackground=C["accent"]))
        input_entry.bind("<FocusOut>", lambda e: input_entry.config(highlightbackground=C["input_border"]))
        input_entry.bind("<KeyRelease>", lambda e: self._on_input_changed())

        browse_in = _btn(pnl, "Browse", self._browse_input,
                         bg=C["surface2"], hover_bg=C["border"],
                         pad_x=12, pad_y=6, font_size=9)
        browse_in.grid(row=1, column=2)

        # Output file
        tk.Label(pnl, text="Output File", bg=C["bg"], fg=C["text_dim"],
                 font=(FONT_FAMILY, 9), width=12, anchor="w").grid(row=2, column=0, sticky="w", pady=4)

        self._output_var = tk.StringVar()
        output_entry = tk.Entry(pnl, textvariable=self._output_var,
                                bg=C["input_bg"], fg=C["text"],
                                insertbackground=C["text"], relief="flat",
                                font=(FONT_FAMILY, 10), bd=0,
                                highlightthickness=1,
                                highlightbackground=C["input_border"],
                                highlightcolor=C["accent"])
        output_entry.grid(row=2, column=1, sticky="ew", padx=(8, 8), ipady=6, ipadx=6)
        output_entry.bind("<FocusIn>", lambda e: output_entry.config(highlightbackground=C["accent"]))
        output_entry.bind("<FocusOut>", lambda e: output_entry.config(highlightbackground=C["input_border"]))

        browse_out = _btn(pnl, "Browse", self._browse_output,
                          bg=C["surface2"], hover_bg=C["border"],
                          pad_x=12, pad_y=6, font_size=9)
        browse_out.grid(row=2, column=2)

        pnl.columnconfigure(1, weight=1)

        # Resume badge
        self._resume_frame = tk.Frame(pnl, bg=C["bg"])
        self._resume_frame.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self._resume_badge = tk.Label(self._resume_frame, text="",
                                       bg=C["bg"], fg=C["resume"],
                                       font=(FONT_FAMILY, 8))
        self._resume_badge.pack(anchor="w")

        # Start / Stop buttons
        btn_row = tk.Frame(pnl, bg=C["bg"])
        btn_row.grid(row=4, column=0, columnspan=3, sticky="w", pady=(14, 0))

        self._start_btn = _btn(btn_row, "▶  Start Generation", self._start_generation,
                                bg=C["btn_bg"], hover_bg=C["btn_hover"],
                                pad_x=24, pad_y=10, font_size=11)
        self._start_btn.pack(side="left")

        self._stop_btn = _btn(btn_row, "⏹  Stop", self._stop_generation,
                               bg=C["btn_stop_bg"], hover_bg=C["btn_stop_h"],
                               pad_x=20, pad_y=10, font_size=11)
        self._stop_btn.pack(side="left", padx=(10, 0))
        self._stop_btn.pack_forget()  # hidden until running

    # ─────────────────────────────────────────────────────────────────── #
    # PROGRESS PANEL
    # ─────────────────────────────────────────────────────────────────── #

    def _build_progress_panel(self):
        pnl = tk.Frame(self, bg=C["bg"], padx=24, pady=14)
        pnl.pack(fill="x")

        hdr = tk.Frame(pnl, bg=C["bg"])
        hdr.pack(fill="x")

        tk.Label(hdr, text="PROGRESS", bg=C["bg"], fg=C["text_dim"],
                 font=(FONT_FAMILY, 8, "bold")).pack(side="left")

        self._elapsed_label = tk.Label(hdr, text="", bg=C["bg"], fg=C["text_dim"],
                                        font=(FONT_FAMILY, 8))
        self._elapsed_label.pack(side="right")

        self._batch_label = tk.Label(hdr, text="Waiting to start…", bg=C["bg"],
                                      fg=C["text_muted"], font=(FONT_FAMILY, 8))
        self._batch_label.pack(side="right", padx=(0, 16))

        # Custom canvas progress bar
        bar_frame = tk.Frame(pnl, bg=C["progress_bg"], height=12)
        bar_frame.pack(fill="x", pady=(8, 4))
        bar_frame.pack_propagate(False)

        self._progress_canvas = tk.Canvas(bar_frame, bg=C["progress_bg"],
                                           height=12, bd=0, highlightthickness=0)
        self._progress_canvas.pack(fill="x", expand=True)
        self._progress_canvas.bind("<Configure>", self._redraw_progress)

        self._progress_pct = 0.0

        # Scenes counter
        self._scenes_label = tk.Label(pnl, text="0 / 0 scenes", bg=C["bg"],
                                       fg=C["text_muted"], font=(FONT_FAMILY, 8))
        self._scenes_label.pack(anchor="e")

    def _redraw_progress(self, event=None):
        c = self._progress_canvas
        w = c.winfo_width()
        h = c.winfo_height() or 12
        c.delete("all")
        # Background
        c.create_rectangle(0, 0, w, h, fill=C["progress_bg"], outline="")
        # Fill
        fill_w = int(w * self._progress_pct)
        if fill_w > 0:
            # Glow effect: slightly lighter strip at top
            c.create_rectangle(0, 0, fill_w, h, fill=C["progress_fg"], outline="")
            c.create_rectangle(0, 0, fill_w, max(3, h // 4),
                               fill=C["accent_glow"], outline="")
        # Text inside bar
        if w > 60:
            pct_text = f"{int(self._progress_pct * 100)}%"
            c.create_text(w // 2, h // 2, text=pct_text,
                          fill=C["text"] if fill_w > w // 2 else C["text_dim"],
                          font=(FONT_FAMILY, 7, "bold"))

    def _set_progress(self, pct: float, batch_str: str = "", scenes_str: str = ""):
        self._progress_pct = max(0.0, min(1.0, pct))
        self._redraw_progress()
        if batch_str:
            self._batch_label.config(text=batch_str)
        if scenes_str:
            self._scenes_label.config(text=scenes_str)

    # ─────────────────────────────────────────────────────────────────── #
    # LOG PANEL
    # ─────────────────────────────────────────────────────────────────── #

    def _build_log_panel(self):
        pnl = tk.Frame(self, bg=C["bg"], padx=24, pady=8)
        pnl.pack(fill="both", expand=True)

        hdr = tk.Frame(pnl, bg=C["bg"])
        hdr.pack(fill="x", pady=(0, 6))
        tk.Label(hdr, text="STATUS LOG", bg=C["bg"], fg=C["text_dim"],
                 font=(FONT_FAMILY, 8, "bold")).pack(side="left")
        clear_btn = tk.Label(hdr, text="Clear", bg=C["bg"], fg=C["text_muted"],
                              font=(FONT_FAMILY, 8), cursor="hand2")
        clear_btn.pack(side="right")
        clear_btn.bind("<Button-1>", lambda e: self._clear_log())

        # Text widget with scrollbar
        log_frame = tk.Frame(pnl, bg=C["border"], padx=1, pady=1)
        log_frame.pack(fill="both", expand=True)

        inner = tk.Frame(log_frame, bg=C["surface"])
        inner.pack(fill="both", expand=True)

        self._log_text = tk.Text(
            inner, bg=C["surface"], fg=C["text"],
            font=(FONT_MONO, 9), wrap="word",
            state="disabled", relief="flat",
            bd=0, padx=12, pady=8, cursor="arrow",
            insertbackground=C["text"],
            selectbackground=C["accent_dim"],
            spacing3=2,
        )
        self._log_text.pack(side="left", fill="both", expand=True)

        # Configure color tags
        for level, color in LEVEL_COLORS.items():
            self._log_text.tag_configure(level.value, foreground=color)
        self._log_text.tag_configure("timestamp", foreground=C["text_muted"])
        self._log_text.tag_configure("prefix", foreground=C["text_dim"])

        scrollbar = tk.Scrollbar(inner, bg=C["surface"], troughcolor=C["surface2"],
                                  activebackground=C["accent_dim"], relief="flat",
                                  command=self._log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self._log_text.config(yscrollcommand=scrollbar.set)

    def _append_log(self, level: LogLevel, message: str, timestamp: str = ""):
        self._log_text.config(state="normal")
        ts = timestamp or time.strftime("%H:%M:%S")
        prefix = LEVEL_PREFIXES.get(level, "·")

        self._log_text.insert("end", f"{ts} ", "timestamp")
        self._log_text.insert("end", f"{prefix} ", level.value)
        self._log_text.insert("end", f"{message}\n", level.value)
        self._log_text.config(state="disabled")
        self._log_text.see("end")

    def _clear_log(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    # ─────────────────────────────────────────────────────────────────── #
    # FOOTER
    # ─────────────────────────────────────────────────────────────────── #

    def _build_footer(self):
        foot = tk.Frame(self, bg=C["surface"], pady=10, padx=24)
        foot.pack(fill="x", side="bottom")

        self._status_label = tk.Label(foot, text="Ready", bg=C["surface"],
                                       fg=C["text_dim"], font=(FONT_FAMILY, 9))
        self._status_label.pack(side="left")

        self._open_btn = _btn(foot, "📄  Open Output", self._open_output,
                               bg=C["surface2"], hover_bg=C["border"],
                               pad_x=14, pad_y=6, font_size=9)
        self._open_btn.pack(side="right")
        self._open_btn.pack_forget()

    # ─────────────────────────────────────────────────────────────────── #
    # ACTIONS
    # ─────────────────────────────────────────────────────────────────── #

    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="Select Script File",
            filetypes=[("Script files", "*.docx *.txt *.doc"), ("All files", "*.*")],
        )
        if path:
            self._input_var.set(path)
            # Auto-set output if blank
            if not self._output_var.get():
                p = Path(path)
                self._output_var.set(str(p.parent / f"{p.stem}_prompts.docx"))
            self._on_input_changed()

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save Output As",
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx"), ("All files", "*.*")],
        )
        if path:
            self._output_var.set(path)

    def _on_input_changed(self):
        """Check if a cached job exists for the selected input file."""
        input_path = self._input_var.get().strip()
        if not input_path:
            self._resume_badge.config(text="")
            return

        p = Path(input_path)
        if not p.exists():
            self._resume_badge.config(text="")
            return

        def check_cache():
            try:
                from prompt_generator.queue import BatchQueue
                from prompt_generator.config import PromptGeneratorConfig
                cfg_path = _REPO_ROOT / "config" / "prompt_generator_config.json"
                cfg = PromptGeneratorConfig.load(cfg_path, base_dir=_REPO_ROOT)
                from prompt_generator.providers.antigravity_cli import AntigravityCLIProvider
                prov = AntigravityCLIProvider(cfg)
                bq = BatchQueue(cfg, prov, cache_dir=_REPO_ROOT / ".prompt_gen_cache")
                job_id = bq.find_resumable_job(p)
                if job_id:
                    job = bq.restore_job_from_cache(job_id)
                    if job:
                        done = job.completed_scenes
                        total = job.total_scenes
                        msg = f"↩  Resume available: {done}/{total} scenes already done (job: {job_id})"
                        self.after(0, lambda: self._resume_badge.config(text=msg, fg=C["resume"]))
                        return
            except Exception:
                pass
            self.after(0, lambda: self._resume_badge.config(text=""))

        threading.Thread(target=check_cache, daemon=True).start()

    def _start_generation(self):
        input_str = self._input_var.get().strip()
        output_str = self._output_var.get().strip()

        if not input_str:
            messagebox.showwarning("Input Required", "Please select an input script file.")
            return
        if not Path(input_str).exists():
            messagebox.showerror("File Not Found", f"Input file not found:\n{input_str}")
            return
        if not output_str:
            messagebox.showwarning("Output Required", "Please specify an output file path.")
            return

        input_path = Path(input_str)
        output_path = Path(output_str)
        self._output_path = output_path

        # Reset UI
        self._clear_log()
        self._set_progress(0, "Starting…", "0 / ? scenes")
        self._status_label.config(text="Running…", fg=C["warn"])
        self._start_btn.pack_forget()
        self._stop_btn.pack(side="left")
        self._open_btn.pack_forget()

        # Start timer
        self._start_time = time.time()
        self._update_timer()

        # Start worker
        self._worker = GenerationWorker(input_path, output_path, _REPO_ROOT)
        self._worker.start()

        # Start polling
        self.after(200, self._poll_worker)

    def _stop_generation(self):
        if self._worker and self._worker.is_running:
            self._worker.cancel()
            self._append_log(LogLevel.WARN, "Stop requested — waiting for current batch to finish…")
            self._status_label.config(text="Stopping…")

    def _open_output(self):
        if self._output_path and self._output_path.exists():
            os.startfile(str(self._output_path))

    # ─────────────────────────────────────────────────────────────────── #
    # WORKER POLLING
    # ─────────────────────────────────────────────────────────────────── #

    def _poll_worker(self):
        if not self._worker:
            return

        while not self._worker.event_queue.empty():
            try:
                event = self._worker.event_queue.get_nowait()
            except Exception:
                break

            if event.type == EventType.LOG:
                p = event.payload
                self._append_log(p.level, p.message, p.timestamp)

            elif event.type == EventType.PROGRESS:
                p = event.payload
                pct = p.scenes_done / p.total_scenes if p.total_scenes > 0 else 0
                batch_str = (f"Batch {p.batch_index} / {p.total_batches}"
                             if p.batch_index > 0 else "Starting…")
                scenes_str = f"{p.scenes_done:,} / {p.total_scenes:,} scenes"
                self._set_progress(pct, batch_str, scenes_str)

            elif event.type == EventType.STATUS:
                status = event.payload
                self._status_label.config(text=status.replace("_", " ").title())

            elif event.type == EventType.DONE:
                self._on_generation_done(event.payload)
                return

            elif event.type == EventType.ERROR:
                self._on_generation_error(event.payload)
                return

        # Continue polling while running
        if self._worker.is_running:
            self.after(200, self._poll_worker)
        else:
            self._on_generation_ended()

    def _on_generation_done(self, output_path: str):
        if self._timer_job:
            self.after_cancel(self._timer_job)

        self._set_progress(1.0, f"Complete ✓", "All scenes generated")
        self._status_label.config(text="✓ Complete", fg=C["ok"])
        self._stop_btn.pack_forget()
        self._start_btn.pack(side="left")

        self._output_path = Path(output_path)
        self._open_btn.pack(side="right")

        elapsed = int(time.time() - self._start_time) if self._start_time else 0
        m, s = divmod(elapsed, 60)
        self._elapsed_label.config(text=f"Total time: {m:02d}:{s:02d}")

    def _on_generation_error(self, error: str):
        if self._timer_job:
            self.after_cancel(self._timer_job)

        self._status_label.config(text="✗ Failed", fg=C["error"])
        self._stop_btn.pack_forget()
        self._start_btn.pack(side="left")
        self._append_log(LogLevel.ERROR, f"Halted: {error}")

    def _on_generation_ended(self):
        """Called when worker thread finished (for any reason)."""
        if self._timer_job:
            self.after_cancel(self._timer_job)
        self._stop_btn.pack_forget()
        self._start_btn.pack(side="left")

    # ─────────────────────────────────────────────────────────────────── #
    # TIMER
    # ─────────────────────────────────────────────────────────────────── #

    def _update_timer(self):
        if self._start_time and self._worker and self._worker.is_running:
            elapsed = int(time.time() - self._start_time)
            m, s = divmod(elapsed, 60)
            self._elapsed_label.config(text=f"Elapsed: {m:02d}:{s:02d}")
            self._timer_job = self.after(1000, self._update_timer)

    # ─────────────────────────────────────────────────────────────────── #
    # ACCOUNT INFO
    # ─────────────────────────────────────────────────────────────────── #

    def _async_load_account_info(self):
        def _load():
            try:
                hint = self._account_manager.get_current_email_hint()
                active = self._account_manager.get_active_account()
                label = active.label if active else hint
                self.after(0, lambda: self._update_account_display(label))
            except Exception:
                self.after(0, lambda: self._update_account_display("Session Active"))

        threading.Thread(target=_load, daemon=True).start()

    def _update_account_display(self, label: str):
        self._acc_label.config(text=label, fg=C["text"])
        self._acc_dot.config(fg=C["ok"])

    def _on_account_switched(self):
        self._async_load_account_info()
        self._append_log(LogLevel.OK, "Account switched. Verify quota and re-run if needed.")

    def _open_account_switcher(self):
        AccountSwitcherModal(self, self._account_manager, self._on_account_switched)

    # ─────────────────────────────────────────────────────────────────── #
    # QUOTA
    # ─────────────────────────────────────────────────────────────────── #

    def _async_load_quota(self):
        def _fetch():
            info = fetch_quota()
            self.after(0, lambda: self._update_quota_display(info))
            # Re-schedule every 5 minutes
            self._quota_job = self.after(300_000, self._async_load_quota)

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_quota_display(self, info: QuotaInfo):
        self._quota_info = info
        pct = info.overall_gemini_pct()
        if pct is not None:
            label = f"Gemini {pct:.0f}%"
            color = quota_color(pct)
            status = info.status_label()
            self._quota_label.config(text=label, fg=color)
            self._quota_dot.config(fg=color)
        elif info.error:
            self._quota_label.config(text="Error", fg=C["error"])
            self._quota_dot.config(fg=C["error"])
        else:
            self._quota_label.config(text="Unknown", fg=C["text_dim"])


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = PromptGeneratorApp()
    app.mainloop()
