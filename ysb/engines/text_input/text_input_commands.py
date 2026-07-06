from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QTextCursor, QKeySequence

from .text_input_state import clamp_index, selected_range, apply_text_state
from .text_input_selection import has_selection, inline_selection_dirty_rect
from .text_input_navigation import (
    update_desired_caret_axis_from_current,
    move_horizontal_line,
    move_vertical_column,
    move_partial_horizontal_inline,
    move_vertical_out_of_partial_horizontal,
)
from .text_input_lifecycle import push_undo_snapshot
from ysb.settings.shortcut_settings import TEXT_SYMBOLS


def _sync_after_text_change(owner: Any, reason: str) -> None:
    try:
        owner._sync_direct_editor_after_text_change(reason=reason)
    except Exception:
        pass
    try:
        update_desired_caret_axis_from_current(owner)
    except Exception:
        pass


def set_caret(owner: Any, pos: int, keep_anchor: bool = False, preserve_desired: bool = False) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    text_len = len(owner.toPlainText())
    old_caret = int(getattr(owner, '_v_caret_index', 0) or 0)
    old_anchor = int(old_caret if getattr(owner, '_v_selection_anchor', old_caret) is None else getattr(owner, '_v_selection_anchor', old_caret))
    old_dirty = old_selection_dirty = None
    try:
        old_dirty = QRectF(__import__("ysb.engines.text_input.text_input_hit_test", fromlist=["cursor_rect"]).cursor_rect(owner)).adjusted(-10, -10, 10, 10)
    except Exception:
        pass
    try:
        if old_anchor != old_caret:
            old_selection_dirty = inline_selection_dirty_rect(owner)
    except Exception:
        pass

    pos = clamp_index(pos, text_len)
    owner._v_caret_index = pos
    if not keep_anchor:
        owner._v_selection_anchor = pos
    owner._v_preedit_text = ''
    owner._v_ime_selection_preedit_active = False
    owner._v_cursor_visible = True
    if not preserve_desired:
        try:
            update_desired_caret_axis_from_current(owner)
        except Exception:
            pass
    try:
        new_dirty = QRectF(__import__("ysb.engines.text_input.text_input_hit_test", fromlist=["cursor_rect"]).cursor_rect(owner)).adjusted(-10, -10, 10, 10)
        old_selected = old_anchor != old_caret
        new_selected = int(pos if getattr(owner, '_v_selection_anchor', pos) is None else getattr(owner, '_v_selection_anchor', pos)) != pos
        dirty = QRectF()
        for r in (old_dirty, old_selection_dirty, new_dirty, inline_selection_dirty_rect(owner) if new_selected else None):
            try:
                if r is not None and QRectF(r).isValid():
                    rr = QRectF(r)
                    dirty = rr if dirty.isNull() else dirty.united(rr)
            except Exception:
                pass
        if old_selected or new_selected or bool(keep_anchor):
            try:
                dirty = dirty.united(QRectF(owner.boundingRect()).adjusted(-12, -12, 12, 12)) if not dirty.isNull() else QRectF(owner.boundingRect()).adjusted(-12, -12, 12, 12)
            except Exception:
                pass
            owner._force_inline_editor_dirty_repaint(dirty, reason='selection-caret-change')
        elif old_dirty is not None:
            owner._force_inline_editor_dirty_repaint(old_dirty.united(new_dirty), reason='caret-move')
        else:
            owner._force_inline_editor_dirty_repaint(new_dirty, reason='caret-move')
    except Exception:
        try:
            owner._force_inline_editor_dirty_repaint(reason='caret-fallback')
        except Exception:
            pass
    return True


def replace_selection(owner: Any, insert_text: str, push_undo: bool = True, reason: str = 'text-change') -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    text = owner.toPlainText()
    a, b = selected_range(owner)
    insert_text = str(insert_text or '')
    caret = clamp_index(getattr(owner, '_v_caret_index', 0), len(text))
    has_selection = bool(b > a)
    if not has_selection:
        a = b = caret
    action = 'replace' if has_selection else 'insert'
    if a == b and not insert_text:
        return True
    if push_undo:
        try:
            push_undo_snapshot(owner)
        except Exception:
            pass
    new_text = text[:a] + insert_text + text[b:]
    new_caret = a + len(insert_text)
    apply_text_state(owner, new_text, new_caret, new_caret)
    owner._v_preedit_text = ''
    owner._v_ime_selection_preedit_active = False
    _sync_after_text_change(owner, reason)
    try:
        owner._inline_trace('INLINE_EDITOR_TEXT_CHANGE', action=action, inserted_len=len(insert_text), new_len=len(owner._v_text), caret=owner._v_caret_index)
    except Exception:
        pass
    return True


