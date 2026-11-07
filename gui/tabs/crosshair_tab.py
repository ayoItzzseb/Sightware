"""Sightware GUI — Crosshair tab (crosshair overlay editor & control).

The whole crosshair-overlay feature lives here: live preview, style editor
(cross / circle / dot / pixel art / imported image), the preset library, ADS
switching, hotkeys, quickload slots and the app whitelist. The overlay
windows themselves are owned by backend.crosshair_overlay.OverlayEngine.
"""
from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk
import crosshair_codes as xcodes

_GALLERY_BUNDLED = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'pro_gallery.json')
import crosshair_render as render
import crosshair_store as store
from ..theme import (AMBER, BG, BG_RAISED, CARD, CARD_HI, LINE, RED, RED_SOFT,
                   TEAL, TEAL_DIM, TEXT, TEXT_DIM, TEXT_FAINT)
from ..widgets import ScrollFrame, Switch, SightwareSlider, card, section_title

STYLES = [("cross", "CROSS"), ("circle", "CIRCLE"), ("arc", "ARC"),
          ("pixels", "PIXEL ART"), ("custom", "IMAGE")]
LINE_ARROWS = ["↑", "↓", "←", "→"]
SLOTS = 4


def _slider(parent, label, frm, to, get, set_cb, fmt="{:.4f}", bg=CARD, res=None):
    """Slider + numeric entry. Values are continuous down to 0.0001 — typed
    decimals are stored exactly (the slider range auto-expands to cover
    them); dragging moves the same continuous value."""
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=3)
    tk.Label(row, text=label, bg=bg, fg=TEXT_DIM,
             font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
    # effectively continuous: typed values are never stepped away
    s = SightwareSlider(row, from_=frm, to=to, value=get(), resolution=0.0001,
                     length=150, bg=bg)
    entry_var = tk.StringVar(value=_fmt_val(get(), fmt))
    entry = tk.Entry(row, textvariable=entry_var, width=9, bd=0,
                     bg=BG_RAISED, fg=TEXT, insertbackground=RED,
                     highlightthickness=1, highlightbackground=LINE,
                     highlightcolor=RED, justify="center",
                     font=("Consolas", 8))
    suffix = "x" if fmt.endswith("x") else ""

    def _show(v):
        entry_var.set(f"{v:.4f}".rstrip("0").rstrip(".") + suffix)

    def commit(_e=None):
        try:
            v = round(float(entry_var.get().replace(",", ".")), 4)
        except ValueError:
            _show(s.get())
            return
        lo, hi = s.cget("from_"), s.cget("to")
        if v < lo:
            s.configure(from_=v)
        elif v > hi:
            s.configure(to=v)
        s.set(v)
        set_cb(s.get())
        _show(s.get())

    def on_slider(_v):
        set_cb(s.get())
        _show(s.get())

    s.configure(command=on_slider)
    entry.bind("<Return>", commit)
    entry.bind("<FocusOut>", commit)
    s._commit = commit          # exposed for tests
    s._entry_var = entry_var
    s.pack(side="left", padx=(0, 5), pady=2)
    entry.pack(side="left")
    return s


def _fmt_val(v, fmt):
    return f"{v:.4f}".rstrip("0").rstrip(".") + ("x" if fmt.endswith("x") else "")


def _alpha_slider(parent, get_hex, set_hex, bg=CARD):
    """0–100% opacity slider that rewrites the alpha byte of a #RRGGBBAA tint."""
    row = parent  # appended after the color swatch
    start = int(_hex8_alpha(get_hex()) * 100 / 255)
    val = tk.Label(row, text=f"{start}%", bg=bg, fg=TEXT,
                   font=("Segoe UI", 9, "bold"), width=4)

    def _change(_v=None):
        src = get_hex()
        a = round(int(s.get()) * 255 / 100)
        set_hex(src[:7] + f"{a:02X}")
        val.configure(text=f"{s.get():.0f}%")
    s = SightwareSlider(row, from_=0, to=100, value=start, resolution=1,
                     length=120, bg=bg, command=_change)
    s.pack(side="left", padx=(2, 4), pady=2)
    val.pack(side="left")
    return s


def _hex8_alpha(color: str) -> int:
    c = str(color or "")
    if c.startswith("#") and len(c) == 9:
        try:
            return int(c[7:9], 16)
        except ValueError:
            return 255
    return 255


def _color_button(parent, get_hex, set_hex, bg=CARD):
    """Small swatch that opens a color picker (RGB) — alpha stays separate."""
    sw = tk.Label(parent, text="", bg=get_hex()[:7] or "#FFFFFF",
                  width=4, relief="flat", cursor="hand2",
                  highlightbackground=LINE, highlightthickness=1)

    def pick():
        rgb, hex6 = colorchooser.askcolor(color=get_hex()[:7], parent=parent,
                                          title="Pick a color")
        if hex6:
            set_hex(hex6 + get_hex()[7:] if len(get_hex()) == 9 else hex6 + "FF")
            sw.configure(bg=get_hex()[:7])
    sw.bind("<Button-1>", lambda e: pick())
    return sw


class CrosshairTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.engine = app.crosshair_engine
        self._updating = False

        # ── header row ─────────────────────────────────────────
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 2))
        self.status_pill = tk.Label(top, text="OVERLAY OFF", bg=BG_RAISED,
                                    fg=TEXT_FAINT, font=("Segoe UI", 8, "bold"),
                                    padx=10, pady=3)
        self.status_pill.pack(side="left")
        ttk.Button(top, text="Copy share code", style="Ghost.TButton",
                   command=self._copy_share_code).pack(side="right")
        ttk.Button(top, text="Save to gallery", style="Ghost.TButton",
                   command=self._save_to_gallery).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Gallery", style="Ghost.TButton",
                   command=self._open_gallery).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Paste crosshair code", style="Accent.TButton",
                   command=self._import_code).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Open data folder", style="Ghost.TButton",
                   command=self._open_data_folder).pack(side="right", padx=(0, 6))
        self.enabled_switch = Switch(top, on=self.engine.settings.get("enabled", True),
                                     command=self._toggle_enabled)
        self.enabled_switch.pack(side="right", padx=(0, 10))
        tk.Label(top, text="OVERLAY", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 8, "bold")).pack(side="right", padx=(0, 4))

        # ── main split ─────────────────────────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        left = ScrollFrame(body, bg=BG)
        left.pack(side="left", fill="both", expand=False, padx=(16, 8), pady=6)
        left.configure(width=430)
        ctrl = left.inner

        self._build_style_section(ctrl)
        self._build_shape_sections(ctrl)
        self._build_actions(ctrl)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(4, 16), pady=6)
        self._build_preview(right)
        self._build_library(right)
        self._build_hotkeys(right)
        self._build_ads(right)
        self._build_whitelist(right)

        # engine callbacks
        self.engine.on_status = self._on_status
        self.engine.on_crosshair_changed = self._on_external_crosshair
        self.engine.on_capture_done = self._on_capture_done
        self._load_into_ui(store.get_crosshair())
        self.after(250, self._on_status)

    # ── editor: style ──────────────────────────────────────────
    def _build_style_section(self, parent):
        c = card(parent)
        c.pack(fill="x", pady=(0, 8))
        c0 = tk.Frame(c, bg=CARD)
        c0.pack(fill="both", expand=True, padx=12, pady=10)
        section_title(c0, "style", bg=CARD).pack(anchor="w")
        row = tk.Frame(c0, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        self._style_buttons: dict[str, tk.Label] = {}
        for key, label in STYLES:
            b = tk.Label(row, text=label, bg=BG_RAISED, fg=TEXT_DIM,
                         font=("Segoe UI", 9, "bold"), padx=12, pady=6,
                         cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, k=key: self._set_style(k))
            self._style_buttons[key] = b

    def _build_shape_sections(self, parent):
        c = card(parent)
        c.pack(fill="x", pady=(0, 8))
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=12, pady=10)

        section_title(f, "cross", bg=CARD).pack(anchor="w")
        self._sliders = {}
        self._sliders["gap"] = _slider(f, "Gap", 0, 40,
                                       lambda: self._get("gap", 2),
                                       lambda v: self._set("gap", v), bg=CARD)
        self._sliders["length"] = _slider(f, "Length", 1, 40,
                                          lambda: self._get("length", 4),
                                          lambda v: self._set("length", v), bg=CARD)
        self._sliders["thickness"] = _slider(f, "Thickness", 1, 16,
                                             lambda: self._get("thickness", 2),
                                             lambda v: self._set("thickness", v), bg=CARD)
        lines_row = tk.Frame(f, bg=CARD)
        lines_row.pack(fill="x", pady=(4, 10))
        tk.Label(lines_row, text="Lines", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        self._line_btns: list[tk.Label] = []
        for i, arrow in enumerate(LINE_ARROWS):
            b = tk.Label(lines_row, text=arrow, bg=BG_RAISED, fg=TEXT_DIM, width=3,
                         font=("Segoe UI", 10, "bold"), cursor="hand2", pady=2)
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, i=i: self._toggle_line(i))
            self._line_btns.append(b)

        section_title(f, "circle", bg=CARD).pack(anchor="w")
        self._sliders["radius"] = _slider(f, "Radius", 0, 40,
                                          lambda: self._get("gap", 2),
                                          lambda v: self._set("gap", v), bg=CARD)
        self._sliders["circle_thickness"] = _slider(f, "Thickness", 1, 16,
                                                    lambda: self._get("thickness", 2),
                                                    lambda v: self._set("thickness", v), bg=CARD)

        section_title(f, "center dot", bg=CARD).pack(anchor="w", pady=(8, 0))
        dot_row = tk.Frame(f, bg=CARD)
        dot_row.pack(fill="x", pady=(4, 2))
        self.dot_switch = Switch(dot_row, on=self._dot_on(),
                                 command=self._toggle_dot)
        self.dot_switch.pack(side="left")
        self._dot_shape_btns: dict[str, tk.Label] = {}
        for key, label in (("circle", "ROUND"), ("square", "SQUARE")):
            b = tk.Label(dot_row, text=label, bg=BG_RAISED, fg=TEXT_DIM,
                         font=("Segoe UI", 8, "bold"), padx=8, pady=4,
                         cursor="hand2")
            b.pack(side="left", padx=(8, 0))
            b.bind("<Button-1>", lambda e, k=key: self._set_dot_style(k))
            self._dot_shape_btns[key] = b
        self._sliders["dot_size"] = _slider(f, "Dot size", 1, 24,
                                            lambda: max(self._dot_size(), 1),
                                            lambda v: self._set_dot_size(v), bg=CARD)

        section_title(f, "colors", bg=CARD).pack(anchor="w", pady=(8, 0))
        tint_row = tk.Frame(f, bg=CARD)
        tint_row.pack(fill="x", pady=3)
        tk.Label(tint_row, text="Tint", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        self._sw_tint = _color_button(tint_row, lambda: self._get("tint", "#FFFFFFFF"),
                                      lambda h: self._set("tint", h))
        self._sw_tint.pack(side="left")
        self._sliders["tint_alpha"] = _alpha_slider(
            tint_row, lambda: self._get("tint", "#FFFFFFFF"),
            lambda h: self._set("tint", h))
        out_row = tk.Frame(f, bg=CARD)
        out_row.pack(fill="x", pady=3)
        tk.Label(out_row, text="Outline", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        self._sw_outline = _color_button(out_row,
                                         lambda: self._get_outline("tint", "#00000080"),
                                         lambda h: self._set_outline("tint", h))
        self._sw_outline.pack(side="left")
        self._sliders["outline_alpha"] = _alpha_slider(
            out_row, lambda: self._get_outline("tint", "#00000080"),
            lambda h: self._set_outline("tint", h))
        self._sliders["outline_thickness"] = _slider(f, "Outline width", 0, 10,
                                                     lambda: self._get_outline("thickness", 2),
                                                     lambda v: self._set_outline("thickness", v), bg=CARD)
        dotc_row = tk.Frame(f, bg=CARD)
        dotc_row.pack(fill="x", pady=3)
        tk.Label(dotc_row, text="Dot tint", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        self._sw_dot = _color_button(dotc_row, lambda: self._get_dot("tint", "#FFFFFFFF"),
                                     lambda h: self._set_dot("tint", h))
        self._sw_dot.pack(side="left")

        # pixel art section
        section_title(f, "pixel art", bg=CARD).pack(anchor="w", pady=(8, 0))
        self._sliders["pixels_scale"] = _slider(f, "Scale", 0.25, 6,
                                                lambda: self._get_px("scale", 1),
                                                lambda v: self._set_px("scale", v),
                                                fmt="{:.4f}x", bg=CARD)
        px_row = tk.Frame(f, bg=CARD)
        px_row.pack(fill="x", pady=3)
        self._sw_pixels = _color_button(px_row, lambda: self._get_px("tint", "#FFFFFFFF"),
                                        lambda h: self._set_px("tint", h))
        self._sw_pixels.pack(side="left")
        ttk.Button(px_row, text="Open pixel editor", style="TButton",
                   command=self._open_pixel_editor).pack(side="left", padx=8)
        pxrow2 = tk.Frame(f, bg=CARD)
        pxrow2.pack(fill="x", pady=3)
        tk.Label(pxrow2, text="Canvas", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
        self.px_size_cb = ttk.Combobox(pxrow2, state="readonly", width=6,
                                       values=["32", "48", "64"])
        self.px_size_cb.set(str(int(self._get_px("size", 32) or 32)))
        self.px_size_cb.pack(side="left")
        self.px_size_cb.bind("<<ComboboxSelected>>",
                             lambda e: self._set_px("size", int(self.px_size_cb.get())))

        # image section
        section_title(f, "image crosshair", bg=CARD).pack(anchor="w", pady=(8, 0))
        self._sliders["custom_scale"] = _slider(f, "Scale", 0.25, 6,
                                                lambda: self._get_custom("scale", 1),
                                                lambda v: self._set_custom("scale", v),
                                                fmt="{:.4f}x", bg=CARD)
        filt_row = tk.Frame(f, bg=CARD)
        filt_row.pack(fill="x", pady=3)
        self._filter_btns: dict[str, tk.Label] = {}
        for key, label in (("linear", "SMOOTH"), ("nearest", "PIXELATED")):
            b = tk.Label(filt_row, text=label, bg=BG_RAISED, fg=TEXT_DIM,
                         font=("Segoe UI", 8, "bold"), padx=8, pady=4,
                         cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, k=key: self._set_filter(k))
            self._filter_btns[key] = b
        self._sw_custom = _color_button(filt_row, lambda: self._get_custom("tint", "#FFFFFFFF"),
                                        lambda h: self._set_custom("tint", h))
        self._sw_custom.pack(side="left", padx=(4, 8))
        ttk.Button(filt_row, text="Import PNG…", style="TButton",
                   command=self._import_png).pack(side="left")
        self.custom_lbl = tk.Label(f, text="No image selected", bg=CARD,
                                   fg=TEXT_FAINT, font=("Segoe UI", 8))
        self.custom_lbl.pack(anchor="w")

    def _build_actions(self, parent):
        c = card(parent)
        c.pack(fill="x", pady=(0, 8))
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=12, pady=10)
        ttk.Button(f, text="APPLY TO OVERLAY", style="Accent.TButton",
                   command=self._apply).pack(side="left")
        ttk.Button(f, text="Save to library", style="Success.TButton",
                   command=self._save_library).pack(side="left", padx=8)
        ttk.Button(f, text="Reset", style="Ghost.TButton",
                   command=self._reset).pack(side="left")
        ttk.Button(f, text="Preview on screen", style="Ghost.TButton",
                   command=self._toggle_preview).pack(side="right")
        self._previewing = False

    # ── preview ────────────────────────────────────────────────
    def _build_preview(self, parent):
        c = card(parent)
        c.pack(fill="both", expand=True)
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=12, pady=10)
        section_title(f, "live preview — mirrors the overlay", bg=CARD).pack(anchor="w")
        self.preview = tk.Canvas(f, height=230, bg=CARD_HI, highlightthickness=0, bd=0)
        self.preview.pack(fill="both", expand=True, pady=(6, 0))
        self.preview.bind("<Configure>", lambda e: self._draw_preview())
        self._preview_images: list = []
        self._preview_bg_photo = None
        bgbar = tk.Frame(f, bg=CARD)
        bgbar.pack(fill="x", pady=(6, 0))
        ttk.Button(bgbar, text="Preview background…", style="Ghost.TButton",
                   command=self._pick_preview_bg).pack(side="left")
        ttk.Button(bgbar, text="Clear background", style="Ghost.TButton",
                   command=self._clear_preview_bg).pack(side="left", padx=6)

    def _pick_preview_bg(self):
        src = filedialog.askopenfilename(
            title="Pick a background image",
            filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not src:
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(src).convert("RGB")
            self._preview_bg_src = img
            self._draw_preview()
        except Exception as exc:
            toast_msg = f"Could not load image: {exc}"
            self.app.toast.show(toast_msg, kind="error")

    def _clear_preview_bg(self):
        self._preview_bg_src = None
        self._preview_bg_photo = None
        self._draw_preview()

    def _draw_preview(self):
        cv = self.preview
        if not cv.winfo_exists():
            return
        cv.delete("all")
        self._preview_images.clear()
        w = cv.winfo_width() or 400
        h = cv.winfo_height() or 230
        if getattr(self, "_preview_bg_src", None):
            try:
                img = self._preview_bg_src.copy()
                img.thumbnail((w, h))
                self._preview_bg_photo = ImageTk.PhotoImage(img)
                cv.create_image(w / 2, h / 2, image=self._preview_bg_photo)
            except Exception:
                pass
        else:
            # checkerboard in theme shades
            step = 26
            for y in range(0, h, step):
                for x in range(0, w, step):
                    if (x // step + y // step) % 2 == 0:
                        cv.create_rectangle(x, y, x + step, y + step,
                                            fill="#1A2634", width=0)
        cfg = self._working()
        cv.create_rectangle(0, 0, w, h, outline=LINE)
        if cfg["crosshair"]["style"] == "pixels" and not cfg["pixels"]["data"]:
            cv.create_text(w / 2, h / 2, text="Draw pixels or import an image",
                           fill=TEXT_FAINT, font=("Segoe UI", 9))
            return
        if cfg["crosshair"]["style"] == "custom" and cfg["custom"]["path"] == "-":
            cv.create_text(w / 2, h / 2, text="Import a PNG below",
                           fill=TEXT_FAINT, font=("Segoe UI", 9))
            return
        if cfg["crosshair"]["style"] == "cross"                 and not any(cfg["crosshair"].get("lines", [])):
            cv.create_text(w / 2, h / 2, text="All lines are off — tap the arrows",
                           fill=TEXT_FAINT, font=("Segoe UI", 9))
            return
        self._draw_scaled(cv, w / 2, h / 2, cfg)

    def _draw_scaled(self, cv, cx, cy, cfg):
        scale = float(self.engine.settings.get("scale", 1) or 1)
        try:
            from crosshair_overlay import OverlayEngine
            scaled = OverlayEngine._scaled(cfg, scale)
        except Exception:
            scaled = cfg
        render.draw_crosshair(cv, cx, cy, scaled, image_holder=self._preview_images)

    # ── library ────────────────────────────────────────────────
    def _build_library(self, parent):
        section_title(parent, "library").pack(anchor="w", pady=(10, 3))
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x")
        ttk.Button(bar, text="Save current…", style="TButton",
                   command=self._save_library).pack(side="left")
        ttk.Button(bar, text="Import PNGs", style="Ghost.TButton",
                   command=self._import_png).pack(side="left", padx=6)
        ttk.Button(bar, text="Export pack…", style="Ghost.TButton",
                   command=self._export_pack).pack(side="left", padx=6)
        ttk.Button(bar, text="Import pack…", style="Ghost.TButton",
                   command=self._import_pack).pack(side="left")
        self.lib_frame = ScrollFrame(parent, bg=BG)
        self.lib_frame.configure(height=190)
        self.lib_frame.pack_propagate(False)
        self.lib_frame.pack(fill="x", pady=(4, 0))
        self._lib_cards: dict[str, dict] = {}
        self._refresh_library()

    def _refresh_library(self):
        for child in self.lib_frame.inner.winfo_children():
            child.destroy()
        self._lib_cards.clear()
        for item in store.library_list():
            self._lib_card(self.lib_frame.inner, item["name"], item["config"])
        for item in store.custom_list():
            self._lib_card(self.lib_frame.inner, item["name"], None, png=item["path"])
        if not self._lib_cards:
            tk.Label(self.lib_frame.inner,
                     text="Library is empty — save your crosshair or import your "
                          "Simple Sight library (button up top).",
                     bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 9)).pack(anchor="w", padx=4, pady=8)

    def _lib_card(self, parent, name, cfg, png=None):
        wrap = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        wrap.pack(side="left", padx=4, pady=4)
        self._lib_cards[name] = wrap
        thumb = tk.Canvas(wrap, width=92, height=74, bg=CARD_HI,
                          highlightthickness=0, bd=0)
        thumb.pack(padx=6, pady=(6, 0))
        refs: list = []
        if cfg:
            render.draw_crosshair(thumb, 46, 37, self._thumb_cfg(cfg), image_holder=refs)
        elif png:
            try:
                from PIL import Image, ImageTk
                with Image.open(png) as img:
                    img.thumbnail((84, 66))
                    photo = ImageTk.PhotoImage(img.convert("RGBA"))
                refs.append(photo)
                thumb.create_image(46, 37, image=photo)
            except Exception:
                pass
        thumb._refs = refs
        tk.Label(wrap, text=name, bg=CARD, fg=TEXT, font=("Segoe UI", 8, "bold"),
                 width=14).pack()
        btns = tk.Frame(wrap, bg=CARD)
        btns.pack(pady=(0, 6))
        if cfg or png:
            ttk.Button(btns, text="Use", style="Ghost.TButton",
                       command=lambda: self._use_preset(name)).pack(side="left", padx=2)
        if cfg:
            ttk.Button(btns, text="✕", style="Danger.TButton",
                       command=lambda: self._delete_preset(name)).pack(side="left", padx=2)

    @staticmethod
    def _thumb_cfg(cfg):
        import copy
        out = copy.deepcopy(cfg)
        c = out["crosshair"]
        if c["style"] == "pixels":
            out["pixels"]["scale"] = min(float(out["pixels"].get("scale", 1) or 1), 2.0)
        elif c["style"] == "custom":
            out["custom"]["scale"] = min(float(out["custom"].get("scale", 1) or 1), 2.0)
        return out

    # ── hotkeys / overlay settings ─────────────────────────────
    def _build_hotkeys(self, parent):
        section_title(parent, "overlay & hotkeys").pack(anchor="w", pady=(10, 3))
        c = card(parent)
        c.pack(fill="x")
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=12, pady=10)

        s = self.engine.settings
        from crosshair_overlay import monitor_bounds
        monitors = monitor_bounds()
        disp_values = ["Primary"] + (["All displays"] if len(monitors) > 1 else []) + \
                      [f"Display {i + 1}" for i in range(len(monitors))][1:]
        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x", pady=2)
        tk.Label(row, text="Target display", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.display_cb = ttk.Combobox(row, state="readonly", width=18,
                                       values=disp_values)
        td = str(s.get("targetDisplay", "primary"))
        self.display_cb.set({"primary": "Primary", "all": "All displays"}.get(
            td, f"Display {int(td) + 1}" if td.isdigit() else "Primary"))
        self.display_cb.pack(side="left")
        self.display_cb.bind("<<ComboboxSelected>>", self._on_display_selected)

        self._sliders["offset_x"] = _slider(f, "Offset X", -200, 200,
                                            lambda: s.get("offsetX", 0),
                                            lambda v: self._set_setting("offsetX", int(v)), bg=CARD)
        self._sliders["offset_y"] = _slider(f, "Offset Y", -200, 200,
                                            lambda: s.get("offsetY", 0),
                                            lambda v: self._set_setting("offsetY", int(v)), bg=CARD)
        self._sliders["overlay_scale"] = _slider(f, "Overlay scale", 0.25, 4,
                                                 lambda: s.get("scale", 1),
                                                 lambda v: self._set_setting("scale", v),
                                                 fmt="{:.4f}x", bg=CARD)

        bind_row = tk.Frame(f, bg=CARD)
        bind_row.pack(fill="x", pady=(8, 2))
        tk.Label(bind_row, text="Hide/show key", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.bind_toggle = self._bind_button(bind_row, s.get("toggleKey", ""),
                                             ("toggleKey", -1))
        self.bind_toggle2 = self._bind_button(bind_row, s.get("toggleKey2", ""),
                                              ("toggleKey", -2))

        section_title(f, "quickload slots", bg=CARD).pack(anchor="w", pady=(10, 2))
        self._slot_widgets = []
        for i in range(SLOTS):
            slots = s.get("quickload", [])
            slot = slots[i] if i < len(slots) else {"name": f"Slot {i + 1}", "key": "", "crosshair": ""}
            row = tk.Frame(f, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=slot.get("name", f"Slot {i + 1}"), bg=CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 8), width=8, anchor="w").pack(side="left")
            b = self._bind_button(row, slot.get("key", ""), ("slot", i))
            names = [p["name"] for p in store.library_list()] + \
                    [p["name"] for p in store.custom_list()]
            cb = ttk.Combobox(row, state="readonly", width=16, values=["—"] + names)
            cb.set(slot.get("crosshair", "") or "—")
            cb.pack(side="left", padx=4)
            cb.bind("<<ComboboxSelected>>",
                    lambda e, i=i, c=cb: self._set_slot_crosshair(i, c.get()))
            self._slot_widgets.append((b, cb))

    def _build_ads(self, parent):
        section_title(parent, "aim-down-sights (ads)").pack(anchor="w", pady=(10, 3))
        c = card(parent)
        c.pack(fill="x")
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=12, pady=10)
        s = self.engine.settings

        head = tk.Frame(f, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="ENABLED", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.ads_switch = Switch(head, on=s.get("enableAds", False),
                                 command=self._toggle_ads)
        self.ads_switch.pack(side="left", padx=8)
        tk.Label(head, text="(hold MOUSE RIGHT to hide or switch, like the standalone app)",
                 bg=CARD, fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(side="left")
        self.ads_body = tk.Frame(f, bg=CARD)
        self.ads_body.pack(fill="x", pady=(6, 0))

        def _build_action_row(parent):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text="When aiming", bg=CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            self.ads_action_cb = ttk.Combobox(row, state="readonly", width=16,
                                              values=["hide", "switch"])
            self.ads_action_cb.set(s.get("adsAction", "hide"))
            self.ads_action_cb.pack(side="left")
            self.ads_action_cb.bind("<<ComboboxSelected>>",
                                    lambda e: self._set_setting("adsAction", self.ads_action_cb.get()))

        def _build_behaviour_row(parent):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text="Trigger", bg=CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            self.ads_beh_cb = ttk.Combobox(row, state="readonly", width=16,
                                           values=["hold", "toggle"])
            self.ads_beh_cb.set(s.get("adsBehaviour", "hold"))
            self.ads_beh_cb.pack(side="left")
            self.ads_beh_cb.bind("<<ComboboxSelected>>",
                                 lambda e: self._set_setting("adsBehaviour", self.ads_beh_cb.get()))

        def _build_key_row(parent):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text="Aim key", bg=CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            self.bind_ads = self._bind_button(row, s.get("adsKey", ""), ("adsKey", -1))
            self.bind_ads2 = self._bind_button(row, s.get("adsKey2", ""), ("adsKey", -2))

        def _build_switch_row(parent):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text="Switch to", bg=CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            names = [p["name"] for p in store.library_list()]
            self.ads_path_cb = ttk.Combobox(row, state="readonly", width=18,
                                            values=["—"] + names)
            self.ads_path_cb.set(s.get("adsPath", "") or "—")
            self.ads_path_cb.pack(side="left")
            self.ads_path_cb.bind("<<ComboboxSelected>>",
                                  lambda e: self._set_setting(
                                      "adsPath",
                                      "" if self.ads_path_cb.get() == "—"
                                      else self.ads_path_cb.get()))

        self._ads_builders = [_build_action_row, _build_behaviour_row,
                              _build_key_row, _build_switch_row]
        self._sync_ads_body()

    def _build_whitelist(self, parent):
        section_title(parent, "only show in whitelisted apps").pack(anchor="w", pady=(10, 3))
        c = card(parent)
        c.pack(fill="x", pady=(0, 8))
        f = tk.Frame(c, bg=CARD)
        f.pack(fill="both", expand=True, padx=12, pady=10)
        s = self.engine.settings
        head = tk.Frame(f, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="ENABLED", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.wl_switch = Switch(head, on=s.get("whitelistEnabled", False),
                                command=self._toggle_whitelist)
        self.wl_switch.pack(side="left", padx=8)
        tk.Label(head, text="(matched by window title — no processes are opened)",
                 bg=CARD, fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(side="left")
        self.wl_list = tk.Frame(f, bg=CARD)
        self.wl_list.pack(fill="x", pady=(6, 2))
        btns = tk.Frame(f, bg=CARD)
        btns.pack(fill="x")
        ttk.Button(btns, text="Add VALORANT", style="Success.TButton",
                   command=self._wl_add_valorant).pack(side="left")
        ttk.Button(btns, text="Add by name…", style="Ghost.TButton",
                   command=self._wl_add_name).pack(side="left", padx=6)
        ttk.Button(btns, text="Remove selected", style="Danger.TButton",
                   command=self._wl_remove).pack(side="left", padx=2)
        self._wl_value = tk.Listbox(f, bg=BG_RAISED, fg=TEXT, height=4, bd=0,
                                    highlightthickness=1,
                                    highlightbackground=LINE,
                                    selectbackground=RED,
                                    activestyle="none",
                                    font=("Segoe UI", 9))
        self._wl_value.pack(fill="x", pady=(6, 0))
        self.wl_per_app = tk.Frame(f, bg=CARD)
        self.wl_per_app.pack(fill="x", pady=(2, 0))
        self._refresh_whitelist()

    # ── share codes / packs ────────────────────────────────────
    def _import_code(self):
        dlg = tk.Toplevel(self)
        dlg.title("Import VALORANT crosshair code")
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        tk.Label(dlg, text="Paste a crosshair code (0;P;c;5;o;1;...)",
                 bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")
                 ).pack(padx=16, pady=(14, 6))
        var = tk.StringVar()
        ent = ttk.Entry(dlg, textvariable=var, width=52)
        ent.pack(padx=16, pady=(0, 4))
        msg = tk.Label(dlg, text="", bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8))
        msg.pack(anchor="w", padx=16)

        def ok(_e=None):
            cfg, info = xcodes.decode_with_info(var.get())
            if not cfg:
                msg.configure(text=info, fg=RED_SOFT)
                return
            self._load_into_ui(cfg)
            self.engine.set_crosshair_runtime(cfg)
            dlg.destroy()
            self.app.toast.show(f"Imported — {info}", kind="ok")
        ent.bind("<Return>", ok)
        ttk.Button(dlg, text="Import", style="Accent.TButton",
                   command=ok).pack(pady=(6, 14))
        ent.focus_set()

    def _copy_share_code(self):
        self._sync_from_ui()
        code = xcodes.encode(self._working())
        if not code:
            self.app.toast.show("Share codes need a Cross, Circle or Arc style.",
                                kind="error")
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        self.app.toast.show("Share code copied to clipboard.", kind="ok")

    def _export_pack(self):
        dest = filedialog.asksaveasfilename(
            title="Export crosshair pack", defaultextension=".zip",
            filetypes=[("Crosshair pack", "*.zip")])
        if not dest:
            return
        r = store.export_pack(dest)
        self.app.toast.show(f"Pack saved: {r['presets']} presets, "
                            f"{r['images']} images.", kind="ok")

    def _import_pack(self):
        src = filedialog.askopenfilename(title="Import crosshair pack",
                                         filetypes=[("Crosshair pack", "*.zip")])
        if not src:
            return
        r = store.import_pack(src)
        self.app.toast.show(f"Pack imported: {r['presets']} presets, "
                            f"{r['images']} images"
                            + (f", {r['skipped']} skipped" if r["skipped"] else ""),
                            kind="ok")
        self._refresh_library()

    # ── crosshair gallery ──────────────────────────────────────
    def _gallery_entries(self) -> list[dict]:
        entries = []
        try:
            bundled = json.load(open(_GALLERY_BUNDLED, encoding="utf-8"))
            for e in bundled:
                e["_user"] = False
                entries.append(e)
        except Exception:
            pass
        try:
            user_file = os.path.join(store._BASE, "gallery.json")
            for e in json.load(open(user_file, encoding="utf-8")):
                e["_user"] = True
                entries.append(e)
        except Exception:
            pass
        return entries

    def _save_user_gallery(self, entries):
        user_file = os.path.join(store._BASE, "gallery.json")
        os.makedirs(os.path.dirname(user_file), exist_ok=True)
        with open(user_file, "w", encoding="utf-8") as f:
            json.dump([e for e in entries if e.get("_user")], f, indent=2)

    def _save_to_gallery(self):
        name = self._ask_name("Save to gallery", "My crosshair")
        if not name:
            return
        self._gallery_add(name)

    def _gallery_add(self, name: str) -> None:
        code = xcodes.encode(self._working())
        if not code:
            self.app.toast.show("Gallery needs a Cross, Circle or Arc style.",
                                kind="error")
            return
        entries = self._gallery_entries()
        entries.append({"name": name, "code": code, "source": "you",
                        "_user": True})
        self._save_user_gallery(entries)
        self.app.toast.show(f'"{name}" added to your gallery.', kind="ok")

    def _open_gallery(self):
        entries = self._gallery_entries()
        dlg = tk.Toplevel(self)
        dlg.title("Crosshair gallery")
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.geometry("780x560")
        head = tk.Frame(dlg, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(head, text="CROSSHAIR GALLERY", bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        search_var = tk.StringVar()
        tk.Label(head, text="search ", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8)).pack(side="right")
        ent = tk.Entry(head, textvariable=search_var, width=22, bd=0,
                       bg=BG_RAISED, fg=TEXT, insertbackground=RED,
                       highlightthickness=1, highlightbackground=LINE,
                       highlightcolor=RED)
        ent.pack(side="right")

        body = tk.Frame(dlg, bg=BG)
        body.pack(fill="both", expand=True, padx=16)
        lb = tk.Listbox(body, bg=BG_RAISED, fg=TEXT, bd=0, width=30,
                        highlightthickness=1, highlightbackground=LINE,
                        highlightcolor=RED, selectbackground=RED,
                        activestyle="none", font=("Segoe UI", 9))
        lb.pack(side="left", fill="y")

        preview = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                           highlightthickness=1)
        preview.pack(side="left", fill="both", expand=True, padx=(10, 0))
        prev_wrap = tk.Frame(preview, bg=CARD_HI)
        prev_wrap.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        info = tk.Label(preview, text="", bg=CARD, fg=TEXT_FAINT,
                        font=("Segoe UI", 8), wraplength=340, justify="left")
        info.pack(fill="x", padx=10, pady=6)
        btns = tk.Frame(preview, bg=CARD)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        refs = []

        def current():
            sel = lb.curselection()
            if sel and sel[0] < len(filtered):
                return filtered[sel[0]]
            return None

        filtered = entries

        def show_preview(e):
            nonlocal prev_wrap
            for w in preview.winfo_children():
                if w is not prev_wrap and w is not info and w is not btns:
                    w.destroy()
            prev_wrap.destroy()
            prev_wrap = tk.Frame(preview, bg=CARD_HI)
            prev_wrap.pack(fill="both", expand=True, padx=10, pady=(10, 0))
            cfg = xcodes.decode(e.get("code", ""))
            if not cfg:
                tk.Label(prev_wrap, text="code could not be displayed",
                         bg=CARD_HI, fg=LOSS).pack(pady=30)
                return
            zoom = 3
            cv = tk.Canvas(prev_wrap, bg=CARD_HI, highlightthickness=0)
            cv.pack(fill="both", expand=True, padx=6, pady=6)
            cv._zoom = zoom
            cv._cfg = cfg
            refs_local = []
            render.draw_crosshair(cv, 60, 60, cfg, image_holder=refs_local)
            # scale up via zoom on the canvas transform
            cv.scale("all", 0, 0, zoom, zoom)
            cv.configure(width=120 * zoom, height=120 * zoom)

        def render_list(_e=None):
            nonlocal filtered
            q = search_var.get().casefold()
            lb.delete(0, "end")
            filtered = [e for e in entries
                        if not q or q in e.get("name", "").casefold()]
            for e in filtered:
                lb.insert("end", e.get("name", "?"))
            if lb.size():
                lb.selection_set(0)
            show_sel()

        def show_sel(_e=None):
            e = current()
            if e:
                show_preview(e)
                info.configure(text="source: " + e.get("source", "—"))

        def use(_e=None):
            e = current()
            if not e:
                return
            cfg = xcodes.decode(e.get("code", ""))
            if not cfg:
                self.app.toast.show("That entry's code could not be parsed.",
                                    kind="error")
                return
            self._load_into_ui(cfg)
            self.engine.set_crosshair_runtime(cfg)
            dlg.destroy()
            self.app.toast.show(f'Loaded "{e.get("name")}" — tune and Apply.',
                                kind="ok")

        def copy_code(_e=None):
            e = current()
            if e:
                self.clipboard_clear()
                self.clipboard_append(e["code"])
                self.app.toast.show("Code copied.", kind="ok")

        def delete(_e=None):
            e = current()
            if not e or not e.get("_user"):
                self.app.toast.show("Built-in entries can't be deleted.",
                                    kind="warn")
                return
            entries.remove(e)
            self._save_user_gallery(entries)
            render_list()

        lb.bind("<<ListboxSelect>>", show_sel)
        search_var.trace_add("write", render_list)
        ttk.Button(btns, text="Use this crosshair", style="Accent.TButton",
                   command=use).pack(side="left")
        ttk.Button(btns, text="Copy code", style="Ghost.TButton",
                   command=copy_code).pack(side="left", padx=4)
        ttk.Button(btns, text="Delete", style="Danger.TButton",
                   command=delete).pack(side="right")
        render_list()

    # ── state helpers ──────────────────────────────────────────
    def _working(self) -> dict:
        if not hasattr(self, "_work"):
            self._work = store.get_crosshair()
        return self._work

    def _get(self, key, default):
        return self._working()["crosshair"].get(key, default)

    def _set(self, key, value):
        self._working()["crosshair"][key] = value
        self._redraw_preview_only()

    def _get_outline(self, key, default):
        return self._working()["crosshair"].setdefault("outline", {}).get(key, default)

    def _set_outline(self, key, value):
        self._working()["crosshair"].setdefault("outline", {})[key] = value
        self._redraw_preview_only()

    def _dot_on(self):
        return float(self._get_dot("size", 0)) > 0

    def _dot_size(self):
        return float(self._get_dot("size", 0))

    def _get_dot(self, key, default):
        return self._working()["crosshair"].setdefault("dot", {}).get(key, default)

    def _set_dot(self, key, value):
        self._working()["crosshair"].setdefault("dot", {})[key] = value
        self._redraw_preview_only()

    def _set_dot_size(self, value):
        self._set_dot("size", value)

    def _get_px(self, key, default):
        return self._working().setdefault("pixels", {}).get(key, default)

    def _set_px(self, key, value):
        self._working().setdefault("pixels", {})[key] = value
        self._redraw_preview_only()

    def _get_custom(self, key, default):
        return self._working().setdefault("custom", {}).get(key, default)

    def _set_custom(self, key, value):
        self._working().setdefault("custom", {})[key] = value
        self._redraw_preview_only()

    def _redraw_preview_only(self):
        self._sync_style_ui()
        self._draw_preview()

    # ── style / shape handlers ─────────────────────────────────
    def _set_style(self, key):
        self._working()["crosshair"]["style"] = key
        # switching to Cross is an explicit intent to draw lines: if every
        # line toggle happens to be off (e.g. after loading a dot-only
        # preset), bring them back so the cross is never invisibly empty
        if key == "cross" and not any(self._working()["crosshair"].get("lines", [])):
            self._working()["crosshair"]["lines"] = [True, True, True, True]
        self._sync_style_ui()
        self._draw_preview()

    def _toggle_line(self, i):
        lines = self._working()["crosshair"].setdefault("lines", [True] * 4)
        lines[i] = not lines[i]
        self._sync_style_ui()
        self._draw_preview()

    def _toggle_dot(self):
        cur = self._dot_size()
        self._set_dot("size", 3 if cur <= 0 else 0)
        self._sync_style_ui()
        self._draw_preview()

    def _set_dot_style(self, key):
        self._set_dot("style", key)
        self._sync_style_ui()

    def _set_filter(self, key):
        self._set_custom("filter", key)
        self._sync_style_ui()
        self._draw_preview()

    def _sync_style_ui(self):
        c = self._working()["crosshair"]
        style = c.get("style", "cross")
        for k, b in self._style_buttons.items():
            b.configure(bg=RED if k == style else BG_RAISED,
                        fg="#FFFFFF" if k == style else TEXT_DIM)
        # sweep row only matters for the arc style
        if "arc-sweep" in getattr(self, "_sliders", {}):
            row_of_arc = self._sliders["arc-sweep"].master
            row_of_arc.pack(fill="x") if style == "arc" else row_of_arc.pack_forget()
        for i, b in enumerate(self._line_btns):
            on = c.get("lines", [True] * 4)[i]
            b.configure(bg=RED if on else BG_RAISED, fg="#FFFFFF" if on else TEXT_DIM)
        dot_on = self._dot_on()
        self.dot_switch.set(dot_on, fire=False)
        dot_style = self._get_dot("style", "circle")
        for k, b in self._dot_shape_btns.items():
            b.configure(bg=RED if k == dot_style else BG_RAISED,
                        fg="#FFFFFF" if k == dot_style else TEXT_DIM)
        filt = self._get_custom("filter", "linear")
        for k, b in self._filter_btns.items():
            b.configure(bg=RED if k == filt else BG_RAISED,
                        fg="#FFFFFF" if k == filt else TEXT_DIM)
        for sw, getter in ((self._sw_tint, lambda: self._get("tint", "#FFFFFFFF")),
                           (self._sw_outline, lambda: self._get_outline("tint", "#00000080")),
                           (self._sw_dot, lambda: self._get_dot("tint", "#FFFFFFFF")),
                           (self._sw_pixels, lambda: self._get_px("tint", "#FFFFFFFF")),
                           (self._sw_custom, lambda: self._get_custom("tint", "#FFFFFFFF"))):
            sw.configure(bg=getter()[:7])
        path = self._get_custom("path", "-")
        self.custom_lbl.configure(
            text=path if path != "-" else "No image selected")

    # ── apply / save / reset / preview ─────────────────────────
    def _apply(self):
        self.engine.save_crosshair(self._working())
        self._previewing = False
        self.app.toast.show("Crosshair applied to the overlay.", kind="ok")

    def _save_library(self):
        name = self._ask_name("Save crosshair as", "My crosshair")
        if not name:
            return
        saved = store.save_to_library(name, self._working())
        if saved:
            self.app.toast.show(f'Saved "{saved}" to the library.', kind="ok")
            self._refresh_library()
        else:
            self.app.toast.show("Could not save — check the name.", kind="error")

    def _reset(self):
        import copy
        self._work = copy.deepcopy(store.CROSSHAIR_DEFAULT)
        self._load_into_ui(self._work)
        self.engine.set_crosshair_runtime(None)
        self.app.toast.show("Reset to the default crosshair.")

    def _toggle_preview(self):
        self._previewing = not self._previewing
        if self._previewing:
            self._sync_from_ui()
            self.engine.set_crosshair_runtime(self._working())
        else:
            self.engine.set_crosshair_runtime(store.get_crosshair())

    def _sync_from_ui(self):
        pass  # sliders already write straight into self._work

    # ── library actions ────────────────────────────────────────
    def _use_preset(self, name):
        cfg = store.load_from_library(name)
        if not cfg:
            self.app.toast.show("Preset not found.", kind="error")
            return
        self.engine.save_crosshair(cfg)
        self._load_into_ui(cfg)
        self.app.toast.show(f'Loaded "{name}".', kind="ok")

    def _delete_preset(self, name):
        if messagebox.askyesno("Sightware", f'Delete "{name}" from the library?'):
            store.delete_from_library(name)
            self._refresh_library()

    def _import_png(self):
        files = filedialog.askopenfilenames(title="Import crosshair images",
                                            filetypes=[("PNG images", "*.png")])
        if files:
            n = store.import_pngs(list(files))
            self.app.toast.show(f"Imported {n} image(s).", kind="ok")
            self._refresh_library()

    def _import_library(self):
        guess = store.detect_import_dir()
        if guess and messagebox.askyesno(
                "Sightware", f"Import crosshairs from:\n{guess}\n\n"
                          "(Cancel to pick a different folder)"):
            src = guess
        else:
            src = filedialog.askdirectory(title="Choose a Simple Sight library folder")
            if not src:
                return
        r = store.import_library(src)
        msg = f'Imported {r["imported"]} item(s)'
        if r["skipped"]:
            msg += f', skipped {r["skipped"]} existing'
        self.app.toast.show(msg + ".", kind="ok" if not r["errors"] else "warn")
        self._refresh_library()

    def _open_data_folder(self):
        import os, subprocess
        path = store._BASE
        os.makedirs(path, exist_ok=True)
        subprocess.Popen(["explorer", os.path.abspath(path)])

    # ── pixel editor ───────────────────────────────────────────
    def _open_pixel_editor(self):
        PixelEditorDialog(self, self._get_px("data", ""),
                          self._sw_pixels.cget("bg") or "#FFFFFF",
                          on_save=lambda b64: (self._set_px("data", b64),
                                               self._draw_preview()),
                          size=int(self._get_px("size", 32) or 32))

    # ── bindings / settings plumbing ───────────────────────────
    def _bind_button(self, parent, value, target):
        b = ttk.Button(parent, text=value or "— bind —", style="TButton", width=16)
        b.pack(side="left", padx=3)
        b.configure(command=lambda: self._start_capture(b, target))
        b._target = target
        return b

    def _start_capture(self, btn, target):
        btn.configure(text="press any key…")
        self._capture_btn = btn
        self.engine.begin_capture(target[0], target[1])

    def _on_capture_done(self, kind, index, key):
        btn = getattr(self, "_capture_btn", None)
        if btn:
            btn.configure(text=key)
        s = self.engine.settings
        if kind == "toggleKey":
            s["toggleKey" if index == -1 else "toggleKey2"] = key
        elif kind == "adsKey":
            s["adsKey" if index == -1 else "adsKey2"] = key
        elif kind == "slot":
            while len(s.get("quickload", [])) <= index:
                s.setdefault("quickload", []).append(
                    {"name": f"Slot {len(s['quickload']) + 1}", "key": "",
                     "crosshair": ""})
            s["quickload"][index]["key"] = key
        self.engine.save_settings(s)

    def _on_display_selected(self, _e=None):
        v = self.display_cb.get()
        value = {"Primary": "primary", "All displays": "all"}.get(v)
        if value is None and v.startswith("Display "):
            value = str(int(v.split()[1]) - 1)
        if value is not None:
            self._set_setting("targetDisplay", value)

    def _set_setting(self, key, value):
        self.engine.save_settings({**self.engine.settings, key: value})
        if key in ("targetDisplay", "offsetX", "offsetY", "scale"):
            self._draw_preview()

    def _set_slot_crosshair(self, i, value):
        self.engine.settings["quickload"][i]["crosshair"] = "" if value == "—" else value
        self.engine.save_settings(self.engine.settings)

    def _toggle_enabled(self):
        on = self.enabled_switch.on
        self.engine.save_settings({**self.engine.settings, "enabled": on})
        self._on_status()

    def _toggle_ads(self):
        self.engine.save_settings({**self.engine.settings,
                                   "enableAds": self.ads_switch.on})
        self._sync_ads_body()

    def _sync_ads_body(self):
        on = bool(self.engine.settings.get("enableAds"))
        for child in self.ads_body.winfo_children():
            child.destroy()
        if not on:
            tk.Label(self.ads_body, text="Enable ADS to configure aim keys and switching.",
                     bg=CARD, fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(anchor="w")
            return
        # rebuild the ADS controls (they live in self._ads_builders)
        for build in self._ads_builders:
            build(self.ads_body)

    def _toggle_whitelist(self):
        self.engine.save_settings({**self.engine.settings,
                                   "whitelistEnabled": self.wl_switch.on})

    def _wl_add_valorant(self):
        wl = self.engine.settings.setdefault("whitelist", [])
        if not any(e.get("name") == "VALORANT" for e in wl):
            wl.append({"name": "VALORANT", "path": "VALORANT.exe"})
            self.engine.save_settings(self.engine.settings)
            self._refresh_whitelist()

    def _wl_add_name(self):
        name = self._ask_name("Add app by window title", "VALORANT")
        if name:
            wl = self.engine.settings.setdefault("whitelist", [])
            wl.append({"name": name, "path": f"{name}.exe"})
            self.engine.save_settings(self.engine.settings)
            self._refresh_whitelist()

    def _wl_remove(self):
        sel = self._wl_value.curselection()
        if sel:
            del self.engine.settings["whitelist"][sel[0]]
            self.engine.save_settings(self.engine.settings)
            self._refresh_whitelist()

    def _save_per_app(self, app_name, preset):
        mapping = store.get_per_app()
        if preset:
            mapping[app_name] = preset
        else:
            mapping.pop(app_name, None)
        store.set_per_app(mapping)

    def _refresh_whitelist(self):
        self._wl_value.delete(0, "end")
        per_app = store.get_per_app()
        names = [p["name"] for p in store.library_list()] + \
                [p["name"] for p in store.custom_list()]
        for e in self.engine.settings.get("whitelist", []):
            self._wl_value.insert("end", e.get("name", "?"))
        # per-app crosshair memory rows
        for w in self.wl_per_app.winfo_children():
            w.destroy()
        if self.engine.settings.get("whitelistEnabled"):
            tk.Label(self.wl_per_app, text="Crosshair per app:", bg=CARD,
                     fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(anchor="w")
            for e in self.engine.settings.get("whitelist", []):
                row = tk.Frame(self.wl_per_app, bg=CARD)
                row.pack(fill="x", pady=1)
                cb = ttk.Combobox(row, state="readonly", width=16,
                                  values=["— default —"] + names)
                cb.set(per_app.get(e.get("name", ""), "") or "— default —")
                cb.pack(side="left")
                cb.bind("<<ComboboxSelected>>",
                        lambda _e, n=e.get("name", ""), c=cb:
                        self._save_per_app(n, "" if c.get().startswith("—")
                                           else c.get()))
                tk.Label(row, text=e.get("name", "?"), bg=CARD, fg=TEXT_DIM,
                         font=("Segoe UI", 8)).pack(side="left", padx=6)

    # ── misc ───────────────────────────────────────────────────
    def _ask_name(self, title, initial) -> str | None:
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.resizable(False, False)
        tk.Label(dlg, text=title, bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(padx=16, pady=(14, 6))
        var = tk.StringVar(value=initial)
        ent = ttk.Entry(dlg, textvariable=var, width=32)
        ent.pack(padx=16, pady=(0, 12))
        ent.selection_range(0, "end")
        ent.focus_set()
        out = {"name": None}

        def ok(_e=None):
            out["name"] = var.get().strip() or None
            dlg.destroy()
        ent.bind("<Return>", ok)
        row = tk.Frame(dlg, bg=BG)
        row.pack(pady=(0, 14))
        ttk.Button(row, text="OK", style="Accent.TButton", command=ok).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", style="Ghost.TButton",
                   command=dlg.destroy).pack(side="left", padx=4)
        self.wait_window(dlg)
        return out["name"]

    def _load_into_ui(self, cfg):
        self._work = cfg
        self._sync_style_ui()
        self._draw_preview()

    def _on_external_crosshair(self, cfg):
        def apply():
            self._load_into_ui(cfg)
        self.app._post_ui(apply)

    def _on_status(self, status=None):
        s = self.engine.settings
        if status is None:
            visible = bool(self.engine.windows) and s.get("enabled", True)
            status = {"visible": visible, "windows": len(self.engine.windows),
                      "hiddenByToggle": self.engine.hidden_by_toggle}
        if s.get("enabled", True):
            if status.get("hiddenByToggle"):
                self.status_pill.configure(text="HIDDEN (hotkey)", bg="#4A3B14", fg=AMBER)
            elif status.get("visible"):
                self.status_pill.configure(text=f"LIVE · {status.get('windows', 1)} display(s)",
                                           bg=TEAL_DIM, fg="#D9FFF3")
            else:
                self.status_pill.configure(text="READY", bg=BG_RAISED, fg=TEXT_DIM)
        else:
            self.status_pill.configure(text="OVERLAY OFF", bg=BG_RAISED, fg=TEXT_FAINT)

    def on_show(self):
        self._refresh_library()
        self._on_status()


# ── pixel editor dialog ────────────────────────────────────────

class PixelEditorDialog(tk.Toplevel):
    SIZES = (32, 48, 64)

    def __init__(self, master, data_b64, color, on_save, size=32):
        super().__init__(master)
        self.title("Pixel editor")
        self.configure(bg=BG)
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)
        self.on_save = on_save
        self.color = color[:7] if color else "#FFFFFF"
        self.tool = "pencil"
        self.mirror_x = False
        self.mirror_y = False
        self._undo = []
        self._redo = []
        self._palette = self._load_palette()
        self.SIZE = size
        self.grid = [[None] * self.SIZE for _ in range(self.SIZE)]
        self._load_existing(data_b64)

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(head, text=f"PIXEL EDITOR - {self.SIZE}x{self.SIZE}", bg=BG,
                 fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        tools = tk.Frame(head, bg=BG)
        tools.pack(side="right")
        self.pencil_btn = tk.Label(tools, text="PENCIL", bg=RED, fg="#FFFFFF",
                                   font=("Segoe UI", 8, "bold"), padx=8, pady=4,
                                   cursor="hand2")
        self.pencil_btn.pack(side="left", padx=2)
        self.eraser_btn = tk.Label(tools, text="ERASER", bg=BG_RAISED, fg=TEXT_DIM,
                                   font=("Segoe UI", 8, "bold"), padx=8, pady=4,
                                   cursor="hand2")
        self.eraser_btn.pack(side="left", padx=2)
        self.pencil_btn.bind("<Button-1>", lambda e: self._set_tool("pencil"))
        self.eraser_btn.bind("<Button-1>", lambda e: self._set_tool("eraser"))

        row2 = tk.Frame(self, bg=BG)
        row2.pack(fill="x", padx=14, pady=(0, 2))
        tk.Label(row2, text="Canvas", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self.size_cb = ttk.Combobox(row2, state="readonly", width=5,
                                    values=[str(x) for x in self.SIZES])
        self.size_cb.set(str(self.SIZE))
        self.size_cb.pack(side="left", padx=(4, 10))
        self.size_cb.bind("<<ComboboxSelected>>", self._change_size)
        self.mx_btn = tk.Label(row2, text="MIRROR X", bg=BG_RAISED, fg=TEXT_DIM,
                               font=("Segoe UI", 8, "bold"), padx=6, pady=3,
                               cursor="hand2")
        self.mx_btn.pack(side="left", padx=2)
        self.mx_btn.bind("<Button-1>", lambda e: self._toggle_mirror("x"))
        self.my_btn = tk.Label(row2, text="MIRROR Y", bg=BG_RAISED, fg=TEXT_DIM,
                               font=("Segoe UI", 8, "bold"), padx=6, pady=3,
                               cursor="hand2")
        self.my_btn.pack(side="left", padx=2)
        self.my_btn.bind("<Button-1>", lambda e: self._toggle_mirror("y"))
        self.undo_btn = tk.Label(row2, text="UNDO", bg=BG_RAISED, fg=TEXT_DIM,
                                 font=("Segoe UI", 8, "bold"), padx=6, pady=3,
                                 cursor="hand2")
        self.undo_btn.pack(side="left", padx=2)
        self.undo_btn.bind("<Button-1>", lambda e: self._undo_pop())
        self.redo_btn = tk.Label(row2, text="REDO", bg=BG_RAISED, fg=TEXT_DIM,
                                 font=("Segoe UI", 8, "bold"), padx=6, pady=3,
                                 cursor="hand2")
        self.redo_btn.pack(side="left", padx=2)
        self.redo_btn.bind("<Button-1>", lambda e: self._redo_pop())

        body = tk.Frame(self, bg=BG)
        body.pack(padx=14, pady=6)
        self.cell = max(320 // self.SIZE, 5)
        self.canvas = tk.Canvas(body, width=self.SIZE * self.cell,
                                height=self.SIZE * self.cell,
                                bg=CARD_HI, highlightthickness=1,
                                highlightbackground=LINE, bd=0)
        self.canvas.pack()
        self._drawing = False
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>",
                         lambda e: setattr(self, "_drawing", False))
        self.canvas.bind("<Button-3>", lambda e: self._paint(e, erase=True))
        self.bind("<Control-z>", lambda e: self._undo_pop())
        self.bind("<Control-y>", lambda e: self._redo_pop())
        self._draw_grid()
        self._draw_palette()

        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))
        ttk.Button(btns, text="Clear", style="Danger.TButton",
                   command=self._clear).pack(side="left")
        ttk.Button(btns, text="Cancel", style="Ghost.TButton",
                   command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Use this pixel crosshair", style="Accent.TButton",
                   command=self._save).pack(side="right")

    # palette (persisted per install)
    def _palette_path(self):
        import crosshair_store as _store
        import os
        return os.path.join(_store._DATA_DIR, "crosshair", "pixel-palette.json")

    def _load_palette(self):
        import json
        try:
            with open(self._palette_path(), "r", encoding="utf-8") as f:
                return json.load(f)[:14]
        except Exception:
            return ["#00FF66", "#FF4655", "#35E2E2", "#FFFFFF", "#000000"]

    def _save_palette(self):
        import json
        try:
            with open(self._palette_path(), "w", encoding="utf-8") as f:
                json.dump(self._palette, f)
        except Exception:
            pass

    def _draw_palette(self):
        if hasattr(self, "_pal_frame") and self._pal_frame.winfo_exists():
            self._pal_frame.destroy()
        self._pal_frame = tk.Frame(self, bg=BG)
        self._pal_frame.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(self._pal_frame, text="Palette:", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8)).pack(side="left")
        for col in self._palette:
            sw = tk.Label(self._pal_frame, text="", bg=col, width=3,
                          cursor="hand2", highlightbackground=LINE,
                          highlightthickness=1)
            sw.pack(side="left", padx=2)
            sw.bind("<Button-1>", lambda e, c=col: self._pick_color(c))

    def _pick_color(self, col):
        self.color = col

    def _remember_color(self, col):
        col = col[:7]
        if col in self._palette:
            return
        self._palette.insert(0, col)
        self._palette = self._palette[:14]
        self._save_palette()
        self._draw_palette()

    # undo / redo
    def _snapshot(self):
        return [row[:] for row in self.grid]

    def _push_undo(self):
        self._undo.append(self._snapshot())
        self._redo.clear()

    def _undo_pop(self):
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self.grid = self._undo.pop()
        self._draw_grid()

    def _redo_pop(self):
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self.grid = self._redo.pop()
        self._draw_grid()

    def _toggle_mirror(self, axis):
        if axis == "x":
            self.mirror_x = not self.mirror_x
            self.mx_btn.configure(bg=RED if self.mirror_x else BG_RAISED,
                                  fg="#FFFFFF" if self.mirror_x else TEXT_DIM)
        else:
            self.mirror_y = not self.mirror_y
            self.my_btn.configure(bg=RED if self.mirror_y else BG_RAISED,
                                  fg="#FFFFFF" if self.mirror_y else TEXT_DIM)

    def _change_size(self, _e=None):
        new_size = int(self.size_cb.get())
        if new_size == self.SIZE:
            return
        old = self.grid
        old_size = self.SIZE
        self.SIZE = new_size
        self.grid = [[None] * new_size for _ in range(new_size)]
        sx = new_size / old_size
        for y in range(new_size):
            for x in range(new_size):
                ox = min(int(x / sx), old_size - 1)
                oy = min(int(y / sx), old_size - 1)
                self.grid[y][x] = old[oy][ox]
        self.cell = max(320 // new_size, 5)
        self.canvas.configure(width=self.SIZE * self.cell,
                              height=self.SIZE * self.cell)
        self._draw_grid()

    def _load_existing(self, data_b64):
        if not data_b64:
            return
        try:
            import base64, io
            from PIL import Image
            raw = base64.b64decode(data_b64)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            if img.size != (self.SIZE, self.SIZE):
                img = img.resize((self.SIZE, self.SIZE), Image.NEAREST)
            px = img.load()
            for y in range(self.SIZE):
                for x in range(self.SIZE):
                    r, g, b, a = px[x, y]
                    self.grid[y][x] = (r, g, b, a) if a > 0 else None
        except Exception:
            pass

    def _set_tool(self, tool):
        self.tool = tool
        self.pencil_btn.configure(bg=RED if tool == "pencil" else BG_RAISED,
                                  fg="#FFFFFF" if tool == "pencil" else TEXT_DIM)
        self.eraser_btn.configure(bg=RED if tool == "eraser" else BG_RAISED,
                                  fg="#FFFFFF" if tool == "eraser" else TEXT_DIM)

    def _draw_grid(self):
        cv = self.canvas
        cv.delete("all")
        cell = self.cell
        for y in range(self.SIZE):
            for x in range(self.SIZE):
                px = self.grid[y][x]
                if px:
                    color = "#%02X%02X%02X" % (px[0], px[1], px[2])
                    cv.create_rectangle(x * cell, y * cell,
                                        (x + 1) * cell, (y + 1) * cell,
                                        fill=color, width=0)
        for i in range(self.SIZE + 1):
            cv.create_line(i * cell, 0, i * cell, self.SIZE * cell,
                           fill="#202D3A")
            cv.create_line(0, i * cell, self.SIZE * cell, i * cell,
                           fill="#202D3A")

    def _paint(self, evt, erase=False):
        x = int(evt.x // self.cell)
        y = int(evt.y // self.cell)
        if not (0 <= x < self.SIZE and 0 <= y < self.SIZE):
            return
        # one undo snapshot per stroke, not per pixel — a drag would
        # otherwise flood the undo stack with copies of the whole grid
        if not getattr(self, "_stroke_saved", True):
            self._push_undo()
            self._stroke_saved = True
        targets = [(x, y)]
        if self.mirror_x:
            targets.append((self.SIZE - 1 - x, y))
        if self.mirror_y:
            targets.append((x, self.SIZE - 1 - y))
        if self.mirror_x and self.mirror_y:
            targets.append((self.SIZE - 1 - x, self.SIZE - 1 - y))
        for tx, ty in targets:
            if erase or self.tool == "eraser":
                self.grid[ty][tx] = None
            else:
                h = self.color.lstrip("#")
                self.grid[ty][tx] = (int(h[0:2], 16), int(h[2:4], 16),
                                     int(h[4:6], 16), 255)
                self._remember_color(self.color)
        self._draw_grid()

    def _press(self, evt):
        self._drawing = True
        self._stroke_saved = False
        self._paint(evt)

    def _drag(self, evt):
        if self._drawing:
            self._paint(evt)

    def _clear(self):
        self._push_undo()
        self.grid = [[None] * self.SIZE for _ in range(self.SIZE)]
        self._draw_grid()

    def _save(self):
        import io, base64
        from PIL import Image
        img = Image.new("RGBA", (self.SIZE, self.SIZE), (0, 0, 0, 0))
        px = img.load()
        for y in range(self.SIZE):
            for x in range(self.SIZE):
                if self.grid[y][x]:
                    px[x, y] = self.grid[y][x]
        buf = io.BytesIO()
        img.save(buf, "PNG")
        self.on_save(base64.b64encode(buf.getvalue()).decode("ascii"))
        self.destroy()
