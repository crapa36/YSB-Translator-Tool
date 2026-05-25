import math
import base64
import copy
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem, QInputDialog
from PyQt6.QtGui import QFont, QFontMetrics, QPainterPath, QPen, QBrush, QColor, QTransform, QImage, QPixmap, QLinearGradient, QPainter, QPolygonF
from PyQt6.QtCore import Qt, QRectF, QPointF, QBuffer, QByteArray, QIODevice


# Photoshop의 Faux Italic 느낌에 맞춘 합성 기울임 강도.
# 너무 크면 글자가 과하게 누워 보이므로, Qt 기본 italic은 끄고 이 값만 적용한다.
FAUX_ITALIC_SHEAR = -0.13


def _qcolor(value, fallback):
    c = QColor(str(value or fallback))
    if not c.isValid():
        c = QColor(fallback)
    return c




def _bool_value(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "y")
    return bool(value)


def _int_value(value, default=0, lo=None, hi=None):
    try:
        out = int(round(float(value)))
    except Exception:
        out = int(default)
    if lo is not None:
        out = max(int(lo), out)
    if hi is not None:
        out = min(int(hi), out)
    return out


def _image_from_base64_png(value):
    if not value:
        return QImage()
    try:
        raw = base64.b64decode(str(value).encode("ascii"), validate=False)
        img = QImage()
        img.loadFromData(raw, "PNG")
        return img
    except Exception:
        return QImage()


def _image_to_base64_png(image):
    if image is None or image.isNull():
        return ""
    ba = QByteArray()
    buf = QBuffer(ba)
    if not buf.open(QIODevice.OpenModeFlag.WriteOnly):
        return ""
    try:
        image.save(buf, "PNG")
    finally:
        buf.close()
    return bytes(ba.toBase64()).decode("ascii")


def _gradient_brush(rect, color1, color2, angle=0, ratio=50):
    rect = QRectF(rect)
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        rect = QRectF(0, 0, 1, 1)

    c1 = _qcolor(color1, "#000000")
    c2 = _qcolor(color2, "#FFFFFF")

    try:
        rad = math.radians(float(angle or 0))
    except Exception:
        rad = 0.0
    # Rect diagonal length keeps the gradient long enough for any angle.
    length = max(1.0, math.hypot(rect.width(), rect.height()))
    dx = math.cos(rad) * length / 2.0
    dy = math.sin(rad) * length / 2.0
    center = rect.center()
    grad = QLinearGradient(QPointF(center.x() - dx, center.y() - dy), QPointF(center.x() + dx, center.y() + dy))

    # ratio is interpreted as the point where color 2 becomes dominant.
    # 50 = normal two-color gradient.  Lower values make color 2 appear earlier;
    # higher values keep color 1 longer.
    t = max(1, min(99, _int_value(ratio, 50, 1, 99))) / 100.0
    grad.setColorAt(0.0, c1)
    grad.setColorAt(t, c2)
    grad.setColorAt(1.0, c2)
    return QBrush(grad)

def _projective_transform_for_quads(src_points, dst_points):
    try:
        src_poly = QPolygonF([QPointF(p) for p in src_points])
        dst_poly = QPolygonF([QPointF(p) for p in dst_points])
    except Exception:
        return None

    # PyQt/PySide 버전에 따라 quadToQuad 반환 형식이 조금 다르다.
    try:
        trans = QTransform()
        ok = QTransform.quadToQuad(src_poly, dst_poly, trans)
        if ok:
            return trans
    except TypeError:
        pass
    except Exception:
        pass

    try:
        result = QTransform.quadToQuad(src_poly, dst_poly)
        if isinstance(result, tuple):
            if len(result) == 2 and isinstance(result[1], QTransform):
                ok, trans = result
                if ok:
                    return trans
            elif len(result) >= 3 and isinstance(result[-1], QTransform):
                ok = bool(result[0])
                trans = result[-1]
                if ok:
                    return trans
        elif isinstance(result, QTransform):
            return result
    except Exception:
        pass
    return None


def _trapezoid_quad_from_rect(rect, left_pct=0, right_pct=0, top_pct=0, bottom_pct=0):
    rect = QRectF(rect)
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        rect = QRectF(0, 0, 1, 1)
    lp = max(-95, min(95, int(round(float(left_pct or 0)))))
    rp = max(-95, min(95, int(round(float(right_pct or 0)))))
    tp = max(-95, min(95, int(round(float(top_pct or 0)))))
    bp = max(-95, min(95, int(round(float(bottom_pct or 0)))))
    half_h = rect.height() / 2.0
    half_w = rect.width() / 2.0
    left_inset = half_h * (lp / 100.0)
    right_inset = half_h * (rp / 100.0)
    top_inset = half_w * (tp / 100.0)
    bottom_inset = half_w * (bp / 100.0)
    return [
        QPointF(rect.left() + top_inset, rect.top() + left_inset),
        QPointF(rect.right() - top_inset, rect.top() + right_inset),
        QPointF(rect.right() - bottom_inset, rect.bottom() - right_inset),
        QPointF(rect.left() + bottom_inset, rect.bottom() - left_inset),
    ]


def _apply_trapezoid_transform_to_path(path, left_pct=0, right_pct=0, top_pct=0, bottom_pct=0):
    if path is None:
        return path
    rect = path.boundingRect()
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return path
    src = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
    dst = _trapezoid_quad_from_rect(rect, left_pct, right_pct, top_pct, bottom_pct)
    trans = _projective_transform_for_quads(src, dst)
    if trans is None:
        return path
    try:
        return trans.map(path)
    except Exception:
        return path


