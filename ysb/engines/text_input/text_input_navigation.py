from __future__ import annotations

from typing import Any, List, Dict
from PyQt6.QtCore import QPointF


def inline_caret_point(owner: Any, pos=None) -> QPointF:
    try:
        layout = owner._layout_vertical_text()
        caret_map = layout.get('caret_map') or {}
        if pos is None:
            pos = int(getattr(owner, '_v_caret_index', 0) or 0)
        p = caret_map.get(int(pos))
        if p is not None:
            return QPointF(p)
    except Exception:
        pass
    try:
        return QPointF(owner.boundingRect().center())
    except Exception:
        return QPointF(0, 0)


def update_desired_caret_axis_from_current(owner: Any) -> None:
    try:
        p = inline_caret_point(owner, int(getattr(owner, '_v_caret_index', 0) or 0))
        owner._v_desired_caret_x = float(p.x())
        owner._v_desired_caret_y = float(p.y())
    except Exception:
        pass


def line_index_for_caret(lines, starts, pos) -> int:
    try:
        pos = int(pos)
    except Exception:
        pos = 0
    for i, start in enumerate(starts or []):
        try:
            start = int(start)
            line_len = len(str(lines[i] if i < len(lines) else ''))
            if start <= pos <= start + line_len:
                return i
        except Exception:
            pass
    return max(0, len(lines or ['']) - 1)


def horizontal_visual_rows(owner: Any) -> List[Dict[str, Any]]:
    layout = owner._layout_vertical_text()
    rows = []
    for order, row in enumerate(layout.get('columns') or []):
        try:
            line = str(row.get('line') or '')
            start = int(row.get('start') or 0)
            y0 = float(row.get('y0') or 0.0)
            pitch = max(1.0, float(row.get('pitch') or row.get('line_h') or 1.0))
            x0 = float(row.get('x') or 0.0)
            rows.append({'visual_order': order, 'line': line, 'start': start, 'length': len(line), 'y': y0 + pitch / 2.0, 'x': x0, 'pitch': pitch})
        except Exception:
            continue
    rows.sort(key=lambda r: (float(r.get('y', 0.0)), int(r.get('start', 0))))
    return rows


def nearest_visual_row_index_for_caret(owner: Any, rows, pos) -> int:
    if not rows:
        return 0
    try:
        pos = int(pos)
    except Exception:
        pos = 0
    try:
        p = inline_caret_point(owner, pos)
        py = float(p.y())
        return min(range(len(rows)), key=lambda i: (abs(float(rows[i].get('y', 0.0)) - py), abs(int(rows[i].get('start', 0)) - pos)))
    except Exception:
        pass
    for i, row in enumerate(rows):
        start = int(row.get('start') or 0)
        end = start + int(row.get('length') or 0)
        if start <= pos <= end:
            return i
    return 0


def nearest_caret_in_line_by_axis(owner: Any, target_start, target_len, axis_value, axis='x') -> int:
    layout = owner._layout_vertical_text()
    caret_map = layout.get('caret_map') or {}
    candidates = []
    for off in range(0, int(target_len) + 1):
        idx = int(target_start) + off
        p = caret_map.get(idx)
        if p is None:
            continue
        try:
            p = QPointF(p)
            v = float(p.x()) if axis == 'x' else float(p.y())
            candidates.append((abs(v - float(axis_value)), off, idx))
        except Exception:
            continue
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return int(candidates[0][2])
    return int(target_start) + min(max(0, int(target_len)), int(target_len))





