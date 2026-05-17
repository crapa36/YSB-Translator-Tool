import math
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem, QInputDialog
from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QPen, QBrush, QColor, QTransform
from PyQt6.QtCore import Qt, QRectF, QPointF


# Photoshop의 Faux Italic 느낌에 맞춘 합성 기울임 강도.
# 너무 크면 글자가 과하게 누워 보이므로, Qt 기본 italic은 끄고 이 값만 적용한다.
FAUX_ITALIC_SHEAR = -0.13


def _qcolor(value, fallback):
    c = QColor(str(value or fallback))
    if not c.isValid():
        c = QColor(fallback)
    return c



def build_typesetting_text_path(lines, font, align="center", line_height=None, letter_spacing=0):
    """Build a QPainterPath with manual tracking and faux italic support.

    Qt/QPainterPath does not reliably synthesize Photoshop-style font effects for
    every font.  In particular, some OTF/CJK fonts ignore QFont.setItalic() or
    negative tracking when the family has no matching face.  This helper therefore
    lays out characters manually and applies a small synthetic shear when italic
    is requested.  The returned rects are already in the final local coordinates.

    Returns: (path, line_rects)
    """
    align = (align or "center").lower()
    if align not in ("left", "center", "right"):
        align = "center"
    try:
        letter_spacing = int(letter_spacing or 0)
    except Exception:
        letter_spacing = 0

    italic_requested = bool(font.italic())

    # Qt가 지원하는 italic face와 YSB의 faux italic shear가 겹치면
    # 포토샵보다 훨씬 과하게 기울어질 수 있다. 렌더용 path는 항상
    # italic을 끈 기본 글꼴로 만들고, 아래에서 Photoshop식 합성 shear만 적용한다.
    path_font = QFont(font)
    path_font.setItalic(False)

    fm = QFontMetrics(path_font)
    if line_height is None:
        line_height = fm.lineSpacing()
    line_height = max(1, int(line_height))

    path = QPainterPath()
    line_rects = []
    current_y = 0

    for line in lines or []:
        line = str(line or "")
        line_path = QPainterPath()

        if line:
            if letter_spacing == 0:
                # Build at baseline 0 first.  This lets us apply faux italic per
                # line without shifting lower lines sideways.
                line_path.addText(0, 0, path_font, line)
            else:
                cursor_x = 0.0
                for ch in line:
                    line_path.addText(cursor_x, 0, path_font, ch)
                    try:
                        advance = fm.horizontalAdvance(ch)
                    except Exception:
                        advance = fm.boundingRect(ch).width()
                    cursor_x += float(advance) + float(letter_spacing)

        if italic_requested and not line_path.isEmpty():
            # Photoshop can fake italic even for fonts without an italic face.
            # QFont.setItalic() is ignored by some fonts, but applying both
            # Qt italic and shear makes supported fonts lean too much.
            # Therefore the path is built from a non-italic font and only this
            # moderate Photoshop-like shear is applied.
            shear = QTransform()
            shear.shear(FAUX_ITALIC_SHEAR, 0.0)
            line_path = shear.map(line_path)

        line_rect = line_path.boundingRect()
        if line_rect.isNull() or line_rect.width() <= 0 or line_rect.height() <= 0:
            line_rect = QRectF(0, -fm.ascent(), 1, max(1, fm.height()))

        if align == "left":
            dx = -line_rect.left()
        elif align == "right":
            dx = -line_rect.right()
        else:
            dx = -line_rect.center().x()

        tr = QTransform()
        tr.translate(dx, current_y)
        if not line_path.isEmpty():
            mapped = tr.map(line_path)
            path.addPath(mapped)
            line_rect = mapped.boundingRect()
        else:
            line_rect = QRectF(line_rect)
            line_rect.translate(dx, current_y)

        line_rects.append(QRectF(line_rect))
        current_y += line_height

    return path, line_rects

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

        fm = QFontMetrics(font)
        line_height = max(1, int(fm.lineSpacing() * (line_spacing_pct / 100.0)))
        self._strike_lines = []
        self._synthetic_bold_width = max(0.0, float(item_font_size) * 0.045) if bool(data.get('bold', False)) else 0.0

        sx = char_width_pct / 100.0
        sy = char_height_pct / 100.0

        path, line_rects = build_typesetting_text_path(lines, font, item_align, line_height, letter_spacing)

        if data.get('strike', False):
            for line_rect in line_rects:
                y_line = line_rect.center().y() - fm.ascent() * 0.15
                self._strike_lines.append((line_rect.left() * sx, y_line * sy, line_rect.right() * sx, y_line * sy))

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
        final_x = float(rect[0]) + float(data.get('x_off', 0) or 0)
        final_y = float(rect[1]) + float(data.get('y_off', 0) or 0)
        rect_w = max(1.0, float(rect[2]))
        rect_h = max(1.0, float(rect[3]))

        # v1.6.3+: 초기 OCR 박스에서는 글자를 박스의 가로/세로 중심에 배치한다.
        # 기존 상단 붙임 방식은 말풍선 안에서 아래쪽 빈칸이 남고,
        # 이후 변형 박스와 실제 글자 위치가 따로 노는 원인이 되었다.
        path_rect = path.boundingRect()
        if path_rect.isNull() or path_rect.width() <= 0 or path_rect.height() <= 0:
            path_rect = QRectF(0, 0, 1, max(1, item_font_size))

        if item_align == 'left':
            anchor_x = final_x
            pos_x = anchor_x - path_rect.left()
        elif item_align == 'right':
            anchor_x = final_x + rect_w
            pos_x = anchor_x - path_rect.right()
        else:
            anchor_x = final_x + rect_w / 2.0
            pos_x = anchor_x - path_rect.center().x()

        anchor_y = final_y + rect_h / 2.0
        pos_y = anchor_y - path_rect.center().y()
        self.setPos(pos_x, pos_y)

        # 작업용 텍스트 영역은 OCR 단계와 편집 이후 단계의 기준을 분리한다.
        # - OCR 단계: 원래 OCR 영역 전체를 선택/변형 박스로 사용한다.
        # - 텍스트 편집 이후: 실제 글자 bounds를 새 텍스트 영역으로 사용한다.
        #   최종화면에서 수정한 순간부터 기존 OCR 박스는 더 이상 기준이 아니기 때문이다.
        self._text_path_rect = QRectF(path_rect)
        text_anchor_mode = str(data.get('text_anchor_mode') or '').lower() == 'text'
        manual_rect = bool(data.get('manual_text_rect')) or text_anchor_mode
        if manual_rect:
            self._local_text_area_rect = QRectF(self._text_path_rect)
        else:
            scene_rect = QRectF(final_x, final_y, rect_w, rect_h)
            self._local_text_area_rect = self.mapFromScene(scene_rect).boundingRect()

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
        OCR 단계에서는 OCR 영역을 쓰고, 텍스트 수정 이후에는 실제 글자 영역을 쓴다.
        이렇게 해야 일반 선택 박스와 변형 박스가 같은 기준을 바라본다.
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

        # rotate_handle_pos()는 다시 transform_rect()를 부르므로,
        # shape()/boundingRect() 안에서 반복 호출되면 최종화면 전환 시 불필요한 재계산이 커진다.
        # 같은 rect에서 직접 계산해 가볍게 처리한다.
        rotate_pos = QPointF(rect.center().x(), rect.top() - 34)

        pts = {
            'rotate': rotate_pos,
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
        live_rect = getattr(self, '_transform_live_rect', None)
        if live_rect is not None:
            return QRectF(live_rect)

        # 텍스트 수정 이후에는 실제 글자 bounds가 곧 텍스트 영역이다.
        # 주의: getattr(..., QGraphicsPathItem.boundingRect(self)) 형태는 default 인자가 매번 평가되어
        # shape()/boundingRect() 호출 중 Qt 쪽 재귀를 만들 수 있다. path().boundingRect()로 가볍게 계산한다.
        text_anchor_mode = str(self.data.get('text_anchor_mode') or '').lower() == 'text'
        if bool(self.data.get('manual_text_rect')) or text_anchor_mode or bool(self.data.get('_transform_mode', False)):
            rect = getattr(self, '_text_path_rect', None)
            if rect is None:
                rect = self.path().boundingRect()
            if not rect.isNull() and rect.width() > 0 and rect.height() > 0:
                return QRectF(rect)

        # OCR 초기 단계에서는 원래 OCR 박스 전체를 선택 기준으로 쓴다.
        area_rect = getattr(self, '_local_text_area_rect', None)
        if area_rect is not None:
            return QRectF(area_rect)

        rect = self.data.get('rect', [0, 0, 0, 0])
        x_off = float(self.data.get('x_off', 0) or 0)
        y_off = float(self.data.get('y_off', 0) or 0)
        scene_rect = QRectF(
            float(rect[0]) + x_off,
            float(rect[1]) + y_off,
            max(1.0, float(rect[2])),
            max(1.0, float(rect[3])),
        )
        return self.mapFromScene(scene_rect).boundingRect()

    def text_content_scene_rect(self):
        """실제 글자가 차지하는 영역. 직접 편집 시작 위치/영역 계산에 쓴다."""
        rect = getattr(self, '_text_path_rect', None)
        if rect is None:
            rect = self.path().boundingRect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            rect = self.text_area_rect()
        return self.mapToScene(rect).boundingRect()

    def boundingRect(self):
        # QGraphicsPathItem.boundingRect()/shape()는 PyQt에서 다시 파이썬 override를 타는 경우가 있어
        # 최종화면 진입 때 재귀/렉을 만들 수 있다. 순수 path bounds 기준으로 직접 계산한다.
        base = self.path().boundingRect()
        area = self.text_area_rect()
        out = base.united(area)
        if self.data.get('_transform_mode', False):
            tr = self.transform_rect()
            for r in self.transform_handle_rects().values():
                out = out.united(r)
            hp = QPointF(tr.center().x(), tr.top() - 34)
            out = out.united(QRectF(hp.x() - 24, hp.y() - 24, 48, 48))
        return out.adjusted(-12, -12, 12, 12)

    def shape(self):
        # 클릭 판정은 실제 글자 선이 아니라 작업용 텍스트 영역 전체로 잡는다.
        # super().shape() 호출은 Qt 내부에서 다시 boundingRect()/shape()로 이어져 재귀가 날 수 있으므로
        # path()를 직접 더하는 방식으로 가볍게 처리한다.
        s = QPainterPath()
        area = self.text_area_rect()
        s.addRect(area)
        text_path = self.path()
        if not text_path.isEmpty():
            s.addPath(text_path)
        if self.data.get('_transform_mode', False):
            tr = self.transform_rect()
            s.addRect(tr.adjusted(-10, -10, 10, 10))
            for r in self.transform_handle_rects().values():
                s.addRect(r.adjusted(-6, -6, 6, 6))
            hp = QPointF(tr.center().x(), tr.top() - 34)
            s.addEllipse(QRectF(hp.x() - 22, hp.y() - 22, 44, 44))
        return s

    def paint(self, painter, option, widget=None):
        # 최종 화면 작업용 영역 표시.
        # 선택 전에는 옅은 회색, 선택 후에는 붉은 점선.
        # 변형 모드에서는 실제 글자 영역을 파란 실선 + 핸들로 표시한다.
        # 단, 파일 출력용 오프스크린 렌더에서는 보조 박스/핸들이 이미지에 찍히면 안 되므로 숨길 수 있게 한다.
        suppress_guides = bool(getattr(self, "suppress_guides", False))
        area_rect = self.text_area_rect()
        if not suppress_guides:
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

        synthetic_bold_width = float(getattr(self, '_synthetic_bold_width', 0.0) or 0.0)

        if self.pen_stroke.widthF() > 0:
            stroke_pen = QPen(self.pen_stroke)
            if synthetic_bold_width > 0:
                # If we embolden the fill, the outline must grow with it too.
                stroke_pen.setWidthF(float(stroke_pen.widthF()) + synthetic_bold_width)
            painter.setPen(stroke_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())

        if synthetic_bold_width > 0:
            # Some fonts have no bold face.  Photoshop fakes this; Qt often does
            # not.  Stroke the glyph path with the fill color to synthesize bold.
            bold_pen = QPen(self.brush_fill.color(), synthetic_bold_width)
            bold_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            bold_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(bold_pen)
            painter.setBrush(self.brush_fill)
            painter.drawPath(self.path())
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.brush_fill)
            painter.drawPath(self.path())

        if getattr(self, '_strike_lines', None):
            font_size = int(getattr(self, 'data', {}).get('font_size', 20) or 20)
            base_width = max(1.2, float(font_size) * 0.075 + synthetic_bold_width * 0.4)
            # Draw a stroke-color underlay first so the strikethrough is visible
            # even on very dark/heavy glyphs.
            if self.pen_stroke.widthF() > 0:
                under_pen = QPen(self.pen_stroke.color(), base_width + max(2.0, float(self.pen_stroke.widthF())))
                under_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(under_pen)
                for x1, y1, x2, y2 in self._strike_lines:
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            pen = QPen(self.brush_fill.color(), base_width)
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
        self._normal_move_press_pos = QPointF(self.pos())
        try:
            self._normal_move_press_xoff = int(self.data.get('x_off', 0) or 0)
            self._normal_move_press_yoff = int(self.data.get('y_off', 0) or 0)
        except Exception:
            self._normal_move_press_xoff = 0
            self._normal_move_press_yoff = 0
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
                        try:
                            if main is not None and hasattr(main, 'push_page_text_undo'):
                                main.push_page_text_undo('텍스트 회전 각도 지정')
                        except Exception:
                            pass
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
        path_rect = getattr(self, '_text_path_rect', QGraphicsPathItem.boundingRect(self))
        try:
            rect_x = float(rect[0])
            rect_y = float(rect[1])
            rect_w = max(1.0, float(rect[2]))
            rect_h = max(1.0, float(rect[3]))
            if align == 'left':
                new_x_off = int(round(float(new_pos.x()) + float(path_rect.left()) - rect_x))
            elif align == 'right':
                new_x_off = int(round(float(new_pos.x()) + float(path_rect.right()) - (rect_x + rect_w)))
            else:
                new_x_off = int(round(float(new_pos.x()) + float(path_rect.center().x()) - (rect_x + rect_w / 2.0)))
            new_y_off = int(round(float(new_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
        except Exception:
            new_x_off = int(round(float(new_pos.x()) - float(rect[0])))
            new_y_off = int(self.data.get('y_off', 0) or 0)
        old_x_off = int(self.data.get('x_off', 0) or 0)
        old_y_off = int(self.data.get('y_off', 0) or 0)

        # A plain click should not create an undo record or a "moved" log.
        if new_x_off == old_x_off and new_y_off == old_y_off:
            return

        main = getattr(self, "main_window", None)
        if main is not None and hasattr(main, 'push_page_text_undo'):
            try:
                main.push_page_text_undo('텍스트 이동')
            except Exception:
                pass

        try:
            self.prepareGeometryChange()
        except Exception:
            pass

        self.data['x_off'] = new_x_off
        self.data['y_off'] = new_y_off
        self.update()

        # 이동 직후에는 화면 좌표 -> data 좌표를 먼저 확정한 뒤 자동저장한다.
        # update_cb가 자동저장을 호출하지만, callback 누락/예외 상황에서도 좌표 저장이 빠지지 않게 보강한다.
        if main is not None:
            try:
                if hasattr(main, 'sync_final_text_scene_to_data'):
                    main.sync_final_text_scene_to_data()
            except Exception:
                pass

        if self.update_cb:
            self.update_cb(f"📍 텍스트 이동됨 (ID: {self.data.get('id')})")
        elif main is not None:
            try:
                if hasattr(main, 'auto_save_project'):
                    main.auto_save_project()
            except Exception:
                pass


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
