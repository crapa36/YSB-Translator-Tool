from __future__ import annotations

"""Independent horizontal text layout engine for YSB.

This module owns horizontal text flow: path placement, line rects, character
slots, caret positions and hit-test geometry.  Existing UI/canvas files should
call this module instead of re-implementing horizontal text math locally.
"""

from typing import Any, Callable, Dict, List, Tuple

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QTransform

from .common_glyph_engine import (
    HORIZONTAL_LONG_MARK_CHARS,
    glyph_path,
    horizontal_long_mark_path_in_rect,
    qfont_for_style,
    style_scale,
)

FAUX_ITALIC_SHEAR = -0.13


def is_available() -> bool:
    return True


def legacy_boundary_note() -> Dict[str, Any]:
    return {
        'engine': 'horizontal',
        'status': 'independent-module-active',
        'note': 'Horizontal writing is routed through ysb.engines.text_layout.horizontal_layout_engine.',
    }


def _default_style_provider(_display_index: int) -> Dict[str, Any]:
    return {}


def _line_starts_for(lines: List[str]) -> List[int]:
    starts = []
    p = 0
    for line in lines:
        starts.append(p)
        p += len(str(line or '')) + 1
    return starts


def _is_horizontal_long_mark_char(ch: str) -> bool:
    return str(ch or '') in HORIZONTAL_LONG_MARK_CHARS


def _long_mark_run_len(chars: List[str], start: int) -> int:
    try:
        if start < 0 or start >= len(chars) or not _is_horizontal_long_mark_char(chars[start]):
            return 0
        n = 1
        i = start + 1
        while i < len(chars) and _is_horizontal_long_mark_char(chars[i]):
            n += 1
            i += 1
        return n
    except Exception:
        return 0


def _font_for_display_index(font: QFont, style_provider: Callable[[int], Dict[str, Any]] | None, base_style: Dict[str, Any], display_index: int) -> tuple[QFont, Dict[str, Any]]:
    st = dict(base_style or {})
    try:
        st.update((style_provider or _default_style_provider)(int(display_index)) or {})
    except Exception:
        pass
    return qfont_for_style(st, font), st


def _advance_for_char(ch: str, font: QFont, style: Dict[str, Any]) -> float:
    fm = QFontMetrics(font)
    sx = style_scale(style, 'char_width', 100)
    try:
        adv = float(fm.horizontalAdvance(str(ch or ' '))) * sx
    except Exception:
        try:
            adv = float(fm.boundingRect(str(ch or ' ')).width()) * sx
        except Exception:
            adv = float(fm.height()) * 0.5 * sx
    return max(1.0, adv)


def _line_height_for(font: QFont, style: Dict[str, Any], fallback_line_height: float | None) -> float:
    fm = QFontMetrics(font)
    sy = style_scale(style, 'char_height', 100)
    try:
        raw = float(fm.lineSpacing()) * sy
    except Exception:
        raw = max(1.0, float(fm.height()) * sy)
    if fallback_line_height is None:
        return max(1.0, raw)
    try:
        return max(1.0, float(fallback_line_height), raw)
    except Exception:
        return max(1.0, raw)


