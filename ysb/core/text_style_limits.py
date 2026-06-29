"""Central text style numeric limits for YSB UI/rendering.

The editor keeps practical text-style ranges wide enough for manga typesetting,
but not so huge that the compact right-panel controls become permanently wide.
Input widgets can still auto-expand visually when a displayed value needs it.
"""

TEXT_FONT_SIZE_MIN = 1
TEXT_FONT_SIZE_MAX = 99999
TEXT_LINE_SPACING_MIN = -99999
TEXT_LINE_SPACING_MAX = 99999
TEXT_LETTER_SPACING_MIN = -99999
TEXT_LETTER_SPACING_MAX = 99999
TEXT_CHAR_SCALE_MIN = 1
TEXT_CHAR_SCALE_MAX = 99999
TEXT_STROKE_WIDTH_MAX = 99999
# QFont.setStretch has its own practical range. Final canvas rendering still uses
# the full char_width/char_height transform range; this cap is only for Qt font metrics.
QT_FONT_STRETCH_MAX = 999


def clamp_int(value, default, minimum=None, maximum=None):
    try:
        out = int(round(float(value if value is not None else default)))
    except Exception:
        out = int(default)
    if minimum is not None:
        out = max(int(minimum), out)
    if maximum is not None:
        out = min(int(maximum), out)
    return out


def clamp_text_font_size(value, default=24):
    return clamp_int(value, default, TEXT_FONT_SIZE_MIN, TEXT_FONT_SIZE_MAX)


def clamp_text_line_spacing(value, default=100):
    return clamp_int(value, default, TEXT_LINE_SPACING_MIN, TEXT_LINE_SPACING_MAX)


def clamp_text_letter_spacing(value, default=0):
    return clamp_int(value, default, TEXT_LETTER_SPACING_MIN, TEXT_LETTER_SPACING_MAX)


def clamp_text_char_scale(value, default=100):
    return clamp_int(value, default, TEXT_CHAR_SCALE_MIN, TEXT_CHAR_SCALE_MAX)


def text_line_height_from_percent(base_line_height, percent, default_percent=100):
    """Convert percentage line spacing into a render step.

    Negative values are allowed for experimental overlap/reverse line flow.  A
    non-zero percentage is never rounded to 0, so tiny values still move by one
    pixel.  Exactly 0% intentionally stacks lines on the same baseline.
    """
    try:
        base = float(base_line_height)
    except Exception:
        base = 1.0
    try:
        pct = float(percent)
    except Exception:
        pct = float(default_percent)
    raw = base * (pct / 100.0)
    if raw == 0:
        return 0
    if -1.0 < raw < 1.0:
        return 1 if raw > 0 else -1
    return int(round(raw))


def positive_scale_factor(percent, default=100, minimum_factor=0.01):
    try:
        pct = float(percent)
    except Exception:
        pct = float(default)
    return max(float(minimum_factor), pct / 100.0)


def qt_font_stretch_value(percent, default=100):
    return clamp_int(percent, default, TEXT_CHAR_SCALE_MIN, QT_FONT_STRETCH_MAX)
