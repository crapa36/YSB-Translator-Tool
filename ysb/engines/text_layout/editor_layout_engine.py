from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QTransform

from ysb.core.text_style_limits import clamp_text_line_spacing, positive_scale_factor
from .vertical_layout_engine import build_vertical_text_layout
from .horizontal_layout_engine import build_horizontal_text_layout
from .common_glyph_engine import qfont_for_style


def _qcolor_name(value: Any, fallback: str) -> str:
    try:
        c = QColor(value) if isinstance(value, QColor) else QColor(str(value if value is not None and value != '' else fallback))
    except Exception:
        c = QColor(fallback)
    if not c.isValid():
        c = QColor(fallback)
    return c.name()


def _base_style_from_owner(owner: Any, font: QFont, fm: QFontMetrics) -> Dict[str, Any]:
    try:
        target = getattr(owner, 'target_item', None)
        data = getattr(target, 'data', {}) if target is not None else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    try:
        font_size = font.pixelSize() if font.pixelSize() > 0 else int(data.get('font_size') or fm.height())
    except Exception:
        font_size = 24
    try:
        family = str(data.get('font_family') or font.family() or 'Arial')
    except Exception:
        family = 'Arial'
    return {
        'font_family': family,
        'font_size': max(1, int(font_size or 24)),
        'text_color': _qcolor_name(getattr(owner, '_inline_text_color', data.get('text_color', '#000000')), '#000000'),
        'stroke_color': _qcolor_name(getattr(owner, '_inline_stroke_color', data.get('stroke_color', '#FFFFFF')), '#FFFFFF'),
        'stroke_width': int(getattr(owner, '_inline_stroke_width', data.get('stroke_width', 0)) or 0),
        'bold': bool(data.get('bold', font.bold())),
        'italic': bool(data.get('italic', font.italic())),
        'strike': bool(data.get('strike', data.get('strikeout', False))),
        'line_spacing': int(getattr(owner, 'line_spacing_pct', data.get('line_spacing', 100)) or 100),
        'letter_spacing': int(getattr(owner, 'letter_spacing', data.get('letter_spacing', 0)) or 0),
        'char_width': int(getattr(owner, 'char_width_pct', data.get('char_width', 100)) or 100),
        'char_height': int(getattr(owner, 'char_height_pct', data.get('char_height', 100)) or 100),
        'partial_horizontal_writing_enabled': bool(getattr(owner, 'partial_horizontal_writing_enabled', data.get('partial_horizontal_writing_enabled', True))),
    }


def _style_provider_from_owner(owner: Any, logical_len: int, preedit_caret: int, preedit_len: int, base_style: Dict[str, Any]):
    def _style(display_index: int) -> Dict[str, Any]:
        try:
            li = owner._logical_index_for_display_char(int(display_index), preedit_caret, preedit_len)
        except Exception:
            li = int(display_index)
        if li < 0:
            li = max(0, min(logical_len, int(preedit_caret or 0)))
        try:
            st = dict(owner._partial_style_for_index(li) or {})
        except Exception:
            st = {}
        out = dict(base_style)
        out.update(st)
        out.setdefault('text_color', base_style.get('text_color'))
        out.setdefault('stroke_color', base_style.get('stroke_color'))
        out.setdefault('stroke_width', base_style.get('stroke_width', 0))
        out.setdefault('char_width', base_style.get('char_width', 100))
        out.setdefault('char_height', base_style.get('char_height', 100))
        out.setdefault('letter_spacing', base_style.get('letter_spacing', 0))
        return out
    return _style


def _split_vertical_lines(owner: Any, text: str):
    try:
        return owner._split_vertical_lines(text)
    except Exception:
        lines = str(text or '').split('\n')
        starts = []
        p = 0
        for line in lines:
            starts.append(p)
            p += len(line) + 1
        return lines, starts


