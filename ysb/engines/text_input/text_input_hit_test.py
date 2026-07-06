from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt


def _qrect(value) -> QRectF:
    try:
        return QRectF(value)
    except Exception:
        return QRectF()


def caret_index_from_pos(owner: Any, pos) -> int:
    """Return editor caret index from a mouse position using layout data only.

    This module owns hit testing for custom text input.  main_window_support.py
    should not duplicate vertical/horizontal caret math.
    """
    layout = owner._layout_vertical_text()
    text = str(owner.toPlainText() or '')
    text_len = len(text)
    try:
        p = QPointF(pos)
    except Exception:
        p = QPointF(0, 0)

    if layout.get('horizontal_direct'):
        rows = list(layout.get('columns') or [])
        if not rows:
            return 0
        y = float(p.y())
        row = min(rows, key=lambda c: abs(y - (float(c.get('y0', 0.0)) + float(c.get('pitch', 1.0)) / 2.0)))
        line = str(row.get('line') or '')
        start = int(row.get('start') or 0)
        char_rects = [(idx, ch, _qrect(r)) for idx, ch, r in (layout.get('char_rects') or []) if start <= int(idx) < start + len(line)]
        x = float(p.x())
        if not char_rects:
            return max(0, min(text_len, start))
        for idx, _ch, r in char_rects:
            if x < r.center().x():
                return max(0, min(text_len, int(idx)))
        return max(0, min(text_len, start + len(line)))

    # Prefer explicit flow_start/flow_end carried by char_paths when available.
    try:
        cps = [cp for cp in (layout.get('char_paths') or []) if int(cp.get('logical_index', -1)) >= 0]
        if cps:
            x = float(p.x()); y = float(p.y())
            # choose nearest column first, then nearest flow boundary in that column
            columns = list(layout.get('columns') or [])
            if columns:
                col = min(columns, key=lambda c: abs(x - float(c.get('x', 0.0))))
                start = int(col.get('start') or 0)
                line = str(col.get('line') or '')
                cps = [cp for cp in cps if start <= int(cp.get('logical_index', 0)) <= start + len(line)] or cps
            boundaries = []
            for cp in cps:
                li = int(cp.get('logical_index', 0))
                fs = cp.get('flow_start')
                fe = cp.get('flow_end')
                if fs is not None:
                    fs = QPointF(fs)
                    boundaries.append((abs(float(fs.y()) - y) + abs(float(fs.x()) - x) * 0.08, li))
                if fe is not None:
                    fe = QPointF(fe)
                    boundaries.append((abs(float(fe.y()) - y) + abs(float(fe.x()) - x) * 0.08, li + 1))
            if boundaries:
                return max(0, min(text_len, sorted(boundaries, key=lambda v: v[0])[0][1]))
    except Exception:
        pass

    columns = layout.get('columns') or []
    if not columns:
        return 0
    x = float(p.x()); y = float(p.y())
    col = min(columns, key=lambda c: abs(x - float(c.get('x', 0.0))))
    line = str(col.get('line') or '')
    start = int(col.get('start') or 0)
    try:
        candidates = []
        caret_map = layout.get('caret_map') or {}
        for off in range(0, len(line) + 1):
            pp = caret_map.get(start + off)
            if pp is not None:
                pp = QPointF(pp)
                candidates.append((abs(float(pp.y()) - y) + abs(float(pp.x()) - x) * 0.08, off))
        if candidates:
            return max(0, min(text_len, start + sorted(candidates, key=lambda pair: pair[0])[0][1]))
    except Exception:
        pass
    pitch = max(1.0, float(col.get('pitch') or 1.0))
    y0 = float(col.get('y0') or 0.0)
    offset = int(round((y - y0) / pitch))
    return max(0, min(text_len, start + max(0, min(len(line), offset))))


def cursor_rect(owner: Any) -> QRectF:
    layout = owner._layout_vertical_text()
    caret_map = layout.get('caret_map') or {}
    try:
        caret_index = int(getattr(owner, '_v_caret_index', 0))
    except Exception:
        caret_index = 0
    try:
        p = caret_map.get(caret_index)
    except Exception:
        p = None
    if p is None:
        p = QPointF(owner.boundingRect().center())
    else:
        p = QPointF(p)
    if layout.get('horizontal_direct'):
        line_h = float(layout.get('pitch') or 14.0)
        try:
            line_rects = [QRectF(r) for r in (layout.get('line_rects') or []) if QRectF(r).isValid()]
            if line_rects:
                lr = min(line_rects, key=lambda rr: abs(float(rr.center().y()) - float(p.y())))
                if lr.width() > 0 and lr.height() > 0:
                    line_h = max(8.0, float(lr.height()) + 4.0)
                    p = QPointF(float(p.x()), float(lr.center().y()))
        except Exception:
            pass
        thickness = max(2.0, min(5.0, line_h * 0.08))
        return QRectF(p.x() - thickness / 2.0, p.y() - line_h * 0.5, thickness, line_h)

    # Vertical editor with partial horizontal writing: inside latin/code/digit/
    # symbol runs the caret must become the normal horizontal-editor caret, i.e.
    # a vertical bar moving left-to-right across the row.
    try:
        info = (layout.get('caret_styles') or {}).get(caret_index)
        if isinstance(info, dict) and str(info.get('orientation') or '') == 'horizontal':
            line_h = max(8.0, float(info.get('height') or 0.0))
            try:
                center_y = float(info.get('center_y'))
            except Exception:
                center_y = float(p.y())
            thickness = max(2.0, min(5.0, line_h * 0.08))
            return QRectF(p.x() - thickness / 2.0, center_y - line_h * 0.5, thickness, line_h)
    except Exception:
        pass

    cell_w = float(layout.get('base_cell_w') or 10.0)
    thickness = max(3.0, min(8.0, cell_w * 0.08))
    return QRectF(p.x() - cell_w * 0.58, p.y() - thickness / 2.0, cell_w * 1.16, thickness)