def partial_horizontal_runs(owner: Any) -> List[Dict[str, Any]]:
    """Return visual partial-horizontal runs in the vertical inline editor.

    A run such as "456" is still one vertical-flow item, but its internal
    carets move on the X axis.  Keyboard navigation must know that range so
    Left/Right can behave like horizontal text while Up/Down leave the row.
    """
    try:
        layout = owner._layout_vertical_text()
    except Exception:
        return []
    runs: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    def _flush() -> None:
        nonlocal current
        if not current:
            return
        try:
            start = int(current.get('start', 0))
            end = int(current.get('end', start))
            if end > start:
                runs.append(dict(current))
        except Exception:
            pass
        current = None

    cps = []
    for cp in (layout.get('char_paths') or []):
        try:
            if not (bool(cp.get('inline_horizontal', False)) or str(cp.get('caret_axis') or '') == 'horizontal'):
                continue
            li = int(cp.get('logical_index', -1))
            if li < 0:
                continue
            fs = cp.get('flow_start')
            fe = cp.get('flow_end')
            try:
                fs_p = QPointF(fs) if fs is not None else QPointF(cp.get('slot').center())
            except Exception:
                fs_p = QPointF(0, 0)
            try:
                fe_p = QPointF(fe) if fe is not None else fs_p
            except Exception:
                fe_p = fs_p
            token_index = cp.get('token_index')
            try:
                token_key = int(token_index)
            except Exception:
                # Fallback for older layouts: keep only visually adjacent chars
                # with almost the same Y center in one run.
                token_key = (str(cp.get('token') or ''), round(float(fs_p.y()), 2))
            cps.append({
                'li': li,
                'token_key': token_key,
                'flow_start': fs_p,
                'flow_end': fe_p,
                'slot': cp.get('slot'),
            })
        except Exception:
            continue
    cps.sort(key=lambda item: int(item.get('li', 0)))
    for item in cps:
        li = int(item.get('li', 0))
        token_key = item.get('token_key')
        fs_p = QPointF(item.get('flow_start'))
        fe_p = QPointF(item.get('flow_end'))
        if current is None:
            current = {
                'start': li,
                'end': li + 1,
                'token_key': token_key,
                'center_y': float(fs_p.y()),
                'min_x': min(float(fs_p.x()), float(fe_p.x())),
                'max_x': max(float(fs_p.x()), float(fe_p.x())),
            }
            continue
        same_token = current.get('token_key') == token_key
        contiguous = li == int(current.get('end', li))
        same_row = abs(float(current.get('center_y', 0.0)) - float(fs_p.y())) <= 3.0
        if same_token and contiguous and same_row:
            current['end'] = li + 1
            try:
                current['min_x'] = min(float(current.get('min_x', fs_p.x())), float(fs_p.x()), float(fe_p.x()))
                current['max_x'] = max(float(current.get('max_x', fs_p.x())), float(fs_p.x()), float(fe_p.x()))
                current['center_y'] = (float(current.get('center_y', fs_p.y())) + float(fs_p.y())) / 2.0
            except Exception:
                pass
        else:
            _flush()
            current = {
                'start': li,
                'end': li + 1,
                'token_key': token_key,
                'center_y': float(fs_p.y()),
                'min_x': min(float(fs_p.x()), float(fe_p.x())),
                'max_x': max(float(fs_p.x()), float(fe_p.x())),
            }
    _flush()
    return runs


def partial_horizontal_run_for_caret(owner: Any, pos=None) -> Dict[str, Any] | None:
    try:
        if pos is None:
            pos = int(getattr(owner, '_v_caret_index', 0) or 0)
        pos = int(pos)
    except Exception:
        pos = 0
    for run in partial_horizontal_runs(owner):
        try:
            start = int(run.get('start', 0))
            end = int(run.get('end', start))
            if start <= pos <= end:
                return run
        except Exception:
            continue
    return None


def move_partial_horizontal_inline(owner: Any, right=True, keep_anchor=False) -> bool:
    """Move inside a partial-horizontal run with Left/Right keys.

    Returns True when the caret is in a partial-horizontal run and the key was
    consumed.  At the left/right edge we intentionally stay in place; Up/Down is
    the way to leave the row visually.
    """
    try:
        pos = int(getattr(owner, '_v_caret_index', 0) or 0)
    except Exception:
        pos = 0
    run = partial_horizontal_run_for_caret(owner, pos)
    if not run:
        return False
    try:
        start = int(run.get('start', 0))
        end = int(run.get('end', start))
    except Exception:
        return False
    target = pos + (1 if right else -1)
    if target < start or target > end:
        target = pos
    owner._set_vertical_caret(target, keep_anchor=keep_anchor, preserve_desired=False)
    return True