def build_vertical_editor_layout(owner: Any, cache_key=None) -> Dict[str, Any]:
    rect = QRectF(owner.boundingRect())
    pad_x = 5.0
    pad_y = 5.0
    font = QFont(getattr(owner, '_inline_font', QFont()))
    try:
        fm = owner._cached_font_metrics(font)
    except Exception:
        fm = QFontMetrics(font)
    base_style = _base_style_from_owner(owner, font, fm)
    font = qfont_for_style(base_style, font)
    try:
        display_text, logical_text, _preedit, preedit_caret, preedit_len = owner._inline_display_text_with_preedit()
    except Exception:
        display_text = owner.toPlainText()
        logical_text = display_text
        preedit_caret = 0
        preedit_len = 0
    text = str(display_text or '')
    logical_text = str(logical_text or '')
    logical_len = len(logical_text)
    lines, starts = _split_vertical_lines(owner, text)
    if not lines:
        lines, starts = [''], [0]
    try:
        line_spacing_pct = clamp_text_line_spacing(getattr(owner, 'line_spacing_pct', 100), 100)
    except Exception:
        line_spacing_pct = 100
    try:
        nominal = max(1.0, float(fm.lineSpacing()))
    except Exception:
        nominal = max(1.0, float(fm.height()))
    line_height = nominal * max(0.10, float(line_spacing_pct) / 100.0)
    try:
        letter_spacing = float(getattr(owner, 'letter_spacing', 0) or 0)
    except Exception:
        letter_spacing = 0.0
    style_provider = _style_provider_from_owner(owner, logical_len, int(preedit_caret or 0), int(preedit_len or 0), base_style)
    raw = build_vertical_text_layout(
        lines,
        font,
        align=getattr(owner, 'align', 'center'),
        line_height=line_height,
        letter_spacing=letter_spacing,
        style_provider=style_provider,
        line_starts=starts,
        base_style=base_style,
        partial_horizontal_enabled=bool(getattr(owner, 'partial_horizontal_writing_enabled', True)),
    )
    raw_rect = QRectF(raw.get('content_rect') or QRectF())
    if raw_rect.isNull() or raw_rect.width() <= 0 or raw_rect.height() <= 0:
        raw_rect = QRectF(0.0, 0.0, max(1.0, float(raw.get('base_cell_w') or 10.0)), max(1.0, float(fm.height())))
    available_w = max(1.0, float(rect.width()) - pad_x * 2.0)
    available_h = max(1.0, float(rect.height()) - pad_y * 2.0)
    dx = pad_x + (available_w - raw_rect.width()) / 2.0 - raw_rect.left()
    # Vertical text should be easy to edit: center by default, but never let the
    # first quote/caret start outside the visible editor frame.
    dy = pad_y + (available_h - raw_rect.height()) / 2.0 - raw_rect.top()
    dy = max(pad_y - raw_rect.top(), min(float(rect.height()) * 3.0, dy))

    tr = QTransform(); tr.translate(dx, dy)
    char_paths = []
    char_rects = []
    content_rect = QRectF()
    for slot in raw.get('char_slots') or []:
        try:
            display_index = int(slot.get('display_index', 0))
            li = owner._logical_index_for_display_char(display_index, int(preedit_caret or 0), int(preedit_len or 0))
        except Exception:
            li = int(slot.get('display_index', 0))
        if li < 0:
            li = max(0, min(logical_len, int(preedit_caret or 0)))
        rr = tr.mapRect(QRectF(slot.get('slot') or QRectF()))
        p = slot.get('path') or QPainterPath()
        mp = tr.map(p) if p is not None and not p.isEmpty() else QPainterPath()
        st = dict(slot.get('style') or base_style)
        kind = str(slot.get('kind') or '')
        char_rects.append((int(li), str(slot.get('char') or ''), QRectF(rr)))
        inline_horizontal = bool(slot.get('inline_horizontal', False))
        char_paths.append({
            'logical_index': int(li),
            'display_index': display_index,
            'char': str(slot.get('char') or ''),
            'kind': kind,
            'token': str(slot.get('token') or ''),
            'slot': QRectF(rr),
            'path': mp,
            'style': st,
            'flow_start': tr.map(QPointF(slot.get('flow_start'))) if slot.get('flow_start') is not None else QPointF(rr.center().x(), rr.top()),
            'flow_end': tr.map(QPointF(slot.get('flow_end'))) if slot.get('flow_end') is not None else QPointF(rr.center().x(), rr.bottom()),
            'inline_horizontal': inline_horizontal,
            'caret_axis': 'horizontal' if inline_horizontal else str(slot.get('caret_axis') or 'vertical'),
            'token_index': slot.get('token_index'),
        })
        if not mp.isEmpty():
            br = mp.boundingRect()
            try:
                sw = max(0.0, float(st.get('stroke_width', 0) or 0.0)) / 2.0 + 1.0
                br = br.adjusted(-sw, -sw, sw, sw)
            except Exception:
                pass
            if kind not in {'quote_open', 'quote_close'}:
                content_rect = QRectF(br) if content_rect.isNull() else content_rect.united(QRectF(br))
        if kind not in {'quote_open', 'quote_close'}:
            content_rect = QRectF(rr) if content_rect.isNull() else content_rect.united(QRectF(rr))

    display_caret_map = {}
    for k, p in (raw.get('display_caret_map') or {}).items():
        try:
            display_caret_map[int(k)] = tr.map(QPointF(p))
        except Exception:
            pass

    # Build the real editor caret map from each character's flow_start.
    # This is the same invariant as horizontal text: caret N is placed at the
    # start boundary of glyph N, not at the end of glyph N-1.  This prevents
    # quotes, commas, ellipses and merged long marks from pushing later carets.
    # Partial horizontal runs also expose a caret style map so the caret shape
    # becomes the normal horizontal-editor vertical bar while it moves across
    # the row.
    caret_map = {}
    caret_styles = {}
    ordered_chars = sorted(
        [cp for cp in char_paths if int(cp.get('logical_index', -1)) >= 0],
        key=lambda cp: (int(cp.get('logical_index', 0)), int(cp.get('display_index', 0)))
    )

    def _remember_caret_style(idx, point, slot, inline_horizontal=False):
        try:
            idx = int(idx)
            pp = QPointF(point) if point is not None else QPointF(QRectF(slot).center())
            rr = QRectF(slot)
            if bool(inline_horizontal):
                h = max(8.0, float(rr.height()) + 4.0)
                caret_styles[idx] = {
                    'orientation': 'horizontal',
                    'height': h,
                    'center_y': float(rr.center().y()),
                    'slot': QRectF(rr),
                    'point': QPointF(pp),
                }
            elif idx not in caret_styles:
                caret_styles[idx] = {
                    'orientation': 'vertical',
                    'width': max(1.0, float(rr.width())),
                    'center_x': float(pp.x()),
                    'slot': QRectF(rr),
                    'point': QPointF(pp),
                }
        except Exception:
            pass

    for cp in ordered_chars:
        try:
            li = int(cp.get('logical_index', 0))
            fs = cp.get('flow_start')
            slot_rr = QRectF(cp.get('slot') or QRectF())
            inline_horizontal = bool(cp.get('inline_horizontal', False)) or str(cp.get('caret_axis') or '') == 'horizontal'
            if fs is not None:
                caret_map[li] = QPointF(fs)
                _remember_caret_style(li, fs, slot_rr, inline_horizontal=inline_horizontal)
            fe = cp.get('flow_end')
            if inline_horizontal and fe is not None:
                # End boundary inside the same partial-horizontal row must keep
                # the vertical-bar caret, including the position after the last
                # character of the run.
                caret_map[li + 1] = QPointF(fe)
                _remember_caret_style(li + 1, fe, slot_rr, inline_horizontal=True)
        except Exception:
            pass
    if ordered_chars:
        last = ordered_chars[-1]
        try:
            li = int(last.get('logical_index', 0))
            fe = last.get('flow_end')
            if (li + 1) not in caret_map:
                caret_map[li + 1] = QPointF(fe) if fe is not None else QPointF(QRectF(last.get('slot')).center().x(), QRectF(last.get('slot')).bottom())
                _remember_caret_style(li + 1, caret_map.get(li + 1), QRectF(last.get('slot') or QRectF()), inline_horizontal=bool(last.get('inline_horizontal', False)))
        except Exception:
            pass
    # Fill gaps/newline positions from the raw display map as fallback only.
    for logical_pos in range(0, logical_len + 1):
        if logical_pos in caret_map:
            continue
        try:
            if preedit_len and logical_pos == preedit_caret:
                display_pos = int(preedit_caret) + int(preedit_len)
            else:
                display_pos = owner._display_index_for_logical_caret(logical_pos, int(preedit_caret or 0), int(preedit_len or 0))
        except Exception:
            display_pos = logical_pos
        pnt = display_caret_map.get(int(display_pos))
        if pnt is not None:
            caret_map[logical_pos] = QPointF(pnt)
    if logical_len not in caret_map:
        pnt = display_caret_map.get(len(text))
        caret_map[logical_len] = QPointF(pnt) if pnt is not None else QPointF(float(rect.center().x()), float(rect.center().y()))

    line_rects = [tr.mapRect(QRectF(r)).adjusted(-2, -2, 2, 2) for r in (raw.get('line_rects') or [])]
    if content_rect.isNull() or content_rect.width() <= 0 or content_rect.height() <= 0:
        content_rect = QRectF(float(rect.center().x()) - 5.0, float(rect.center().y()) - 5.0, 10.0, 10.0)
    # Vertical punctuation can intentionally bleed outside the core glyph column
    # (e.g. 「」 wrapping Hangul).  Size the custom editor from the union of the
    # actual ink/slot bounds so clipped narrow boxes do not force quotes inward.
    try:
        bleed_w = max(float(content_rect.width()), float(raw.get('base_cell_w') or 0.0) + float(raw.get('base_cell_h') or 0.0) * 0.55)
    except Exception:
        bleed_w = float(content_rect.width())
    desired_w = max(18.0, bleed_w + 14.0)
    desired_h = max(18.0, float(content_rect.height()) + 14.0)
    return {
        'key': cache_key,
        'font': font,
        'fm': fm,
        'columns': [
            {
                'x': float((line_rects[i].center().x() if i < len(line_rects) else content_rect.center().x())),
                'y0': float((line_rects[i].top() if i < len(line_rects) else content_rect.top())),
                'height': float((line_rects[i].height() if i < len(line_rects) else content_rect.height())),
                'pitch': max(1.0, float(raw.get('base_cell_h') or fm.height())),
                'line': str(lines[i] if i < len(lines) else ''),
                'start': int(starts[i] if i < len(starts) else 0),
            }
            for i in range(max(1, len(lines)))
        ],
        'caret_map': caret_map,
        'caret_styles': caret_styles,
        'char_rects': char_rects,
        'char_paths': char_paths,
        'content_rect': QRectF(content_rect).adjusted(-2, -2, 2, 2),
        'line_rects': line_rects,
        'base_cell_w': max(1.0, float(raw.get('base_cell_w') or fm.height())),
        'pitch': max(1.0, float(raw.get('base_cell_h') or fm.height())),
        'editor_live_renderer': True,
        'vertical_path_editor': True,
        'text_layout_refactor': True,
        'vertical_engine_independent': True,
        'desired_size': (desired_w, desired_h),
    }



