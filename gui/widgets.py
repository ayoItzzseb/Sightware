"""Sightware GUI — shared custom widgets.

Canvas-based, dependency-free: sortable virtualized DataTable, toggle
switch, win-probability bar, pills, stat cards, RR chart, toasts and an
async PNG image cache (tk.PhotoImage reads PNG natively — no PIL needed).
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .theme import (AMBER, BG, BG_RAISED, BLUE, CARD, CARD_HI,
                   GRAD_RULE, LINE, LINE_SOFT, TEAL_DIM,
                   LOSS, ORANGE, RED, RED_SOFT, TEAL, TEXT, TEXT_DIM,
                   TEXT_FAINT, WIN, alpha_hex, mix, multi_stop, rgb, shade)


# ── pills & cards ──────────────────────────────────────────────
class Pill(tk.Label):
    """Small rounded-look status pill (bg-colored label)."""

    def __init__(self, master, text: str = "", *, bg: str = CARD_HI,
                 fg: str = TEXT, font=None, pad=(10, 3)):
        super().__init__(master, text=text, bg=bg, fg=fg, padx=pad[0], pady=pad[1],
                         font=font, bd=0, highlightthickness=0)


class StatCard(tk.Frame):
    def __init__(self, master, title: str, value: str = "—", sub: str = "",
                 value_color: str = TEXT, bg: str = CARD, width: int = 0):
        super().__init__(master, bg=bg, padx=14, pady=10,
                         highlightbackground=LINE, highlightthickness=1)
        self.title_lbl = tk.Label(self, text=title.upper(), bg=bg, fg=TEXT_FAINT,
                                  font=("Segoe UI", 8, "bold"))
        self.value_lbl = tk.Label(self, text=value, bg=bg, fg=value_color,
                                  font=("Segoe UI", 15, "bold"))
        self.sub_lbl = tk.Label(self, text=sub, bg=bg, fg=TEXT_DIM,
                                font=("Segoe UI", 8))
        self.title_lbl.pack(anchor="w")
        self.value_lbl.pack(anchor="w")
        if sub:
            self.sub_lbl.pack(anchor="w")
        if width:
            self.configure(width=width)
            self.pack_propagate(False)

    def set(self, value: str, sub: str | None = None,
            color: str | None = None) -> None:
        self.value_lbl.configure(text=value,
                                 fg=color or self.value_lbl.cget("fg"))
        if sub is not None:
            self.sub_lbl.configure(text=sub)


class Banner(tk.Frame):
    """Notice banner with a colored left edge (info / warn / ok)."""

    LEVELS = {"info": BLUE, "warn": AMBER, "ok": TEAL, "error": RED}

    def __init__(self, master, message: str = "", level: str = "info", bg: str = CARD):
        super().__init__(master, bg=bg)
        self.strip = tk.Label(self, bg=self.LEVELS.get(level, BLUE), width=2)
        self.label = tk.Label(self, text=message, bg=bg, fg=TEXT,
                              font=("Segoe UI", 9), wraplength=1, justify="left")
        self.strip.pack(side="left", fill="y", padx=(0, 8))
        self.label.pack(side="left", fill="x", expand=True, pady=6, padx=(2, 10))
        self._bg = bg
        self.bind("<Configure>", self._wrap)

    def _wrap(self, evt) -> None:
        self.label.configure(wraplength=max(80, evt.width - 40))

    def set(self, message: str, level: str = "info") -> None:
        self.label.configure(text=message)
        self.strip.configure(bg=self.LEVELS.get(level, BLUE))

    def show(self, message: str | None, level: str = "info") -> None:
        if message:
            self.set(message, level)
            self.pack(fill="x", padx=1, pady=(2, 6))
        else:
            self.pack_forget()


# ── toggle switch ──────────────────────────────────────────────
class Switch(tk.Canvas):
    """A real toggle switch drawn on canvas (replaces ttk.Checkbutton)."""

    def __init__(self, master, *, on: bool = False, command=None, width: int = 42):
        super().__init__(master, width=width, height=22, bg=master.cget("bg")
                         if hasattr(master, "cget") else BG,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._on = bool(on)
        self._command = command
        self._sw_w = width
        self._anim: str | None = None
        self._phase = 1.0 if self._on else 0.0
        self.bind("<Button-1>", self._toggle)
        self.bind("<Return>", self._toggle)
        self.configure(takefocus=1)
        self._draw()

    @property
    def on(self) -> bool:
        return self._on

    def set(self, on: bool, *, fire: bool = False) -> None:
        self._on = bool(on)
        self._phase = 1.0 if self._on else 0.0
        self._draw()
        if fire and self._command:
            self._command()

    def _toggle(self, _evt=None) -> None:
        self._on = not self._on
        self._animate()
        if self._command:
            try:
                self._command()
            except Exception:
                pass

    def _animate(self) -> None:
        if self._anim:
            return
        self._slide()

    def _slide(self) -> None:
        try:
            alive = self.winfo_exists()
        except Exception:
            alive = False
        if not alive:
            self._anim = None
            return
        target = 1.0 if self._on else 0.0
        self._phase += (target - self._phase) * 0.35
        if abs(target - self._phase) < 0.02:
            self._phase = target
            self._anim = None
            self._draw()
            return
        self._draw()
        self._anim = self.after(16, self._slide)

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._sw_w, 22
        knob = 16
        t = max(0.0, min(1.0, self._phase))
        track = mix("#2C3B47", TEAL_DIM, t)
        self.create_oval(1, 2, w - 1, h - 2, fill=track, outline=track)
        x = 3 + t * (w - knob - 6)
        self.create_oval(x, 3, x + knob, h - 3, fill="#F5F7FA", outline="")


# ── win-probability / progress bars ────────────────────────────
class WinProbBar(tk.Canvas):
    def __init__(self, master, height: int = 10):
        super().__init__(master, height=height, bg=master.cget("bg"),
                         highlightthickness=0, bd=0)
        self._height = height
        self._pct = 50

    def set(self, pct: int) -> None:
        self._pct = max(0, min(100, int(pct)))
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = max(self.winfo_reqwidth(), self.winfo_width()) or 300
        h = self._height
        # track with a soft gradient, then a teal→red split with a blend seam
        for x in range(w):
            c = multi_stop(["#222E38", "#2B3945"], x / max(1, w - 1))
            self.create_line(x, 0, x, h, fill=c)
        split = w * self._pct / 100
        seam = max(6, w // 14)
        for x in range(w):
            if x < split - seam / 2:
                c = multi_stop(["#2E7D51", WIN], x / max(1, split))
            elif x < split + seam / 2:
                c = "#3E4A52"
            else:
                t = (x - split) / max(1, w - split)
                c = multi_stop([LOSS, "#7A2E36"], min(1.0, t))
            self.create_line(x, 0, x, h, fill=c)


class MiniProgress(tk.Canvas):
    def __init__(self, master, height: int = 6, color: str = RED):
        super().__init__(master, height=height, bg=master.cget("bg"),
                         highlightthickness=0, bd=0)
        self._height = height
        self._color = color
        self._pct = 0

    def set(self, pct: float) -> None:
        self._pct = max(0.0, min(100.0, float(pct)))
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width() or 200
        self.create_rectangle(0, 0, w, self._height, fill="#26333E", width=0)
        if self._pct > 0:
            self.create_rectangle(0, 0, w * self._pct / 100, self._height,
                                  fill=self._color, width=0)


# ── data table ─────────────────────────────────────────────────
class Column:
    __slots__ = ("key", "label", "width", "anchor", "sortable", "stretch", "minw")

    def __init__(self, key: str, label: str, width: int, anchor: str = "w",
                 sortable: bool = True, stretch: bool = False, minw: int = 0):
        self.key, self.label, self.width = key, label, width
        self.anchor, self.sortable, self.stretch = anchor, sortable, stretch
        self.minw = minw or width


class DataTable(tk.Canvas):
    """High-performance canvas table: virtualized rows, sortable headers,
    per-cell colors, small icons, hover, row-click callbacks."""

    PAD_X = 8
    ROW_H = 30
    HEAD_H = 30

    def __init__(self, master, columns: list[Column], *, height: int = 200,
                 zebra: bool = True, on_row_click=None, bg: str = CARD,
                 head_bg: str = BG_RAISED, row_h: int = 30, font=None,
                 small_font=None, auto_height: bool = False,
                 section_h: int = 0):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0)
        self.columns = columns
        self._rows: list[dict] = []
        self._sort_key: str | None = None
        self._sort_dir = -1
        self._hover_idx = -1
        self._offsets: list[int] = []
        self._total_w = 0
        self._zebra = zebra
        self._on_row_click = on_row_click
        self._bg, self._head_bg = bg, head_bg
        self._row_h, self._head_h = row_h, row_h if row_h < 34 else 32
        self._font = font or ("Segoe UI", 9)
        self._small = small_font or ("Segoe UI", 8)
        self._auto_height = auto_height
        self._section_h = section_h or self._row_h
        self._heights: list[int] = []
        self._images: dict[int, dict[str, tk.PhotoImage]] = {}
        self._vbar: ttk.Scrollbar | None = None
        self._yview_first = 0.0
        self.configure(yscrollincrement=self._row_h)
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", self._on_wheel)   # linux
        self.bind("<Button-5>", self._on_wheel)
        self.bind("<Key-Up>", lambda e: self.yview_scroll(-1, "units"))
        self.bind("<Key-Down>", lambda e: self.yview_scroll(1, "units"))
        self.configure(height=height)

    # public API ────────────────────────────────────────────────
    def set_rows(self, rows: list[dict], *, keep_sort: bool = True) -> None:
        self._rows = list(rows)
        self._heights = [self._section_h if r.get("section") else self._row_h
                         for r in self._rows]
        if self._auto_height:
            heights = self._heights[:12]
            self.configure(height=self._head_h + sum(heights)
                           + (self._row_h if len(self._rows) > 12 else 0))
        if not keep_sort or self._sort_key is None:
            if self._rows:
                self._sort_key = None
        self._sort()
        self._update_scroll()
        self.redraw()

    def rows(self) -> list[dict]:
        return self._rows

    def clear(self) -> None:
        self.set_rows([])

    def set_sort(self, key: str | None, direction: int = -1) -> None:
        self._sort_key, self._sort_dir = key, direction
        self._sort()
        self._update_scroll()
        self.redraw()

    def attach_scrollbar(self, bar: ttk.Scrollbar) -> None:
        self._vbar = bar
        bar.configure(command=self.yview)
        self.configure(yscrollcommand=bar.set)

    # internals ────────────────────────────────────────────────
    def _sort(self) -> None:
        if not self._sort_key:
            return
        col = next((c for c in self.columns if c.key == self._sort_key), None)
        if col is None or not col.sortable:
            return

        def val(row):
            cells = row.get("cells", {})
            raw = row.get("sort", {}).get(col.key, cells.get(col.key))
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                return (0, raw)
            if raw is None or raw == "" or raw == "—":
                return (1, 0)
            s = str(raw)
            try:
                return (0, float(s.rstrip("%").rstrip("x")))
            except ValueError:
                return (2, s.lower())

        self._rows.sort(key=val,
                        reverse=(self._sort_dir < 0))

    def _update_scroll(self) -> None:
        total_h = self._head_h + sum(self._heights)
        self.configure(scrollregion=(0, 0, max(self._total_w, 1), total_h))

    def _layout(self) -> None:
        w = self.winfo_width() or 800
        fixed = sum(c.width for c in self.columns if not c.stretch)
        stretch = [c for c in self.columns if c.stretch]
        stretch_base = sum(c.width for c in stretch)
        extra = max(0, w - fixed - stretch_base - 2) // len(stretch) \
            if stretch else 0
        self._offsets = []
        x = 1
        for c in self.columns:
            self._offsets.append(x)
            cw = max(c.minw, c.width + (extra if c.stretch else 0))
            x += cw
        self._total_w = x + 1
        self._update_scroll()

    def _col_w(self, i: int) -> int:
        if i + 1 < len(self.columns):
            return self._offsets[i + 1] - self._offsets[i]
        return max(self._total_w, self.winfo_width()) - self._offsets[i]

    def redraw(self) -> None:
        self.delete("all")
        self._images.clear()
        if not self.winfo_width():
            return
        self._layout()
        w = max(self._total_w, self.winfo_width())
        # header
        self.create_rectangle(0, 0, w, self._head_h, fill=self._head_bg, width=0)
        for i, col in enumerate(self.columns):
            x = self._offsets[i]
            cw = self._col_w(i)
            ax = {"w": x + self.PAD_X, "center": x + cw // 2,
                  "e": x + cw - self.PAD_X}[col.anchor]
            label = col.label
            if self._sort_key == col.key:
                label = ("▼ " if self._sort_dir < 0 else "▲ ") + label
            self.create_text(ax, self._head_h // 2, text=label, fill=TEXT_DIM,
                             font=("Segoe UI", 8, "bold"), anchor={
                                 "w": "w", "center": "center", "e": "e"}[col.anchor])
            if col.sortable:
                self.create_rectangle(x, 0, x + cw, self._head_h,
                                      fill="", outline="", tags=("sort", col.key))
            if i:
                self.create_line(x, 4, x, self._head_h - 4, fill=LINE_SOFT)
        # rows (virtualized)
        y = self._head_h
        top = self.canvasy(0)
        bottom = top + self.winfo_height() + self._row_h
        for idx, rh in enumerate(self._heights):
            y_next = y + rh
            if y_next >= top and y <= bottom:
                self._draw_row(idx, y)
            y = y_next

    def _draw_row(self, idx: int, y: int) -> None:
        row = self._rows[idx]

        # ── section header row (e.g. "// YOUR TEAM") ──────────
        if row.get("section"):
            w = max(self._total_w, self.winfo_width())
            bg = row.get("bg") or mix(self._bg, "#FFFFFF", 0.045)
            self.create_rectangle(0, y, w, y + self._row_h, fill=bg, width=0)
            self.create_text(self.PAD_X + 2, y + self._row_h // 2,
                             text=row["section"], anchor="w",
                             fill=row.get("section_color", TEAL),
                             font=("Segoe UI", 8, "bold"))
            return

        bg = row.get("bg") or (mix(self._bg, "#FFFFFF", 0.03)
                               if (idx % 2 and self._zebra) else self._bg)
        if idx == self._hover_idx and not row.get("bg"):
            bg = row.get("hover_bg", mix(self._bg, "#FFFFFF", 0.07))
        w = max(self._total_w, self.winfo_width())
        self.create_rectangle(0, y, w, y + self._row_h, fill=bg, width=0,
                              tags=("row", str(idx)))
        if row.get("accent"):
            self.create_rectangle(0, y + 1, 3, y + self._row_h - 1,
                                  fill=row["accent"], width=0)
        row_imgs: dict[str, tk.PhotoImage] = {}
        if idx in self._images:
            row_imgs = self._images[idx]
        icons = row.get("icons", {})
        for i, col in enumerate(self.columns):
            x = self._offsets[i]
            cw = self._col_w(i)
            cells = row.get("cells", {})
            cell = cells.get(col.key)
            color = (row.get("colors", {}) or {}).get(col.key, TEXT)
            font = (row.get("fonts", {}) or {}).get(col.key, self._font)
            img = row_imgs.get(col.key) or icons.get(col.key)
            if img is not None and not hasattr(img, "width"):
                img = None  # a URL string still waiting on the image cache
            pad = self.PAD_X
            if img:
                pad += img.width() + 6
            ax = {"w": x + pad, "center": x + max(pad, cw // 2),
                  "e": x + cw - self.PAD_X}[col.anchor]
            anchor = {"w": "w", "center": "center", "e": "e"}[col.anchor]
            if col.anchor == "center" and img:
                ax = x + (cw + img.width()) // 2 + 3
                anchor = "w"
            if img:
                iy = y + self._row_h // 2
                self.create_image(x + self.PAD_X, iy, image=img, anchor="w")

            # ── two-line cell: {"main": str, "sub": str, "sub_color"?} ──
            if isinstance(cell, dict) and "main" in cell:
                cy = y + self._row_h // 2
                self.create_text(ax, cy - 7, text=str(cell.get("main", "—")),
                                 fill=color, font=font, anchor=anchor,
                                 tags=("row", str(idx), "cell", f"{col.key}"))
                if cell.get("sub"):
                    self.create_text(ax, cy + 9, text=str(cell["sub"]),
                                     fill=cell.get("sub_color", TEXT_FAINT),
                                     font=("Segoe UI", 7), anchor=anchor,
                                     tags=("row", str(idx), "cell",
                                           f"{col.key}"))
                continue

            # ── multi-color segments: [(text, color), …] ──────────
            if isinstance(cell, list):
                seg_font = tkfont.Font(font=font) if hasattr(tkfont, "Font")                     else None
                sx = ax if anchor == "w" else None
                if sx is None:
                    total = sum(self._text_width(t, font) for t, _c in cell)
                    sx = (x + cw // 2 - total // 2) if col.anchor == "center"                         else (x + cw - self.PAD_X - total)
                for t, c in cell:
                    self.create_text(sx, y + self._row_h // 2, text=t,
                                     fill=c, font=font, anchor="w",
                                     tags=("row", str(idx), "cell",
                                           f"{col.key}"))
                    sx += self._text_width(t, font)
                continue

            text = "—" if cell is None else str(cell)
            if text:
                self.create_text(ax, y + self._row_h // 2, text=text,
                                 fill=color, font=font, anchor=anchor,
                                 tags=("row", str(idx), "cell", f"{col.key}"))

        # ── party underline under the NAME cell ─────────────────
        if row.get("underline_color"):
            name_i = next((i for i, c in enumerate(self.columns)
                           if c.key == "name"), 2)
            ux = self._offsets[name_i] + self.PAD_X
            self.create_line(ux, y + self._row_h - 5, ux + 78,
                             y + self._row_h - 5,
                             fill=row["underline_color"], width=2)

    def _text_width(self, text: str, font) -> int:
        try:
            key = ("Segoe UI", font[1] if isinstance(font, tuple) else 9)
            f = tkfont.Font(family=key[0], size=key[1],
                            weight=font[2] if isinstance(font, tuple)
                            and len(font) > 2 else "normal")
            return f.measure(str(text))
        except Exception:
            return len(str(text)) * 7

    def set_cell_image(self, row_idx: int, key: str, photo: tk.PhotoImage) -> None:
        """Called by ImageCache when an icon for a row arrives."""
        if 0 <= row_idx < len(self._rows):
            self._images.setdefault(row_idx, {})[key] = photo
            y = self._head_h + sum(self._heights[:row_idx])
            self._draw_row(row_idx, y)

    def clear_images(self) -> None:
        self._images.clear()
        self.redraw()

    # events ────────────────────────────────────────────────────
    def _row_at(self, y: int) -> int:
        ry = self.canvasy(y) - self._head_h
        if ry < 0:
            return -1
        acc = 0
        for idx, rh in enumerate(self._heights):
            acc += rh
            if ry < acc:
                return idx
        return -1

    def _on_motion(self, evt) -> None:
        idx = self._row_at(evt.y)
        if idx >= len(self._rows):
            idx = -1
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.redraw()

    def _on_leave(self, _evt) -> None:
        if self._hover_idx != -1:
            self._hover_idx = -1
            self.redraw()

    def _on_click(self, evt) -> None:
        if self.canvasy(evt.y) < self._head_h:
            # header hit: find column → sort toggle
            for i, col in enumerate(self.columns):
                x = self._offsets[i]
                if x <= evt.x <= x + self._col_w(i):
                    if not col.sortable:
                        return
                    if self._sort_key == col.key:
                        self._sort_dir *= -1
                    else:
                        self._sort_key = col.key
                        self._sort_dir = 1 if col.key == "deaths" else -1
                    self._sort()
                    self._update_scroll()
                    self.redraw()
                    return
        idx = self._row_at(evt.y)
        self._sel = idx
        if 0 <= idx < len(self._rows) and self._on_row_click:
            self._on_row_click(self._rows[idx].get("data", self._rows[idx]))

    def _content_overflows(self) -> bool:
        region = self.cget("scrollregion")
        try:
            total = float(str(region).split()[-1]) if region else 0.0
        except (ValueError, IndexError):
            total = 0.0
        return total > self.winfo_height() + 2

    def _on_wheel(self, evt) -> None:
        if not self._content_overflows():
            return  # everything fits — don't hijack the wheel
        step = -1 if getattr(evt, "delta", 0) > 0 or evt.num == 4 else 1
        self.yview_scroll(step * 3, "units")


# ── RR / rank history chart ────────────────────────────────────
class RRChart(tk.Canvas):
    """Cumulative-RR line chart with win/loss markers and hover tooltip."""

    HEIGHT = 180

    def __init__(self, master, bg: str = CARD):
        super().__init__(master, bg=bg, height=self.HEIGHT, highlightthickness=1,
                         highlightbackground=LINE, bd=0)
        self._points: list[dict] = []
        self._hover: tuple[int, int, str] | None = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: (setattr(self, "_hover", None),
                                        self.redraw()))

    def set_points(self, points: list[dict]) -> None:
        self._points = list(points)
        self.redraw()

    def _series(self) -> list[tuple[float, dict]]:
        out = []
        run = 0.0
        for p in self._points:
            if p.get("result") not in ("Victory", "Defeat"):
                continue
            rr = p.get("rr")
            if isinstance(rr, (int, float)):
                y = float(rr)
            else:
                d = p.get("delta")
                run += float(d) if isinstance(d, (int, float)) else 0.0
                y = run
            out.append((y, p))
        return out

    def redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width() or 600
        h = self.HEIGHT
        pad_l, pad_r, pad_t, pad_b = 46, 12, 14, 20
        series = self._series()
        if len(series) < 2:
            self.create_text(w // 2, h // 2,
                             text="Not enough ranked matches yet — play a few games",
                             fill=TEXT_FAINT, font=("Segoe UI", 9))
            return
        ys = [y for y, _ in series]
        lo, hi = min(ys), max(ys)
        if hi - lo < 20:
            mid = (hi + lo) / 2
            lo, hi = mid - 15, mid + 15
        span = hi - lo
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        def px(i):
            return pad_l + plot_w * i / max(1, len(series) - 1)

        def py(v):
            return pad_t + plot_h * (1 - (v - lo) / span)

        # grid + y labels
        for i in range(3):
            v = lo + span * i / 2
            gy = py(v)
            self.create_line(pad_l, gy, w - pad_r, gy, fill=LINE_SOFT)
            self.create_text(pad_l - 6, gy, text=str(round(v)), fill=TEXT_FAINT,
                             font=("Segoe UI", 7), anchor="e")
        # gradient area fill under the line (layered strips)
        band = 26
        for k in range(band, 0, -1):
            alpha = (1 - k / band) * 0.30
            fill = mix(self.cget("bg"), RED, alpha)
            strip = [pad_l, py(ys[0]) + k]
            for i in range(len(series)):
                strip.extend((px(i), py(ys[i]) + k))
            strip.extend([w - pad_r, py(ys[-1]) + k,
                          w - pad_r, pad_t + plot_h, pad_l, pad_t + plot_h])
            self.create_polygon(*strip, fill=fill, width=0,
                                smooth=True, outline="")
        # line
        coords = []
        for i, (v, _p) in enumerate(series):
            coords.extend((px(i), py(v)))
        self.create_line(*coords, fill=RED, width=2, smooth=True)
        # glowing head marker on the newest point
        hx, hy = px(len(series) - 1), py(ys[-1])
        for r, c in ((8, alpha_hex(RED, 70)), (5, RED)):
            self.create_oval(hx - r, hy - r, hx + r, hy + r, fill=c, outline="")
        # markers
        for i, (v, p) in enumerate(series):
            color = WIN if p.get("result") == "Victory" else LOSS
            r = 3
            cx, cy = px(i), py(v)
            if self._hover and self._hover[0] == i:
                r = 5
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color,
                             outline="")
        # zero line for cumulative charts
        if lo < 0 < hi:
            self.create_line(pad_l, py(0), w - pad_r, py(0),
                             fill=LINE, dash=(3, 3))
        # hover tooltip
        if self._hover:
            i, cx, cy = self._hover
            p = series[i][1]
            delta = p.get("delta")
            txt = f"{p.get('agent') or ''} {p.get('agent2') or ''}".strip()
            line1 = f"{p.get('result', '')}  {('+' if (delta or 0) > 0 else '')}{delta if delta is not None else ''} RR"
            line2 = f"{p.get('map', '')} · {p.get('mode', '')}"
            lines = [line1, line2]
            tw = 0  # noqa
            width = max(len(l) for l in lines) * 6 + 16
            bx = min(max(cx + 10, 4), w - width - 4)
            by = max(cy - 44, 4)
            self.create_rectangle(bx, by, bx + width, by + 36,
                                  fill="#0A121A", outline=LINE)
            self.create_text(bx + 8, by + 10, text=lines[0], anchor="w",
                             fill=TEXT, font=("Segoe UI", 8, "bold"))
            self.create_text(bx + 8, by + 25, text=lines[1], anchor="w",
                             fill=TEXT_DIM, font=("Segoe UI", 8))
            self.create_line(cx, cy, cx, by + 36, fill=LINE_SOFT)

    def _on_motion(self, evt) -> None:
        series = self._series()
        if len(series) < 2:
            return
        w = self.winfo_width() or 600
        pad_l, pad_r = 46, 12
        plot_w = w - pad_l - pad_r
        i = round((evt.x - pad_l) / plot_w * (len(series) - 1))
        if not (0 <= i < len(series)):
            if self._hover:
                self._hover = None
                self.redraw()
            return
        ys = [y for y, _ in series]
        lo, hi = min(ys), max(ys)
        if hi - lo < 20:
            mid = (hi + lo) / 2
            lo, hi = mid - 15, mid + 15
        pad_t, pad_b = 14, 20
        plot_h = self.HEIGHT - pad_t - pad_b
        v = lo + (1 - (evt.y - pad_t) / plot_h) * (hi - lo)
        cx = pad_l + plot_w * i / max(1, len(series) - 1)
        cy = pad_t + plot_h * (1 - (series[i][0] - lo) / (hi - lo))
        self._hover = (i, cx, cy)
        self.redraw()


# ── play-calendar heatmap ──────────────────────────────────────
class CalendarHeatmap(tk.Canvas):
    """GitHub-style W/L calendar built from history's schedule.calendar rows
    ({name: 'YYYY-MM-DD', games, wins, winRate, netRr}).
    Hover shows a summary; clicking a day fires on_click(day)."""

    CELL = 19
    GAP = 4
    PAD_L = 34
    PAD_T = 18

    def __init__(self, master, bg: str = CARD, on_hover=None, height: int = 160,
                 on_click=None):
        super().__init__(master, bg=bg, height=height, highlightthickness=1,
                         highlightbackground=LINE, bd=0)
        self._days: dict[str, dict] = {}
        self._cells: list[tuple[int, int, dict]] = []
        self._on_hover = on_hover
        self._on_click = on_click
        self._hovered: str | None = None
        self._month: str | None = None
        self.configure(cursor="hand2")
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: (self._hover_cb(None),
                                        self._set_hovered(None)))
        self.bind("<Button-1>", self._on_click_day)

    def set_days(self, calendar: list[dict]) -> None:
        self._days = {d.get("name", ""): d for d in calendar or []}
        self.redraw()

    # ── month view ─────────────────────────────────────────────
    def months_available(self) -> list[str]:
        """Sorted 'YYYY-MM' strings that have any recorded games."""
        return sorted({name[:7] for name in self._days})

    def set_month(self, year_month: str | None) -> None:
        """Show a single month ('YYYY-MM') as its own grid."""
        self._month = year_month
        self._hovered = None
        self.redraw()

    def step_month(self, delta: int) -> str | None:
        months = self.months_available()
        if not months:
            return None
        if self._month not in months:
            self.set_month(months[-1])
            return self._month
        i = max(0, min(len(months) - 1, months.index(self._month) + delta))
        self.set_month(months[i])
        return self._month

    def _set_hovered(self, name: str | None) -> None:
        if self._hovered != name:
            self._hovered = name
            self.redraw()

    def _on_click_day(self, evt) -> None:
        for x, y, day in self._cells:
            if x <= evt.x <= x + self.CELL and y <= evt.y <= y + self.CELL:
                if self._on_click and day.get("games"):
                    self._on_click(day)
                return

    def _hover_cb(self, text: str | None) -> None:
        if self._on_hover:
            try:
                self._on_hover(text)
            except Exception:
                pass

    @staticmethod
    def _cell_color(day: dict) -> str:
        games = int(day.get("games") or 0)
        if games <= 0:
            return "#1A2530"
        net = day.get("netRr") or 0
        if net > 0:
            t = min(1.0, 0.25 + net / 60)
            return mix("#1A2530", WIN, t)
        if net < 0:
            t = min(1.0, 0.25 + abs(net) / 60)
            return mix("#1A2530", LOSS, t)
        return mix("#1A2530", TEXT_DIM, 0.3)

    def redraw(self) -> None:
        self.delete("all")
        self._cells = []
        if getattr(self, "_month", None):
            self._redraw_month()
            return
        days = sorted(self._days)
        if not days:
            self.create_text(120, (self.winfo_height() or 130) // 2,
                             text="no rated games recorded yet", fill=TEXT_FAINT,
                             font=("Segoe UI", 8))
            return
        from datetime import date
        w = self.winfo_width() or 600
        h = self.winfo_height() or 130
        step = self.CELL + self.GAP
        cols = max(1, (w - self.PAD_L - 8) // step)
        try:
            d0 = date.fromisoformat(days[0])
            first_wd = d0.weekday()  # Mon=0
        except ValueError:
            first_wd = 0
        # right-align: drop the OLDEST days when the window is too narrow
        total_cols = (first_wd + len(days) - 1) // 7 + 1
        skip = max(0, total_cols - cols) * 7 - first_wd if total_cols > cols else 0
        row_labels = ["M", "T", "W", "T", "F", "S", "S"]
        for r, lab in enumerate(row_labels):
            self.create_text(self.PAD_L - 8, self.PAD_T + r * step + self.CELL // 2,
                             text=lab, fill=TEXT_FAINT, font=("Segoe UI", 7))
        shown = days[skip:] if skip > 0 else days
        base = first_wd + skip if skip > 0 else first_wd
        # month labels: drawn above the first column where the month changes
        prev_month = None
        if skip > 0:
            try:
                prev_month = date.fromisoformat(days[skip - 1]).month
            except ValueError:
                prev_month = None
        months = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
                  "Aug", "Sep", "Oct", "Nov", "Dec")
        for i, name in enumerate(shown):
            slot = base + i
            col, row = divmod(slot, 7)
            x = self.PAD_L + col * step
            y = self.PAD_T + row * step
            if x + self.CELL > w or y + self.CELL > h:
                continue
            day = self._days[name]
            try:
                this_month = date.fromisoformat(name).month
            except ValueError:
                this_month = None
            if row == 0 and this_month and this_month != prev_month:
                self.create_text(x + self.CELL / 2, self.PAD_T - 9,
                                 text=months[this_month], fill=TEXT_DIM,
                                 font=("Segoe UI", 7, "bold"))
            prev_month = this_month
            self.create_rectangle(x, y, x + self.CELL, y + self.CELL,
                                  fill=self._cell_color(day), outline="",
                                  tags=("day", name))
            # day-of-month number, contrast-adjusted
            day_num = name[-2:].lstrip("0")
            r8, g8, b8 = rgb(self._cell_color(day))
            lum = (0.2126 * r8 + 0.7152 * g8 + 0.0722 * b8) / 255
            num_col = "#0B0D12" if lum > 0.55 else "#F5F7FA"
            self.create_text(x + self.CELL / 2, y + self.CELL - 5,
                             text=day_num, fill=num_col,
                             font=("Segoe UI", 7, "bold"))
            if self._hovered and day.get("name") == self._hovered:
                self.create_rectangle(x - 2, y - 2, x + self.CELL + 2,
                                      y + self.CELL + 2,
                                      outline=TEXT, width=1)
            self._cells.append((x, y, day))
        self.configure(scrollregion=(0, 0, w, h))

    def _redraw_month(self) -> None:
        from datetime import date as _date
        import datetime as _dt
        y, m = (int(x) for x in self._month.split("-"))
        first = _date(y, m, 1)
        nxt = _date(y + (m == 12), 1 if m == 12 else m + 1, 1)
        dim = (nxt - first).days
        first_wd = first.weekday()  # Mon=0

        w = self.winfo_width() or 640
        step = self.CELL + self.GAP
        head_y = 6
        for c, lab in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            self.create_text(self.PAD_L + c * step + self.CELL / 2, head_y,
                             text=lab, fill=TEXT_FAINT,
                             font=("Segoe UI", 7, "bold"))
        month_total = 0
        month_net = 0
        for d in range(dim):
            name = f"{y:04d}-{m:02d}-{d + 1:02d}"
            col, row = divmod(first_wd + d, 7)
            x = self.PAD_L + col * step
            yy = head_y + 14 + row * step
            if x + self.CELL > w:
                continue
            day = self._days.get(name) or {"name": name, "games": 0,
                                           "wins": 0, "winRate": None,
                                           "netRr": 0}
            games = int(day.get("games") or 0)
            month_total += games
            month_net += int(day.get("netRr") or 0)
            fill = self._cell_color(day) if games else "#121826"
            self.create_rectangle(x, yy, x + self.CELL, yy + self.CELL,
                                  fill=fill, outline="",
                                  tags=("day", name))
            r8, g8, b8 = rgb(fill)
            lum = (0.2126 * r8 + 0.7152 * g8 + 0.0722 * b8) / 255
            num_col = "#0B0D12" if lum > 0.55 else (
                "#3A4556" if not games else "#F5F7FA")
            self.create_text(x + self.CELL / 2, yy + self.CELL - 5,
                             text=str(d + 1), fill=num_col,
                             font=("Segoe UI", 7, "bold"))
            self._cells.append((x, yy, day))
        self.configure(scrollregion=(0, 0, w, head_y + 14 + 6 * step + 6))
        net_txt = f"{'+' if month_net > 0 else ''}{month_net} RR"
        self.create_text(w - 6, head_y, text=f"{month_total} games · {net_txt}",
                         anchor="e", fill=TEXT_DIM, font=("Segoe UI", 8, "bold"))

    def _on_motion(self, evt) -> None:
        hit = None
        for x, y, day in self._cells:
            if x <= evt.x <= x + self.CELL and y <= evt.y <= y + self.CELL:
                hit = day
                break
        self._set_hovered(hit.get("name") if hit else None)
        if hit is None:
            self._hover_cb(None)
            return
        wr = hit.get("winRate")
        text = (f"{hit.get('name')}  ·  {hit.get('games', 0)} games  ·  "
                f"{hit.get('wins', 0)}W  ·  "
                f"{f'{wr}%' if wr is not None else '—'} WR  ·  "
                f"{'+' if (hit.get('netRr') or 0) > 0 else ''}{hit.get('netRr', 0)} RR")
        self._hover_cb(text)


# ── gradients & canvas helpers ─────────────────────────────────
class GradientFrame(tk.Canvas):
    """Multi-stop linear gradient drawn with 1px lines (drawn once per
    resize — cheap). direction: 'v' (top→bottom) or 'h' (left→right)."""

    def __init__(self, master, colors: list[str], direction: str = "v",
                 height: int = 0, width: int = 0, **kw):
        super().__init__(master, height=height or 3, width=width or 3,
                         highlightthickness=0, bd=0, **kw)
        self._colors = list(colors)
        self._dir = direction
        self.bind("<Configure>", lambda e: self.redraw())
        self.redraw()

    def set_stops(self, colors: list[str], direction: str | None = None) -> None:
        self._colors = list(colors)
        if direction:
            self._dir = direction
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width() or 1
        h = self.winfo_height() or 1
        n = h if self._dir == "v" else w
        for i in range(n):
            c = multi_stop(self._colors, i / max(1, n - 1))
            if self._dir == "v":
                self.create_line(0, i, w, i, fill=c)
            else:
                self.create_line(i, 0, i, h, fill=c)


def AccentRule(parent, colors=None, height: int = 3, pady: str = "0") -> tk.Frame:
    """Thin brand gradient rule (red → magenta → teal) under headers."""
    wrap = tk.Frame(parent, bg=parent.cget("bg") if hasattr(parent, "cget")
                    else BG)
    bar = GradientFrame(wrap, colors or GRAD_RULE, direction="h",
                        height=height)
    bar.pack(fill="x")
    return wrap


def cover_crop(photo, target_w: int, target_h: int):
    """Center-crop + downscale a tk.PhotoImage to cover a target box
    (aspect-fill). Uses tk's copy(-from) for the crop, subsample for
    scaling. Returns None if it can't fit."""
    try:
        w, h = photo.width(), photo.height()
        if w < 8 or h < 8:
            return None
        factor = max(1, round(h / max(1, target_h)))
        while factor > 1 and (w // factor < target_w or h // factor < target_h):
            factor -= 1
        cw = min(w, target_w * factor)
        ch = min(h, target_h * factor)
        cx = (w - cw) // 2
        cy = max(0, min((h - ch) // 2, h - ch))
        # 1:1 crop into a full-size image FIRST, then downscale —
        # copying into a pre-shrunk canvas clips instead of scaling
        out = tk.PhotoImage(width=cw, height=ch)
        out.tk.call(str(out), "copy", str(photo),
                    "-from", cx, cy, cx + cw, cy + ch, "-to", 0, 0)
        if factor > 1:
            out = out.subsample(factor, factor)
        return out
    except Exception:
        return None


# ── toasts ─────────────────────────────────────────────────────
class Toast:
    def __init__(self, root):
        self.root = root
        self._lbl: tk.Label | None = None
        self._job: str | None = None

    def show(self, message: str, ms: int = 3200, *, kind: str = "info") -> None:
        colors = {"info": (CARD_HI, TEXT), "ok": (TEAL_DIM, "#D9FFF3"),
                  "warn": ("#4A3B14", AMBER), "error": ("#3A1B20", RED_SOFT)}
        bg, fg = colors.get(kind, colors["info"])
        if self._lbl and self._lbl.winfo_exists():
            self._lbl.destroy()
        if self._job:
            self.root.after_cancel(self._job)
        self._lbl = tk.Label(self.root, text=message, bg=bg, fg=fg,
                             font=("Segoe UI", 9, "bold"), padx=16, pady=9, bd=0)
        self._lbl.place(relx=0.5, rely=1.0, anchor="s", y=-18)

        def hide():
            if self._lbl and self._lbl.winfo_exists():
                self._lbl.place_forget()
        self._job = self.root.after(ms, hide)


# ── async PNG image cache ──────────────────────────────────────
class ImageCache:
    """Background-downloading PNG cache backed by tk.PhotoImage.

    tk 8.6 renders PNG natively; big art is downscaled with .subsample().
    Disk cache lives under backend/data/artcache. Respects the loadArt
    setting (when off, get() always returns None and nothing downloads).
    """

    MAX_MEM = 350

    def __init__(self, root, cache_dir, load_art_fn, post_fn=None):
        self.root = root
        self.cache_dir = Path(cache_dir)
        # post_fn: thread-safe "run on UI thread" (defaults to root.after)
        self._post = post_fn or (lambda fn: root.after(0, fn))
        self.load_art_enabled = load_art_fn
        self._mem: OrderedDict[str, tk.PhotoImage] = OrderedDict()
        self._inflight: set[str] = set()
        self._subscribers: dict[str, list] = {}
        self._lock = threading.Lock()
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def get(self, url: str | None, *, target: int = 0) -> tk.PhotoImage | None:
        if not url or not self.load_art_enabled():
            return None
        key = f"{url}@{target}"
        with self._lock:
            hit = self._mem.get(key)
            if hit:
                self._mem.move_to_end(key)
                return hit
        # try disk cache on the UI thread (fast, local file)
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".png")
        if path.is_file():
            try:
                photo = self._load_scaled(path, target)
            except Exception:
                photo = None
            if photo is not None:
                self._put(key, photo)
                return photo
            # corrupt cache entry
            try:
                path.unlink()
            except OSError:
                pass
        with self._lock:
            if url in self._inflight:
                return None
            self._inflight.add(url)
        threading.Thread(target=self._download, args=(url, path), daemon=True,
                         name="art-dl").start()
        return None

    def when_ready(self, url: str | None, callback) -> None:
        if not url:
            return
        with self._lock:
            self._subscribers.setdefault(url, []).append(callback)

    def _put(self, key: str, photo: tk.PhotoImage) -> None:
        with self._lock:
            self._mem[key] = photo
            self._mem.move_to_end(key)
            while len(self._mem) > self.MAX_MEM:
                self._mem.popitem(last=False)

    @staticmethod
    def _load_scaled(path: Path, target: int) -> tk.PhotoImage | None:
        photo = tk.PhotoImage(file=str(path))
        if target and photo.width() > target * 1.6:
            factor = max(1, round(photo.width() / target))
            photo = photo.subsample(factor, factor)
        return photo

    def _download(self, url: str, path: Path) -> None:
        try:
            import requests
            resp = requests.get(url, timeout=8,
                                headers={"User-Agent": "sightware-gui/3.0"})
            resp.raise_for_status()
            if not resp.content.startswith(b"\x89PNG"):
                raise ValueError("not a PNG")
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(resp.content)
            tmp.replace(path)
        except Exception:
            with self._lock:
                self._inflight.discard(url)
            return
        with self._lock:
            self._inflight.discard(url)
            subs = self._subscribers.pop(url, [])
        self._post(lambda: self._notify(url, path, subs))

    def _notify(self, url: str, path: Path, subs: list) -> None:
        if not subs:
            return
        try:
            photo = tk.PhotoImage(file=str(path))
        except Exception:
            return
        self._put(f"{url}@0", photo)
        for cb in subs:
            try:
                cb(photo)
            except Exception:
                pass

    def clear_images_all(self) -> None:
        """Drop every cached image (called when the loadArt setting flips)."""
        with self._lock:
            self._mem.clear()
            self._subscribers.clear()


# ── section helpers ────────────────────────────────────────────
def section_title(parent, text: str, bg: str = BG) -> tk.Label:
    return tk.Label(parent, text=text.upper(), bg=bg, fg=TEXT_FAINT,
                    font=("Segoe UI", 8, "bold"))


def hline(parent, bg: str = BG, color: str = LINE_SOFT) -> tk.Frame:
    return tk.Frame(parent, bg=color, height=1)


def card(parent, bg: str = CARD) -> tk.Frame:
    return tk.Frame(parent, bg=bg, highlightbackground=LINE, highlightthickness=1)


def spinner_label(parent, bg: str = CARD, text: str = "Loading…") -> tk.Label:
    return tk.Label(parent, text=text, bg=bg, fg=TEXT_DIM, font=("Segoe UI", 9))


class ScrollFrame(tk.Frame):
    """Vertical scrolling container (canvas + inner frame + dark scrollbar)."""

    def __init__(self, master, bg: str = BG):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # wheel scrolling for the whole subtree
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.inner.bind("<Enter>", lambda e: self._active(True))
        self.inner.bind("<Leave>", lambda e: self._active(False))
        self._bind_wheel_recursive(self.inner)

    def _active(self, on: bool) -> None:
        self._over = on

    def _on_inner_configure(self, _e) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._bind_wheel_recursive(self.inner)

    def _on_canvas_configure(self, e) -> None:
        self.canvas.itemconfigure(self._win, width=e.width)

    def _on_wheel(self, evt) -> None:
        """Scroll when the pointer is inside this ScrollFrame's bounds."""
        try:
            px, py = self.winfo_pointerx(), self.winfo_pointery()
            wx, wy = self.winfo_rootx(), self.winfo_rooty()
            ww, wh = self.winfo_width(), self.winfo_height()
            if not (wx <= px <= wx + ww and wy <= py <= wy + wh):
                return
            delta = getattr(evt, "delta", 0)
            self.canvas.yview_scroll(-3 if delta > 0 else 3, "units")
        except Exception:
            pass

    def _bind_wheel_recursive(self, widget) -> None:
        """Force-bind MouseWheel on every descendant so no child class
        binding can block scrolling."""
        widget.bind("<MouseWheel>", self._on_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child)


class BusyDots:
    """Animates 'Loading…' dots on a label until stopped."""

    def __init__(self, label: tk.Label, prefix: str = "Loading"):
        self.label = label
        self.prefix = prefix
        self._n = 0
        self._job: str | None = None
        self._base_fg = label.cget("fg")
        label.configure(text=self.prefix, fg=TEXT_DIM)

    def tick(self) -> None:
        self._n = (self._n + 1) % 4
        self.label.configure(text=self.prefix + "." * self._n)
        self._job = self.label.after(300, self.tick)

    def start(self) -> None:
        self.stop()
        self.tick()

    def stop(self, text: str | None = None) -> None:
        if self._job:
            self.label.after_cancel(self._job)
            self._job = None
        if text is not None:
            self.label.configure(text=text, fg=self._base_fg)


# ── slider ─────────────────────────────────────────────────────
class SightwareSlider(tk.Canvas):
    """Theme slider with a visible trough, red fill and clear round thumb.

    Drop-in for tk.Scale in this app: get()/set()/configure(state=|from_=|to=|
    command=|resolution=) are supported. Fires `command(value)` while dragging.
    """

    HEIGHT = 30
    TROUGH_H = 6
    THUMB_R = 8

    def __init__(self, master, *, from_=0.0, to=100.0, value=None, resolution=1.0,
                 length=280, command=None, bg=CARD, state="normal", **kw):
        super().__init__(master, width=length, height=self.HEIGHT, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._from = float(from_)
        self._to = float(to)
        if self._to < self._from:
            self._from, self._to = self._to, self._from
        self._res = max(float(resolution), 0.0001)
        self._command = command
        self._state = state
        self._hover = False
        self._dragging = False
        self._job = None
        self._value = self._clamp(float(value) if value is not None else self._from)

        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.redraw()

    # ── public API (tk.Scale compatible subset) ────────────────
    def get(self):
        return self._value

    def set(self, value, fire=False):
        self._value = self._clamp(float(value))
        self.redraw()
        if fire:
            self._fire()

    def configure(self, cnf=None, **kw):
        if cnf is not None:
            kw.update(cnf)
        if "from_" in kw:
            self._from = float(kw.pop("from_"))
        if "to" in kw:
            self._to = float(kw.pop("to"))
        if "resolution" in kw:
            self._res = max(float(kw.pop("resolution")), 0.0001)
        if "command" in kw:
            self._command = kw.pop("command")
        if "state" in kw:
            self._state = kw.pop("state")
        if "value" in kw:
            self.set(kw.pop("value"))
        for key in list(kw):
            if key in ("bg", "background"):
                super().configure(background=kw.pop(key))
        if kw:
            super().configure(**kw)
        self._value = self._clamp(self._value)
        self.redraw()

    config = configure

    def cget(self, key):
        if key == "state":
            return self._state
        if key == "from_":
            return self._from
        if key == "to":
            return self._to
        return super().cget(key)

    def state(self, tags=None):
        return self._state

    # ── internals ──────────────────────────────────────────────
    def _clamp(self, value):
        stepped = round((value - self._from) / self._res) * self._res + self._from
        return max(self._from, min(self._to, stepped))

    def _value_to_x(self, value=None):
        w = max(self.winfo_width(), 1)
        pad = self.THUMB_R + 2
        span = (self._to - self._from) or 1
        v = self._value if value is None else value
        return pad + (w - 2 * pad) * (v - self._from) / span

    def _x_to_value(self, x):
        w = max(self.winfo_width(), 1)
        pad = self.THUMB_R + 2
        span = (self._to - self._from) or 1
        t = (x - pad) / max(w - 2 * pad, 1)
        return self._clamp(self._from + max(0.0, min(1.0, t)) * span)

    def _enabled(self):
        return str(self._state) != "disabled"

    def _fire(self):
        if self._command and self._enabled():
            try:
                self._command(self._value)
            except Exception:
                pass

    def _on_press(self, e):
        if not self._enabled():
            return
        self._dragging = True
        self.set(self._x_to_value(e.x))
        self._fire()

    def _on_motion(self, e):
        if not self._dragging or not self._enabled():
            return
        self.set(self._x_to_value(e.x))
        self._fire()

    def _on_release(self, _e):
        self._dragging = False
        self._fire()

    def _on_enter(self, _e):
        self._hover = True
        self.redraw()

    def _on_leave(self, _e):
        self._hover = False
        self.redraw()

    def redraw(self):
        w = max(self.winfo_width(), 2)
        h = self.HEIGHT
        self.delete("all")
        cy = h // 2
        pad = self.THUMB_R + 2
        enabled = self._enabled()
        x = self._value_to_x()

        # trough
        self._rounded(2, cy - self.TROUGH_H // 2, w - 2, cy + self.TROUGH_H // 2,
                      self.TROUGH_H // 2,
                      fill=BG_RAISED if enabled else shade(BG_RAISED, -0.2),
                      outline=LINE if enabled else LINE_SOFT)
        # filled portion
        if x > pad + 1:
            fill = RED if enabled else shade(CARD_HI, 0.1)
            self._rounded(2, cy - self.TROUGH_H // 2, x, cy + self.TROUGH_H // 2,
                          self.TROUGH_H // 2, fill=fill, outline="")
        # thumb
        r = self.THUMB_R + (1 if (self._hover or self._dragging) and enabled else 0)
        thumb_fill = RED if enabled else CARD_HI
        thumb_outline = "#FFFFFF" if enabled else LINE
        if self._hover and enabled and not self._dragging:
            thumb_outline = RED_SOFT
        self.create_oval(x - r, cy - r, x + r, cy + r,
                         fill=thumb_fill, outline=thumb_outline, width=2)

    def _rounded(self, x1, y1, x2, y2, radius, **opts):
        radius = min(radius, (y2 - y1) / 2, (x2 - x1) / 2)
        if x2 - x1 < radius * 2 + 1:
            x2 = x1 + radius * 2 + 1
        points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
                  x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
                  x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
        return self.create_polygon(points, smooth=True, **opts)


# ── sparkline ──────────────────────────────────────────────────
class Sparkline(tk.Canvas):
    """Tiny trend line with min/max dots. values: list of floats."""

    def __init__(self, master, values=None, color=RED, label="", bg=CARD,
                 width=150, height=44, **kw):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._values = list(values or [])
        self._color = color
        self._label = label
        self.bind("<Configure>", lambda e: self.redraw())
        self.redraw()

    def set_values(self, values, color=None):
        self._values = list(values or [])
        if color:
            self._color = color
        self.redraw()

    def redraw(self):
        self.delete("all")
        w = max(self.winfo_width(), 1)
        h = max(self.winfo_height(), 1)
        vals = self._values
        if self._label:
            self.create_text(2, 2, text=self._label, anchor="nw",
                             fill=TEXT_FAINT, font=("Segoe UI", 7, "bold"))
        if len(vals) < 2:
            self.create_text(w / 2, h / 2 + 6, text="not enough data",
                             fill=TEXT_FAINT, font=("Segoe UI", 7))
            return
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        pad = 6
        step = (w - 2 * pad) / (len(vals) - 1)
        pts = []
        for i, v in enumerate(vals):
            x = pad + i * step
            y = h - pad - (v - lo) / span * (h - 2 * pad - 8)
            pts += [x, y]
        up = vals[-1] >= vals[0]
        line_color = self._color if self._color != RED else (WIN if up else LOSS)
        self.create_line(*pts, fill=line_color, width=2, smooth=True)
        # last-point marker + value
        self.create_oval(pts[-2] - 3, pts[-1] - 3, pts[-2] + 3, pts[-1] + 3,
                         fill=line_color, outline="")
        last = vals[-1]
        txt = f"{last:g}" if abs(last) < 100 else f"{last:.0f}"
        self.create_text(w - 3, 4, text=txt, anchor="ne", fill=TEXT_DIM,
                         font=("Segoe UI", 8, "bold"))


def section_head(parent, text: str, bg: str | None = None):
    """Section header: orange accent bar + uppercase title."""
    try:
        bg = bg or parent.cget("bg")
    except Exception:
        bg = BG
    head = tk.Frame(parent, bg=bg)
    tk.Frame(head, bg=RED, width=3).pack(side="left", fill="y", padx=(0, 8))
    tk.Label(head, text=text.upper(), bg=bg, fg=TEXT,
             font=("Segoe UI", 10, "bold")).pack(side="left")
    return head