def _warp_path_by_arc_sides(path, top_pct=0, bottom_pct=0, left_pct=0, right_pct=0, top_pos=50, bottom_pos=50, left_pos=50, right_pos=50):
    if path is None:
        return path
    rect = path.boundingRect()
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return path

    w = max(1.0, float(rect.width()))
    h = max(1.0, float(rect.height()))
    left = float(rect.left())
    top = float(rect.top())
    top_pct = float(top_pct or 0)
    bottom_pct = float(bottom_pct or 0)
    left_pct = float(left_pct or 0)
    right_pct = float(right_pct or 0)
    top_c = max(0.0, min(1.0, float(top_pos or 50) / 100.0))
    bottom_c = max(0.0, min(1.0, float(bottom_pos or 50) / 100.0))
    left_c = max(0.0, min(1.0, float(left_pos or 50) / 100.0))
    right_c = max(0.0, min(1.0, float(right_pos or 50) / 100.0))

    def bell_center(t, c):
        t = max(0.0, min(1.0, float(t)))
        c = max(0.0, min(1.0, float(c)))
        # 클릭한 위치를 가장 강하게 하고 주변으로 부드럽게 사라지는 1점 제어 곡선.
        radius = 0.55
        d = abs(t - c) / radius
        if d >= 1.0:
            return 0.0
        return (1.0 - d * d) ** 2

    def map_point(pt):
        u = (pt.x() - left) / w
        v = (pt.y() - top) / h
        dx = (bell_center(v, left_c) * left_pct * (1.0 - u) + bell_center(v, right_c) * right_pct * u) * (w * 0.35 / 100.0)
        dy = (bell_center(u, top_c) * top_pct * (1.0 - v) + bell_center(u, bottom_c) * bottom_pct * v) * (h * 0.35 / 100.0)
        return QPointF(pt.x() + dx, pt.y() + dy)

    polys = path.toSubpathPolygons()
    if not polys:
        return path
    out = QPainterPath()
    out.setFillRule(path.fillRule())
    for poly in polys:
        if not poly:
            continue
        pts = [map_point(pt) for pt in poly]
        if not pts:
            continue
        out.moveTo(pts[0])
        for pt in pts[1:]:
            out.lineTo(pt)
        out.closeSubpath()
    return out




def _arc_handles_from_data(data):
    out = []
    raw = []
    try:
        raw = data.get('arc_handles') or []
    except Exception:
        raw = []
    if isinstance(raw, list):
        for h in raw:
            if not isinstance(h, dict):
                continue
            side = str(h.get('side') or '')
            if side not in ('top', 'bottom', 'left', 'right'):
                continue
            try:
                t = max(0, min(100, int(round(float(h.get('t', 50))))))
                value = max(-100, min(100, int(round(float(h.get('value', 0))))))
            except Exception:
                continue
            out.append({'side': side, 't': t, 'value': value})
    if out:
        return out

    # 구버전/단일 부채꼴 값 호환. 저장 구조가 바뀌어도 기존 프로젝트는 유지한다.
    legacy = []
    for side in ('top', 'bottom', 'left', 'right'):
        try:
            value = int(round(float(data.get(f'arc_{side}', 0) or 0)))
        except Exception:
            value = 0
        if value:
            try:
                t = int(round(float(data.get(f'arc_{side}_pos', 50) or 50)))
            except Exception:
                t = 50
            legacy.append({'side': side, 't': max(0, min(100, t)), 'value': max(-100, min(100, value))})
    return legacy


