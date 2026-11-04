"""Valtix GUI — design system (Redesign Prototype).

"Signal" theme: deep charcoal-navy surfaces, warm orange identity accent,
violet secondary accent. Applied to ttk widgets plus shared helpers.

NOTE ON NAMES: tokens keep their historical names (RED, TEAL, ...) so every
tab inherits the palette without code churn. In this redesign:
RED      → the ORANGE primary identity accent (#FF7A1A)
TEAL     → the positive/success status colour (#35C98A)
PURPLE   → new secondary accent (#8B5CF6)
"""
from __future__ import annotations

import tkinter.font as tkfont
from tkinter import ttk

# ── palette ────────────────────────────────────────────────────
BG        = "#0B0D12"   # window background
BG_RAISED = "#10141D"   # sidebar / header
CARD      = "#151B27"   # card background
CARD_HI   = "#1B2331"   # elevated surface / hover
LINE      = "#252D3A"   # hairline borders
LINE_SOFT = "#1B2230"

TEXT      = "#F5F7FA"   # primary text

# ── theme variants (selected in Settings → UI theme; needs restart) ──
# Tokens are imported by name everywhere, so variants rebind the accent
# globals at import time based on the saved setting.
_VARIANTS = {
    "signal": {"RED": "#FF7A1A", "RED_DARK": "#B85A10", "RED_SOFT": "#FFA552",
               "ORANGE": "#FF7A1A",
               "GRAD_RULE": ["#FF7A1A", "#8B5CF6", "#35C98A"]},
    "classic": {"RED": "#FF4655", "RED_DARK": "#B8323E", "RED_SOFT": "#FF8A94",
                "ORANGE": "#FF9C41", "GRAD_RULE": ["#141F2A", "#FF4655", "#141F2A"]},
    "violet": {"RED": "#8B5CF6", "RED_DARK": "#5B3FA8", "RED_SOFT": "#C4B1FA",
               "ORANGE": "#A78BFA",
               "GRAD_RULE": ["#10141D", "#8B5CF6", "#10141D"]},
}


def _active_variant() -> str:
    try:
        data_dir = _os.environ.get("VALTIX_DATA_DIR") or _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)), "..", "backend", "data")
        with open(_os.path.join(data_dir, "settings.json"), "r",
                  encoding="utf-8") as f:
            v = _json.load(f).get("uiTheme", "signal")
        return v if v in _VARIANTS else "signal"
    except Exception:
        return "signal"


def _apply_variant_overrides():
    set_variant(_active_variant())


def set_variant(name: str) -> None:
    """Rebind the accent tokens live (no restart needed)."""
    if name not in _VARIANTS:
        name = "signal"
    for key, val in _VARIANTS[name].items():
        globals()[key] = val


import os as _os
import json as _json

TEXT      = "#F5F7FA"   # primary text
TEXT_DIM  = "#929CAC"   # secondary text
TEXT_FAINT= "#5A6475"   # tertiary text

RED       = "#FF7A1A"   # PRIMARY identity accent (orange signal)
RED_DARK  = "#B85A10"
RED_SOFT  = "#FFA552"
PURPLE    = "#8B5CF6"   # secondary accent
PURPLE_DIM= "#4A3A78"
PURPLE_SOFT = "#C4B1FA"
TEAL      = "#35C98A"   # positive status
TEAL_DIM  = "#17754F"
AMBER     = "#F5B942"   # warning status
ORANGE    = "#FF7A1A"
BLUE      = "#5AA7E8"

WIN      = "#35C98A"
LOSS     = "#F05C67"
DRAW     = "#929CAC"

_apply_variant_overrides()   # rebind accents per the saved uiTheme

FAMILY_MAIN = "Segoe UI"
FAMILY_MONO = "Consolas"


def rgb(hexcolor: str) -> tuple[int, int, int]:
    h = hexcolor.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """Blend two hex colors (t=0 → a, t=1 → b)."""
    r1, g1, b1 = rgb(a)
    r2, g2, b2 = rgb(b)
    return "#{:02X}{:02X}{:02X}".format(
        round(r1 + (r2 - r1) * t),
        round(g1 + (g2 - g1) * t),
        round(b1 + (b2 - b1) * t))


