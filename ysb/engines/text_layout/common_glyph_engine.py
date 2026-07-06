from __future__ import annotations

from typing import Any, Dict, Tuple

from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QTransform

from ysb.core.text_style_limits import positive_scale_factor

FAUX_ITALIC_SHEAR = -0.13

LONG_MARK_CHARS = set("ㅡー─━—―－-–﹘﹣│｜丨ㅣ┃┆┇")
HORIZONTAL_LONG_MARK_CHARS = set("ㅡー─━—―－-–﹘﹣")
VERTICAL_LONG_MARK_CHARS = set("│｜丨ㅣ┃┆┇")

QUOTE_OPEN = set("「『【〔［｛〈《〝“‘（([｛＜")
QUOTE_CLOSE = set("」』】〕］｝〉》〟”’）)]｝＞")
ASCII_QUOTE = set("\"'")

DOT_PUNCT = set(".．。")
COMMA_PUNCT = set(",，、")
CENTER_PUNCT = set("！？!?‼⁉♡♥♪☆★※〇○●◎□■△▲▽▼")
FIXED_SIDEWAYS_PUNCT = set("〜～／＼:;：；")
ELLIPSIS_TOKENS = {"...", "....", ".....", "......", "．．", "．．．", "．．．．", "…", "‥", "……"}
# Consecutive vertical punctuation such as !? should stay horizontal until
# the user inserts a space. The run is laid out as one visual word while
# source text/copy remains individual characters.
INLINE_HORIZONTAL_SYMBOL_CHARS = set("!?！？‼⁉")

# Vertical-writing presentation forms.  These are intentionally centralized so
# vertical punctuation can be corrected by editing this module only.
#
# Important: corner brackets and quotation marks are different characters.
# Do NOT turn straight/curly quotes into corner brackets.  Only true corner
# brackets use vertical presentation forms.  Quotation marks keep their own
# glyph identity and only receive vertical placement/rotation rules later.
VERTICAL_CORNER_QUOTE_FORMS = {
    "「": "﹁", "」": "﹂",
    "『": "﹃", "』": "﹄",
}
CORNER_QUOTE_CHARS = set(VERTICAL_CORNER_QUOTE_FORMS.keys())

# Quote marks are not corner brackets.  In vertical writing they keep a
# comma-like quote shape; open/close are paired by 180-degree rotation in the
# vertical layout engine.
NORMAL_DOUBLE_QUOTE_CHARS = set('\"“”〝〟')
NORMAL_SINGLE_QUOTE_CHARS = set("'‘’")
NORMAL_QUOTE_CHARS = NORMAL_DOUBLE_QUOTE_CHARS | NORMAL_SINGLE_QUOTE_CHARS


def is_normal_quote(ch: str) -> bool:
    return str(ch or '') in NORMAL_QUOTE_CHARS


def vertical_normal_quote_display_char(ch: str, kind: str = 'quote_open') -> str:
    ch = str(ch or '')
    if ch in NORMAL_SINGLE_QUOTE_CHARS:
        return '‘'
    if ch in NORMAL_DOUBLE_QUOTE_CHARS:
        return '“'
    return ch


def is_corner_quote(ch: str) -> bool:
    return str(ch or "") in CORNER_QUOTE_CHARS


def vertical_quote_display_char(ch: str, kind: str = "quote_open") -> str:
    """Return the glyph to draw for quote/bracket characters in vertical writing.

    Source text is never changed.  Only true corner brackets are swapped to their
    vertical presentation glyphs.  Straight quotes, curly quotes, primes and
    other quote marks stay visually distinct from corner brackets.
    """
    ch = str(ch or "")
    if ch in VERTICAL_CORNER_QUOTE_FORMS:
        return VERTICAL_CORNER_QUOTE_FORMS.get(ch, ch)
    return ch


def qfont_for_style(style: Dict[str, Any] | None, fallback_font: QFont | None = None) -> QFont:
    style = dict(style or {})
    fallback_font = QFont(fallback_font) if fallback_font is not None else QFont()
    family = str(style.get('font_family') or fallback_font.family() or 'Arial')
    font = QFont(family)
    try:
        size = int(round(float(style.get('font_size') or (fallback_font.pixelSize() if fallback_font.pixelSize() > 0 else 20) or 20)))
    except Exception:
        size = 20
    font.setPixelSize(max(1, size))
    try:
        if bool(style.get('bold', fallback_font.bold())):
            font.setWeight(QFont.Weight.DemiBold)
        else:
            font.setWeight(QFont.Weight.Normal)
    except Exception:
        try:
            font.setBold(bool(style.get('bold', fallback_font.bold())))
        except Exception:
            pass
    try:
        font.setItalic(bool(style.get('italic', fallback_font.italic())))
    except Exception:
        pass
    return font


