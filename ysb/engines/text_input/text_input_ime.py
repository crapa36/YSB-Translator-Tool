from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt

from .text_input_commands import replace_selection, delete_selection_for_ime_preedit
from .text_input_selection import has_selection
from .text_input_state import selected_range
from .text_input_hit_test import cursor_rect


def process_input_method_event(owner: Any, event: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    try:
        commit = str(event.commitString() or '')
    except Exception:
        commit = ''
    try:
        preedit = str(event.preeditString() or '')
    except Exception:
        preedit = ''
    replaced_selection_for_preedit = False
    try:
        if preedit and not commit and has_selection(owner):
            replaced_selection_for_preedit = delete_selection_for_ime_preedit(owner)
    except Exception:
        pass
    if commit:
        suppress_commit_undo = bool(getattr(owner, '_v_ime_selection_preedit_active', False))
        replace_selection(owner, commit, push_undo=not suppress_commit_undo, reason='ime-commit')
        owner._v_ime_selection_preedit_active = False
    elif not preedit:
        owner._v_ime_selection_preedit_active = False
    owner._v_preedit_text = preedit
    try:
        owner._v_ime_composition_serial = int(getattr(owner, '_v_ime_composition_serial', 0) or 0) + 1
    except Exception:
        owner._v_ime_composition_serial = 1
    try:
        visible_preedit = visible_preedit_text(preedit)
        if preedit and visible_preedit != preedit:
            owner._inline_trace('INLINE_EDITOR_IME_PREEDIT_VISIBLE_MAP', raw_len=len(preedit), visible_len=len(visible_preedit), serial=int(getattr(owner, '_v_ime_composition_serial', 0) or 0))
    except Exception:
        pass
    try:
        owner.invalidate_vertical_layout()
    except Exception:
        pass
    try:
        owner._sync_direct_editor_after_text_change(reason='ime-preedit-replace-selection' if replaced_selection_for_preedit else 'ime-preedit')
    except Exception:
        pass
    try:
        owner._force_inline_editor_dirty_repaint(reason='ime-preedit-serial')
    except Exception:
        pass
    try:
        event.accept()
    except Exception:
        pass
    return True


def input_method_query(owner: Any, query: Any):
    if not getattr(owner, '_vertical_editor', False):
        return None
    if query == Qt.InputMethodQuery.ImCursorRectangle:
        return cursor_rect(owner)
    if query == Qt.InputMethodQuery.ImSurroundingText:
        return owner.toPlainText()
    if query == Qt.InputMethodQuery.ImCursorPosition:
        return int(getattr(owner, '_v_caret_index', 0))
    if query == Qt.InputMethodQuery.ImAnchorPosition:
        return int(getattr(owner, '_v_selection_anchor', getattr(owner, '_v_caret_index', 0)))
    if query == Qt.InputMethodQuery.ImCurrentSelection:
        try:
            a, b = selected_range(owner)
        except Exception:
            a = b = 0
        return owner.toPlainText()[a:b]
    return None


_CHOSEONG = {
    0x1100: 'ㄱ', 0x1101: 'ㄲ', 0x1102: 'ㄴ', 0x1103: 'ㄷ', 0x1104: 'ㄸ',
    0x1105: 'ㄹ', 0x1106: 'ㅁ', 0x1107: 'ㅂ', 0x1108: 'ㅃ', 0x1109: 'ㅅ',
    0x110A: 'ㅆ', 0x110B: 'ㅇ', 0x110C: 'ㅈ', 0x110D: 'ㅉ', 0x110E: 'ㅊ',
    0x110F: 'ㅋ', 0x1110: 'ㅌ', 0x1111: 'ㅍ', 0x1112: 'ㅎ',
}
_JUNGSEONG = {
    0x1161: 'ㅏ', 0x1162: 'ㅐ', 0x1163: 'ㅑ', 0x1164: 'ㅒ', 0x1165: 'ㅓ',
    0x1166: 'ㅔ', 0x1167: 'ㅕ', 0x1168: 'ㅖ', 0x1169: 'ㅗ', 0x116A: 'ㅘ',
    0x116B: 'ㅙ', 0x116C: 'ㅚ', 0x116D: 'ㅛ', 0x116E: 'ㅜ', 0x116F: 'ㅝ',
    0x1170: 'ㅞ', 0x1171: 'ㅟ', 0x1172: 'ㅠ', 0x1173: 'ㅡ', 0x1174: 'ㅢ', 0x1175: 'ㅣ',
}
_JONGSEONG = {
    0x11A8: 'ㄱ', 0x11A9: 'ㄲ', 0x11AA: 'ㄳ', 0x11AB: 'ㄴ', 0x11AC: 'ㄵ',
    0x11AD: 'ㄶ', 0x11AE: 'ㄷ', 0x11AF: 'ㄹ', 0x11B0: 'ㄺ', 0x11B1: 'ㄻ',
    0x11B2: 'ㄼ', 0x11B3: 'ㄽ', 0x11B4: 'ㄾ', 0x11B5: 'ㄿ', 0x11B6: 'ㅀ',
    0x11B7: 'ㅁ', 0x11B8: 'ㅂ', 0x11B9: 'ㅄ', 0x11BA: 'ㅅ', 0x11BB: 'ㅆ',
    0x11BC: 'ㅇ', 0x11BD: 'ㅈ', 0x11BE: 'ㅊ', 0x11BF: 'ㅋ', 0x11C0: 'ㅌ',
    0x11C1: 'ㅍ', 0x11C2: 'ㅎ',
}


def visible_preedit_text(preedit: str) -> str:
    text = str(preedit or '')
    if not text:
        return ''
    out = []
    changed = False
    for ch in text:
        repl = _CHOSEONG.get(ord(ch)) or _JUNGSEONG.get(ord(ch)) or _JONGSEONG.get(ord(ch))
        if repl is not None:
            out.append(repl); changed = True
        else:
            out.append(ch)
    return ''.join(out) if changed else text


def plain_text_with_preedit(owner: Any) -> str:
    try:
        text = str(owner.toPlainText() or '')
    except Exception:
        text = ''
    preedit = visible_preedit_text(getattr(owner, '_v_preedit_text', '') or '')
    if not preedit:
        return text
    try:
        pos = int(getattr(owner, '_v_caret_index', len(text)) or 0)
    except Exception:
        pos = len(text)
    pos = max(0, min(len(text), pos))
    return text[:pos] + preedit + text[pos:]


def display_text_with_preedit(owner: Any):
    try:
        text = str(owner.toPlainText() or '')
    except Exception:
        text = ''
    preedit = visible_preedit_text(getattr(owner, '_v_preedit_text', '') or '')
    try:
        caret = int(getattr(owner, '_v_caret_index', len(text)) or 0)
    except Exception:
        caret = len(text)
    caret = max(0, min(len(text), caret))
    if not preedit:
        return text, text, '', caret, 0
    return text[:caret] + preedit + text[caret:], text, preedit, caret, len(preedit)


def display_index_for_logical_caret(owner: Any, logical_pos, caret=None, preedit_len=None) -> int:
    try:
        pos = int(logical_pos or 0)
    except Exception:
        pos = 0
    try:
        if caret is None:
            caret = int(getattr(owner, '_v_caret_index', 0) or 0)
    except Exception:
        caret = 0
    try:
        if preedit_len is None:
            preedit_len = len(str(getattr(owner, '_v_preedit_text', '') or ''))
    except Exception:
        preedit_len = 0
    if preedit_len and pos > int(caret):
        return pos + int(preedit_len)
    return pos


def logical_index_for_display_char(owner: Any, display_index, caret=None, preedit_len=None) -> int:
    try:
        d = int(display_index or 0)
    except Exception:
        d = 0
    try:
        if caret is None:
            caret = int(getattr(owner, '_v_caret_index', 0) or 0)
    except Exception:
        caret = 0
    try:
        if preedit_len is None:
            preedit_len = len(str(getattr(owner, '_v_preedit_text', '') or ''))
    except Exception:
        preedit_len = 0
    if preedit_len and int(caret) <= d < int(caret) + int(preedit_len):
        return -100000 - (d - int(caret))
    if preedit_len and d >= int(caret) + int(preedit_len):
        return d - int(preedit_len)
    return d
