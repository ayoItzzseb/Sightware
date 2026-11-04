"""VALORANT crosshair share-code codec.

Parses the community-documented semicolon format, e.g.
    0;P;c;5;o;1;d;1;z;3;f;0;0t;1;0l;3;0o;2;0a;1;0f;0;1b;0
into Valtix's crosshair config (and back). Pure string work — no game
interaction of any kind.

Colour index mapping (in-game colour picker order):
    0 white · 1 green · 2 yellow · 3 orange · 4 pink · 5 cyan · 6 red · 7 purple
Outer-line keys (1t/1l/1o/1a) have no equivalent in Valtix's single-ring
model and are ignored on import.
"""
from __future__ import annotations

COLORS = ["#FFFFFF", "#00FF66", "#FFFF00", "#FF9C41",
          "#FF6EC7", "#35E2E2", "#FF4655", "#8B5CF6"]

_BASE = {
    "crosshair": {
        "style": "cross", "gap": 2, "length": 4, "thickness": 2,
        "tint": "#FFFFFFFF", "lines": [True, True, True, True],
        "outline": {"thickness": 2, "tint": "#000000FF"},
        "dot": {"style": "circle", "size": 0, "tint": "#FFFFFFFF",
                "outline": {"thickness": 0, "tint": "#000000FF"}},
    },
    "custom": {"path": "-", "filter": "linear", "scale": 1.0,
               "tint": "#FFFFFFFF"},
    "pixels": {"data": "", "size": 32, "scale": 1.0, "tint": "#FFFFFFFF"},
}


def _rgba_to_hex8(r, g, b, a=255):
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}{int(a):02X}"


def _hex8_rgb(tint: str):
    h = str(tint or "").lstrip("#")
    if len(h) >= 6:
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            pass
    return 255, 255, 255


def _hex8_alpha(tint: str) -> int:
    h = str(tint or "").lstrip("#")
    if len(h) == 8:
        try:
            return int(h[6:8], 16)
        except ValueError:
            return 255
    return 255


def decode(code: str) -> dict | None:
    """Share code → config dict, or None if the code is not parseable."""
    if not code:
        return None
    parts = [p.strip() for p in str(code).replace("\n", ";").split(";") if p.strip() != ""]
    if len(parts) < 4 or parts[0] != "0":
        return None
    kv = {}
    # '0;P;' prefix (profile slot + primary weapon), then key;value pairs
    start = 2 if len(parts) > 2 and parts[1] in ("P", "S") else 1
    for i in range(start, len(parts) - 1, 2):
        kv[parts[i]] = parts[i + 1]

    def num(key, default):
        try:
            return float(kv.get(key, default))
        except (TypeError, ValueError):
            return default

    import copy
    cfg = copy.deepcopy(_BASE)
    c = cfg["crosshair"]

    idx = int(num("c", 0))
    if 0 <= idx < len(COLORS):
        c["tint"] = COLORS[idx] + "FF"

    # Valtix has one ring of lines; VALORANT has inner (0*) AND outer (1*).
    # Prefer the inner set when it is visible, otherwise fall back to the
    # outer set — many real codes are outer-line-only.
    inner_alpha = max(num("0a", 1), 0)
    inner_len = num("0l", 0)
    outer_alpha = max(num("1a", 0), 0)
    outer_len = num("1l", 0)

    if inner_alpha > 0 and inner_len > 0:
        src = ("0t", "0l", "0o", inner_alpha)
    elif outer_alpha > 0 and outer_len > 0:
        src = ("1t", "1l", "1o", outer_alpha)
    else:
        src = None

    if src is not None:
        kt, kl, ko, ka = src
        c["thickness"] = max(num(kt, 2), 0.1)
        c["length"] = max(num(kl, 4), 0)
        c["gap"] = max(num(ko, 2), 0)
        r, g, b = _hex8_rgb(c["tint"])
        c["tint"] = _rgba_to_hex8(r, g, b, int(ka * 255))
        c["lines"] = [True, True, True, True]
    else:
        c["lines"] = [False, False, False, False]

    # outlines: o is outline opacity (0-1)
    o = max(num("o", 0), 0)
    c["outline"]["thickness"] = 2 if o > 0 else 0
    c["outline"]["tint"] = "#000000FF" if o > 0 else "#00000000"

    # center dot: d is dot opacity (0-1), z is dot size
    d_op = num("d", 0)
    z = num("z", 0)
    if d_op > 0 and z > 0:
        c["dot"]["size"] = max(z, 1)
        c["dot"]["tint"] = _rgba_to_hex8(*_hex8_rgb(c["tint"]),
                                         int(d_op * 255))
    else:
        c["dot"]["size"] = 0
    return cfg


def encode(cfg: dict) -> str | None:
    """Config dict → share code (inner lines + dot + colour)."""
    c = (cfg or {}).get("crosshair", {})
    if c.get("style") not in ("cross", "circle"):
        return None
    r, g, b = _hex8_rgb(c.get("tint", "#FFFFFFFF"))
    # nearest in-game colour index by RGB distance
    best_i, best_d = 0, 1e9
    for i, col in enumerate(COLORS):
        cr, cg, cb = _hex8_rgb(col)
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < best_d:
            best_i, best_d = i, d

    a = _hex8_alpha(c.get("tint", "#FFFFFFFF")) / 255
    dot = c.get("dot", {}) or {}
    o_alpha = _hex8_alpha((c.get("outline") or {}).get("tint", "#000000FF")) / 255 \
        if (c.get("outline") or {}).get("thickness", 0) else 0

    parts = ["0", "P",
             "c", str(best_i),
             "o", f"{o_alpha:g}",
             "d", "1" if float(dot.get("size", 0) or 0) >= 1 else "0",
             "z", f"{float(dot.get('size', 0) or 0):g}",
             "f", "0",
             "0t", f"{float(c.get('thickness', 2) or 2):g}",
             "0l", f"{float(c.get('length', 4) or 0):g}",
             "0o", f"{float(c.get('gap', 2) or 0):g}",
             "0a", f"{a:g}",
             "0f", "0",
             "1b", "0"]
    return ";".join(parts)
