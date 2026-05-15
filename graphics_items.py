from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem
from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QRectF


def _qcolor(value, fallback):
    c = QColor(str(value or fallback))
    if not c.isValid():
        c = QColor(fallback)
    return c


class TypesettingItem(QGraphicsPathItem):
    """최종 결과 탭에서 드래그/선택 가능한 텍스트 객체."""

    def __init__(
        self,
        data,
        font_family,
        font_size_px,
        stroke_width,
        update_cb,
        text_color="#000000",
        stroke_color="#FFFFFF",
        align="center",
    ):
        super().__init__()
        self.data = data
        self.update_cb = update_cb

        # 번역문이 비어 있으면 최종 화면에는 아무 글자도 만들지 않는다.
        text = str(data.get('translated_text', '') or '')
        lines = text.split('\n') if text.strip() else []

        item_font_family = data.get('font_family') or font_family
        item_font_size = int(data.get('font_size', font_size_px) or font_size_px)
        item_stroke = int(data.get('stroke_width', stroke_width) or 0)
        item_text_color = data.get('text_color') or text_color
        item_stroke_color = data.get('stroke_color') or stroke_color
        item_align = (data.get('align') or align or 'center').lower()
        if item_align not in ('left', 'center', 'right'):
            item_align = 'center'

        font = QFont(item_font_family)
        font.setPixelSize(item_font_size)

        path = QPainterPath()
        fm = QFontMetrics(font)
        line_height = fm.height()
        current_y = 0

        for line in lines:
            text_width = fm.horizontalAdvance(line)
            if item_align == 'left':
                x = 0
            elif item_align == 'right':
                x = -text_width
            else:
                x = -text_width / 2
            path.addText(x, current_y, font, line)
            current_y += line_height

        self.setPath(path)

        self.pen_stroke = QPen(
            _qcolor(item_stroke_color, "#FFFFFF"),
            item_stroke,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        self.brush_fill = QBrush(_qcolor(item_text_color, "#000000"))

        rect = data['rect']
        final_x = rect[0] + data.get('x_off', 0)
        final_y = rect[1] + data.get('y_off', 0)

        if item_align == 'left':
            anchor_x = final_x
        elif item_align == 'right':
            anchor_x = final_x + rect[2]
        else:
            anchor_x = final_x + rect[2] / 2

        center_y = final_y + rect[3] / 2 - current_y / 2 + line_height / 2
        self.setPos(anchor_x, center_y)

        self.setFlags(
            self.GraphicsItemFlag.ItemIsMovable
            | self.GraphicsItemFlag.ItemIsSelectable
            | self.GraphicsItemFlag.ItemSendsGeometryChanges
        )

    def text_area_rect(self):
        """최종 화면에서 표시할 작업용 텍스트 영역. 실제 출력에는 포함되지 않는다."""
        rect = self.data.get('rect', [0, 0, 0, 0])
        x_off = self.data.get('x_off', 0)
        y_off = self.data.get('y_off', 0)
        scene_rect = QRectF(
            float(rect[0] + x_off),
            float(rect[1] + y_off),
            float(rect[2]),
            float(rect[3]),
        )
        return self.mapFromScene(scene_rect).boundingRect()

    def boundingRect(self):
        base = super().boundingRect()
        area = self.text_area_rect()
        return base.united(area).adjusted(-4, -4, 4, 4)

    def shape(self):
        # 클릭 판정은 실제 글자 선이 아니라 작업용 텍스트 영역 전체로 잡는다.
        # 그래서 사각형 내부 어디를 눌러도 해당 텍스트를 누른 것으로 판정된다.
        s = QPainterPath()
        s.addRect(self.text_area_rect())
        s.addPath(super().shape())
        return s

    def paint(self, painter, option, widget=None):
        # 최종 화면 작업용 영역 표시.
        # 선택 전에는 옅은 회색, 선택 후에는 붉은 점선으로 보이게 한다.
        area_rect = self.text_area_rect()
        if self.isSelected():
            area_pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)
        else:
            area_pen = QPen(QColor(180, 180, 180, 150), 1, Qt.PenStyle.DotLine)
        painter.setPen(area_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(area_rect)

        if self.pen_stroke.widthF() > 0:
            painter.setPen(self.pen_stroke)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.brush_fill)
        painter.drawPath(self.path())

    def mousePressEvent(self, event):
        self.last_press_y = self.pos().y()
        self._ctrl_select_press = False
        if event.button() == Qt.MouseButton.LeftButton:
            # Ctrl+클릭은 선택을 계속 누적한다.
            # 이미 선택된 항목도 Ctrl+클릭으로 해제하지 않는다. 해제는 ESC로 한다.
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._ctrl_select_press = True
                self.setSelected(True)
                event.accept()
                return

            # 일반 클릭은 해당 텍스트만 단독 선택한다.
            if self.scene() is not None:
                for item in self.scene().selectedItems():
                    if item is not self:
                        item.setSelected(False)
                self.setSelected(True)

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, '_ctrl_select_press', False):
            self._ctrl_select_press = False
            event.accept()
            return

        super().mouseReleaseEvent(event)
        new_pos = self.pos()
        rect = self.data['rect']
        align = (self.data.get('align') or 'center').lower()
        if align == 'left':
            orig_x = rect[0]
        elif align == 'right':
            orig_x = rect[0] + rect[2]
        else:
            orig_x = rect[0] + rect[2] / 2

        self.data['x_off'] = int(new_pos.x() - orig_x)

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
            # 0: 원본 / 1: 분석도 / 2: 텍스트 마스크 / 3: 페인팅 마스크 / 4: 최종결과
            if self.main.cb_mode.currentIndex() == 1:
                self.main.toggle_check_from_box(self.data_item)
                event.accept()
                return

        super().mousePressEvent(event)