def style_scale(style: Dict[str, Any] | None, key: str, default_pct: int = 100) -> float:
    try:
        return positive_scale_factor((style or {}).get(key, default_pct))
    except Exception:
        try:
            return max(0.01, float(default_pct) / 100.0)
        except Exception:
            return 1.0


def glyph_path(text: str, font: QFont, style: Dict[str, Any] | None = None, *, baseline: QPointF | None = None) -> QPainterPath:
    text = str(text or '')
    path_font = QFont(font)
    italic_requested = False
    try:
        italic_requested = bool(path_font.italic())
        path_font.setItalic(False)
    except Exception:
        pass
    path = QPainterPath()
    if text and not text.isspace():
        path.addText(baseline or QPointF(0.0, 0.0), path_font, text)
    if path.isEmpty():
        return path
    if italic_requested:
        shear = QTransform()
        shear.shear(FAUX_ITALIC_SHEAR, 0.0)
        path = shear.map(path)
    sx = style_scale(style, 'char_width', 100)
    sy = style_scale(style, 'char_height', 100)
    if abs(sx - 1.0) > 0.001 or abs(sy - 1.0) > 0.001:
        tr = QTransform()
        tr.scale(float(sx), float(sy))
        path = tr.map(path)
    return path


def rotate_path_around_center(path: QPainterPath, angle: float) -> QPainterPath:
    if path is None or path.isEmpty():
        return QPainterPath()
    rect = path.boundingRect()
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return QPainterPath(path)
    tr = QTransform()
    tr.translate(rect.center().x(), rect.center().y())
    tr.rotate(float(angle or 0.0))
    tr.translate(-rect.center().x(), -rect.center().y())
    return tr.map(path)


def flip_path_vertically_around_center(path: QPainterPath) -> QPainterPath:
    """Mirror a path top-to-bottom around its own center."""
    if path is None or path.isEmpty():
        return QPainterPath()
    rect = path.boundingRect()
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return QPainterPath(path)
    tr = QTransform()
    tr.translate(rect.center().x(), rect.center().y())
    tr.scale(1.0, -1.0)
    tr.translate(-rect.center().x(), -rect.center().y())
    return tr.map(path)


def _vertical_punct_size(font: QFont, style: Dict[str, Any] | None = None) -> float:
    fs = _font_size_from(font, style)
    try:
        return max(1.6, min(fs * 0.18, fs * 0.125 + 1.0))
    except Exception:
        return 3.0


def vertical_dot_mark_path(font: QFont, style: Dict[str, Any] | None = None) -> QPainterPath:
    """Stable round dot for vertical punctuation.

    Do not use the font glyph for vertical dots/ellipsis.  Some fonts expose
    period-like glyphs with tall bounds, and rotating/scaling those paths makes
    the dot look like a long dash.  A geometric dot keeps '.', '…' and '……'
    visually stable regardless of the font face.
    """
    s = _vertical_punct_size(font, style)
    out = QPainterPath()
    out.addEllipse(QRectF(-s * 0.5, -s * 0.5, s, s))
    return out


def vertical_ellipsis_path(token: str, font: QFont, style: Dict[str, Any] | None = None) -> QPainterPath:
    token = str(token or '')
    if token == '‥':
        count = 2
    elif token == '…':
        count = 3
    elif token == '……':
        count = 6
    elif token and set(token) == {'.'}:
        count = max(2, len(token))
    elif token and set(token) == {'．'}:
        count = max(2, len(token))
    else:
        count = max(3, len(token) if token else 3)
    s = _vertical_punct_size(font, style)
    gap = max(s * 1.10, _font_size_from(font, style) * 0.115)
    out = QPainterPath()
    y = 0.0
    for _ in range(count):
        dot = vertical_dot_mark_path(font, style)
        tr = QTransform(); tr.translate(0.0, y)
        out.addPath(tr.map(dot))
        y += gap
    br = out.boundingRect()
    if not br.isNull() and (br.left() != 0 or br.top() != 0):
        tr = QTransform(); tr.translate(-br.center().x(), -br.top())
        out = tr.map(out)
    return out


