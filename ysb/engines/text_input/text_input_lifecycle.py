from __future__ import annotations

from typing import Any
from PyQt6.QtWidgets import QApplication

from .text_input_state import apply_text_state, clamp_index
from .text_input_navigation import update_desired_caret_axis_from_current


def push_undo_snapshot(owner: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    try:
        snap = (
            owner.toPlainText(),
            int(getattr(owner, '_v_caret_index', 0) or 0),
            int(getattr(owner, '_v_selection_anchor', 0) or 0),
        )
        stack = getattr(owner, '_v_undo_stack', None)
        if stack is None:
            owner._v_undo_stack = []
            stack = owner._v_undo_stack
        if not stack or stack[-1] != snap:
            stack.append(snap)
            if len(stack) > 120:
                del stack[0:len(stack) - 120]
        owner._v_redo_stack = []
        return True
    except Exception:
        return False


def restore_snapshot(owner: Any, snap: Any) -> bool:
    try:
        text, caret, anchor = snap
    except Exception:
        return False
    text = str(text or '')
    caret = clamp_index(caret, len(text))
    anchor = clamp_index(anchor, len(text))
    try:
        apply_text_state(owner, text, caret, anchor)
        owner._v_preedit_text = ''
        owner._v_ime_selection_preedit_active = False
        owner._sync_direct_editor_after_text_change(reason='restore-snapshot')
        update_desired_caret_axis_from_current(owner)
        return True
    except Exception:
        return False


def prepare_text_for_commit(owner: Any, reason: str = 'commit') -> str:
    """Commit pending text-input state before the inline editor closes.

    Text options/style UI stay outside this module.  This only handles input
    lifecycle: visible IME preedit -> committed text, then returns plain text.
    """
    if getattr(owner, '_vertical_editor', False):
        try:
            preedit = str(getattr(owner, '_v_preedit_text', '') or '')
        except Exception:
            preedit = ''
        if preedit:
            try:
                owner._inline_trace(
                    'INLINE_EDITOR_IME_PREEDIT_FORCE_COMMIT',
                    reason=str(reason or ''),
                    preedit_len=len(preedit),
                    caret=int(getattr(owner, '_v_caret_index', 0) or 0),
                )
            except Exception:
                pass
            try:
                from .text_input_commands import replace_selection
                replace_selection(owner, preedit, push_undo=False, reason='ime-preedit-force-commit')
            except Exception:
                try:
                    text = owner.toPlainText()
                    caret = clamp_index(getattr(owner, '_v_caret_index', 0), len(text))
                    apply_text_state(owner, text[:caret] + preedit + text[caret:], caret + len(preedit), caret + len(preedit))
                except Exception:
                    pass
        try:
            return owner.toPlainText()
        except Exception:
            return str(getattr(owner, '_v_text', '') or '')

    try:
        im = QApplication.inputMethod()
        if im is not None and hasattr(im, 'commit'):
            im.commit()
    except Exception:
        pass
    try:
        edit = getattr(owner, '_edit', None)
        if edit is not None:
            edit.document().adjustSize()
    except Exception:
        pass
    try:
        return owner.toPlainText()
    except Exception:
        return ''


def perform_inline_local_undo(owner: Any) -> bool:
    if getattr(owner, '_vertical_editor', False):
        try:
            stack = getattr(owner, '_v_undo_stack', [])
            if not stack:
                return True
            current = (
                owner.toPlainText(),
                int(getattr(owner, '_v_caret_index', 0) or 0),
                int(getattr(owner, '_v_selection_anchor', 0) or 0),
            )
            if not hasattr(owner, '_v_redo_stack') or getattr(owner, '_v_redo_stack', None) is None:
                owner._v_redo_stack = []
            owner._v_redo_stack.append(current)
            snap = stack.pop()
            restore_snapshot(owner, snap)
        except Exception:
            pass
        return True
    try:
        if getattr(owner, '_edit', None) is not None:
            owner._edit.undo()
    except Exception:
        pass
    try:
        owner._schedule_adjust_to_contents(reason='undo')
    except Exception:
        pass
    return True


def perform_inline_local_redo(owner: Any) -> bool:
    if getattr(owner, '_vertical_editor', False):
        try:
            stack = getattr(owner, '_v_redo_stack', [])
            if not stack:
                return True
            current = (
                owner.toPlainText(),
                int(getattr(owner, '_v_caret_index', 0) or 0),
                int(getattr(owner, '_v_selection_anchor', 0) or 0),
            )
            if not hasattr(owner, '_v_undo_stack') or getattr(owner, '_v_undo_stack', None) is None:
                owner._v_undo_stack = []
            owner._v_undo_stack.append(current)
            snap = stack.pop()
            restore_snapshot(owner, snap)
        except Exception:
            pass
        return True
    try:
        if getattr(owner, '_edit', None) is not None:
            owner._edit.redo()
    except Exception:
        pass
    try:
        owner._schedule_adjust_to_contents(reason='redo')
    except Exception:
        pass
    return True
