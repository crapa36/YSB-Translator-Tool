from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem
from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QPen, QBrush, QColor
from PyQt6.QtCore import Qt


class TypesettingItem(QGraphicsPathItem):
    """최종 결과 탭에서 드래그 가능한 텍스트 객체."""

    def __init__(self, data, font_family, font_size_px, stroke_width, update_cb):
        super().__init__()
        self.data = data
        self.update_cb = update_cb

        text = data.get('translated_text', data.get('text', ''))
        if not text:
            text = "..."

        lines = text.split('\n')

        font = QFont(font_family)
        font.setPixelSize(int(font_size_px))

        path = QPainterPath()
        fm = QFontMetrics(font)
        line_height = fm.height()
        current_y = 0

        for line in lines:
            text_width = fm.horizontalAdvance(line)
            path.addText(-text_width / 2, current_y, font, line)
            current_y += line_height

        self.setPath(path)

        self.pen_stroke = QPen(
            Qt.GlobalColor.white,
            stroke_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        self.brush_fill = QBrush(Qt.GlobalColor.black)

        rect = data['rect']
        final_x = rect[0] + data.get('x_off', 0)
        final_y = rect[1] + data.get('y_off', 0)

        center_x = final_x + rect[2] / 2
        center_y = final_y + rect[3] / 2 - current_y / 2 + line_height / 2

        self.setPos(center_x, center_y)

        self.setFlags(
            self.GraphicsItemFlag.ItemIsMovable
            | self.GraphicsItemFlag.ItemIsSelectable
            | self.GraphicsItemFlag.ItemSendsGeometryChanges
        )

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            painter.setPen(QPen(Qt.GlobalColor.yellow, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

        painter.setPen(self.pen_stroke)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.brush_fill)
        painter.drawPath(self.path())

    def mousePressEvent(self, event):
        self.last_press_y = self.pos().y()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        new_pos = self.pos()
        rect = self.data['rect']
        orig_cx = rect[0] + rect[2] / 2

        self.data['x_off'] = int(new_pos.x() - orig_cx)

        if hasattr(self, 'last_press_y'):
            delta_y = int(new_pos.y() - self.last_press_y)
            self.data['y_off'] = self.data.get('y_off', 0) + delta_y

        if self.update_cb:
            self.update_cb(f"📍 텍스트 이동됨 (ID: {self.data.get('id')})")


class ToggleBoxItem(QGraphicsRectItem):
    """분석도/마스크 화면에서 클릭하면 해당 체크 상태를 토글하는 박스."""

    def __init__(self, rect, data_item, main_window, pen, brush=None, z_value=20):
        x, y, w, h = rect
        super().__init__(x, y, w, h)

        self.data_item = data_item
        self.main = main_window

        self.setPen(pen)
        self.setBrush(brush if brush is not None else QBrush(Qt.BrushStyle.NoBrush))
        self.setZValue(z_value)

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def hoverEnterEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().hoverEnterEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 분석도 화면에서만 박스 클릭 토글 허용
            # 0: 원본 / 1: 분석도 / 2: 2차 마스크 / 3: 1차 마스크 / 4: 최종결과
            if self.main.cb_mode.currentIndex() == 1:
                self.main.toggle_check_from_box(self.data_item)
                event.accept()
                return

        super().mousePressEvent(event)
