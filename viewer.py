import numpy as np
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QImage, QPixmap, QFont
from PyQt6.QtCore import Qt, QRectF

from graphics_items import ToggleBoxItem, TypesettingItem


class MuleImageViewer(QGraphicsView):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

        self.draw_mode = None
        self.user_mask_item = None
        self.user_mask_img = None
        self.last_pt = None
        self.brush_size = 25
        self.mask_color = QColor(255, 0, 0, 100)
        self.history = []
        self.is_mask_painting = False

    def undo(self):
        if not self.history:
            self.main.log("⚠️ 실행 취소할 내역이 없습니다.")
            return

        last_pixmap = self.history.pop()
        self.user_mask_img = last_pixmap.toImage()
        self.user_mask_item.setPixmap(last_pixmap)
        self.main.log("↩️ 실행 취소됨")

        self.main.on_view_mask_edited()

    def set_image(self, img):
        self.scene.clear()
        self.user_mask_item = None
        self.history.clear()
        if img is None:
            return

        if isinstance(img, bytes):
            q_img = QImage.fromData(img)
        else:
            q_img = self._np2pix(img).toImage()

        pix = QPixmap.fromImage(q_img)
        self.scene.addPixmap(pix)
        self.scene.setSceneRect(QRectF(pix.rect()))
        self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_overlay(self, bg, mask, color):
        self.scene.clear()
        if bg is None:
            return

        bg_pix = self._np2pix(bg)
        bg_item = self.scene.addPixmap(bg_pix)
        bg_item.setZValue(0)

        w, h = bg.shape[1], bg.shape[0]
        self.user_mask_img = QImage(w, h, QImage.Format.Format_ARGB32)
        self.user_mask_img.fill(Qt.GlobalColor.transparent)

        if mask is not None:
            m_qimg = self._np2pix(mask).toImage().convertToFormat(QImage.Format.Format_Grayscale8)
            target_color_img = QImage(w, h, QImage.Format.Format_ARGB32)
            target_color_img.fill(color)
            target_color_img.setAlphaChannel(m_qimg)

            p = QPainter(self.user_mask_img)
            p.drawImage(0, 0, target_color_img)
            p.end()

        self.user_mask_item = self.scene.addPixmap(QPixmap.fromImage(self.user_mask_img))
        self.user_mask_item.setZValue(10)

        self.scene.setSceneRect(QRectF(bg_pix.rect()))
        self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def draw_static_boxes(self, data):
        font = QFont("Arial", 16, QFont.Weight.Bold)

        for d in data:
            is_active = d.get('use_inpaint', True)
            x, y, w, h = d['rect']

            pen_box = QPen(QColor(255, 0, 0), 2) if is_active else QPen(QColor(150, 150, 150), 2, Qt.PenStyle.DotLine)

            rect_item = ToggleBoxItem(
                [x, y, w, h],
                d,
                self.main,
                pen_box,
                brush=QBrush(Qt.BrushStyle.NoBrush),
                z_value=20,
            )
            self.scene.addItem(rect_item)

            id_str = str(d.get('id', ''))
            bg_w = 40 + (len(id_str) - 1) * 16
            bg_h = 36

            bx, by = x, y - bg_h
            if by < 0:
                by = y

            if is_active:
                brush_bg = QBrush(QColor(255, 215, 0))
                text_color = Qt.GlobalColor.black
            else:
                brush_bg = QBrush(QColor(100, 100, 100))
                text_color = Qt.GlobalColor.white

            handle_item = ToggleBoxItem(
                [bx, by, bg_w, bg_h],
                d,
                self.main,
                QPen(Qt.PenStyle.NoPen),
                brush=brush_bg,
                z_value=21,
            )
            self.scene.addItem(handle_item)

            t_item = self.scene.addText(id_str, font)
            t_item.setDefaultTextColor(text_color)
            br = t_item.boundingRect()
            t_item.setPos(bx + (bg_w - br.width()) / 2, by + (bg_h - br.height()) / 2)
            t_item.setZValue(22)
            t_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def draw_movable_texts(self, data, font, size_px, stroke):
        for d in data:
            if not d.get('use_inpaint', True):
                continue
            item = TypesettingItem(d, font, size_px, stroke, self.main.on_text_item_moved)
            self.scene.addItem(item)

    def get_mask_np(self):
        if not self.user_mask_item:
            return None

        # 화면 표시용 색상값이 아니라, ARGB32의 알파 채널을 직접 읽는다.
        # 그래야 페이지 이동/자동저장 반복 시 마스크가 연해지지 않는다.
        qimg = self.user_mask_item.pixmap().toImage().convertToFormat(
            QImage.Format.Format_ARGB32
        )

        w = qimg.width()
        h = qimg.height()
        bytes_per_line = qimg.bytesPerLine()

        ptr = qimg.bits()
        ptr.setsize(qimg.sizeInBytes())

        buf = np.frombuffer(ptr, dtype=np.uint8)

        # Format_ARGB32는 한 픽셀당 4바이트.
        # Windows/little-endian 환경에서는 메모리 순서가 B, G, R, A라서 3번 채널이 alpha.
        arr = buf.reshape((h, bytes_per_line // 4, 4))
        alpha = arr[:, :w, 3].copy()

        # 저장용 마스크는 반투명값을 그대로 저장하지 말고 0/255로 고정
        mask = np.where(alpha > 10, 255, 0).astype(np.uint8)

        return mask

    def _np2pix(self, np_img):
        if isinstance(np_img, QImage):
            return QPixmap.fromImage(np_img)
        if np_img.ndim == 2:
            h, w = np_img.shape
            q = QImage(np_img.data, w, h, w, QImage.Format.Format_Grayscale8)
            return QPixmap.fromImage(q)
        if np_img.ndim == 3:
            h, w, c = np_img.shape
            if c == 3:
                q = QImage(np_img.data, w, h, c * w, QImage.Format.Format_RGB888).rgbSwapped()
            elif c == 4:
                q = QImage(np_img.data, w, h, c * w, QImage.Format.Format_RGBA8888)
            else:
                return QPixmap()
            return QPixmap.fromImage(q)
        return QPixmap()

    def mousePressEvent(self, e):
        if self.draw_mode and e.button() == Qt.MouseButton.LeftButton:
            self.is_mask_painting = True
            if self.user_mask_item:
                self.history.append(self.user_mask_item.pixmap().copy())
                if len(self.history) > 20:
                    self.history.pop(0)
            self.last_pt = self.mapToScene(e.pos())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.draw_mode and self.last_pt and self.user_mask_item:
            now = self.mapToScene(e.pos())
            pix = self.user_mask_item.pixmap()
            p = QPainter(pix)
            if self.draw_mode == 'draw':
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                idx = self.main.cb_mode.currentIndex()
                color = QColor(0, 0, 255, 150) if idx == 3 else QColor(255, 0, 0, 150)
            else:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                color = Qt.GlobalColor.transparent
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(color, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(self.last_pt, now)
            p.end()
            self.user_mask_item.setPixmap(pix)
            self.last_pt = now
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        was_painting = self.is_mask_painting
        self.is_mask_painting = False
        self.last_pt = None

        if was_painting and self.user_mask_item:
            self.main.on_view_mask_edited()

        super().mouseReleaseEvent(e)
        

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.25 if e.angleDelta().y() > 0 else 0.8
            self.scale(factor, factor)
        else:
            super().wheelEvent(e)
