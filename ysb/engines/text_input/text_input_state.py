from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


@dataclass
class TextInputState:
    text: str = ''
    caret: int = 0
    anchor: int = 0
    preedit: str = ''
    ime_selection_preedit_active: bool = False
    writing_direction: str = 'horizontal'

    @property
    def selection(self) -> Tuple[int, int]:
        return (min(int(self.caret), int(self.anchor)), max(int(self.caret), int(self.anchor)))


def clamp_index(value: Any, text_len: int) -> int:
    try:
        i = int(value or 0)
    except Exception:
        i = 0
    return max(0, min(int(text_len or 0), i))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def selected_range(owner: Any) -> Tuple[int, int]:
    try:
        c = _safe_int(getattr(owner, '_v_caret_index', 0), 0)
        # Anchor 0 is a real position.  Never use `or c` here.
        a = _safe_int(getattr(owner, '_v_selection_anchor', c), c)
        return (min(a, c), max(a, c))
    except Exception:
        return (0, 0)


def state_from_owner(owner: Any) -> TextInputState:
    text = str(owner.toPlainText() if hasattr(owner, 'toPlainText') else getattr(owner, '_v_text', '') or '')
    caret = clamp_index(getattr(owner, '_v_caret_index', 0), len(text))
    anchor = clamp_index(getattr(owner, '_v_selection_anchor', caret), len(text))
    try:
        direction = 'vertical' if owner._is_vertical_writing() else 'horizontal'
    except Exception:
        direction = str(getattr(owner, 'writing_direction', 'horizontal') or 'horizontal')
    return TextInputState(
        text=text,
        caret=caret,
        anchor=anchor,
        preedit=str(getattr(owner, '_v_preedit_text', '') or ''),
        ime_selection_preedit_active=bool(getattr(owner, '_v_ime_selection_preedit_active', False)),
        writing_direction=direction,
    )


def apply_text_state(owner: Any, text: str, caret: int, anchor: int | None = None) -> None:
    text = str(text or '')
    caret = clamp_index(caret, len(text))
    anchor = caret if anchor is None else clamp_index(anchor, len(text))
    owner._v_text = text
    owner._v_caret_index = caret
    owner._v_selection_anchor = anchor
    try:
        owner._v_document.setPlainText(owner._v_text)
    except Exception:
        pass
