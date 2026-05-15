import math
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem, QInputDialog
from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QPen, QBrush, QColor, QTransform
from PyQt6.QtCore import Qt, QRectF, QPointF


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
        lines = text.split('\n') if text.strip() else ([''] if data.get('force_show') else [])

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
        font.setBold(bool(data.get('bold', False)))
        font.setItalic(bool(data.get('italic', False)))

        try:
            letter_spacing = int(data.get('letter_spacing', 0) or 0)
        except Exception:
            letter_spacing = 0
        if letter_spacing:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(letter_spacing))

        try:
            line_spacing_pct = max(50, min(300, int(data.get('line_spacing', 100) or 100)))
        except Exception:
            line_spacing_pct = 100
        try:
            char_width_pct = max(10, min(300, int(data.get('char_width', 100) or 100)))
        except Exception:
            char_width_pct = 100
        try:
            char_height_pct = max(10, min(300, int(data.get('char_height', 100) or 100)))
        except Exception:
            char_height_pct = 100

        path = QPainterPath()
        fm = QFontMetrics(font)
        line_height = max(1, int(fm.lineSpacing() * (line_spacing_pct / 100.0)))
        current_y = 0
        self._strike_lines = []

        sx = char_width_pct / 100.0
        sy = char_height_pct / 100.0

        for line in lines:
            text_width = fm.horizontalAdvance(line)
            if item_align == 'left':
                x = 0
            elif item_align == 'right':
                x = -text_width
            else:
                x = -text_width / 2
            path.addText(x, current_y, font, line)

            if data.get('strike', False):
                y_line = current_y - fm.ascent() * 0.35
                self._strike_lines.append((x * sx, y_line * sy, (x + text_width) * sx, y_line * sy))

            current_y += line_height

        if sx != 1.0 or sy != 1.0:
            tr = QTransform()
            tr.scale(sx, sy)
            path = tr.map(path)

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

        # 텍스트는 작업 영역의 최상단에 붙인다.
        # 기존처럼 세로 중앙 배치하면 더블클릭 편집 시 QGraphicsTextItem의 상단 기준과 달라져
        # 좌표는 그대로인데 화면상 텍스트가 위아래로 움직이는 느낌이 생긴다.
        path_rect = path.boundingRect()
        top_y = final_y - path_rect.top()
        self.setPos(anchor_x, top_y)

        # 작업용 텍스트 영역은 로컬 좌표로 고정한다.
        # 이동 중에도 빨간 선택 박스가 텍스트와 같이 움직이고, 이전 위치에 잔상이 남지 않는다.
        scene_rect = QRectF(
            float(rect[0] + data.get('x_off', 0)),
            float(rect[1] + data.get('y_off', 0)),
            float(rect[2]),
            float(rect[3]),
        )
        self._local_text_area_rect = self.mapFromScene(scene_rect).boundingRect()
        self._text_path_rect = QGraphicsPathItem.boundingRect(self)

        # 텍스트 변형: 회전은 실제 글자 영역의 중앙을 기준으로 한다.
        try:
            self.setTransformOriginPoint(self.transform_rect().center())
            self.setRotation(float(data.get('rotation', 0) or 0))
        except Exception:
            pass

        self._transform_action = None
        self._transform_press_pos = None
        self._transform_press_angle = 0.0
        self._transform_press_rotation = 0.0
        self._transform_press_char_width = int(data.get('char_width', 100) or 100)
        self._transform_press_char_height = int(data.get('char_height', 100) or 100)
        self._transform_press_rect = QRectF()
        self._transform_live_rect = None
        self._transform_press_scene_pos = QPointF()
        self._transform_press_item_pos = QPointF()
        self._transform_press_rect_data = None

        self.setZValue(30)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)

        self.setFlags(
            self.GraphicsItemFlag.ItemIsMovable
            | self.GraphicsItemFlag.ItemIsSelectable
            | self.GraphicsItemFlag.ItemSendsGeometryChanges
        )

    def transform_rect(self):
        """텍스트 변형 모드에서 조작할 기준 박스.
        사용감 안정성을 위해 실제 글자 타이트 박스 대신 작업용 텍스트 영역(rect)을 기준으로 잡는다.
        """
        rect = self.text_area_rect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            rect = getattr(self, '_text_path_rect', QGraphicsPathItem.boundingRect(self))
        return QRectF(rect)

    def rotate_handle_pos(self):
        rect = self.transform_rect()
        return QPointF(rect.center().x(), rect.top() - 34)

    def transform_handle_rects(self):
        rect = self.transform_rect()
        s = 14.0
        half = s / 2.0

        def box(pt):
            return QRectF(pt.x() - half, pt.y() - half, s, s)

        pts = {
            'rotate': self.rotate_handle_pos(),
            'left': QPointF(rect.left(), rect.center().y()),
            'right': QPointF(rect.right(), rect.center().y()),
            'top': QPointF(rect.center().x(), rect.top()),
            'bottom': QPointF(rect.center().x(), rect.bottom()),
            'top_left': rect.topLeft(),
            'top_right': rect.topRight(),
            'bottom_left': rect.bottomLeft(),
            'bottom_right': rect.bottomRight(),
        }
        return {name: box(pt) for name, pt in pts.items()}

    def transform_action_at(self, pos):
        if not self.data.get('_transform_mode', False):
            return None
        rect = self.transform_rect()
        rects = self.transform_handle_rects()
        border = 10.0

        if rects.get('rotate') and rects['rotate'].contains(pos):
            return 'rotate'

        for name in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
            r = rects.get(name)
            if r and r.adjusted(-4, -4, 4, 4).contains(pos):
                return name

        if abs(pos.x() - rect.left()) <= border and rect.top() - border <= pos.y() <= rect.bottom() + border:
            return 'left'
        if abs(pos.x() - rect.right()) <= border and rect.top() - border <= pos.y() <= rect.bottom() + border:
            return 'right'
        if abs(pos.y() - rect.top()) <= border and rect.left() - border <= pos.x() <= rect.right() + border:
            return 'top'
        if abs(pos.y() - rect.bottom()) <= border and rect.left() - border <= pos.x() <= rect.right() + border:
            return 'bottom'

        for name in ('left', 'right', 'top', 'bottom'):
            r = rects.get(name)
            if r and r.adjusted(-4, -4, 4, 4).contains(pos):
                return name
        return None

    def set_transform_rotation(self, angle):
        try:
            angle = float(angle)
        except Exception:
            angle = 0.0
        # 보기 좋게 -360~360 근처로 정리
        while angle > 360:
            angle -= 360
        while angle < -360:
            angle += 360
        self.data['rotation'] = round(angle, 2)
        try:
            self.setTransformOriginPoint(self.transform_rect().center())
            self.setRotation(angle)
        except Exception:
            pass
        self.update()

    def apply_transform_scale_from_drag(self, pos):
        action = self._transform_action
        if not action:
            return

        press_rect = QRectF(self._transform_press_rect)
        if press_rect.width() <= 1 or press_rect.height() <= 1:
            return

        dx = float(pos.x() - self._transform_press_pos.x())
        dy = float(pos.y() - self._transform_press_pos.y())

        new_rect = QRectF(press_rect)
        min_w = 12.0
        min_h = 12.0

        if 'left' in action:
            new_left = min(press_rect.right() - min_w, press_rect.left() + dx)
            new_rect.setLeft(new_left)
        elif 'right' in action:
            new_right = max(press_rect.left() + min_w, press_rect.right() + dx)
            new_rect.setRight(new_right)

        if 'top' in action:
            new_top = min(press_rect.bottom() - min_h, press_rect.top() + dy)
            new_rect.setTop(new_top)
        elif 'bottom' in action:
            new_bottom = max(press_rect.top() + min_h, press_rect.bottom() + dy)
            new_rect.setBottom(new_bottom)

        new_rect = new_rect.normalized()
        self._transform_live_rect = QRectF(new_rect)

        # 영역 크기 변화만큼 글자 너비/높이 비율도 같이 바꾼다.
        cw = int(round(self._transform_press_char_width * (new_rect.width() / press_rect.width())))
        ch = int(round(self._transform_press_char_height * (new_rect.height() / press_rect.height())))
        cw = max(10, min(300, cw))
        ch = max(10, min(300, ch))
        self.data['char_width'] = cw
        self.data['char_height'] = ch

        # data['rect']도 같이 조인다. 좌표계는 현재 아이템의 로컬 좌표 변화량을
        # 이미지 좌표 변화량으로 간주한다. 회전 중에는 근사지만, 무회전/일반 작업에서는 직관적이다.
        base = list(self._transform_press_rect_data or self.data.get('rect', [0, 0, 0, 0]))
        if len(base) < 4:
            base = [0, 0, int(press_rect.width()), int(press_rect.height())]
        local_dx = new_rect.left() - press_rect.left()
        local_dy = new_rect.top() - press_rect.top()
        base[0] = int(round(base[0] + local_dx))
        base[1] = int(round(base[1] + local_dy))
        base[2] = max(1, int(round(base[2] * (new_rect.width() / press_rect.width()))))
        base[3] = max(1, int(round(base[3] * (new_rect.height() / press_rect.height()))))
        self.data['rect'] = base
        self.update()

    def text_area_rect(self):
        """최종 화면에서 표시할 작업용 텍스트 영역. 실제 출력에는 포함되지 않는다."""
        # 변형 드래그 중에는 화면에 보이는 박스가 즉시 줄거나 늘어야 하므로
        # 임시 live rect를 최우선으로 사용한다.
        if getattr(self, '_transform_live_rect', None) is not None:
            return QRectF(self._transform_live_rect)

        # 변형 모드에서는 data['rect']가 계속 바뀔 수 있으므로 저장된 캐시 대신
        # 현재 데이터 기준으로 매번 계산한다.
        if not self.data.get('_transform_mode', False) and hasattr(self, '_local_text_area_rect'):
            return QRectF(self._local_text_area_rect)

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

    def text_content_scene_rect(self):
        """실제 글자가 차지하는 영역. 직접 편집 시작 위치/영역 계산에 쓴다."""
        rect = getattr(self, '_text_path_rect', QGraphicsPathItem.boundingRect(self))
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            rect = self.text_area_rect()
        return self.mapToScene(rect).boundingRect()

    def boundingRect(self):
        base = super().boundingRect()
        area = self.text_area_rect()
        out = base.united(area)
        if self.data.get('_transform_mode', False):
            for r in self.transform_handle_rects().values():
                out = out.united(r)
            hp = self.rotate_handle_pos()
            out = out.united(QRectF(hp.x() - 24, hp.y() - 24, 48, 48))
        return out.adjusted(-12, -12, 12, 12)

    def shape(self):
        # 클릭 판정은 실제 글자 선이 아니라 작업용 텍스트 영역 전체로 잡는다.
        # 변형 모드에서는 바깥 회전 핸들과 변 전체도 클릭 판정에 포함한다.
        s = QPainterPath()
        area = self.text_area_rect()
        s.addRect(area)
        s.addPath(super().shape())
        if self.data.get('_transform_mode', False):
            tr = self.transform_rect()
            s.addRect(tr.adjusted(-10, -10, 10, 10))
            for r in self.transform_handle_rects().values():
                s.addRect(r.adjusted(-6, -6, 6, 6))
            hp = self.rotate_handle_pos()
            s.addEllipse(QRectF(hp.x() - 22, hp.y() - 22, 44, 44))
        return s

    def paint(self, painter, option, widget=None):
        # 최종 화면 작업용 영역 표시.
        # 선택 전에는 옅은 회색, 선택 후에는 붉은 점선.
        # 변형 모드에서는 실제 글자 영역을 파란 실선 + 핸들로 표시한다.
        area_rect = self.text_area_rect()
        if self.data.get('_transform_mode', False):
            tr = self.transform_rect()
            area_pen = QPen(QColor(60, 150, 255), 2, Qt.PenStyle.SolidLine)
            painter.setPen(area_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(tr)

            handle_pos = self.rotate_handle_pos()
            painter.setPen(QPen(QColor(60, 150, 255), 2))
            painter.drawLine(QPointF(tr.center().x(), tr.top()), handle_pos)

            handle_rects = self.transform_handle_rects()
            painter.setBrush(QBrush(QColor(60, 150, 255)))
            painter.setPen(QPen(QColor(230, 245, 255), 1))
            for name, r in handle_rects.items():
                if name == 'rotate':
                    painter.drawEllipse(r)
                    inner = r.adjusted(4, 4, -4, -4)
                    painter.setBrush(QBrush(QColor(230, 245, 255)))
                    painter.drawEllipse(inner)
                    painter.setBrush(QBrush(QColor(60, 150, 255)))
                else:
                    painter.drawRect(r)
        else:
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

        if getattr(self, '_strike_lines', None):
            pen = QPen(self.brush_fill.color(), max(1, int(getattr(self, 'data', {}).get('font_size', 20) * 0.06)))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            for x1, y1, x2, y2 in self._strike_lines:
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def transform_cursor_for_action(self, action):
        if action == 'rotate':
            return Qt.CursorShape.CrossCursor
        if action == 'move':
            return Qt.CursorShape.SizeAllCursor
        if action in ('left', 'right'):
            return Qt.CursorShape.SizeHorCursor
        if action in ('top', 'bottom'):
            return Qt.CursorShape.SizeVerCursor
        if action in ('top_left', 'bottom_right'):
            return Qt.CursorShape.SizeFDiagCursor
        if action in ('top_right', 'bottom_left'):
            return Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.ArrowCursor

    def begin_transform_action(self, action, local_pos, scene_pos):
        """뷰어가 직접 넘겨주는 변형 조작 시작. 핸들이 itemAt에 안 잡히는 경우까지 방어한다."""
        if not self.data.get('_transform_mode', False) or not action:
            return False

        main = getattr(self, "main_window", None)
        if main is not None and hasattr(main, 'push_page_text_undo'):
            if action == 'rotate':
                reason = '텍스트 회전'
            elif action == 'move':
                reason = '텍스트 이동'
            else:
                reason = '텍스트 영역/비율 조정'
            main.push_page_text_undo(reason)

        self._transform_action = action
        self._transform_press_pos = QPointF(local_pos)
        self._transform_press_rotation = float(self.data.get('rotation', 0) or 0)
        self._transform_press_char_width = int(self.data.get('char_width', 100) or 100)
        self._transform_press_char_height = int(self.data.get('char_height', 100) or 100)
        self._transform_press_rect = QRectF(self.transform_rect())
        self._transform_live_rect = None
        self._transform_press_scene_pos = QPointF(scene_pos)
        self._transform_press_item_pos = QPointF(self.pos())
        self._transform_press_rect_data = list(self.data.get('rect', [0, 0, 0, 0]))
        center = self.transform_rect().center()
        self._transform_press_angle = math.degrees(math.atan2(local_pos.y() - center.y(), local_pos.x() - center.x()))
        self.setSelected(True)
        self.update()
        return True

    def update_transform_action(self, local_pos, scene_pos):
        if not self._transform_action:
            return False
        if self._transform_action == 'rotate':
            center = self.transform_rect().center()
            now_angle = math.degrees(math.atan2(local_pos.y() - center.y(), local_pos.x() - center.x()))
            delta = now_angle - self._transform_press_angle
            self.set_transform_rotation(self._transform_press_rotation + delta)
        elif self._transform_action == 'move':
            delta = QPointF(scene_pos) - self._transform_press_scene_pos
            new_pos = self._transform_press_item_pos + delta
            self.setPos(new_pos)
            rect = list(self._transform_press_rect_data or self.data.get('rect', [0, 0, 0, 0]))
            rect[0] = int(round(rect[0] + delta.x()))
            rect[1] = int(round(rect[1] + delta.y()))
            self.data['rect'] = rect
            self.update()
        else:
            self.apply_transform_scale_from_drag(local_pos)
            self.update()
        return True

    def finish_transform_action(self):
        if not self._transform_action:
            return False

        action = self._transform_action
        self._transform_action = None
        self._transform_live_rect = None
        main = getattr(self, "main_window", None)
        selected_id = self.data.get('id')
        if main is not None:
            try:
                main.auto_save_project()
                if main.cb_mode.currentIndex() == 4:
                    main.mode_chg(4)
                    if selected_id is not None:
                        main.reselect_text_items([selected_id])
            except Exception:
                pass
            try:
                if action == 'move':
                    main.log("🔷 텍스트 이동 적용")
                else:
                    main.log(f"🔷 텍스트 변형 적용: 회전 {self.data.get('rotation', 0)}°, 너비 {self.data.get('char_width', 100)}%, 높이 {self.data.get('char_height', 100)}%")
            except Exception:
                pass
        return True

    def hoverMoveEvent(self, event):
        if self.data.get('_transform_mode', False):
            action = self.transform_action_at(event.pos())
            if action:
                self.setCursor(self.transform_cursor_for_action(action))
            elif self.transform_rect().adjusted(-10, -10, 10, 10).contains(event.pos()):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        main = getattr(self, "main_window", None)
        # 이동 모드가 아닐 때는 텍스트 선택/이동을 막는다.
        # 브러시/지우개/텍스트 도구 사용 중에는 캔버스 도구가 우선이다.
        if main is not None and getattr(getattr(main, "view", None), "draw_mode", None) is not None:
            event.ignore()
            return

        self.last_press_y = self.pos().y()
        self._ctrl_select_press = False

        active_transform = main.current_transform_data_item() if main is not None and hasattr(main, 'current_transform_data_item') else None
        if active_transform is not None and active_transform is not self.data:
            self.setSelected(False)
            event.accept()
            return

        if self.data.get('_transform_mode', False) and event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                if self.transform_rect().adjusted(-10, -10, 10, 10).contains(event.pos()):
                    if self.begin_transform_action('move', event.pos(), event.scenePos()):
                        event.accept()
                        return

            action = self.transform_action_at(event.pos())
            if action:
                if self.begin_transform_action(action, event.pos(), event.scenePos()):
                    event.accept()
                    return

            self.setSelected(True)
            event.accept()
            return

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

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            main = getattr(self, "main_window", None)
            if main is not None and getattr(getattr(main, "view", None), "draw_mode", None) is not None:
                event.ignore()
                return

            if self.data.get('_transform_mode', False):
                action = self.transform_action_at(event.pos())
                if action == 'rotate':
                    current = float(self.data.get('rotation', 0) or 0)
                    angle, ok = QInputDialog.getDouble(None, "텍스트 회전", "회전 각도(도):", current, -360.0, 360.0, 1)
                    if ok:
                        self.set_transform_rotation(angle)
                        try:
                            if main is not None:
                                main.auto_save_project()
                                main.log(f"🔷 텍스트 회전 각도 지정: {angle}°")
                        except Exception:
                            pass
                    event.accept()
                    return
                # 변형 모드에서는 더블클릭으로 텍스트 편집에 들어가지 않는다.
                event.accept()
                return

            if main is not None and hasattr(main, "start_inline_text_edit"):
                main.start_inline_text_edit(self)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self._transform_action:
            self.update_transform_action(event.pos(), event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._transform_action:
            self.finish_transform_action()
            event.accept()
            return

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

        try:
            self.prepareGeometryChange()
        except Exception:
            pass

        self.data['x_off'] = int(new_pos.x() - orig_x)

        if hasattr(self, 'last_press_y'):
            delta_y = int(new_pos.y() - self.last_press_y)
            self.data['y_off'] = self.data.get('y_off', 0) + delta_y

        self.update()

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