def move_vertical_out_of_partial_horizontal(owner: Any, down=True, keep_anchor=False) -> bool:
    """Let Up/Down leave a partial-horizontal row as one visual unit."""
    try:
        text_len = len(owner.toPlainText())
        pos = int(getattr(owner, '_v_caret_index', 0) or 0)
    except Exception:
        text_len = 0
        pos = 0
    run = partial_horizontal_run_for_caret(owner, pos)
    if not run:
        return False
    try:
        start = int(run.get('start', 0))
        end = int(run.get('end', start))
    except Exception:
        return False
    if down:
        # Inside the row -> jump to the after-run boundary.  If already at the
        # boundary, continue normal vertical movement by one logical step.
        target = end if pos < end else min(text_len, end + 1)
    else:
        # Inside the row -> jump to the before-run boundary.  If already at the
        # boundary, continue normal vertical movement by one logical step.
        target = start if pos > start else max(0, start - 1)
    owner._set_vertical_caret(target, keep_anchor=keep_anchor, preserve_desired=False)
    return True

def move_horizontal_line(owner: Any, up=True, keep_anchor=False) -> bool:
    text = owner.toPlainText()
    lines, starts = owner._split_vertical_lines(text)
    if not lines:
        return True
    pos = int(getattr(owner, '_v_caret_index', 0) or 0)
    try:
        desired_x = getattr(owner, '_v_desired_caret_x', None)
        if desired_x is None:
            desired_x = float(inline_caret_point(owner, pos).x())
            owner._v_desired_caret_x = desired_x
    except Exception:
        desired_x = float(inline_caret_point(owner, pos).x())
    rows = horizontal_visual_rows(owner)
    if rows:
        current_row = nearest_visual_row_index_for_caret(owner, rows, pos)
        target_row = current_row + (-1 if up else 1)
        if target_row < 0 or target_row >= len(rows):
            owner._set_vertical_caret(pos, keep_anchor=keep_anchor, preserve_desired=True)
            return True
        row = rows[target_row]
        target_pos = nearest_caret_in_line_by_axis(owner, int(row.get('start') or 0), int(row.get('length') or 0), desired_x, axis='x')
        owner._set_vertical_caret(target_pos, keep_anchor=keep_anchor, preserve_desired=True)
        return True
    current_line = line_index_for_caret(lines, starts, pos)
    target_line = current_line + (-1 if up else 1)
    if target_line < 0 or target_line >= len(lines):
        owner._set_vertical_caret(pos, keep_anchor=keep_anchor, preserve_desired=True)
        return True
    target_pos = nearest_caret_in_line_by_axis(owner, int(starts[target_line]), len(lines[target_line]), desired_x, axis='x')
    owner._set_vertical_caret(target_pos, keep_anchor=keep_anchor, preserve_desired=True)
    return True


def move_vertical_column(owner: Any, left=True, keep_anchor=False) -> bool:
    text = owner.toPlainText()
    lines, starts = owner._split_vertical_lines(text)
    if not lines:
        return True
    pos = int(getattr(owner, '_v_caret_index', 0) or 0)
    current_line = line_index_for_caret(lines, starts, pos)
    target_line = current_line + (1 if left else -1)
    if target_line < 0 or target_line >= len(lines):
        owner._set_vertical_caret(pos, keep_anchor=keep_anchor, preserve_desired=True)
        return True
    try:
        desired_y = getattr(owner, '_v_desired_caret_y', None)
        if desired_y is None:
            desired_y = float(inline_caret_point(owner, pos).y())
            owner._v_desired_caret_y = desired_y
    except Exception:
        desired_y = float(inline_caret_point(owner, pos).y())
    target_pos = nearest_caret_in_line_by_axis(owner, int(starts[target_line]), len(lines[target_line]), desired_y, axis='y')
    owner._set_vertical_caret(target_pos, keep_anchor=keep_anchor, preserve_desired=True)
    return True
