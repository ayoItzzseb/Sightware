"""Crosshair Overlay — drawing.

``draw_crosshair`` paints the active config into a ``tk.Canvas`` — used
identically by the tab's live preview and the click-through overlay windows.
Cross / circle / dot are native canvas shapes; pixel art and imported PNGs go
through Pillow (recolor with alpha preserved, then scale).
"""
from __future__ import annotations

import base64
import io
import binascii

import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk
    _PIL = True
except ImportError:   # pragma: no cover — Pillow ships in requirements
    Image = ImageDraw = ImageTk = None
    _PIL = False

PIXEL_SIZE = 32  # pixel-art grid the editor draws on
SS = 6           # supersampling factor for antialiased vector crosshairs


def _hex8(color: str, fallback: str = "#FFFFFFFF") -> str:
    """Normalize any tint the editor stored into #RRGGBBAA."""
    c = str(color or "").strip()
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h) + "FF"
        if len(h) == 6:
            h += "FF"
        if len(h) == 8:
            try:
                int(h, 16)
                return "#" + h.upper()
            except ValueError:
                pass
    return fallback


def _rgba(color: str) -> tuple[int, int, int, int]:
    h = _hex8(color).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)


def _paint(color: str) -> dict:
    """tk canvas paint options for a #RRGGBBAA tint.

    tk has no 8-bit alpha on canvas items, and the overlay window uses a
    chroma key — so translucency is dithered: stipple patterns leave "off"
    pixels in the transparent-key color, which fall through to the game.
    (On opaque surfaces like the preview, stipple blends against the card
    background and reads as the same translucency.)
    """
    r, g, b, a = _rgba(color)
    if a <= 8:
        return {"fill": "", "outline": "", "width": 0}
    stipple = None
    if a < 64:
        stipple = "gray25"
    elif a < 192:
        stipple = "gray50"
    elif a < 255:
        stipple = "gray75"
    out = {"fill": f"#{r:02X}{g:02X}{b:02X}",
           "outline": "", "width": 0}
    if stipple:
        out["stipple"] = stipple
    return out


# ── geometry ───────────────────────────────────────────────────

def config_extent(cfg: dict) -> tuple[int, int]:
    """Half-extent (x, y) the crosshair needs around its center, in px."""
    c = cfg.get("crosshair", {})
    style = c.get("style", "cross")
    gap = float(c.get("gap", 0) or 0)
    length = float(c.get("length", 0) or 0)
    thickness = max(float(c.get("thickness", 1) or 1), 1)
    outline = max(float(c.get("outline", {}).get("thickness", 0) or 0), 0)
    dot = c.get("dot", {}) or {}
    dot_size = max(float(dot.get("size", 0) or 0), 0)
    dot_o = max(float(dot.get("outline", {}).get("thickness", 0) or 0), 0)
    dot_r = (dot_size + dot_o) / 2 if dot_size > 0 else 0

    if style in ("circle", "arc"):
        radius = gap + thickness / 2
        r = radius + thickness / 2 + outline / 2
        ext = max(r, dot_r)
        return ext + 2, ext + 2
    if style == "cross":
        ex = gap + length + outline / 2
        return max(ex, dot_r) + 2, max(ex, dot_r) + 2
    # pixels / custom: image handles its own size
    return 128, 128


def _canvas_dot(cv, cx, cy, dot, ) -> None:
    size = float(dot.get("size", 0) or 0)
    if size <= 0:
        return
    tint = _paint(dot.get("tint", "#FFFFFFFF"))
    o_t = max(float(dot.get("outline", {}).get("thickness", 0) or 0), 0)
    o_c = _paint(dot.get("outline", {}).get("tint", "#000000FF"))
    if o_t > 0:
        if dot.get("style") == "square":
            cv.create_rectangle(cx - size / 2 - o_t / 2, cy - size / 2 - o_t / 2,
                                cx + size / 2 + o_t / 2, cy + size / 2 + o_t / 2,
                                **o_c)
        else:
            cv.create_oval(cx - size / 2 - o_t / 2, cy - size / 2 - o_t / 2,
                           cx + size / 2 + o_t / 2, cy + size / 2 + o_t / 2,
                           **o_c)
    if dot.get("style") == "square":
        cv.create_rectangle(cx - size / 2, cy - size / 2,
                            cx + size / 2, cy + size / 2, **tint)
    else:
        cv.create_oval(cx - size / 2, cy - size / 2,
                       cx + size / 2, cy + size / 2, **tint)