def vertical_comma_mark_path(font: QFont, style: Dict[str, Any] | None = None, *, tail_direction: str = 'left', flip_vertical: bool | None = None) -> QPainterPath:
    """Geometric vertical comma mark.

    tail_direction='left'  -> tail points left / inward when mark sits on right.
    tail_direction='right' -> tail points right / inward when mark sits on left.

    This intentionally avoids rotating the font comma glyph.  Font comma glyphs
    vary wildly and caused the quote/comma marks to point the wrong way.
    """
    s = _vertical_punct_size(font, style)
    direction = str(tail_direction or 'left').lower()
    sign = -1.0 if direction != 'right' else 1.0
    out = QPainterPath()
    # round head
    out.addEllipse(QRectF(-s * 0.42, -s * 0.42, s * 0.84, s * 0.84))
    # pointed tail toward the text interior
    out.moveTo(sign * s * 0.12, -s * 0.12)
    out.lineTo(sign * s * 1.18, s * 0.34)
    out.lineTo(sign * s * 0.12, s * 0.52)
    out.closeSubpath()
    return out


def vertical_normal_quote_path(ch: str, kind: str, font: QFont, style: Dict[str, Any] | None = None) -> QPainterPath:
    """세로쓰기 따옴표: 폰트 원본 글리프 + 180도 회전.

    현재 화면에 나온 결과물 기준으로 open/close 둘 다 180도 추가 회전.

    글리프 선택:
      싱글 open  -> ‘ (‘, 꼬리 오른쪽) + 180도 -> 꼬리 왼쪽(안쪽)
      싱글 close -> ’ (’, 꼬리 왼쪽) + 180도 -> 꼬리 오른쪽(안쪽)
      더블 open  -> “ (“, 꼬리 오른쪽) + 180도 -> 꼬리 왼쪽(안쪽)
      더블 close -> ” (”, 꼬리 왼쪽) + 180도 -> 꼬리 오른쪽(안쪽)
    """
    ch = str(ch or "")
    kind = str(kind or "quote_open")
    if ch in NORMAL_SINGLE_QUOTE_CHARS:
        display_ch = "‘" if kind == "quote_open" else "’"
    else:
        display_ch = "“" if kind == "quote_open" else "”"
    path = glyph_path(display_ch, font, style)
    if path.isEmpty():
        path = glyph_path(ch, font, style)
    if path.isEmpty():
        return path
    return rotate_path_around_center(path, 180.0)

def place_path_in_vertical_cell(path: QPainterPath, cell_w: float, cell_h: float, offset_x: float = 0.0, offset_y: float = 0.0) -> QPainterPath:
    if path is None or path.isEmpty():
        return QPainterPath()
    br = path.boundingRect()
    if br.isNull() or br.width() <= 0 or br.height() <= 0:
        return QPainterPath(path)
    tr = QTransform()
    tr.translate(float(offset_x) - br.center().x(), float(cell_h) * 0.5 - br.center().y() + float(offset_y))
    return tr.map(path)


def tight_vertical_cell_metrics(font: QFont, fm: QFontMetrics | None = None) -> Tuple[float, float]:
    fm = fm or QFontMetrics(font)
    try:
        widths, heights = [], []
        for ch in "가漢あ":
            p = glyph_path(ch, font, {'char_width': 100, 'char_height': 100})
            r = p.boundingRect()
            if not r.isNull() and r.width() > 0 and r.height() > 0:
                widths.append(float(r.width()))
                heights.append(float(r.height()))
        fw = max(1.0, float(fm.height()))
        fl = max(1.0, float(fm.lineSpacing()))
        cell_w = min(max(max(widths) if widths else fw * 0.72, fw * 0.62, 1.0), fw)
        cell_h = min(max(max(heights) if heights else fl * 0.72, fl * 0.62, 1.0), fl)
        return cell_w, cell_h
    except Exception:
        return max(1.0, float(fm.height())), max(1.0, float(fm.lineSpacing()))


def vertical_effective_char_gap(base_cell_h: float, raw_gap: float = 0.0) -> float:
    try:
        base = max(1.0, float(base_cell_h or 1.0))
    except Exception:
        base = 1.0
    try:
        raw = float(raw_gap or 0.0)
    except Exception:
        raw = 0.0
    safe = max(0.0, base * 0.08)
    if raw > 0:
        return raw + safe * 0.25
    return raw + safe


def vertical_space_advance(token: str, base_cell_h: float, char_gap: float = 0.0) -> float:
    try:
        base = max(1.0, float(base_cell_h or 1.0))
    except Exception:
        base = 1.0
    try:
        gap = max(0.0, float(char_gap or 0.0))
    except Exception:
        gap = 0.0
    total = 0.0
    for ch in str(token or ' '):
        ratio = 0.50 if ch == '　' else 0.32
        total += max(1.0, base * ratio) + gap * 0.20
    return max(1.0, total)


