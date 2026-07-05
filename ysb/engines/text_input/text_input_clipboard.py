from __future__ import annotations

from typing import Any
from PyQt6.QtWidgets import QApplication

from .text_input_state import selected_range
from .text_input_commands import replace_selection


def clipboard_plain_text_from_qt_selection(text: Any) -> str:
    return str(text or '').replace('\u2029', '\n').replace('\r\n', '\n').replace('\r', '\n')


def publish_plain_text_clipboard(owner: Any, text: str, reason='copy') -> bool:
    text = clipboard_plain_text_from_qt_selection(text)
    if not text:
        return False
    try:
        QApplication.clipboard().setText(text)
    except Exception:
        pass
    try:
        main = getattr(owner, 'main_window', None)
        if main is not None and hasattr(main, 'make_text_clipboard_item_from_plain_text'):
            item = main.make_text_clipboard_item_from_plain_text(text)
            if item:
                main.text_clipboard = [item]
                main.text_clipboard_is_plain = True
                main.text_paste_pending = False
                try:
                    if getattr(main, 'view', None) is not None and hasattr(main.view, 'clear_paste_preview'):
                        main.view.clear_paste_preview()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        owner._inline_trace('INLINE_EDITOR_CLIPBOARD_TEXT_COPY', reason=str(reason or ''), text_len=len(text))
    except Exception:
        pass
    return True


def copy_direct_selection_to_plain_clipboard(owner: Any, cut=False) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    a, b = selected_range(owner)
    if b <= a:
        return False
    text = owner.toPlainText()[a:b]
    if not publish_plain_text_clipboard(owner, text, reason='cut' if cut else 'copy'):
        return False
    if cut:
        replace_selection(owner, '')
    return True



def copy_widget_selection_to_plain_clipboard(owner: Any, cut=False) -> bool:
    """Copy/cut selection from the normal horizontal QTextEdit inline editor."""
    if getattr(owner, '_vertical_editor', False):
        return False
    try:
        edit = getattr(owner, '_edit', None)
        if edit is None:
            return False
        cursor = edit.textCursor()
        if not cursor.hasSelection():
            return False
        text = clipboard_plain_text_from_qt_selection(cursor.selectedText())
        if not text:
            return False
        publish_plain_text_clipboard(owner, text, reason='cut' if cut else 'copy')
        if cut:
            cursor.removeSelectedText()
            edit.setTextCursor(cursor)
            try:
                owner._schedule_adjust_to_contents(reason='cut')
            except Exception:
                pass
        return True
    except Exception:
        return False
