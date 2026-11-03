"""Valtix GUI — dark theme & design tokens.

A hand-crafted VALORANT-inspired palette (deep slate blue + signature red)
applied to ttk widgets plus helpers used across the app.
"""
from __future__ import annotations

import tkinter.font as tkfont
from tkinter import ttk

# ── palette ────────────────────────────────────────────────────
BG        = "#0F1923"   # window background (VALORANT dark navy)
BG_RAISED = "#14212D"   # sidebar / header
CARD      = "#16222E"   # card background
CARD_HI   = "#1B2B39"   # card hover
LINE      = "#26343F"   # hairline borders
LINE_SOFT = "#1D2A35"

TEXT      = "#ECE8E1"   # primary text
TEXT_DIM  = "#8B978F"   # secondary text
TEXT_FAINT= "#5F6E6A"   # tertiary text

RED       = "#FF4655"   # Valtix accent
RED_DARK  = "#B8323E"
RED_SOFT  = "#FF8A94"
TEAL      = "#18E2B2"   # success / live
TEAL_DIM  = "#0E8A6C"
AMBER     = "#F5C542"   # warnings
ORANGE    = "#FF9C41"
BLUE      = "#57B4E8"

WIN      = "#3BA55D"
LOSS     = "#E34343"
DRAW     = "#8B978F"

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
    """Lighten a text color until it is legible on the dark background
    (some agent palette colors, e.g. Omen's #47508F, are near-invisible)."""
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
    style.configure("Danger.TButton", background="#2A1B20", foreground=RED_SOFT,
                    borderwidth=0, focusthickness=0, padding=(10, 6))
    style.map("Danger.TButton",
              background=[("active", "#3A2129"), ("pressed", "#241419")])
    style.configure("Success.TButton", background=TEAL_DIM, foreground="#D9FFF3",
                    borderwidth=0, focusthickness=0, padding=(12, 7))
    style.map("Success.TButton",
              background=[("active", shade(TEAL_DIM, 0.15)),
                          ("pressed", shade(TEAL_DIM, -0.2))])

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

    # notebook (used by dialogs / detail windows)
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=TEXT_DIM,
                    padding=(16, 8), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", CARD)],
              foreground=[("selected", TEXT)])
    return fonts


# ── gradients (used by GradientFrame and canvas composits) ─────
GRAD_SIDEBAR = ["#16232F", "#101B24"]          # vertical, subtle
GRAD_HEADER  = ["#1A2531", "#141F2A"]          # horizontal
GRAD_RULE    = ["#FF4655", "#C6447A", "#18E2B2"]  # brand accent rule
GRAD_HERO    = ["#3A1620", "#16222E", "#101A23"]  # diagonal-ish hero fallback
GRAD_CARD    = ["#1A2936", "#151F2A"]
GRAD_WIN     = ["#1E5A3C", "#3BA55D"]
GRAD_LOSS    = ["#5A1E28", "#E34343"]
GRAD_STATUS  = ["#121C26", "#0D151D"]


def multi_stop(stops: "list[str]", t: float) -> str:
    """Sample a multi-stop color ramp at t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    seg = t * (len(stops) - 1)
    j = min(int(seg), len(stops) - 2)
    return mix(stops[j], stops[j + 1], seg - j)