def draw_crosshair(cv: tk.Canvas, cx: float, cy: float, cfg: dict,
                   image_holder: list | None = None) -> None:
    """Paint the crosshair centered at (cx, cy). image_holder keeps
    PhotoImage references alive across redraws."""
    c = cfg.get("crosshair", {})
    style = c.get("style", "cross")

    if style in ("pixels", "custom"):
        photo = make_image_photo(cfg)
        if photo is not None:
            if image_holder is not None:
                image_holder.append(photo)
            cv.create_image(cx, cy, image=photo)
        return

    if style in ("cross", "circle"):
        photo = make_vector_photo(cfg)
        if photo is not None:
            if image_holder is not None:
                image_holder.append(photo)
            cv.create_image(round(cx), round(cy), image=photo)
            return
        # no Pillow: crisp (but hard-edged) canvas fallback below

    _draw_crosshair_canvas(cv, cx, cy, cfg)


def make_vector_photo(cfg: dict):
    """Antialiased PhotoImage for cross / circle styles.

    Geometry is drawn at SS× resolution with Pillow and downscaled, giving
    smooth edges and true per-pixel alpha (no stipple dithering). Semi-
    transparent pixels composite over the overlay's chroma key, so they
    render as a solid blended color instead of a checkerboard — much cleaner
    than dithering over both the preview and the game.
    """
    if not _PIL:
        return None
    c = cfg.get("crosshair", {})
    if c.get("style") not in ("cross", "circle", "arc"):
        return None

    gap = float(c.get("gap", 0) or 0)
    length = float(c.get("length", 0) or 0)
    # sub-pixel thickness is supported: SSx supersampling + AA render it
    thickness = max(float(c.get("thickness", 1) or 0), 0.1)
    tint = _rgba(c.get("tint", "#FFFFFFFF"))
    lines = c.get("lines", [True, True, True, True])
    up, down, left, right = (bool(x) for x in (list(lines) + [True] * 4)[:4])
    outline = c.get("outline", {}) or {}
    o_t = max(float(outline.get("thickness", 0) or 0), 0)
    o_c = _rgba(outline.get("tint", "#000000FF"))
    dot = c.get("dot", {}) or {}
    dot_size = max(float(dot.get("size", 0) or 0), 0)
    dot_shape = dot.get("style") == "square"
    dot_tint = _rgba(dot.get("tint", "#FFFFFFFF"))
    dot_o = max(float(dot.get("outline", {}).get("thickness", 0) or 0), 0)
    dot_oc = _rgba(dot.get("outline", {}).get("tint", "#000000FF"))
    dot_r = (dot_size + dot_o) / 2 if dot_size > 0 else 0

    style = c.get("style")
    if style in ("circle", "arc"):
        radius = gap + thickness / 2
        ext = radius + thickness / 2 + o_t / 2
    else:
        ext = gap + length + o_t / 2
    ext = max(ext, dot_r)
    pad = 3
    size = int(ext * 2) + pad * 2
    if size < 8:
        size = 8
    cx = cy = size / 2

    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def rect(x1, y1, x2, y2, color):
        # Snap edges to the final-pixel grid (round one edge, derive the size)
        # so small crosshairs render crisp instead of smeared across
        # fractional pixels. Circles keep their supersampled AA.
        X1 = round(cx + x1)
        Y1 = round(cy + y1)
        X2 = X1 + max(round(x2 - x1), 1)
        Y2 = Y1 + max(round(y2 - y1), 1)
        d.rectangle([X1 * SS, Y1 * SS, X2 * SS, Y2 * SS], fill=color)

    def ring(R, W, color):
        # Pillow strokes ellipses INWARD from the bbox; expand the bbox by
        # W/2 so the stroke is centered on radius R (spanning R ± W/2).
        outer = R + W / 2
        d.ellipse([(cx - outer) * SS, (cy - outer) * SS,
                   (cx + outer) * SS, (cy + outer) * SS],
                  outline=color, width=max(int(round(W * SS)), 1))

    def arc(R, W, color, sweep_deg):
        """Ring segment centred on the top of the circle (12 o'clock),
        sweeping `sweep_deg` degrees symmetrically."""
        outer = R + W / 2
        half = max(min(float(sweep_deg), 360), 20) / 2
        bbox = [(cx - outer) * SS, (cy - outer) * SS,
                (cx + outer) * SS, (cy + outer) * SS]
        d.arc(bbox, start=270 - half, end=270 + half,
              fill=color, width=max(int(round(W * SS)), 1))

    def dot_pass():
        if dot_size <= 0:
            return
        if dot_o > 0:
            ro = dot_size / 2 + dot_o / 2
            if dot_shape:
                rect(-ro, -ro, ro, ro, dot_oc)
            else:
                d.ellipse([(cx - ro) * SS, (cy - ro) * SS, (cx + ro) * SS, (cy + ro) * SS],
                          fill=dot_oc)
        if dot_shape:
            rect(-dot_size / 2, -dot_size / 2, dot_size / 2, dot_size / 2, dot_tint)
        else:
            d.ellipse([(cx - dot_size / 2) * SS, (cy - dot_size / 2) * SS,
                       (cx + dot_size / 2) * SS, (cy + dot_size / 2) * SS],
                      fill=dot_tint)

    if style in ("circle", "arc"):
        sweep = float(c.get("arcSweep", 270) or 270)
        if o_t > 0:
            # outline centered on the same radius, wide enough to surround the
            # main ring by o_t/2 on both sides — it must hug, not float outside
            if style == "arc":
                arc(radius, thickness + o_t, o_c, sweep)
            else:
                ring(radius, thickness + o_t, o_c)
        if style == "arc":
            arc(radius, thickness, tint, sweep)
        else:
            ring(radius, thickness, tint)
        dot_pass()
    else:
        t = thickness

        # Snap the FILL rects to the pixel grid first, then derive outlines
        # as expansions of the snapped fills — guarantees symmetric, crisp
        # borders even at 1–2 px sizes.
        def snap_v(y_start, y_end):
            X1 = round(cx - t / 2)
            X2 = X1 + max(round(t), 1)
            Y1 = round(cy + y_start)
            Y2 = round(cy + y_end)
            if Y2 <= Y1:
                Y2 = Y1 + 1
            return X1, Y1, X2, Y2

        def snap_h(x_start, x_end):
            Y1 = round(cy - t / 2)
            Y2 = Y1 + max(round(t), 1)
            X1 = round(cx + x_start)
            X2 = round(cx + x_end)
            if X2 <= X1:
                X2 = X1 + 1
            return X1, Y1, X2, Y2

        fills = []
        if up:
            fills.append(snap_v(-gap - length, -gap))
        if down:
            fills.append(snap_v(gap, gap + length))
        if left:
            fills.append(snap_h(-gap - length, -gap))
        if right:
            fills.append(snap_h(gap, gap + length))

        def draw(r, color):
            d.rectangle([r[0] * SS, r[1] * SS, r[2] * SS, r[3] * SS], fill=color)

        if o_t > 0:
            # game semantics: the outline band is the FULL outline thickness
            # on each side of the fill (per the CrosshairSVG reference)
            e = max(int(round(o_t)), 1)
            for (X1, Y1, X2, Y2) in fills:
                draw((X1 - e, Y1 - e, X2 + e, Y2 + e), o_c)
        for r in fills:
            draw(r, tint)
        dot_pass()

    img = img.resize((size, size), Image.BOX)  # area average: AA without Lanczos ringing
    return ImageTk.PhotoImage(img)


