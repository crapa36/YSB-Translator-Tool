from __future__ import annotations

from typing import Any, Tuple
from PyQt6.QtCore import QRectF


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def selected_range(owner: Any) -> Tuple[int, int]:
    try:
        # 0 is a valid anchor/caret.  Avoid `or` so selection from the first
        # position can be created by Shift movement or mouse drag.
        a = _safe_int(getattr(owner, '_v_selection_anchor', 0), 0)
        b = _safe_int(getattr(owner, '_v_caret_index', 0), 0)
        return (min(a, b), max(a, b))
    except Exception:
        return (0, 0)


def has_selection(owner: Any) -> bool:
    a, b = selected_range(owner)
    return bool(b > a)


def inline_selection_dirty_rect(owner: Any) -> QRectF:
    try:
        a, b = selected_range(owner)
        if b <= a:
            return QRectF(owner._vertical_cursor_rect()).adjusted(-8, -8, 8, 8)
        layout = owner._layout_vertical_text()
        rect = QRectF()
        for idx, _ch, r in layout.get('char_rects') or []:
            try:
                if a <= int(idx) < b:
                    rr = QRectF(r).adjusted(-4, -4, 4, 4)
                    rect = rr if rect.isNull() else rect.united(rr)
            except Exception:
                pass
        if rect.isNull():
            rect = QRectF(owner.boundingRect()).adjusted(-8, -8, 8, 8)
        return rect
    except Exception:
        try:
            return QRectF(owner.boundingRect()).adjusted(-8, -8, 8, 8)
        except Exception:
            return QRectF()