def _font_size_from(font: QFont, style: Dict[str, Any] | None = None) -> float:
    try:
        return max(1.0, float((style or {}).get('font_size') or (font.pixelSize() if font.pixelSize() > 0 else QFontMetrics(font).height()) or 20))
    except Exception:
        return 20.0


def long_mark_thickness(font: QFont, style: Dict[str, Any] | None, slot_h: float) -> float:
    """Fill thickness for custom long marks.

    Stroke width is deliberately ignored.  The outline/stroke is applied later by
    the painter.  Using stroke_width here makes vertical long marks look double-
    thick compared with horizontal text.
    """
    try:
        slot_h = max(1.0, float(slot_h or 1.0))
    except Exception:
        slot_h = 1.0
    fs = _font_size_from(font, style)
    try:
        sample_font = qfont_for_style(style, font)
        sample = glyph_path('—', sample_font, style)
        sr = sample.boundingRect()
        if not sr.isNull() and sr.height() > 0:
            return max(1.2, min(slot_h * 0.18, max(float(sr.height()) * 0.82, fs * 0.045, 1.2)))
    except Exception:
        pass
    return max(1.2, min(slot_h * 0.16, fs * 0.075))


def horizontal_long_mark_path_in_rect(rect: QRectF, font: QFont, style: Dict[str, Any] | None = None, overshoot: bool = False) -> QPainterPath:
    rr = QRectF(rect)
    out = QPainterPath()
    if rr.isNull() or rr.width() <= 0 or rr.height() <= 0:
        return out
    th = long_mark_thickness(font, style, float(rr.height()))
    extra = min(float(rr.width()) * 0.12, th * 0.55) if overshoot else 0.0
    bar = QRectF(rr.left() - extra, rr.center().y() - th / 2.0, rr.width() + extra * 2.0, th)
    radius = max(0.4, th / 2.0)
    out.addRoundedRect(bar, radius, radius)
    return out


def horizontal_canonical_rect_for_vertical_slot(slot_rect: QRectF) -> QRectF:
    rr = QRectF(slot_rect)
    return QRectF(0.0, 0.0, max(1.0, rr.height()), max(1.0, rr.width()))


def rotate_horizontal_path_to_vertical_slot(path: QPainterPath, horizontal_rect: QRectF, target_rect: QRectF) -> QPainterPath:
    if path is None or path.isEmpty():
        return QPainterPath()
    hr = QRectF(horizontal_rect)
    trr = QRectF(target_rect)
    tr = QTransform()
    tr.translate(trr.center().x(), trr.center().y())
    tr.rotate(90.0)
    tr.translate(-hr.center().x(), -hr.center().y())
    return tr.map(path)


def vertical_long_mark_path(token: str, slot_rect: QRectF, font: QFont, style: Dict[str, Any] | None = None, overshoot: bool = False) -> QPainterPath:
    rr = QRectF(slot_rect)
    if rr.isNull() or rr.width() <= 0 or rr.height() <= 0:
        return QPainterPath()
    hr = horizontal_canonical_rect_for_vertical_slot(rr)
    hp = horizontal_long_mark_path_in_rect(hr, font, style, overshoot=overshoot)
    return rotate_horizontal_path_to_vertical_slot(hp, hr, rr)


def horizontal_ellipsis_sequence_path(token: str, font: QFont, style: Dict[str, Any] | None = None) -> QPainterPath:
    token = str(token or '')
    if token == '‥':
        chars = ['．', '．']
    elif token == '……':
        chars = ['…', '…']
    elif set(token) == {'.'}:
        chars = list(token)
    elif set(token) == {'．'}:
        chars = list(token)
    elif token == '…':
        chars = ['…']
    else:
        chars = list(token) if token else ['.']
    path = QPainterPath()
    x = 0.0
    f = qfont_for_style(style, font)
    fm = QFontMetrics(f)
    for ch in chars:
        p = glyph_path(ch, f, style)
        br = p.boundingRect()
        if br.isNull() or br.width() <= 0 or br.height() <= 0:
            try:
                adv = max(1.0, float(fm.horizontalAdvance(ch)))
            except Exception:
                adv = max(1.0, _font_size_from(f, style) * 0.25)
            x += adv
            continue
        tr = QTransform()
        tr.translate(x - br.left(), 0.0)
        mapped = tr.map(p)
        path.addPath(mapped)
        try:
            adv = max(float(fm.horizontalAdvance(ch)), float(br.width()))
        except Exception:
            adv = float(br.width())
        x += max(1.0, adv)
    return path