def shade(color: str, factor: float) -> str:
    """Lighten (>0) or darken (<0) a hex color."""
    if factor >= 0:
        return mix(color, "#FFFFFF", factor)
    return mix(color, "#000000", -factor)


def alpha_hex(color: str, alpha: int) -> str:
    """Blend color over the app background to fake alpha (canvas has no RGBA)."""
    return mix(color, BG, 1.0 - alpha / 255.0)


def readable(color: str, threshold: float = 0.42) -> str:
    """Lighten a text color until it is legible on the dark background."""
    try:
        r, g, b = rgb(color)
    except (ValueError, AttributeError, TypeError):
        return TEXT
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum < threshold:
        return mix(color, "#FFFFFF", min(0.8, threshold - lum + 0.18))
    return color


def apply(root) -> dict:
    """Apply the theme to a Tk root/toplevel. Returns the fonts dict."""
    fonts = {
        "h1": tkfont.Font(family=FAMILY_MAIN, size=17, weight="bold"),
        "h2": tkfont.Font(family=FAMILY_MAIN, size=13, weight="bold"),
        "h3": tkfont.Font(family=FAMILY_MAIN, size=11, weight="bold"),
        "base": tkfont.Font(family=FAMILY_MAIN, size=10),
        "small": tkfont.Font(family=FAMILY_MAIN, size=9),
        "tiny": tkfont.Font(family=FAMILY_MAIN, size=8),
        "mono": tkfont.Font(family=FAMILY_MONO, size=10),
        "mono_small": tkfont.Font(family=FAMILY_MONO, size=9),
        "brand": tkfont.Font(family=FAMILY_MAIN, size=15, weight="bold"),
        "big": tkfont.Font(family=FAMILY_MAIN, size=22, weight="bold"),
    }

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    root.configure(background=BG)
    root.option_add("*Font", fonts["base"])
    root.option_add("*Foreground", TEXT)

    style.configure(".", background=BG, foreground=TEXT, borderwidth=0,
                    focuscolor=RED)

    # frames
    style.configure("Card.TFrame", background=CARD, relief="flat")
    style.configure("CardHi.TFrame", background=CARD_HI, relief="flat")
    style.configure("Bg.TFrame", background=BG)
    style.configure("Raised.TFrame", background=BG_RAISED)
    style.configure("Inset.TFrame", background=BG_RAISED)

    # labels
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Dim.TLabel", background=BG, foreground=TEXT_DIM)
    style.configure("CardDim.TLabel", background=CARD, foreground=TEXT_DIM)
    style.configure("Faint.TLabel", background=BG, foreground=TEXT_FAINT)
    style.configure("CardFaint.TLabel", background=CARD, foreground=TEXT_FAINT)
    style.configure("Accent.TLabel", background=BG, foreground=RED)
    style.configure("CardAccent.TLabel", background=CARD, foreground=RED)
    style.configure("CardH2.TLabel", background=CARD, foreground=TEXT,
                    font=fonts["h3"])
    style.configure("Win.TLabel", background=CARD, foreground=WIN)
    style.configure("Loss.TLabel", background=CARD, foreground=LOSS)

    # buttons
    style.configure("TButton", background=CARD_HI, foreground=TEXT,
                    borderwidth=0, focusthickness=0, padding=(14, 7))
    style.map("TButton",
              background=[("pressed", shade(CARD_HI, -0.15)),
                          ("active", shade(CARD_HI, 0.1))],
              foreground=[("disabled", TEXT_FAINT)])
    style.configure("Accent.TButton", background=RED, foreground="#FFFFFF",
                    borderwidth=0, focusthickness=0, padding=(16, 8),
                    font=fonts["h3"])
    style.map("Accent.TButton",
              background=[("disabled", RED_DARK),
                          ("pressed", shade(RED, -0.2)),
                          ("active", shade(RED, 0.12))])
    style.configure("Ghost.TButton", background=BG_RAISED, foreground=TEXT_DIM,
                    borderwidth=0, focusthickness=0, padding=(10, 6))
    style.map("Ghost.TButton",
              background=[("pressed", shade(BG_RAISED, -0.2)),
                          ("active", shade(BG_RAISED, 0.12))],
              foreground=[("disabled", TEXT_FAINT)])
    style.configure("Danger.TButton", background=mix(LOSS, BG, 0.82),
                    foreground=RED_SOFT,
                    borderwidth=0, focusthickness=0, padding=(10, 6))
    style.map("Danger.TButton",
              background=[("active", mix(LOSS, BG, 0.72)),
                          ("pressed", mix(LOSS, BG, 0.88))])
    style.configure("Success.TButton", background=TEAL_DIM, foreground="#E9FFF6",
                    borderwidth=0, focusthickness=0, padding=(12, 7))
    style.map("Success.TButton",
              background=[("active", shade(TEAL_DIM, 0.15)),
                          ("pressed", shade(TEAL_DIM, -0.2))])
    style.configure("Purple.TButton", background=PURPLE_DIM, foreground=PURPLE_SOFT,
                    borderwidth=0, focusthickness=0, padding=(12, 7))
    style.map("Purple.TButton",
              background=[("active", shade(PURPLE_DIM, 0.15)),
                          ("pressed", shade(PURPLE_DIM, -0.2))])

    # combobox
    style.configure("TCombobox", fieldbackground=CARD_HI, background=CARD_HI,
                    foreground=TEXT, arrowcolor=TEXT_DIM, borderwidth=0,
                    lightcolor=CARD_HI, darkcolor=CARD_HI, padding=6)
    style.map("TCombobox",
              fieldbackground=[("readonly", CARD_HI), ("active", CARD_HI)],
              background=[("readonly", CARD_HI), ("active", CARD_HI)],
              foreground=[("readonly", TEXT)])
    root.option_add("*TCombobox*Listbox.Background", CARD_HI)
    root.option_add("*TCombobox*Listbox.Foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", RED)
    root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

    # scrollbars
    style.configure("Vertical.TScrollbar", background=CARD_HI,
                    troughcolor=BG, borderwidth=0, arrowcolor=TEXT_DIM,
                    gripcount=0, width=10)
    style.map("Vertical.TScrollbar",
              background=[("active", shade(CARD_HI, 0.15))])
    style.configure("Horizontal.TScrollbar", background=CARD_HI,
                    troughcolor=BG, borderwidth=0, arrowcolor=TEXT_DIM,
                    gripcount=0, width=10)
    style.map("Horizontal.TScrollbar",
              background=[("active", shade(CARD_HI, 0.15))])

    # entries
    style.configure("TEntry", fieldbackground=CARD_HI, foreground=TEXT,
                    insertcolor=TEXT, borderwidth=0, lightcolor=LINE,
                    darkcolor=LINE, padding=6)
    style.map("TEntry", lightcolor=[("focus", RED)], darkcolor=[("focus", RED)])

    # text
    style.configure("TText", background=BG_RAISED, foreground=TEXT,
                    borderwidth=0)

    # progressbar
    style.configure("Accent.Horizontal.TProgressbar", background=RED,
                    troughcolor=BG_RAISED, borderwidth=0, thickness=6)
    style.configure("Teal.Horizontal.TProgressbar", background=TEAL,
                    troughcolor=BG_RAISED, borderwidth=0, thickness=6)
    style.configure("Purple.Horizontal.TProgressbar", background=PURPLE,
                    troughcolor=BG_RAISED, borderwidth=0, thickness=6)

    # notebook (used by dialogs / detail windows)
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=TEXT_DIM,
                    padding=(16, 8), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", CARD)],
              foreground=[("selected", TEXT)])
    return fonts


# ── gradients (used by GradientFrame and canvas composites) ─────
GRAD_SIDEBAR = ["#10141D", "#0B0D12"]              # vertical, subtle
GRAD_HEADER  = ["#12161F", "#0D1017"]              # horizontal
GRAD_RULE    = ["#FF7A1A", "#8B5CF6", "#35C98A"]   # brand accent rule
GRAD_HERO    = ["#2B1A10", "#151B27", "#0B0D12"]   # diagonal-ish hero fallback
GRAD_CARD    = ["#1A2230", "#141A25"]
GRAD_WIN     = ["#1E5A3C", "#35C98A"]
GRAD_LOSS    = ["#5A1E28", "#F05C67"]
GRAD_STATUS  = ["#10141D", "#0B0D12"]


def multi_stop(stops: "list[str]", t: float) -> str:
    """Sample a multi-stop color ramp at t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    seg = t * (len(stops) - 1)
    j = min(int(seg), len(stops) - 2)
    return mix(stops[j], stops[j + 1], seg - j)
