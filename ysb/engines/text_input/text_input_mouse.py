from __future__ import annotations

from typing import Any
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

from .text_input_hit_test import caret_index_from_pos
from .text_input_commands import set_caret


def handle_mouse_press(owner: Any, event: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    try:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
    except Exception:
        return False
    try:
        owner.setCursor(Qt.CursorShape.IBeamCursor)
    except Exception:
        pass
    try:
        owner.setFocus(Qt.FocusReason.MouseFocusReason)
    except Exception:
        pass
    try:
        keep = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
    except Exception:
        keep = False
    try:
        local_pos = event.pos()
    except Exception:
        local_pos = QPointF(0, 0)
    try:
        owner.adjust_to_contents()
    except Exception:
        pass
    caret = caret_index_from_pos(owner, local_pos)
    set_caret(owner, caret, keep_anchor=keep)
    try:
        owner._inline_trace('INLINE_EDITOR_MOUSE_CARET_SET', caret=int(caret), x=round(float(local_pos.x()), 2), y=round(float(local_pos.y()), 2), keep=bool(keep))
    except Exception:
        pass
    try:
        owner._v_mouse_press_pos = QPointF(local_pos)
        owner._v_mouse_press_caret = int(caret)
    except Exception:
        owner._v_mouse_press_pos = None
        owner._v_mouse_press_caret = int(caret)
    owner._vertical_drag_selecting = bool(keep)
    try:
        event.accept()
    except Exception:
        pass
    return True


def handle_mouse_move(owner: Any, event: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    try:
        if not bool(event.buttons() & Qt.MouseButton.LeftButton):
            return False
    except Exception:
        return False
    try:
        keep = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
    except Exception:
        keep = False
    if not keep and not bool(getattr(owner, '_vertical_drag_selecting', False)):
        try:
            press = QPointF(getattr(owner, '_v_mouse_press_pos', event.pos()))
            delta = QPointF(event.pos()) - press
            threshold = 4
            try:
                threshold = QApplication.startDragDistance()
            except Exception:
                pass
            if abs(float(delta.x())) + abs(float(delta.y())) < max(1, int(threshold)):
                event.accept(); return True
        except Exception:
            try:
                event.accept()
            except Exception:
                pass
            return True
        owner._vertical_drag_selecting = True
    set_caret(owner, caret_index_from_pos(owner, event.pos()), keep_anchor=True)
    try:
        event.accept()
    except Exception:
        pass
    return True


def handle_mouse_release(owner: Any, event: Any) -> bool:
    if not getattr(owner, '_vertical_editor', False):
        return False
    owner._vertical_drag_selecting = False
    owner._v_mouse_press_pos = None
    try:
        event.accept()
    except Exception:
        pass
    return True


def set_initial_caret_from_scene_pos(owner: Any, scene_pos) -> bool:
    try:
        owner.adjust_to_contents()
    except Exception:
        pass
    if getattr(owner, '_vertical_editor', False):
        try:
            local = owner.mapFromScene(QPointF(scene_pos))
        except Exception:
            local = QPointF(0, 0)
        try:
            caret = caret_index_from_pos(owner, local)
        except Exception:
            caret = len(owner.toPlainText())
        set_caret(owner, caret, keep_anchor=False)
        try:
            owner._inline_trace('INLINE_EDITOR_INITIAL_CARET_FROM_DOUBLE_CLICK', caret=int(getattr(owner, '_v_caret_index', 0)), x=round(float(local.x()), 2), y=round(float(local.y()), 2))
        except Exception:
            pass
        return True
    try:
        if getattr(owner, '_edit', None) is None:
            return False
        try:
            local = owner.mapFromScene(QPointF(scene_pos))
        except Exception:
            local = QPointF(0, 0)
        cursor = owner._edit.cursorForPosition(QPoint(int(round(local.x())), int(round(local.y()))))
        cursor.clearSelection()
        owner._edit.setTextCursor(cursor)
        try:
            owner._inline_trace('INLINE_EDITOR_WIDGET_INITIAL_CARET_FROM_DOUBLE_CLICK', caret=int(cursor.position()), x=round(float(local.x()), 2), y=round(float(local.y()), 2))
        except Exception:
            pass
        return True
    except Exception:
        try:
            cursor = owner.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            owner.setTextCursor(cursor)
            return True
        except Exception:
            return False