def delete_selection_for_ime_preedit(owner: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    a, b = selected_range(owner)
    if not (b > a):
        return False
    text = owner.toPlainText()
    try:
        push_undo_snapshot(owner)
    except Exception:
        pass
    apply_text_state(owner, text[:a] + text[b:], a, a)
    owner._v_preedit_text = ''
    owner._v_ime_selection_preedit_active = True
    _sync_after_text_change(owner, 'ime-preedit-replace-selection')
    return True


def delete_backward(owner: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    try:
        if has_selection(owner):
            return replace_selection(owner, '')
    except Exception:
        pass
    text = owner.toPlainText()
    i = clamp_index(getattr(owner, '_v_caret_index', 0), len(text))
    if i <= 0:
        return True
    try:
        push_undo_snapshot(owner)
    except Exception:
        pass
    apply_text_state(owner, text[:i - 1] + text[i:], i - 1, i - 1)
    _sync_after_text_change(owner, 'delete-backward')
    return True


def delete_forward(owner: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    try:
        if has_selection(owner):
            return replace_selection(owner, '')
    except Exception:
        pass
    text = owner.toPlainText()
    i = clamp_index(getattr(owner, '_v_caret_index', 0), len(text))
    if i >= len(text):
        return True
    try:
        push_undo_snapshot(owner)
    except Exception:
        pass
    apply_text_state(owner, text[:i] + text[i + 1:], i, i)
    _sync_after_text_change(owner, 'delete-forward')
    return True


def _inline_selected_text_from_cursor(cursor: QTextCursor) -> str:
    try:
        return str(cursor.selectedText() or '').replace('\u2029', '\n')
    except Exception:
        return ''


def wrap_or_pair_quote(owner: Any, quote_char: str) -> bool:
    """Insert paired straight quotes or wrap selection in vertical editor only.

    Horizontal inline editing must keep normal typing behavior: pressing " or '
    inserts exactly that character through QTextEdit/fallback, not a pair.
    """
    q = str(quote_char or '')
    if q not in {'"', "'"}:
        return False
    if not getattr(owner, '_vertical_editor', False):
        return False
    text = owner.toPlainText()
    a, b = selected_range(owner)
    selected = text[a:b] if b > a else ''
    try:
        push_undo_snapshot(owner)
    except Exception:
        pass
    if b > a:
        new_text = text[:a] + q + selected + q + text[b:]
        apply_text_state(owner, new_text, a + 1 + len(selected), a + 1)
        reason = 'quote-wrap-selection'
    else:
        caret = clamp_index(getattr(owner, '_v_caret_index', 0), len(text))
        new_text = text[:caret] + q + q + text[caret:]
        apply_text_state(owner, new_text, caret + 1, caret + 1)
        reason = 'quote-pair-insert'
    owner._v_preedit_text = ''
    owner._v_ime_selection_preedit_active = False
    _sync_after_text_change(owner, reason)
    return True

def select_all_inline(owner: Any) -> bool:
    """Select all text in either vertical or horizontal inline editor."""
    if getattr(owner, '_vertical_editor', False):
        try:
            owner._v_selection_anchor = 0
            owner._v_caret_index = len(owner.toPlainText())
            owner._v_cursor_visible = True
            try:
                owner.invalidate_vertical_layout()
            except Exception:
                pass
            try:
                owner._force_inline_editor_dirty_repaint(reason='select-all')
            except Exception:
                owner.update()
            return True
        except Exception:
            return False
    try:
        edit = getattr(owner, '_edit', None)
        if edit is not None:
            edit.selectAll()
            try:
                owner._schedule_adjust_to_contents(reason='select-all')
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False


def event_is_select_all(event: Any) -> bool:
    try:
        if event.matches(QKeySequence.StandardKey.SelectAll):
            return True
    except Exception:
        pass
    try:
        mods = event.modifiers()
        return (
            event.key() == Qt.Key.Key_A
            and bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
            and not bool(mods & Qt.KeyboardModifier.AltModifier)
        )
    except Exception:
        return False


def insert_symbol(owner: Any, symbol: str) -> bool:
    symbol = str(symbol or '')
    if not getattr(owner, '_vertical_editor', False):
        return False
    selected = ''
    a, b = selected_range(owner)
    if b > a:
        selected = owner.toPlainText()[a:b]
    pair_map = {"「」": ("「", "」"), "『』": ("『", "』"), "\"\"": ("\"", "\""), "''": ("'", "'")}
    if symbol in pair_map:
        left, right = pair_map[symbol]
        if selected:
            replace_selection(owner, left + selected + right)
        else:
            replace_selection(owner, left + right)
            set_caret(owner, max(0, int(getattr(owner, '_v_caret_index', 0)) - 1), keep_anchor=False)
        return True
    replace_selection(owner, symbol)
    return True




def insert_inline_symbol(owner: Any, symbol: str) -> bool:
    """Insert a configured text symbol in the active inline editor.

    This is input behavior, so main_window_support.py should only call this
    adapter instead of duplicating vertical/horizontal insertion rules.
    """
    symbol = str(symbol or '')
    pair_map = {"「」": ("「", "」"), "『』": ("『", "』"), "\"\"": ("\"", "\""), "''": ("'", "'")}
    if getattr(owner, '_vertical_editor', False):
        selected = ''
        a, b = selected_range(owner)
        if b > a:
            selected = owner.toPlainText()[a:b]
        if symbol in pair_map:
            left, right = pair_map[symbol]
            if selected:
                replace_selection(owner, left + selected + right)
            else:
                replace_selection(owner, left + right)
                set_caret(owner, max(0, int(getattr(owner, '_v_caret_index', 0) or 0) - 1), keep_anchor=False)
            return True
        replace_selection(owner, symbol)
        return True

    pair_map = horizontal_pair_map
    try:
        cursor = owner.textCursor()
    except Exception:
        return False
    try:
        selected = cursor.selectedText()
    except Exception:
        selected = ''
    if symbol in pair_map:
        left, right = pair_map[symbol]
        if selected:
            cursor.insertText(left + selected + right)
        else:
            cursor.insertText(left + right)
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
        owner.setTextCursor(cursor)
        try:
            owner._schedule_adjust_to_contents(reason='symbol')
        except Exception:
            pass
        return True
    cursor.insertText(symbol)
    owner.setTextCursor(cursor)
    try:
        owner._schedule_adjust_to_contents(reason='symbol')
    except Exception:
        pass
    return True


def handle_inline_text_input_shortcut(owner: Any, event: Any) -> bool:
    for key, (_label, symbol) in TEXT_SYMBOLS.items():
        try:
            if owner._shortcut_matches(event, "text_" + key):
                insert_inline_symbol(owner, symbol)
                event.accept()
                return True
        except Exception:
            continue
    return False


def _is_inline_horizontal_char(ch: str) -> bool:
    """세로쓰기 중 가로쓰기 모드를 유발하는 문자인지 판별."""
    if not ch:
        return False
    c = ch[0]
    return (
        ('A' <= c <= 'Z') or ('a' <= c <= 'z') or
        ('0' <= c <= '9') or
        ('Ａ' <= c <= 'Ｚ') or ('ａ' <= c <= 'ｚ') or
        ('０' <= c <= '９') or
        c in '!?！？‼⁉' or
        c in '-_/.:#＋－＿／．：＃'
    )

def handle_key_press(owner: Any, event: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    try:
        if owner._is_alt_modifier_guard_event(event):
            event.accept(); return True
    except Exception:
        pass
    try:
        key = event.key(); mods = event.modifiers()
    except Exception:
        return False
    if key == Qt.Key.Key_Escape:
        owner.main_window.finish_inline_text_edit(commit=False)
        event.accept(); return True
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and mods & Qt.KeyboardModifier.ControlModifier:
        try:
            owner._inline_trace('INLINE_EDITOR_CTRL_ENTER_COMMIT_REQUEST')
        except Exception:
            pass
        owner.main_window.finish_inline_text_edit(commit=True, commit_reason='ctrl_enter')
        event.accept(); return True
    try:
        if handle_inline_text_input_shortcut(owner, event):
            return True
    except Exception:
        pass
    if event_is_select_all(event):
        select_all_inline(owner)
        event.accept(); return True
    if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
        if key == Qt.Key.Key_Z and (mods & Qt.KeyboardModifier.ShiftModifier):
            owner.perform_inline_local_redo(); event.accept(); return True
        if key == Qt.Key.Key_Z:
            owner.perform_inline_local_undo(); event.accept(); return True
        if key == Qt.Key.Key_Y:
            owner.perform_inline_local_redo(); event.accept(); return True
        if key == Qt.Key.Key_A:
            select_all_inline(owner); event.accept(); return True
        if key in (Qt.Key.Key_C, Qt.Key.Key_X):
            __import__('ysb.engines.text_input.text_input_clipboard', fromlist=['copy_direct_selection_to_plain_clipboard']).copy_direct_selection_to_plain_clipboard(owner, cut=(key == Qt.Key.Key_X))
            event.accept(); return True
        if key == Qt.Key.Key_V:
            try:
                clip = QApplication.clipboard().text()
            except Exception:
                clip = ''
            if clip:
                replace_selection(owner, clip)
            event.accept(); return True
    keep = bool(mods & Qt.KeyboardModifier.ShiftModifier)
    if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and not keep:
        try:
            if has_selection(owner):
                a, b = selected_range(owner)
                collapse_to = a if key in (Qt.Key.Key_Left, Qt.Key.Key_Up) else b
                set_caret(owner, collapse_to, keep_anchor=False)
                event.accept(); return True
        except Exception:
            pass
    if key == Qt.Key.Key_Backspace:
        delete_backward(owner); event.accept(); return True
    if key == Qt.Key.Key_Delete:
        delete_forward(owner); event.accept(); return True
    if key == Qt.Key.Key_Space and not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
        # 세로쓰기 + 가로모드 중 스페이스 → 공백 삽입 없이 가로모드 탈출.
        # _v_inline_horizontal_active 플래그로 상태 추적.
        if getattr(owner, '_vertical_editor', False) and owner._is_vertical_writing() and bool(getattr(owner, 'partial_horizontal_writing_enabled', True)):
            if getattr(owner, '_v_inline_horizontal_active', False):
                owner._v_inline_horizontal_active = False
                # 가로모드 탈출: ​(zero-width space) 삽입으로 토큰 경계를 만들고
                # 이어서 공백 삽입으로 커서를 다음 행으로 이동.
                # ​는 렌더링 안 되고 토크나이저가 토큰 경계로 인식해서
                # 앞뒤 latin 토큰이 합쳐지지 않음.
                replace_selection(owner, '​')
                event.accept(); return True
        replace_selection(owner, ' '); event.accept(); return True
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        replace_selection(owner, '\n'); event.accept(); return True
    if key == Qt.Key.Key_Up:
        if owner._is_vertical_writing():
            if not move_vertical_out_of_partial_horizontal(owner, down=False, keep_anchor=keep):
                set_caret(owner, int(getattr(owner, '_v_caret_index', 0)) - 1, keep_anchor=keep)
        else:
            move_horizontal_line(owner, up=True, keep_anchor=keep)
        event.accept(); return True
    if key == Qt.Key.Key_Down:
        if owner._is_vertical_writing():
            if not move_vertical_out_of_partial_horizontal(owner, down=True, keep_anchor=keep):
                set_caret(owner, int(getattr(owner, '_v_caret_index', 0)) + 1, keep_anchor=keep)
        else:
            move_horizontal_line(owner, up=False, keep_anchor=keep)
        event.accept(); return True
    if key == Qt.Key.Key_Home:
        text = owner.toPlainText(); prev_nl = text.rfind('\n', 0, int(getattr(owner, '_v_caret_index', 0)))
        set_caret(owner, prev_nl + 1, keep_anchor=keep); event.accept(); return True
    if key == Qt.Key.Key_End:
        text = owner.toPlainText(); i = int(getattr(owner, '_v_caret_index', 0)); next_nl = text.find('\n', i)
        set_caret(owner, len(text) if next_nl < 0 else next_nl, keep_anchor=keep); event.accept(); return True
    if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
        if owner._is_vertical_writing():
            # 세로쓰기 안의 부분 가로쓰기 런에서는 좌/우가 컬럼 이동이 아니라
            # 가로쓰기 내부 caret 이동이어야 한다. 런 밖에서만 기존 컬럼 이동.
            if not move_partial_horizontal_inline(owner, right=(key == Qt.Key.Key_Right), keep_anchor=keep):
                move_vertical_column(owner, left=(key == Qt.Key.Key_Left), keep_anchor=keep)
        else:
            delta = -1 if key == Qt.Key.Key_Left else 1
            set_caret(owner, int(getattr(owner, '_v_caret_index', 0)) + delta, keep_anchor=keep)
        event.accept(); return True
    try:
        text = event.text()
    except Exception:
        text = ''
    if text and not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)) and not (mods & Qt.KeyboardModifier.AltModifier):
        if text in {'"', "'"}:
            if wrap_or_pair_quote(owner, text):
                event.accept(); return True
        try:
            if int(key or 0) == 0 and str(getattr(owner, '_v_preedit_text', '') or ''):
                event.accept(); return True
        except Exception:
            pass
        # 세로쓰기 중 가로쓰기 유발 문자 입력 → 가로모드 ON
        # 한글 등 일반 문자 입력 → 가로모드 OFF
        if getattr(owner, '_vertical_editor', False) and owner._is_vertical_writing():
            if bool(getattr(owner, 'partial_horizontal_writing_enabled', True)) and _is_inline_horizontal_char(text):
                owner._v_inline_horizontal_active = True
            else:
                owner._v_inline_horizontal_active = False
        replace_selection(owner, text)
        event.accept(); return True
    return False