def _draw_crosshair_canvas(cv: tk.Canvas, cx: float, cy: float, cfg: dict) -> None:
    """Hard-edged canvas fallback (used only when Pillow is unavailable)."""
    c = cfg.get("crosshair", {})
    style = c.get("style", "cross")
    gap = float(c.get("gap", 0) or 0)
    length = float(c.get("length", 0) or 0)
    thickness = max(float(c.get("thickness", 1) or 1), 1)
    tint = _paint(c.get("tint", "#FFFFFFFF"))
    lines = c.get("lines", [True, True, True, True])
    outline = c.get("outline", {}) or {}
    o_t = max(float(outline.get("thickness", 0) or 0), 0)
    o_c = _paint(outline.get("tint", "#000000FF"))

    if style == "circle":
        radius = gap + thickness / 2
        if o_t > 0:
            ow = thickness + o_t
            oopts = {"outline": o_c.get("fill", "")}
            if o_c.get("stipple"):
                oopts["stipple"] = o_c["stipple"]
            cv.create_oval(cx - radius - ow / 2, cy - radius - ow / 2,
                           cx + radius + ow / 2, cy + radius + ow / 2,
                           width=max(int(round(ow)), 1), **oopts)
        topts = {"outline": tint.get("fill", "")}
        if tint.get("stipple"):
            topts["stipple"] = tint["stipple"]
        cv.create_oval(cx - radius - thickness / 2, cy - radius - thickness / 2,
                       cx + radius + thickness / 2, cy + radius + thickness / 2,
                       width=max(int(round(thickness)), 1), **topts)
        _canvas_dot(cv, cx, cy, c.get("dot", {}) or {})
        return
        _canvas_dot(cv, cx, cy, c.get("dot", {}) or {})
        return

    # cross — outline pass first (behind), then the fill pass
    up, down, left, right = (bool(x) for x in (list(lines) + [True] * 4)[:4])
    if o_t > 0:
        ot = thickness + o_t
        if up:
            cv.create_rectangle(cx - ot / 2, cy - gap - length - o_t / 2,
                                cx + ot / 2, cy - gap + o_t / 2, **o_c)
        if down:
            cv.create_rectangle(cx - ot / 2, cy + gap - o_t / 2,
                                cx + ot / 2, cy + gap + length + o_t / 2,
                                **o_c)
        if left:
            cv.create_rectangle(cx - gap - length - o_t / 2, cy - ot / 2,
                                cx - gap + o_t / 2, cy + ot / 2, **o_c)
        if right:
            cv.create_rectangle(cx + gap - o_t / 2, cy - ot / 2,
                                cx + gap + length + o_t / 2, cy + ot / 2,
                                **o_c)
    t = thickness
    if up:
        cv.create_rectangle(cx - t / 2, cy - gap - length, cx + t / 2, cy - gap,
                            **tint)
    if down:
        cv.create_rectangle(cx - t / 2, cy + gap, cx + t / 2, cy + gap + length,
                            **tint)
    if left:
        cv.create_rectangle(cx - gap - length, cy - t / 2, cx - gap, cy + t / 2,
                            **tint)
    if right:
        cv.create_rectangle(cx + gap, cy - t / 2, cx + gap + length, cy + t / 2,
                            **tint)
    _canvas_dot(cv, cx, cy, c.get("dot", {}) or {})


