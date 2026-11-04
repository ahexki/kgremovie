"""Pure geometry for moving the Extra text box on the preview (no tkinter, so it is testable).

Positions are the CENTRE of the box as fractions (0-1) of the picture, the same numbers the render uses
(`extra_text_position`). While dragging, the box keeps the spot where you grabbed it (it does not jump to the mouse),
never leaves the picture, and snaps to the horizontal centre.
"""
from __future__ import annotations

DEFAULT_EXTRA_POS = (0.50, 0.84)
EDGE_MARGIN = 0.01                    # the box stays this far inside the picture
SNAP_TOLERANCE = 0.012                # 1.2 % of the picture width / height


def clamp_center(pos, half=(0.0, 0.0), margin: float = EDGE_MARGIN) -> list[float]:
    """Keep a box of half-size `half` (fractions) fully inside the picture. Too big to fit: it is centred."""
    out = []
    for value, h in zip(pos, half):
        lo, hi = h + margin, 1.0 - h - margin
        out.append(0.5 if lo > hi else max(lo, min(hi, float(value))))
    return out


def drag_position(mouse, grab, origin, size, half=(0.0, 0.0)) -> list[float]:
    """New centre while dragging. mouse / grab / origin / size are in pixels: the mouse position, where inside the box
    (relative to its centre) it was grabbed, the picture's top-left corner and its width / height."""
    pw, ph = max(1.0, float(size[0])), max(1.0, float(size[1]))
    fx = (float(mouse[0]) - float(grab[0]) - float(origin[0])) / pw
    fy = (float(mouse[1]) - float(grab[1]) - float(origin[1])) / ph
    return clamp_center((fx, fy), half)


def snap_center(pos, tolerance: float = SNAP_TOLERANCE) -> tuple[list[float], tuple[bool, bool]]:
    """Snap x to the middle of the picture and y to the middle when within `tolerance`. Returns (pos, (x_snapped, y_snapped))."""
    x, y = float(pos[0]), float(pos[1])
    sx, sy = abs(x - 0.5) <= tolerance, abs(y - 0.5) <= tolerance
    return [0.5 if sx else x, 0.5 if sy else y], (sx, sy)


def slider_to_pos(x_percent: float, y_percent: float, half=(0.0, 0.0)) -> list[float]:
    return clamp_center((float(x_percent) / 100.0, float(y_percent) / 100.0), half)


def pos_to_slider(pos) -> tuple[float, float]:
    return round(float(pos[0]) * 100.0, 1), round(float(pos[1]) * 100.0, 1)


# ---- Myanmar subtitle: anchored at its BOTTOM centre (a one-line and a two-line subtitle share the same bottom edge) ----
DEFAULT_SUB_POS = (0.50, 0.945)       # centred, bottom edge 5.5 % above the bottom of the picture (the old fixed place)
SUB_X_RANGE = (0.15, 0.85)            # centre of the subtitle; the text gets narrower near the sides so it stays inside


def clamp_sub_pos(pos, half_h: float = 0.0, margin: float = EDGE_MARGIN) -> list[float]:
    """Keep a subtitle whose bottom centre is `pos` inside the picture. `half_h` = half the subtitle's height (fraction)."""
    x = max(SUB_X_RANGE[0], min(SUB_X_RANGE[1], float(pos[0])))
    lo, hi = 2.0 * half_h + margin, 1.0 - margin
    y = 0.5 if lo > hi else max(lo, min(hi, float(pos[1])))
    return [x, y]


def drag_sub_position(mouse, grab, origin, size, half_h: float = 0.0) -> list[float]:
    """New bottom centre while dragging. `grab` = where the subtitle was grabbed, in pixels from its bottom centre."""
    pw, ph = max(1.0, float(size[0])), max(1.0, float(size[1]))
    fx = (float(mouse[0]) - float(grab[0]) - float(origin[0])) / pw
    fy = (float(mouse[1]) - float(grab[1]) - float(origin[1])) / ph
    return clamp_sub_pos((fx, fy), half_h)


def snap_x(pos, tolerance: float = SNAP_TOLERANCE) -> tuple[list[float], bool]:
    """Snap x to the middle of the picture when within `tolerance`. Returns (pos, snapped)."""
    x, y = float(pos[0]), float(pos[1])
    snapped = abs(x - 0.5) <= tolerance
    return [0.5 if snapped else x, y], snapped


def normalize_pos(value, default=DEFAULT_EXTRA_POS) -> list[float]:
    """A saved position, repaired: two numbers in 0-1, otherwise the default."""
    try:
        x, y = float(value[0]), float(value[1])
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            return [x, y]
    except Exception:
        pass
    return [float(default[0]), float(default[1])]
