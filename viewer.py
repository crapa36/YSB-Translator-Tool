import copy
import numpy as np
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QImage, QPixmap, QFont, QPainterPath
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
        self.final_paint_item = None
        self.final_paint_above_item = None
        self.final_paint_img = None
        self.final_paint_above_img = None
        self.last_pt = None
        self.brush_size = 25
        self.mask_color = QColor(255, 0, 0, 100)
        self.history = []
        self.is_mask_painting = False
        self.magic_preview_items = []
        self.paste_preview_items = []
        self._active_transform_item = None

    def _active_transform_item_obj(self):
        active = self.main.current_transform_data_item() if hasattr(self.main, 'current_transform_data_item') else None
        if active is None:
            return None
        active_id = active.get('id')
        for item in self.scene.items():
            if isinstance(item, TypesettingItem) and not getattr(item, "is_paste_preview", False):
                if item.data is active or item.data.get('id') == active_id:
                    return item
        return None

    def _scene_text_item_at(self, scene_pos):
        active_item = self._active_transform_item_obj()
        if active_item is not None:
            try:
                local = active_item.mapFromScene(scene_pos)
                if active_item.transform_action_at(local) or active_item.shape().contains(local):
                    return active_item
            except Exception:
                pass
        for item in self.scene.items(scene_pos):
            if isinstance(item, TypesettingItem) and not getattr(item, "is_paste_preview", False):
                return item
        return None

    def _cursor_for_transform_action(self, action):
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

    def undo(self):
        if not self.history:
            self.main.log("⚠️ 실행 취소할 내역이 없습니다.")
            return

        record = self.history.pop()
        if isinstance(record, tuple) and len(record) == 2:
            target_item, last_pixmap = record
        else:
            target_item = None
            last_pixmap = record

        if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
            if target_item is not None:
                target_item.setPixmap(last_pixmap)
                if target_item is self.final_paint_above_item:
                    self.final_paint_above_img = last_pixmap.toImage()
                elif target_item is self.final_paint_item:
                    self.final_paint_img = last_pixmap.toImage()
                self.main.log("↩️ 최종 페인팅 실행 취소됨")
                self.main.on_final_paint_edited()
                return

        if target_item is not None:
            target_item.setPixmap(last_pixmap)
            if target_item is self.user_mask_item:
                self.user_mask_img = last_pixmap.toImage()
                self.main.log("↩️ 실행 취소됨")
                self.main.on_view_mask_edited()
            return

        if self.user_mask_item:
            self.user_mask_img = last_pixmap.toImage()
            self.user_mask_item.setPixmap(last_pixmap)
            self.main.log("↩️ 실행 취소됨")
            self.main.on_view_mask_edited()


    def set_image(self, img, fit=True):
        self.scene.clear()
        self.user_mask_item = None
        self.final_paint_item = None
        self.final_paint_above_item = None
        self.final_paint_img = None
        self.final_paint_above_img = None
        self.magic_preview_items = []
        self.clear_paste_preview()
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
        if fit:
            self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_overlay(self, bg, mask, color, fit=True):
        self.scene.clear()
        self.magic_preview_items = []
        self.paste_preview_items = []
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
        if fit:
            self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _paint_qimage_from_data(self, paint_data, w, h):
        qimg = QImage(w, h, QImage.Format.Format_ARGB32)
        qimg.fill(Qt.GlobalColor.transparent)

        if paint_data is None:
            return qimg

        try:
            if isinstance(paint_data, (bytes, bytearray)):
                loaded = QImage.fromData(bytes(paint_data))
                if not loaded.isNull():
                    qimg = loaded.convertToFormat(QImage.Format.Format_ARGB32)
            elif isinstance(paint_data, QImage):
                qimg = paint_data.convertToFormat(QImage.Format.Format_ARGB32)
            elif isinstance(paint_data, np.ndarray):
                arr = paint_data
                if arr.ndim == 3 and arr.shape[2] == 4:
                    h2, w2 = arr.shape[:2]
                    qimg = QImage(arr.data, w2, h2, 4 * w2, QImage.Format.Format_RGBA8888).copy()
                elif arr.ndim == 3 and arr.shape[2] == 3:
                    h2, w2 = arr.shape[:2]
                    qimg = QImage(arr.data, w2, h2, 3 * w2, QImage.Format.Format_RGB888).copy().convertToFormat(QImage.Format.Format_ARGB32)
            if qimg.width() != w or qimg.height() != h:
                qimg = qimg.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        except Exception:
            qimg = QImage(w, h, QImage.Format.Format_ARGB32)
            qimg.fill(Qt.GlobalColor.transparent)

        return qimg

    def set_final_paint_overlay(self, paint_data=None, paint_above_data=None, fit=False):
        """최종화면용 투명 페인팅 레이어를 만든다.
        아래 레이어는 텍스트보다 아래, 위 레이어는 텍스트보다 위에 고정된다.
        토글은 기존 레이어 순서를 바꾸지 않고, 새 붓질이 들어갈 레이어만 선택한다.
        """
        rect = self.scene.sceneRect()
        w = int(rect.width())
        h = int(rect.height())
        if w <= 0 or h <= 0:
            return

        below_qimg = self._paint_qimage_from_data(paint_data, w, h)
        above_qimg = self._paint_qimage_from_data(paint_above_data, w, h)

        self.final_paint_img = below_qimg
        self.final_paint_item = self.scene.addPixmap(QPixmap.fromImage(below_qimg))
        self.final_paint_item.setZValue(8)

        self.final_paint_above_img = above_qimg
        self.final_paint_above_item = self.scene.addPixmap(QPixmap.fromImage(above_qimg))
        self.final_paint_above_item.setZValue(80)

    def get_final_paint_layer_png_bytes(self, above=False):
        item = self.final_paint_above_item if above else self.final_paint_item
        if not item:
            return None
        qimg = item.pixmap().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        # 완전 투명 레이어면 저장하지 않는다.
        w, h = qimg.width(), qimg.height()
        ptr = qimg.bits()
        ptr.setsize(qimg.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, qimg.bytesPerLine() // 4, 4))
        alpha = arr[:, :w, 3]
        if not np.any(alpha > 0):
            return None

        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")
        return bytes(ba)

    def get_final_paint_png_bytes(self):
        return self.get_final_paint_layer_png_bytes(False)

    def get_final_paint_above_png_bytes(self):
        return self.get_final_paint_layer_png_bytes(True)


    def draw_static_boxes(self, data):
        base_w = int(getattr(self.main, "analysis_number_box_width", 40) or 40)
        font_size = max(8, int(base_w * 0.40))
        font = QFont("Arial", font_size, QFont.Weight.Bold)

        visible_items = [d for d in data]
        total_items = len(visible_items)
        for order_idx, d in enumerate(visible_items):
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
            base_w = int(getattr(self.main, "analysis_number_box_width", 40) or 40)
            bg_w = max(20, base_w + (len(id_str) - 1) * max(8, int(base_w * 0.4)))
            bg_h = max(18, int(base_w * 0.9))

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

    def draw_movable_texts(
        self,
        data,
        font,
        size_px,
        stroke,
        show_text=True,
        text_color="#000000",
        stroke_color="#FFFFFF",
        align="center",
    ):
        if not show_text:
            return

        visible_items = []
        for d in data:
            if not d.get('use_inpaint', True):
                continue
            if not str(d.get('translated_text', '') or '').strip() and not d.get('force_show'):
                continue
            visible_items.append(d)

        total_items = len(visible_items)
        for order_idx, d in enumerate(visible_items):
            item = TypesettingItem(
                d,
                font,
                size_px,
                stroke,
                self.main.on_text_item_moved,
                text_color=text_color,
                stroke_color=stroke_color,
                align=align,
            )
            item.main_window = self.main
            # 번호가 빠른 텍스트가 겹칠 때 위에 보이도록 역순 z값을 준다.
            item.setZValue(30 + (total_items - order_idx))
            self.scene.addItem(item)

    def clear_magic_wand_preview(self):
        if not hasattr(self, "magic_preview_items"):
            self.magic_preview_items = []
        for item in list(self.magic_preview_items):
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.magic_preview_items = []

    def draw_magic_wand_preview(self, mask):
        self.clear_magic_wand_preview()
        if mask is None:
            return

        import cv2
        _, bin_mask = cv2.threshold(mask, 10, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        pen = QPen(QColor(255, 230, 0), 2, Qt.PenStyle.SolidLine)
        brush = QBrush(Qt.BrushStyle.NoBrush)

        for cnt in contours:
            if cnt is None or len(cnt) < 2:
                continue

            path = QPainterPath()
            first = cnt[0][0]
            path.moveTo(float(first[0]), float(first[1]))

            for p in cnt[1:]:
                x, y = p[0]
                path.lineTo(float(x), float(y))

            path.closeSubpath()
            item = self.scene.addPath(path, pen, brush)
            item.setZValue(35)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.magic_preview_items.append(item)

    def set_user_mask_np(self, mask, color):
        if self.user_mask_item is None or mask is None:
            return

        if mask.ndim == 3:
            import cv2
            mask = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY)

        h, w = mask.shape[:2]
        color_img = QImage(w, h, QImage.Format.Format_ARGB32)
        color_img.fill(color)

        qmask = QImage(mask.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        color_img.setAlphaChannel(qmask)

        pix = QPixmap.fromImage(color_img)
        self.user_mask_item.setPixmap(pix)
        self.user_mask_img = color_img

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

    def clear_paste_preview(self):
        if not hasattr(self, "paste_preview_items"):
            self.paste_preview_items = []
        for item in list(self.paste_preview_items):
            try:
                if item.scene() is not None:
                    self.scene.removeItem(item)
            except Exception:
                pass
        self.paste_preview_items = []

    def show_paste_preview(self, data_items, scene_pos):
        """Ctrl+V 후 실제 붙여넣기 전, 커서 위치에 반투명 미리보기만 표시한다."""
        self.clear_paste_preview()

        if not data_items:
            return

        try:
            px, py = float(scene_pos.x()), float(scene_pos.y())
        except Exception:
            px, py = 0.0, 0.0

        src_items = [copy.deepcopy(d) for d in (data_items or []) if isinstance(d, dict)]
        if not src_items:
            return

        first = src_items[0].get('rect') or [0, 0, 1, 1]
        try:
            base_x = float(first[0]) + float(src_items[0].get('x_off', 0) or 0)
            base_y = float(first[1]) + float(src_items[0].get('y_off', 0) or 0)
        except Exception:
            base_x, base_y = 0.0, 0.0

        for d in src_items:
            rect = list(d.get('rect') or [0, 0, 260, 80])
            while len(rect) < 4:
                rect.append(1)

            try:
                old_x = float(rect[0]) + float(d.get('x_off', 0) or 0)
                old_y = float(rect[1]) + float(d.get('y_off', 0) or 0)
                dx = old_x - base_x
                dy = old_y - base_y
                rect[0] = int(round(px + dx))
                rect[1] = int(round(py + dy))
            except Exception:
                rect[0] = int(round(px))
                rect[1] = int(round(py))

            d['rect'] = [int(rect[0]), int(rect[1]), max(1, int(rect[2])), max(1, int(rect[3]))]
            d['x_off'] = 0
            d['y_off'] = 0
            d['manual_text_rect'] = True
            d['_paste_preview'] = True

            item = TypesettingItem(
                d,
                self.main.cb_font.currentFont().family(),
                self.main.sb_font_size.value(),
                self.main.sb_strk.value(),
                None,
                text_color=getattr(self.main, "default_text_color", "#000000"),
                stroke_color=getattr(self.main, "default_stroke_color", "#FFFFFF"),
                align=getattr(self.main, "default_align", "center"),
            )
            item.main_window = self.main
            item.is_paste_preview = True
            item.setOpacity(0.55)
            item.setZValue(95)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            try:
                item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, False)
                item.setFlag(item.GraphicsItemFlag.ItemIsMovable, False)
            except Exception:
                pass

            self.scene.addItem(item)
            self.paste_preview_items.append(item)

    def contextMenuEvent(self, e):
        if (
            getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
        ):
            scene_pos = self.mapToScene(e.pos())
            clicked = self.itemAt(e.pos())

            # 위쪽 페인팅 레이어/픽스맵 등이 itemAt으로 잡혀도,
            # 같은 위치의 텍스트 객체를 우선 찾는다.
            text_item = clicked if isinstance(clicked, TypesettingItem) and not getattr(clicked, "is_paste_preview", False) else None
            if text_item is None:
                for item in self.scene.items(scene_pos):
                    if isinstance(item, TypesettingItem) and not getattr(item, "is_paste_preview", False):
                        text_item = item
                        break

            if text_item is not None:
                self.main.show_final_text_context_menu(text_item, e.globalPos(), scene_pos)
            else:
                self.main.show_final_background_context_menu(e.globalPos(), scene_pos)

            e.accept()
            return

        super().contextMenuEvent(e)

    def mousePressEvent(self, e):
        if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
            active_transform = self.main.current_transform_data_item() if hasattr(self.main, 'current_transform_data_item') else None
            if active_transform is not None:
                pt = self.mapToScene(e.pos())
                active_item = self._active_transform_item_obj()
                hit_item = self._scene_text_item_at(pt)
                active_id = active_transform.get('id')

                # 핸들/테두리/회전 핸들이 QGraphicsView 기본 hit-test에 안 잡히는 경우를 직접 처리한다.
                if active_item is not None and e.button() == Qt.MouseButton.LeftButton:
                    local = active_item.mapFromScene(pt)
                    action = active_item.transform_action_at(local)

                    if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                        if active_item.transform_rect().adjusted(-10, -10, 10, 10).contains(local):
                            action = 'move'

                    if action:
                        if active_item.begin_transform_action(action, local, pt):
                            self._active_transform_item = active_item
                            self.setCursor(self._cursor_for_transform_action(action))
                            e.accept()
                            return

                if (
                    e.button() == Qt.MouseButton.LeftButton
                    and not (e.modifiers() & Qt.KeyboardModifier.AltModifier)
                ):
                    if hit_item is None or hit_item.data.get('id') != active_id:
                        self.main.end_active_text_transform(refresh=True)
                        e.accept()
                        return

        if (
            e.button() == Qt.MouseButton.LeftButton
            and getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
            and e.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            pt = self.mapToScene(e.pos())
            self.main.pick_final_paint_color_from_scene(int(pt.x()), int(pt.y()))
            return

        if self.draw_mode == 'paste_text' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
                pt = self.mapToScene(e.pos())
                self.main.finish_text_paste_at(pt)
                return

        if self.draw_mode == 'final_text' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
                # 텍스트 작성 중에는 새 텍스트 박스를 또 만들지 않는다.
                # 편집기 내부 클릭은 커서 이동으로 넘기고, 편집기 밖 클릭은 현재 텍스트 작성 완료만 한다.
                editor = getattr(self.main, "inline_text_editor", None)
                if editor is not None:
                    clicked = self.itemAt(e.pos())
                    if clicked is editor:
                        super().mousePressEvent(e)
                    else:
                        self.main.finish_inline_text_edit(commit=True, refresh=True)
                    return

                pt = self.mapToScene(e.pos())
                self.main.create_final_text_at(int(pt.x()), int(pt.y()))
                return

        if self.draw_mode == 'magic_wand' and e.button() == Qt.MouseButton.LeftButton:
            pt = self.mapToScene(e.pos())
            self.main.magic_wand_pick(int(pt.x()), int(pt.y()))
            return

        if self.draw_mode and e.button() == Qt.MouseButton.LeftButton:
            self.is_mask_painting = True
            final_mode = (
                getattr(self.main, "cb_mode", None) is not None
                and self.main.cb_mode.currentIndex() == 4
                and self.draw_mode in ('draw', 'erase')
            )
            if final_mode:
                target_item = self.final_paint_above_item if getattr(self.main, "final_paint_above_text", False) else self.final_paint_item
            else:
                target_item = self.user_mask_item

            if target_item:
                self.history.append((target_item, target_item.pixmap().copy()))
                if len(self.history) > 20:
                    self.history.pop(0)
            self.last_pt = self.mapToScene(e.pos())
            return
        elif (
            e.button() == Qt.MouseButton.LeftButton
            and getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
        ):
            # 최종 화면에서는 배경 클릭으로 기존 텍스트 선택을 지우지 않는다.
            # 단, 배경을 누른 채 드래그하면 이미지 이동은 되어야 하므로 super()는 통과시킨다.
            clicked = self.itemAt(e.pos())
            if not isinstance(clicked, TypesettingItem):
                selected = [x for x in self.scene.selectedItems() if isinstance(x, TypesettingItem)]
                self.scene.blockSignals(True)
                try:
                    super().mousePressEvent(e)
                    for item in selected:
                        item.setSelected(True)
                finally:
                    self.scene.blockSignals(False)
                if selected:
                    self.main.on_scene_selection_changed()
                return

        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._active_transform_item is not None:
            item = self._active_transform_item
            pt = self.mapToScene(e.pos())
            try:
                item.update_transform_action(item.mapFromScene(pt), pt)
                self.setCursor(self._cursor_for_transform_action(getattr(item, '_transform_action', None)))
            except Exception:
                pass
            e.accept()
            return

        if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
            active_item = self._active_transform_item_obj()
            if active_item is not None and active_item.data.get('_transform_mode', False):
                pt = self.mapToScene(e.pos())
                local = active_item.mapFromScene(pt)
                action = active_item.transform_action_at(local)
                if e.modifiers() & Qt.KeyboardModifier.AltModifier and active_item.transform_rect().adjusted(-10, -10, 10, 10).contains(local):
                    action = 'move'
                if action:
                    self.setCursor(self._cursor_for_transform_action(action))
                else:
                    self.unsetCursor()

        if (
            self.draw_mode == 'paste_text'
            and getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
        ):
            self.show_paste_preview(getattr(self.main, "text_clipboard", []), self.mapToScene(e.pos()))
            return

        if self.draw_mode in ('draw', 'erase') and self.last_pt:
            final_mode = getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4
            if final_mode:
                target_item = self.final_paint_above_item if getattr(self.main, "final_paint_above_text", False) else self.final_paint_item
            else:
                target_item = self.user_mask_item
            if target_item:
                now = self.mapToScene(e.pos())
                pix = target_item.pixmap()
                p = QPainter(pix)
                if self.draw_mode == 'draw':
                    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                    if final_mode:
                        color = QColor(str(getattr(self.main, "final_paint_color", "#FFFFFF") or "#FFFFFF"))
                        if not color.isValid():
                            color = QColor("#FFFFFF")
                        opacity = max(1, min(100, int(getattr(self.main, "final_paint_opacity", 100) or 100)))
                        color.setAlpha(int(round(255 * opacity / 100)))
                    else:
                        idx = self.main.cb_mode.currentIndex()
                        color = QColor(0, 0, 255, 150) if idx == 3 else QColor(255, 0, 0, 150)
                else:
                    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                    color = Qt.GlobalColor.transparent
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.setPen(QPen(color, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(self.last_pt, now)
                p.end()
                target_item.setPixmap(pix)
                self.last_pt = now
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._active_transform_item is not None:
            try:
                self._active_transform_item.finish_transform_action()
            except Exception:
                pass
            self._active_transform_item = None
            self.unsetCursor()
            e.accept()
            return

        was_painting = self.is_mask_painting
        self.is_mask_painting = False
        self.last_pt = None

        if was_painting:
            if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
                self.main.on_final_paint_edited()
            elif self.user_mask_item:
                self.main.on_view_mask_edited()

        super().mouseReleaseEvent(e)
        

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.25 if e.angleDelta().y() > 0 else 0.8
            self.scale(factor, factor)
        else:
            super().wheelEvent(e)