def _warp_path_by_arc_handles(path, handles):
    handles = [h for h in (handles or []) if isinstance(h, dict) and h.get('side') in ('top', 'bottom', 'left', 'right')]
    if not handles:
        return path
    if path is None:
        return path
    rect = path.boundingRect()
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return path

    w = max(1.0, float(rect.width()))
    h = max(1.0, float(rect.height()))
    left = float(rect.left())
    top = float(rect.top())

    def bell_center(t, c):
        t = max(0.0, min(1.0, float(t)))
        c = max(0.0, min(1.0, float(c)))
        radius = 0.45
        d = abs(t - c) / radius
        if d >= 1.0:
            return 0.0
        return (1.0 - d * d) ** 2

    normalized = []
    for raw in handles:
        side = str(raw.get('side') or '')
        try:
            t = max(0.0, min(1.0, float(raw.get('t', 50) or 50) / 100.0))
            value = max(-100.0, min(100.0, float(raw.get('value', 0) or 0)))
        except Exception:
            continue
        if value:
            normalized.append((side, t, value))
    if not normalized:
        return path

    def map_point(pt):
        u = (pt.x() - left) / w
        v = (pt.y() - top) / h
        dx = 0.0
        dy = 0.0
        for side, t, value in normalized:
            if side == 'top':
                dy += bell_center(u, t) * value * (1.0 - v) * (h * 0.35 / 100.0)
            elif side == 'bottom':
                dy += bell_center(u, t) * value * v * (h * 0.35 / 100.0)
            elif side == 'left':
                dx += bell_center(v, t) * value * (1.0 - u) * (w * 0.35 / 100.0)
            elif side == 'right':
                dx += bell_center(v, t) * value * u * (w * 0.35 / 100.0)
        return QPointF(pt.x() + dx, pt.y() + dy)

    polys = path.toSubpathPolygons()
    if not polys:
        return path
    out = QPainterPath()
    out.setFillRule(path.fillRule())
    for poly in polys:
        if not poly:
            continue
        pts = [map_point(pt) for pt in poly]
        if not pts:
            continue
        out.moveTo(pts[0])
        for pt in pts[1:]:
            out.lineTo(pt)
        out.closeSubpath()
    return out


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

        if _bool_value(data.get('rasterized_text'), False):
            self._init_rasterized_text_item()
            return

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

        skew_x = _int_value(data.get('skew_x', 0), 0, -100, 100) / 100.0
        skew_y = _int_value(data.get('skew_y', 0), 0, -100, 100) / 100.0
        if skew_x or skew_y:
            tr = QTransform()
            tr.shear(skew_x, skew_y)
            path = tr.map(path)

        trap_left = _int_value(data.get('trap_left', 0), 0, -95, 95)
        trap_right = _int_value(data.get('trap_right', 0), 0, -95, 95)
        trap_top = _int_value(data.get('trap_top', 0), 0, -95, 95)
        trap_bottom = _int_value(data.get('trap_bottom', 0), 0, -95, 95)
        if trap_left or trap_right or trap_top or trap_bottom:
            path = _apply_trapezoid_transform_to_path(path, trap_left, trap_right, trap_top, trap_bottom)

        arc_handles = _arc_handles_from_data(data)
        if arc_handles:
            path = _warp_path_by_arc_handles(path, arc_handles)

        self.setPath(path)

        self.pen_stroke = QPen(
            _qcolor(item_stroke_color, "#FFFFFF"),
            item_stroke,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        if _bool_value(data.get('text_gradient_enabled'), False):
            self.brush_fill = _gradient_brush(
                path.boundingRect(),
                data.get('text_gradient_color1') or item_text_color,
                data.get('text_gradient_color2') or "#FFFFFF",
                data.get('text_gradient_angle', 0),
                data.get('text_gradient_ratio', 50),
            )
            self._fill_fallback_color = _qcolor(data.get('text_gradient_color1') or item_text_color, "#000000")
        else:
            self.brush_fill = QBrush(_qcolor(item_text_color, "#000000"))
            self._fill_fallback_color = self.brush_fill.color()

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
        self._skew_action = None
        self._skew_press_pos = QPointF()
        self._skew_press_scene_pos = QPointF()
        self._skew_press_x = int(data.get('skew_x', 0) or 0)
        self._skew_press_y = int(data.get('skew_y', 0) or 0)
        self._trapezoid_action = None
        self._trapezoid_press_pos = QPointF()
        self._trapezoid_press_scene_pos = QPointF()
        self._trapezoid_press_left = int(data.get('trap_left', 0) or 0)
        self._trapezoid_press_right = int(data.get('trap_right', 0) or 0)
        self._trapezoid_press_top = int(data.get('trap_top', 0) or 0)
        self._trapezoid_press_bottom = int(data.get('trap_bottom', 0) or 0)
        self._arc_action = None
        self._arc_press_pos = QPointF()
        self._arc_press_scene_pos = QPointF()
        self._arc_press_top = int(data.get('arc_top', 0) or 0)
        self._arc_press_bottom = int(data.get('arc_bottom', 0) or 0)
        self._arc_press_left = int(data.get('arc_left', 0) or 0)
        self._arc_press_right = int(data.get('arc_right', 0) or 0)

        self._apply_common_text_item_flags()

    def _apply_common_text_item_flags(self):
        self.setZValue(30)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        self.setFlags(
            self.GraphicsItemFlag.ItemIsMovable
            | self.GraphicsItemFlag.ItemIsSelectable
            | self.GraphicsItemFlag.ItemSendsGeometryChanges
        )

    def _init_rasterized_text_item(self):
        self._is_rasterized_text = True
        img = _image_from_base64_png(self.data.get('raster_png'))
        if img.isNull():
            img = QImage(1, 1, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
        self._raster_image = img.convertToFormat(QImage.Format.Format_ARGB32)
        self._raster_rect = QRectF(0, 0, max(1, self._raster_image.width()), max(1, self._raster_image.height()))

        path = QPainterPath()
        path.addRect(self._raster_rect)
        self.setPath(path)
        self.pen_stroke = QPen(Qt.PenStyle.NoPen)
        self.brush_fill = QBrush(Qt.BrushStyle.NoBrush)
        self._fill_fallback_color = QColor("#000000")
        self._strike_lines = []
        self._synthetic_bold_width = 0.0
        self._text_path_rect = QRectF(self._raster_rect)
        self._local_text_area_rect = QRectF(self._raster_rect)

        rect = list(self.data.get('rect') or [0, 0, self._raster_image.width(), self._raster_image.height()])
        while len(rect) < 4:
            rect.append(1)
        try:
            x = float(rect[0]) + float(self.data.get('x_off', 0) or 0)
            y = float(rect[1]) + float(self.data.get('y_off', 0) or 0)
        except Exception:
            x, y = 0.0, 0.0
        self.setPos(x, y)

        try:
            self.setTransformOriginPoint(self.transform_rect().center())
            self.setRotation(float(self.data.get('rotation', 0) or 0))
        except Exception:
            pass

        self._transform_action = None
        self._transform_press_pos = None
        self._transform_press_angle = 0.0
        self._transform_press_rotation = 0.0
        self._transform_press_char_width = int(self.data.get('char_width', 100) or 100)
        self._transform_press_char_height = int(self.data.get('char_height', 100) or 100)
        self._transform_press_rect = QRectF()
        self._transform_live_rect = None
        self._transform_press_scene_pos = QPointF()
        self._transform_press_item_pos = QPointF()
        self._transform_press_rect_data = None
        self._skew_action = None
        self._skew_press_pos = QPointF()
        self._skew_press_scene_pos = QPointF()
        self._skew_press_x = int(self.data.get('skew_x', 0) or 0)
        self._skew_press_y = int(self.data.get('skew_y', 0) or 0)
        self._trapezoid_action = None
        self._trapezoid_press_pos = QPointF()
        self._trapezoid_press_scene_pos = QPointF()
        self._trapezoid_press_left = int(self.data.get('trap_left', 0) or 0)
        self._trapezoid_press_right = int(self.data.get('trap_right', 0) or 0)
        self._trapezoid_press_top = int(self.data.get('trap_top', 0) or 0)
        self._trapezoid_press_bottom = int(self.data.get('trap_bottom', 0) or 0)
        self._arc_action = None
        self._arc_press_pos = QPointF()
        self._arc_press_scene_pos = QPointF()
        self._arc_press_top = int(self.data.get('arc_top', 0) or 0)
        self._arc_press_bottom = int(self.data.get('arc_bottom', 0) or 0)
        self._arc_press_left = int(self.data.get('arc_left', 0) or 0)
        self._arc_press_right = int(self.data.get('arc_right', 0) or 0)
        self._raster_drag_scene_press = None
        self._raster_drag_item_press = None
        self._apply_common_text_item_flags()

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

    def skew_handle_rects(self):
        rect = self.transform_rect()
        s = 16.0
        half = s / 2.0

        def box(pt):
            return QRectF(pt.x() - half, pt.y() - half, s, s)

        pts = {
            'left': QPointF(rect.left(), rect.center().y()),
            'right': QPointF(rect.right(), rect.center().y()),
            'top': QPointF(rect.center().x(), rect.top()),
            'bottom': QPointF(rect.center().x(), rect.bottom()),
        }
        return {name: box(pt) for name, pt in pts.items()}

    def skew_action_at(self, pos):
        if not self.data.get('_skew_mode', False):
            return None
        rects = self.skew_handle_rects()
        for name in ('left', 'right', 'top', 'bottom'):
            r = rects.get(name)
            if r and r.adjusted(-6, -6, 6, 6).contains(pos):
                return name
        return None

    def set_text_skew_values(self, skew_x=None, skew_y=None):
        if skew_x is not None:
            self.data['skew_x'] = max(-100, min(100, int(round(float(skew_x)))))
        if skew_y is not None:
            self.data['skew_y'] = max(-100, min(100, int(round(float(skew_y)))))
        self.update()

    def set_text_skew_angle(self, action, angle):
        try:
            value = math.tan(math.radians(float(angle))) * 100.0
        except Exception:
            value = 0.0
        value = max(-100, min(100, int(round(value))))
        if action in ('top', 'bottom'):
            self.set_text_skew_values(skew_x=value)
        elif action in ('left', 'right'):
            self.set_text_skew_values(skew_y=value)

    def begin_skew_action(self, action, local_pos, scene_pos):
        if not self.data.get('_skew_mode', False) or not action:
            return False
        main = getattr(self, "main_window", None)
        if main is not None and hasattr(main, 'push_page_text_undo'):
            try:
                main.push_page_text_undo('텍스트 기울이기 조정')
            except Exception:
                pass
        self._skew_action = action
        self._skew_press_pos = QPointF(local_pos)
        self._skew_press_scene_pos = QPointF(scene_pos)
        self._skew_press_x = int(self.data.get('skew_x', 0) or 0)
        self._skew_press_y = int(self.data.get('skew_y', 0) or 0)
        self.setSelected(True)
        self.update()
        return True

    def update_skew_action(self, local_pos, scene_pos):
        if not self._skew_action:
            return False
        rect = self.transform_rect()
        w = max(1.0, float(rect.width()))
        h = max(1.0, float(rect.height()))
        dx = float(local_pos.x() - self._skew_press_pos.x())
        dy = float(local_pos.y() - self._skew_press_pos.y())
        if self._skew_action in ('top', 'bottom'):
            sign = -1.0 if self._skew_action == 'top' else 1.0
            value = self._skew_press_x + sign * (dx / h) * 100.0
            self.set_text_skew_values(skew_x=value)
        elif self._skew_action in ('left', 'right'):
            sign = -1.0 if self._skew_action == 'left' else 1.0
            value = self._skew_press_y + sign * (dy / w) * 100.0
            self.set_text_skew_values(skew_y=value)
        return True

    def finish_skew_action(self):
        if not self._skew_action:
            return False
        self._skew_action = None
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
                main.log(f"🔷 텍스트 기울이기 적용: 가로 {self.data.get('skew_x', 0)}%, 세로 {self.data.get('skew_y', 0)}%")
            except Exception:
                pass
        return True

    def trapezoid_handle_rects(self):
        pts = _trapezoid_quad_from_rect(
            self.transform_rect(),
            self.data.get('trap_left', 0),
            self.data.get('trap_right', 0),
            self.data.get('trap_top', 0),
            self.data.get('trap_bottom', 0),
        )
        names = ('top_left', 'top_right', 'bottom_right', 'bottom_left')
        s = 16.0
        half = s / 2.0
        out = {}
        for name, pt in zip(names, pts):
            out[name] = QRectF(pt.x() - half, pt.y() - half, s, s)
        rect = self.transform_rect()
        out['top'] = QRectF(rect.center().x() - half, min(pts[0].y(), pts[1].y()) - half, s, s)
        out['bottom'] = QRectF(rect.center().x() - half, max(pts[2].y(), pts[3].y()) - half, s, s)
        out['left'] = QRectF(min(pts[0].x(), pts[3].x()) - half, rect.center().y() - half, s, s)
        out['right'] = QRectF(max(pts[1].x(), pts[2].x()) - half, rect.center().y() - half, s, s)
        return out

    def trapezoid_action_at(self, pos):
        if not self.data.get('_trapezoid_mode', False):
            return None
        order = ('top_left', 'top_right', 'bottom_right', 'bottom_left', 'top', 'bottom', 'left', 'right')
        for name in order:
            r = self.trapezoid_handle_rects().get(name)
            if r and r.adjusted(-6, -6, 6, 6).contains(pos):
                return name
        return None

    def set_text_trapezoid_values(self, left_pct=None, right_pct=None, top_pct=None, bottom_pct=None):
        if left_pct is not None:
            self.data['trap_left'] = max(-95, min(95, int(round(float(left_pct)))))
        if right_pct is not None:
            self.data['trap_right'] = max(-95, min(95, int(round(float(right_pct)))))
        if top_pct is not None:
            self.data['trap_top'] = max(-95, min(95, int(round(float(top_pct)))))
        if bottom_pct is not None:
            self.data['trap_bottom'] = max(-95, min(95, int(round(float(bottom_pct)))))
        self.update()

    def begin_trapezoid_action(self, action, local_pos, scene_pos):
        if not self.data.get('_trapezoid_mode', False) or not action:
            return False
        main = getattr(self, 'main_window', None)
        if main is not None and hasattr(main, 'push_page_text_undo'):
            try:
                main.push_page_text_undo('사다리꼴 변형 조정')
            except Exception:
                pass
        self._trapezoid_action = action
        self._trapezoid_press_pos = QPointF(local_pos)
        self._trapezoid_press_scene_pos = QPointF(scene_pos)
        self._trapezoid_press_left = int(self.data.get('trap_left', 0) or 0)
        self._trapezoid_press_right = int(self.data.get('trap_right', 0) or 0)
        self._trapezoid_press_top = int(self.data.get('trap_top', 0) or 0)
        self._trapezoid_press_bottom = int(self.data.get('trap_bottom', 0) or 0)
        self.setSelected(True)
        self.update()
        return True

    def update_trapezoid_action(self, local_pos, scene_pos):
        if not self._trapezoid_action:
            return False
        rect = self.transform_rect()
        h = max(1.0, float(rect.height()))
        w = max(1.0, float(rect.width()))
        dx = float(local_pos.x() - self._trapezoid_press_pos.x())
        dy = float(local_pos.y() - self._trapezoid_press_pos.y())
        scale_y = 200.0 / h
        scale_x = 200.0 / w
        action = self._trapezoid_action
        if action in ('top_left', 'bottom_left', 'left'):
            sign = 1.0 if action == 'top_left' else (-1.0 if action == 'bottom_left' else 1.0)
            value = self._trapezoid_press_left + sign * dy * scale_y
            self.set_text_trapezoid_values(left_pct=value)
        elif action in ('top_right', 'bottom_right', 'right'):
            sign = 1.0 if action == 'top_right' else (-1.0 if action == 'bottom_right' else 1.0)
            value = self._trapezoid_press_right + sign * dy * scale_y
            self.set_text_trapezoid_values(right_pct=value)
        elif action == 'top':
            value = self._trapezoid_press_top + dx * scale_x
            self.set_text_trapezoid_values(top_pct=value)
        elif action == 'bottom':
            value = self._trapezoid_press_bottom - dx * scale_x
            self.set_text_trapezoid_values(bottom_pct=value)
        return True

    def finish_trapezoid_action(self):
        if not self._trapezoid_action:
            return False
        self._trapezoid_action = None
        main = getattr(self, 'main_window', None)
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
                main.log(f"🔷 사다리꼴 변형 적용: 왼쪽 {self.data.get('trap_left', 0)}%, 오른쪽 {self.data.get('trap_right', 0)}%, 위쪽 {self.data.get('trap_top', 0)}%, 아래쪽 {self.data.get('trap_bottom', 0)}%")
            except Exception:
                pass
        return True

    def _arc_handles(self):
        handles = _arc_handles_from_data(self.data)
        # 새 구조를 쓰기 시작하면 명시적으로 저장한다.
        try:
            if self.data.get('arc_handles') is None and handles:
                self.data['arc_handles'] = copy.deepcopy(handles)
        except Exception:
            pass
        return handles

    def _save_arc_handles(self, handles):
        clean = []
        for h in handles or []:
            if not isinstance(h, dict):
                continue
            side = str(h.get('side') or '')
            if side not in ('top', 'bottom', 'left', 'right'):
                continue
            try:
                clean.append({
                    'side': side,
                    't': max(0, min(100, int(round(float(h.get('t', 50)))))),
                    'value': max(-100, min(100, int(round(float(h.get('value', 0)))))),
                })
            except Exception:
                pass
        self.data['arc_handles'] = clean
        try:
            self.data['arc_active_index'] = max(-1, min(int(self.data.get('arc_active_index', -1) or -1), len(clean) - 1))
        except Exception:
            self.data['arc_active_index'] = len(clean) - 1 if clean else -1

    def _arc_handle_point_for(self, handle):
        rect = self.transform_rect()
        side = str((handle or {}).get('side') or '')
        try:
            t = max(0.0, min(1.0, float((handle or {}).get('t', 50) or 50) / 100.0))
        except Exception:
            t = 0.5
        if side == 'top':
            return QPointF(rect.left() + rect.width() * t, rect.top())
        if side == 'bottom':
            return QPointF(rect.left() + rect.width() * t, rect.bottom())
        if side == 'left':
            return QPointF(rect.left(), rect.top() + rect.height() * t)
        if side == 'right':
            return QPointF(rect.right(), rect.top() + rect.height() * t)
        return None

    def arc_handle_rects(self):
        handles = self._arc_handles()
        s = 16.0
        half = s / 2.0
        out = {}
        for idx, handle in enumerate(handles):
            pt = self._arc_handle_point_for(handle)
            if pt is not None:
                out[f'arc_{idx}'] = QRectF(pt.x() - half, pt.y() - half, s, s)
        return out

    def _arc_side_and_t_from_pos(self, pos):
        rect = self.transform_rect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return None, 50.0
        p = QPointF(pos)
        margin = 26.0
        if not rect.adjusted(-margin, -margin, margin, margin).contains(p):
            return None, 50.0
        d = {
            'top': abs(p.y() - rect.top()),
            'bottom': abs(p.y() - rect.bottom()),
            'left': abs(p.x() - rect.left()),
            'right': abs(p.x() - rect.right()),
        }
        side = min(d, key=d.get)
        if side in ('top', 'bottom'):
            t = ((p.x() - rect.left()) / max(1.0, rect.width())) * 100.0
        else:
            t = ((p.y() - rect.top()) / max(1.0, rect.height())) * 100.0
        return side, max(0.0, min(100.0, t))

    def create_or_replace_arc_handle_at(self, pos):
        side, t = self._arc_side_and_t_from_pos(pos)
        if not side:
            return None
        handles = self._arc_handles()
        handles.append({'side': side, 't': int(round(t)), 'value': 0})
        self._save_arc_handles(handles)
        idx = len(handles) - 1
        self.data['arc_active_index'] = idx
        self.update()
        return f'arc_{idx}'

    def arc_action_at(self, pos):
        if not self.data.get('_arc_mode', False):
            return None
        for name, r in self.arc_handle_rects().items():
            if r.adjusted(-6, -6, 6, 6).contains(pos):
                return name
        return None

    def _arc_index_from_action(self, action):
        try:
            if isinstance(action, str) and action.startswith('arc_'):
                return int(action.split('_', 1)[1])
        except Exception:
            pass
        # 구버전 액션 문자열 호환
        if action in ('top', 'bottom', 'left', 'right'):
            handles = self._arc_handles()
            for i, h in enumerate(handles):
                if h.get('side') == action:
                    return i
        return -1

    def set_text_arc_values(self, top_pct=None, bottom_pct=None, left_pct=None, right_pct=None):
        # 구버전 API 호환용. 같은 면의 첫 핸들을 갱신하거나 새 핸들을 만든다.
        updates = {'top': top_pct, 'bottom': bottom_pct, 'left': left_pct, 'right': right_pct}
        handles = self._arc_handles()
        for side, value in updates.items():
            if value is None:
                continue
            found = False
            for h in handles:
                if h.get('side') == side:
                    h['value'] = max(-100, min(100, int(round(float(value)))))
                    found = True
                    break
            if not found:
                handles.append({'side': side, 't': 50, 'value': max(-100, min(100, int(round(float(value)))))} )
        self._save_arc_handles(handles)
        self.update()

    def set_text_arc_handle_value(self, index, value):
        handles = self._arc_handles()
        try:
            idx = int(index)
        except Exception:
            return False
        if idx < 0 or idx >= len(handles):
            return False
        handles[idx]['value'] = max(-100, min(100, int(round(float(value)))))
        self._save_arc_handles(handles)
        self.data['arc_active_index'] = idx
        self.update()
        return True

    def begin_arc_action(self, action, local_pos, scene_pos):
        if not self.data.get('_arc_mode', False) or not action:
            return False
        idx = self._arc_index_from_action(action)
        handles = self._arc_handles()
        if idx < 0 or idx >= len(handles):
            return False
        main = getattr(self, 'main_window', None)
        if main is not None and hasattr(main, 'push_page_text_undo'):
            try:
                main.push_page_text_undo('부채꼴 변형 조정')
            except Exception:
                pass
        self._arc_action = f'arc_{idx}'
        self._arc_active_index = idx
        self._arc_press_pos = QPointF(local_pos)
        self._arc_press_scene_pos = QPointF(scene_pos)
        self._arc_press_value = int(handles[idx].get('value', 0) or 0)
        self.data['arc_active_index'] = idx
        self.setSelected(True)
        self.update()
        return True

    def update_arc_action(self, local_pos, scene_pos):
        if not self._arc_action:
            return False
        idx = self._arc_index_from_action(self._arc_action)
        handles = self._arc_handles()
        if idx < 0 or idx >= len(handles):
            return False
        rect = self.transform_rect()
        h = max(1.0, float(rect.height()))
        w = max(1.0, float(rect.width()))
        dx = float(local_pos.x() - self._arc_press_pos.x())
        dy = float(local_pos.y() - self._arc_press_pos.y())
        side = str(handles[idx].get('side') or '')
        base = int(getattr(self, '_arc_press_value', handles[idx].get('value', 0)) or 0)
        if side == 'top':
            value = base + (-dy / h) * 120.0
        elif side == 'bottom':
            value = base + (dy / h) * 120.0
        elif side == 'left':
            value = base + (-dx / w) * 120.0
        else:
            value = base + (dx / w) * 120.0
        return self.set_text_arc_handle_value(idx, value)

    def finish_arc_action(self):
        if not self._arc_action:
            return False
        self._arc_action = None
        main = getattr(self, 'main_window', None)
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
                main.log(f"🔷 부채꼴 변형 적용: 제어점 {len(self._arc_handles())}개")
            except Exception:
                pass
        return True

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
        if bool(self.data.get('manual_text_rect')) or text_anchor_mode or bool(self.data.get('_transform_mode', False)) or bool(self.data.get('_skew_mode', False)) or bool(self.data.get('_trapezoid_mode', False)) or bool(self.data.get('_arc_mode', False)):
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
        if self.data.get('_skew_mode', False):
            out = out.united(self.transform_rect())
            for r in self.skew_handle_rects().values():
                out = out.united(r)
        if self.data.get('_trapezoid_mode', False):
            out = out.united(self.transform_rect())
            for r in self.trapezoid_handle_rects().values():
                out = out.united(r)
        if self.data.get('_arc_mode', False):
            out = out.united(self.transform_rect())
            for r in self.arc_handle_rects().values():
                out = out.united(r)
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
        if self.data.get('_skew_mode', False):
            tr = self.transform_rect()
            s.addRect(tr.adjusted(-10, -10, 10, 10))
            for r in self.skew_handle_rects().values():
                s.addRect(r.adjusted(-8, -8, 8, 8))
        if self.data.get('_trapezoid_mode', False):
            tr = self.transform_rect()
            s.addPolygon(QPolygonF(_trapezoid_quad_from_rect(tr, self.data.get('trap_left', 0), self.data.get('trap_right', 0), self.data.get('trap_top', 0), self.data.get('trap_bottom', 0))))
            for r in self.trapezoid_handle_rects().values():
                s.addRect(r.adjusted(-8, -8, 8, 8))
        if self.data.get('_arc_mode', False):
            tr = self.transform_rect()
            s.addRect(tr.adjusted(-10, -10, 10, 10))
            for r in self.arc_handle_rects().values():
                s.addRect(r.adjusted(-8, -8, 8, 8))
        return s

    def paint(self, painter, option, widget=None):
        # 최종 화면 작업용 영역 표시.
        # 선택 전에는 옅은 회색, 선택 후에는 붉은 점선.
        # 변형 모드에서는 실제 글자 영역을 파란 실선 + 핸들로 표시한다.
        # 단, 파일 출력용 오프스크린 렌더에서는 보조 박스/핸들이 이미지에 찍히면 안 되므로 숨길 수 있게 한다.
        suppress_guides = bool(getattr(self, "suppress_guides", False))
        area_rect = self.text_area_rect()
        try:
            _text_opacity = max(0, min(100, int(self.data.get('opacity', 100) or 100))) / 100.0
        except Exception:
            _text_opacity = 1.0
        painter.save()
        painter.setOpacity(_text_opacity)
        if getattr(self, '_is_rasterized_text', False):
            if not suppress_guides:
                if self.isSelected():
                    area_pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)
                else:
                    area_pen = QPen(QColor(180, 180, 180, 150), 1, Qt.PenStyle.DotLine)
                painter.setPen(area_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(area_rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawImage(QPointF(0, 0), self._raster_image)
            painter.restore()
            return

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
            elif self.data.get('_skew_mode', False):
                tr = self.transform_rect()
                painter.setPen(QPen(QColor(60, 150, 255), 2, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(tr)
                painter.setBrush(QBrush(QColor(60, 150, 255)))
                painter.setPen(QPen(QColor(230, 245, 255), 1))
                for name, r in self.skew_handle_rects().items():
                    painter.drawRect(r)
            elif self.data.get('_trapezoid_mode', False):
                quad = _trapezoid_quad_from_rect(self.transform_rect(), self.data.get('trap_left', 0), self.data.get('trap_right', 0), self.data.get('trap_top', 0), self.data.get('trap_bottom', 0))
                painter.setPen(QPen(QColor(60, 150, 255), 2, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(QPolygonF(quad))
                painter.setBrush(QBrush(QColor(60, 150, 255)))
                painter.setPen(QPen(QColor(230, 245, 255), 1))
                for name, r in self.trapezoid_handle_rects().items():
                    painter.drawRect(r)
            elif self.data.get('_arc_mode', False):
                tr = self.transform_rect()
                painter.setPen(QPen(QColor(60, 150, 255), 2, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(tr)
                painter.setBrush(QBrush(QColor(60, 150, 255)))
                painter.setPen(QPen(QColor(230, 245, 255), 1))
                for name, r in self.arc_handle_rects().items():
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
        text_path = self.path()

        if synthetic_bold_width > 0:
            # 합성 볼드는 글자 내부를 두껍게 만드는 용도다. 획보다 나중에 그리면
            # 문자 그라데이션의 첫 색이 획 바깥으로 번져 보일 수 있으므로 먼저 깔고,
            # 실제 획을 그 위에 다시 올린 뒤 fill을 마지막에 정리한다.
            bold_pen = QPen()
            bold_pen.setBrush(self.brush_fill)
            bold_pen.setWidthF(synthetic_bold_width)
            bold_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            bold_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(bold_pen)
            painter.setBrush(self.brush_fill)
            painter.drawPath(text_path)

        if self.pen_stroke.widthF() > 0:
            stroke_pen = QPen(self.pen_stroke)
            if _bool_value(self.data.get('stroke_gradient_enabled'), False):
                stroke_pen.setBrush(_gradient_brush(
                    text_path.boundingRect(),
                    self.data.get('stroke_gradient_color1') or self.pen_stroke.color().name(),
                    self.data.get('stroke_gradient_color2') or "#000000",
                    self.data.get('stroke_gradient_angle', 0),
                    self.data.get('stroke_gradient_ratio', 50),
                ))
            if synthetic_bold_width > 0:
                stroke_pen.setWidthF(float(stroke_pen.widthF()) + synthetic_bold_width)
            painter.setPen(stroke_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(text_path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.brush_fill)
        painter.drawPath(text_path)

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
            pen = QPen(getattr(self, '_fill_fallback_color', self.brush_fill.color()), base_width)
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
        if self.data.get('_skew_mode', False):
            action = self.skew_action_at(event.pos())
            if action:
                self.setCursor(self.transform_cursor_for_action(action))
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if self.data.get('_trapezoid_mode', False):
            action = self.trapezoid_action_at(event.pos())
            if action:
                self.setCursor(self.transform_cursor_for_action(action))
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if self.data.get('_arc_mode', False):
            action = self.arc_action_at(event.pos())
            if action:
                self.setCursor(self.transform_cursor_for_action(action))
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

        # 객체화된 텍스트는 더 이상 텍스트 편집 대상은 아니지만,
        # 기존 텍스트와 같은 레이어의 이동 가능한 객체여야 한다.
        # QGraphicsItem 기본 이동이 draw/erase 도구와 섞일 때 불안정할 수 있어
        # rasterized_text만 별도 드래그 이동을 직접 처리한다.
        if getattr(self, '_is_rasterized_text', False) and event.button() == Qt.MouseButton.LeftButton:
            if self.scene() is not None:
                for item in self.scene().selectedItems():
                    if item is not self:
                        item.setSelected(False)
            self.setSelected(True)
            self._raster_drag_scene_press = QPointF(event.scenePos())
            self._raster_drag_item_press = QPointF(self.pos())
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

        if self.data.get('_skew_mode', False) and event.button() == Qt.MouseButton.LeftButton:
            action = self.skew_action_at(event.pos())
            if action:
                if self.begin_skew_action(action, event.pos(), event.scenePos()):
                    event.accept()
                    return
            self.setSelected(True)
            event.accept()
            return

        if self.data.get('_trapezoid_mode', False) and event.button() == Qt.MouseButton.LeftButton:
            action = self.trapezoid_action_at(event.pos())
            if action:
                if self.begin_trapezoid_action(action, event.pos(), event.scenePos()):
                    event.accept()
                    return
            self.setSelected(True)
            event.accept()
            return

        if self.data.get('_arc_mode', False) and event.button() == Qt.MouseButton.LeftButton:
            action = self.arc_action_at(event.pos())
            if not action:
                action = self.create_or_replace_arc_handle_at(event.pos())
            if action:
                if self.begin_arc_action(action, event.pos(), event.scenePos()):
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

            if getattr(self, '_is_rasterized_text', False) or self.data.get('rasterized_text'):
                # 객체화된 텍스트는 일반 이미지 객체로 취급한다.
                # 더블클릭해도 인라인 텍스트 편집으로 들어가지 않는다.
                event.accept()
                return

            if self.data.get('_skew_mode', False):
                action = self.skew_action_at(event.pos())
                if action:
                    current_pct = float(self.data.get('skew_x' if action in ('top', 'bottom') else 'skew_y', 0) or 0)
                    current_angle = math.degrees(math.atan(current_pct / 100.0))
                    angle, ok = QInputDialog.getDouble(None, "평행사변형 변형", "기울임 각도(도):", current_angle, -45.0, 45.0, 1)
                    if ok:
                        try:
                            if main is not None and hasattr(main, 'push_page_text_undo'):
                                main.push_page_text_undo('평행사변형 변형 각도 지정')
                        except Exception:
                            pass
                        self.set_text_skew_angle(action, angle)
                        try:
                            if main is not None:
                                main.auto_save_project()
                                main.mode_chg(4)
                                main.reselect_text_items([self.data.get('id')])
                                main.log(f"🔷 평행사변형 변형 각도 지정: {angle}°")
                        except Exception:
                            pass
                    event.accept()
                    return
                event.accept()
                return

            if self.data.get('_trapezoid_mode', False):
                action = self.trapezoid_action_at(event.pos())
                if action:
                    if action in ('top_left', 'bottom_left', 'left'):
                        side_key = 'trap_left'
                        side_name = '왼쪽'
                    elif action in ('top_right', 'bottom_right', 'right'):
                        side_key = 'trap_right'
                        side_name = '오른쪽'
                    elif action == 'top':
                        side_key = 'trap_top'
                        side_name = '위쪽'
                    else:
                        side_key = 'trap_bottom'
                        side_name = '아래쪽'
                    current_pct = float(self.data.get(side_key, 0) or 0)
                    value, ok = QInputDialog.getInt(None, '사다리꼴 변형', f'{side_name} 크기(%)', int(round(current_pct)), -95, 95, 1)
                    if ok:
                        try:
                            if main is not None and hasattr(main, 'push_page_text_undo'):
                                main.push_page_text_undo('사다리꼴 변형 수치 지정')
                        except Exception:
                            pass
                        if side_key == 'trap_left':
                            self.set_text_trapezoid_values(left_pct=value)
                        elif side_key == 'trap_right':
                            self.set_text_trapezoid_values(right_pct=value)
                        elif side_key == 'trap_top':
                            self.set_text_trapezoid_values(top_pct=value)
                        else:
                            self.set_text_trapezoid_values(bottom_pct=value)
                        try:
                            if main is not None:
                                main.auto_save_project()
                                main.mode_chg(4)
                                main.reselect_text_items([self.data.get('id')])
                                main.log(f"🔷 사다리꼴 변형 수치 지정: {side_name} {value}%")
                        except Exception:
                            pass
                    event.accept()
                    return
                event.accept()
                return

            if self.data.get('_arc_mode', False):
                action = self.arc_action_at(event.pos())
                if action:
                    idx = self._arc_index_from_action(action)
                    handles = self._arc_handles()
                    if 0 <= idx < len(handles):
                        handle = handles[idx]
                        side = str(handle.get('side') or '')
                        side_name = {'top':'위쪽','bottom':'아래쪽','left':'왼쪽','right':'오른쪽'}.get(side, side)
                        current_pct = float(handle.get('value', 0) or 0)
                        value, ok = QInputDialog.getInt(None, '부채꼴 변형', f'{side_name} 제어점 휘어짐(%)', int(round(current_pct)), -100, 100, 1)
                        if ok:
                            try:
                                if main is not None and hasattr(main, 'push_page_text_undo'):
                                    main.push_page_text_undo('부채꼴 변형 수치 지정')
                            except Exception:
                                pass
                            self.set_text_arc_handle_value(idx, value)
                            try:
                                if main is not None:
                                    main.auto_save_project()
                                    main.mode_chg(4)
                                    main.reselect_text_items([self.data.get('id')])
                                    main.log(f"🔷 부채꼴 변형 수치 지정: {side_name} 제어점 {value}%")
                            except Exception:
                                pass
                    event.accept()
                    return
                event.accept()
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
        if (
            getattr(self, '_is_rasterized_text', False)
            and getattr(self, '_raster_drag_scene_press', None) is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            try:
                delta = QPointF(event.scenePos()) - QPointF(self._raster_drag_scene_press)
                self.setPos(QPointF(self._raster_drag_item_press) + delta)
                self.update()
                event.accept()
                return
            except Exception:
                pass

        if self._transform_action:
            self.update_transform_action(event.pos(), event.scenePos())
            event.accept()
            return
        if self._skew_action:
            self.update_skew_action(event.pos(), event.scenePos())
            event.accept()
            return
        if self._trapezoid_action:
            self.update_trapezoid_action(event.pos(), event.scenePos())
            event.accept()
            return
        if self._arc_action:
            self.update_arc_action(event.pos(), event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._transform_action:
            self.finish_transform_action()
            event.accept()
            return
        if self._skew_action:
            self.finish_skew_action()
            event.accept()
            return
        if self._trapezoid_action:
            self.finish_trapezoid_action()
            event.accept()
            return
        if self._arc_action:
            self.finish_arc_action()
            event.accept()
            return

        if getattr(self, '_ctrl_select_press', False):
            self._ctrl_select_press = False
            event.accept()
            return

        raster_drag_active = getattr(self, '_raster_drag_scene_press', None) is not None
        self._raster_drag_scene_press = None
        self._raster_drag_item_press = None

        # rasterized_text는 위에서 직접 이동했으므로 base mouseRelease가 없어도 된다.
        # 일반 텍스트는 기존 흐름을 유지한다.
        if not raster_drag_active:
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
            if getattr(self, '_is_rasterized_text', False) or self.data.get('rasterized_text'):
                # 객체화 텍스트는 rect 자체가 래스터 이미지의 좌상단 기준이다.
                # align/글자 bounds 보정 없이 위치 차이만 저장해야 이동 후 다시 박혀 보이지 않는다.
                new_x_off = int(round(float(new_pos.x()) - rect_x))
                new_y_off = int(round(float(new_pos.y()) - rect_y))
            elif align == 'left':
                new_x_off = int(round(float(new_pos.x()) + float(path_rect.left()) - rect_x))
                new_y_off = int(round(float(new_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
            elif align == 'right':
                new_x_off = int(round(float(new_pos.x()) + float(path_rect.right()) - (rect_x + rect_w)))
                new_y_off = int(round(float(new_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
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


    def erase_raster_line_scene(self, scene_start, scene_end, brush_size=25):
        if not getattr(self, '_is_rasterized_text', False):
            return False
        if getattr(self, '_raster_image', None) is None or self._raster_image.isNull():
            return False
        try:
            local_start = self.mapFromScene(QPointF(scene_start))
            local_end = self.mapFromScene(QPointF(scene_end))
        except Exception:
            return False
        width = max(1.0, float(brush_size or 1))
        hit_rect = QRectF(local_start, local_end).normalized().adjusted(-width, -width, width, width)
        if not self._raster_rect.intersects(hit_rect):
            return False
        p = QPainter(self._raster_image)
        try:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor(0, 0, 0, 0), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawLine(local_start, local_end)
            if abs(local_start.x() - local_end.x()) < 0.5 and abs(local_start.y() - local_end.y()) < 0.5:
                p.drawPoint(local_start)
        finally:
            p.end()
        self.data['raster_png'] = _image_to_base64_png(self._raster_image)
        self.data['raster_w'] = self._raster_image.width()
        self.data['raster_h'] = self._raster_image.height()
        self.update()
        return True


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