# ── Pillow image pipeline (pixels + custom) ────────────────────

def _recolor(img: Image.Image, tint: str) -> Image.Image:
    """Solid-color tint that keeps the source alpha channel."""
    r, g, b, a = _rgba(tint)
    if a >= 255 and (r, g, b) == (255, 255, 255):
        return img
    alpha = img.getchannel("A")
    solid = Image.new("RGBA", img.size, (r, g, b, a))
    solid.putalpha(alpha.point(lambda v: v * a // 255))
    return solid


def make_image_photo(cfg: dict, size_cache: dict | None = None):
    """PhotoImage for pixels / custom styles; None when there is nothing to show."""
    if not _PIL:
        return None
    c = cfg.get("crosshair", {})
    style = c.get("style")
    try:
        if style == "pixels":
            data = (cfg.get("pixels", {}) or {}).get("data", "")
            if not data:
                return None
            raw = base64.b64decode(data)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            size = int((cfg.get("pixels", {}) or {}).get("size", PIXEL_SIZE) or PIXEL_SIZE)
            if img.size != (size, size):
                img = img.resize((size, size), Image.NEAREST)
            scale = float((cfg.get("pixels", {}) or {}).get("scale", 1) or 1)
            tint = (cfg.get("pixels", {}) or {}).get("tint", "#FFFFFFFF")
        elif style == "custom":
            from crosshair_store import custom_png_path
            path = custom_png_path((cfg.get("custom", {}) or {}).get("path", ""))
            if not os_isfile(path):
                return None
            with open(path, "rb") as f:
                img = Image.open(io.BytesIO(f.read())).convert("RGBA")
            scale = float((cfg.get("custom", {}) or {}).get("scale", 1) or 1)
            tint = (cfg.get("custom", {}) or {}).get("tint", "#FFFFFFFF")
        else:
            return None
    except (binascii.Error, OSError, ValueError, KeyError):
        return None

    img = _recolor(img, tint)
    if scale != 1.0:
        w = max(round(img.width * scale), 1)
        h = max(round(img.height * scale), 1)
        kernel = Image.NEAREST if style == "pixels" else (
            Image.LANCZOS if (cfg.get("custom", {}) or {}).get("filter") != "nearest"
            else Image.NEAREST)
        img = img.resize((w, h), kernel)
    return ImageTk.PhotoImage(img)


def os_isfile(path: str) -> bool:
    import os
    return os.path.isfile(path)