def build_horizontal_text_layout(
    lines: List[str],
    font: QFont,
    *,
    align: str = 'center',
    line_height: float | None = None,
    letter_spacing: float = 0.0,
    style_provider: Callable[[int], Dict[str, Any]] | None = None,
    line_starts: List[int] | None = None,
    base_style: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    align = str(align or 'center').lower()
    if align not in {'left', 'center', 'right'}:
        align = 'center'
    lines = [str(x or '') for x in (lines or [''])]
    if not lines:
        lines = ['']
    line_starts = list(line_starts or _line_starts_for(lines))
    base_style = dict(base_style or {})
    try:
        letter_spacing = float(letter_spacing or 0.0)
    except Exception:
        letter_spacing = 0.0

    measured = []
    max_line_w = 1.0
    total_h = 0.0

    for row, line in enumerate(lines):
        start = int(line_starts[row] if row < len(line_starts) else 0)
        entries = []
        x = 0.0
        line_h = 1.0
        chars = list(line)
        i = 0
        while i < len(chars):
            display_index = start + i
            ch = chars[i]
            f, st = _font_for_display_index(font, style_provider, base_style, display_index)
            fm = QFontMetrics(f)
            line_h = max(line_h, _line_height_for(f, st, line_height))
            run_len = _long_mark_run_len(chars, i)
            if run_len >= 2:
                run_text = ''.join(chars[i:i + run_len])
                run_w = 0.0
                for k, ch2 in enumerate(run_text):
                    f2, st2 = _font_for_display_index(font, style_provider, base_style, display_index + k)
                    run_w += _advance_for_char(ch2, f2, st2)
                slot = QRectF(x, -float(fm.ascent()), max(1.0, run_w), max(1.0, float(fm.height())))
                path0 = horizontal_long_mark_path_in_rect(slot, f, st, overshoot=False)
                entries.append({
                    'kind': 'long_run', 'token': run_text, 'display_index': display_index,
                    'x': x, 'advance': max(1.0, run_w), 'path0': path0,
                    'style': dict(st), 'token_len': run_len,
                })
                x += max(1.0, run_w)
                if i + run_len < len(chars):
                    x += letter_spacing
                i += run_len
                continue

            adv = _advance_for_char(ch, f, st)
            path0 = QPainterPath()
            if ch and not str(ch).isspace():
                path0 = glyph_path(ch, f, st)
                if not path0.isEmpty():
                    tr = QTransform()
                    # Preserve font-native baseline: glyph_path is already at baseline 0.
                    tr.translate(float(x), 0.0)
                    path0 = tr.map(path0)
            entries.append({
                'kind': 'space' if str(ch).isspace() else 'char', 'token': ch, 'display_index': display_index,
                'x': x, 'advance': adv, 'path0': path0,
                'style': dict(st), 'token_len': 1,
            })
            x += adv
            if i < len(chars) - 1:
                x += letter_spacing
            i += 1
        if not chars:
            f, st = _font_for_display_index(font, style_provider, base_style, start)
            line_h = max(line_h, _line_height_for(f, st, line_height))
            x = max(1.0, float(QFontMetrics(f).averageCharWidth()))
        measured.append({'line': line, 'start': start, 'entries': entries, 'width': max(1.0, x), 'height': max(1.0, line_h), 'y': total_h})
        max_line_w = max(max_line_w, max(1.0, x))
        total_h += max(1.0, line_h)

    aggregate = QPainterPath()
    line_rects: List[QRectF] = []
    tokens = []
    char_slots = []
    display_caret_map: Dict[int, QPointF] = {}
    content_rect = QRectF()

    for row, info in enumerate(measured):
        width = float(info.get('width') or 1.0)
        height = float(info.get('height') or 1.0)
        y_top = float(info.get('y') or 0.0)
        if align == 'right':
            dx = -width
        elif align == 'center':
            dx = -width / 2.0
        else:
            dx = 0.0
        baseline_y = y_top + height * 0.5
        try:
            # Use the row's first font as an approximate baseline anchor.
            first_index = int(info.get('start') or 0)
            f0, st0 = _font_for_display_index(font, style_provider, base_style, first_index)
            baseline_y = y_top + (height - float(QFontMetrics(f0).height()) * style_scale(st0, 'char_height', 100)) / 2.0 + float(QFontMetrics(f0).ascent()) * style_scale(st0, 'char_height', 100)
        except Exception:
            pass
        line_path = QPainterPath()
        line_rect = QRectF(dx, y_top, width, height)
        display_caret_map[int(info.get('start') or 0)] = QPointF(dx, y_top + height * 0.5)
        for entry in info.get('entries') or []:
            d0 = int(entry.get('display_index') or 0)
            tok = str(entry.get('token') or '')
            tok_len = max(1, int(entry.get('token_len') or len(tok) or 1))
            adv = max(1.0, float(entry.get('advance') or 1.0))
            local_x = dx + float(entry.get('x') or 0.0)
            p0 = entry.get('path0') or QPainterPath()
            mapped = QPainterPath()
            if not p0.isEmpty():
                tr = QTransform()
                # p0 already has local x for the line. Move to row/baseline.
                tr.translate(dx, baseline_y)
                mapped = tr.map(p0)
                aggregate.addPath(mapped)
                line_path.addPath(mapped)
                r = mapped.boundingRect()
                if not r.isNull() and r.width() > 0 and r.height() > 0:
                    content_rect = QRectF(r) if content_rect.isNull() else content_rect.united(QRectF(r))
                    line_rect = line_rect.united(QRectF(r))
            token_rect = QRectF(local_x, y_top, adv, height)
            if not mapped.isEmpty():
                token_rect = token_rect.united(mapped.boundingRect())
            token_index = len(tokens)
            tokens.append({**entry, 'path': mapped, 'rect': QRectF(token_rect), 'x0': local_x, 'y0': y_top})
            seg_w = max(1.0, adv / float(tok_len))
            for k, ch in enumerate(tok):
                left_k = local_x + seg_w * k
                right_k = local_x + seg_w * (k + 1)
                slot = QRectF(left_k, y_top, max(1.0, right_k - left_k), height)
                char_slots.append({
                    'display_index': d0 + k, 'char': ch, 'slot': slot, 'token_index': token_index,
                    'path': mapped if k == 0 else QPainterPath(), 'style': dict(entry.get('style') or {}),
                    'kind': str(entry.get('kind') or ''), 'token': tok,
                    'flow_start': QPointF(left_k, y_top + height * 0.5),
                    'flow_end': QPointF(right_k, y_top + height * 0.5),
                })
                display_caret_map[d0 + k] = QPointF(left_k, y_top + height * 0.5)
                display_caret_map[d0 + k + 1] = QPointF(right_k, y_top + height * 0.5)
                content_rect = QRectF(slot) if content_rect.isNull() else content_rect.united(QRectF(slot))
        if line_path.isEmpty():
            line_rect = QRectF(dx, y_top, max(1.0, width), height)
        line_rects.append(QRectF(line_rect).adjusted(-1, -1, 1, 1))
    if content_rect.isNull() or content_rect.width() <= 0 or content_rect.height() <= 0:
        content_rect = QRectF(0.0, 0.0, max(1.0, max_line_w), max(1.0, total_h))
    return {
        'path': aggregate,
        'line_rects': line_rects,
        'tokens': tokens,
        'char_slots': char_slots,
        'display_caret_map': display_caret_map,
        'content_rect': content_rect.adjusted(-2, -2, 2, 2),
        'base_line_height': max(1.0, measured[0]['height'] if measured else 1.0),
        'total_width': max_line_w,
        'total_height': max(1.0, total_h),
        'horizontal_engine_independent': True,
    }


def build_horizontal_text_path(lines, font, align='center', line_height=None, letter_spacing=0, base_style=None):
    layout = build_horizontal_text_layout(lines, font, align=align, line_height=line_height, letter_spacing=letter_spacing, base_style=base_style)
    return layout.get('path') or QPainterPath(), layout.get('line_rects') or []
