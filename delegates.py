from PyQt6.QtWidgets import QStyledItemDelegate, QTextEdit
from PyQt6.QtGui import QShortcut, QTextCursor, QKeySequence
from PyQt6.QtCore import Qt, QEvent


class MultilineDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, shortcut_getter=None, linebreak_getter=None):
        super().__init__(parent)
        self.shortcut_getter = shortcut_getter
        self.linebreak_getter = linebreak_getter

    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        editor.installEventFilter(self)
        self._install_symbol_shortcuts(editor)
        return editor

    def _install_symbol_shortcuts(self, editor):
        editor._special_shortcuts = []
        if not self.shortcut_getter:
            return
        shortcut_map = self.shortcut_getter()
        for symbol, seq in shortcut_map.items():
            if not seq or seq.isEmpty():
                continue
            sc = QShortcut(seq, editor)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(lambda checked=False, s=symbol, e=editor: self._insert_symbol(e, s))
            editor._special_shortcuts.append(sc)

    def setEditorData(self, editor, index):
        editor.setText(index.model().data(index, Qt.ItemDataRole.EditRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)

    def _insert_symbol(self, editor, symbol):
        cursor = editor.textCursor()
        selected = cursor.selectedText()
        pair_map = {
            "「」": ("「", "」"),
            "『』": ("『", "』"),
        }
        if symbol in pair_map:
            left, right = pair_map[symbol]
            if selected:
                cursor.insertText(left + selected + right)
            else:
                cursor.insertText(left + right)
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
            editor.setTextCursor(cursor)
            return
        editor.insertPlainText(symbol)

    def _event_to_keysequence(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return QKeySequence()
        try:
            mods_value = event.modifiers().value
        except AttributeError:
            mods_value = int(event.modifiers())
        return QKeySequence(mods_value | key)

    def _linebreak_matches(self, event):
        # 기본 안전장치: Shift+Enter는 항상 줄내림으로 인정
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            return True
        if not self.linebreak_getter:
            return False
        seq = self.linebreak_getter()
        if not seq or seq.isEmpty():
            return False
        pressed = self._event_to_keysequence(event)
        return pressed.matches(seq) == QKeySequence.SequenceMatch.ExactMatch

    def eventFilter(self, editor, event):
        if event.type() == QEvent.Type.KeyPress:
            if self._linebreak_matches(event):
                editor.insertPlainText("\n")
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.commitData.emit(editor)
                self.closeEditor.emit(editor)
                return True
        return super().eventFilter(editor, event)