def build_horizontal_editor_layout(owner: Any, cache_key=None) -> Dict[str, Any]:
    """Build horizontal direct-editor layout through the independent text module.

    This replaces the old main_window_support.py-local horizontal math.  The UI
    still owns painting, IME and event dispatch, but all text flow/caret/slot
    geometry is produced here so horizontal and vertical writing are both routed
    through text_layout modules.
    """
    rect = QRectF(owner.boundingRect())
    pad_x = 5.0
    pad_y = 5.0
    font = QFont(getattr(owner, '_inline_font', QFont()))
    try:
        fm = owner._cached_font_metrics(font)
    except Exception:
        fm = QFontMetrics(font)
    base_style = _base_style_from_owner(owner, font, fm)
    font = qfont_for_style(base_style, font)
    try:
        display_text, logical_text, _preedit, preedit_caret, preedit_len = owner._inline_display_text_with_preedit()
    except Exception:
        display_text = owner.toPlainText()
        logical_text = display_text
        preedit_caret = 0
        preedit_len = 0
    text = str(display_text or '')
    logical_text = str(logical_text or '')
    logical_len = len(logical_text)
    try:
        lines, starts = owner._split_vertical_lines(text)
    except Exception:
        lines = text.split('\n') if text else ['']
        starts = []
        pos = 0
        for line in lines:
            starts.append(pos)
            pos += len(line) + 1
    if not lines:
        lines, starts = [''], [0]
    try:
        line_spacing_pct = clamp_text_line_spacing(getattr(owner, 'line_spacing_pct', 100), 100)
    except Exception:
        line_spacing_pct = 100
    try:
        nominal = max(1.0, float(fm.lineSpacing()))
    except Exception:
        nominal = max(1.0, float(fm.height()))
    line_height = nominal * max(0.10, float(line_spacing_pct) / 100.0)
    try:
        letter_spacing = float(getattr(owner, 'letter_spacing', 0) or 0)
    except Exception:
        letter_spacing = 0.0
    style_provider = _style_provider_from_owner(owner, logical_len, int(preedit_caret or 0), int(preedit_len or 0), base_style)
    raw = build_horizontal_text_layout(
        lines,
        font,
        align=getattr(owner, 'align', 'center'),
        line_height=line_height,
        letter_spacing=letter_spacing,
        style_provider=style_provider,
        line_starts=starts,
        base_style=base_style,
    )
    raw_rect = QRectF(raw.get('content_rect') or QRectF())
    if raw_rect.isNull() or raw_rect.width() <= 0 or raw_rect.height() <= 0:
        raw_rect = QRectF(0.0, 0.0, max(1.0, float(raw.get('total_width') or 10.0)), max(1.0, float(raw.get('total_height') or fm.height())))
    available_w = max(1.0, float(rect.width()) - pad_x * 2.0)
    available_h = max(1.0, float(rect.height()) - pad_y * 2.0)
    # The horizontal engine returns coordinates around the line alignment origin.
    # Place the whole content inside the current edit box using the same workbench
    # feel as the previous inline editor.
    dx = pad_x + (available_w - raw_rect.width()) / 2.0 - raw_rect.left()
    dy = pad_y + (available_h - raw_rect.height()) / 2.0 - raw_rect.top()
    dy = max(pad_y - raw_rect.top(), min(float(rect.height()) * 3.0, dy))
    tr = QTransform(); tr.translate(dx, dy)

    char_paths = []
    char_rects = []
    content_rect = QRectF()
    for slot in raw.get('char_slots') or []:
        try:
            display_index = int(slot.get('display_index', 0))
            li = owner._logical_index_for_display_char(display_index, int(preedit_caret or 0), int(preedit_len or 0))
        except Exception:
            display_index = int(slot.get('display_index', 0) or 0)
            li = display_index
        if li < 0:
            li = max(0, min(logical_len, int(preedit_caret or 0)))
        rr = tr.mapRect(QRectF(slot.get('slot') or QRectF()))
        p = slot.get('path') or QPainterPath()
        mp = tr.map(p) if p is not None and not p.isEmpty() else QPainterPath()
        st = dict(slot.get('style') or base_style)
        kind = str(slot.get('kind') or '')
        fs = slot.get('flow_start')
        fe = slot.get('flow_end')
        char_rects.append((int(li), str(slot.get('char') or ''), QRectF(rr)))
        char_paths.append({
            'logical_index': int(li),
            'display_index': display_index,
            'char': str(slot.get('char') or ''),
            'kind': kind,
            'token': str(slot.get('token') or ''),
            'slot': QRectF(rr),
            'path': mp,
            'style': st,
            'flow_start': tr.map(QPointF(fs)) if fs is not None else QPointF(rr.left(), rr.center().y()),
            'flow_end': tr.map(QPointF(fe)) if fe is not None else QPointF(rr.right(), rr.center().y()),
        })
        content_rect = QRectF(rr) if content_rect.isNull() else content_rect.united(QRectF(rr))
        if not mp.isEmpty():
            content_rect = QRectF(mp.boundingRect()) if content_rect.isNull() else content_rect.united(QRectF(mp.boundingRect()))

    display_caret_map = {}
    for k, p in (raw.get('display_caret_map') or {}).items():
        try:
            display_caret_map[int(k)] = tr.map(QPointF(p))
        except Exception:
            pass
    caret_map = {}
    caret_styles = {}
    ordered_chars = sorted(
        [cp for cp in char_paths if int(cp.get('logical_index', -1)) >= 0],
        key=lambda cp: (int(cp.get('logical_index', 0)), int(cp.get('display_index', 0)))
    )
    for cp in ordered_chars:
        try:
            li = int(cp.get('logical_index', 0))
            fs = cp.get('flow_start')
            if fs is not None:
                caret_map[li] = QPointF(fs)
        except Exception:
            pass
    if ordered_chars:
        try:
            last = ordered_chars[-1]
            li = int(last.get('logical_index', 0))
            fe = last.get('flow_end')
            caret_map[li + 1] = QPointF(fe) if fe is not None else QPointF(QRectF(last.get('slot')).right(), QRectF(last.get('slot')).center().y())
        except Exception:
            pass
    for logical_pos in range(0, logical_len + 1):
        if logical_pos in caret_map:
            continue
        try:
            if preedit_len and logical_pos == preedit_caret:
                display_pos = int(preedit_caret) + int(preedit_len)
            else:
                display_pos = owner._display_index_for_logical_caret(logical_pos, int(preedit_caret or 0), int(preedit_len or 0))
        except Exception:
            display_pos = logical_pos
        pnt = display_caret_map.get(int(display_pos))
        if pnt is not None:
            caret_map[logical_pos] = QPointF(pnt)
    if logical_len not in caret_map:
        pnt = display_caret_map.get(len(text))
        caret_map[logical_len] = QPointF(pnt) if pnt is not None else QPointF(float(rect.center().x()), float(rect.center().y()))

    line_rects = [tr.mapRect(QRectF(r)).adjusted(-2, -2, 2, 2) for r in (raw.get('line_rects') or [])]
    if content_rect.isNull() or content_rect.width() <= 0 or content_rect.height() <= 0:
        content_rect = QRectF(float(rect.center().x()) - 5.0, float(rect.center().y()) - 5.0, 10.0, 10.0)
    desired_w = max(18.0, float(content_rect.width()) + 14.0)
    desired_h = max(18.0, float(content_rect.height()) + 14.0)
    columns = []
    for i, line in enumerate(lines):
        lr = line_rects[i] if i < len(line_rects) else QRectF(content_rect)
        columns.append({
            'line': str(line or ''),
            'start': int(starts[i] if i < len(starts) else 0),
            'display_start': int(starts[i] if i < len(starts) else 0),
            'length': len(str(line or '')),
            'display_length': len(str(line or '')),
            'x': float(lr.left()),
            'y0': float(lr.top()),
            'pitch': max(1.0, float(lr.height())),
            'cell_w': max(1.0, float(raw.get('base_line_height') or fm.height())),
            'line_h': max(1.0, float(lr.height())),
            'col': i,
        })
    return {
        'key': cache_key,
        'font': font,
        'fm': fm,
        'columns': columns,
        'caret_map': caret_map,
        'caret_styles': caret_styles,
        'char_rects': char_rects,
        'char_paths': char_paths,
        'content_rect': QRectF(content_rect).adjusted(-2, -2, 2, 2),
        'line_rects': line_rects,
        'base_cell_w': max(1.0, float(raw.get('base_line_height') or fm.height())),
        'pitch': max(1.0, float(raw.get('base_line_height') or fm.height())),
        'horizontal_direct': True,
        'editor_live_renderer': True,
        'horizontal_engine_independent': True,
        'text_layout_refactor': True,
        'desired_size': (desired_w, desired_h),
    }
