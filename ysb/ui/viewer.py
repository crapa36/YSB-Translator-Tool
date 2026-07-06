import copy
import math
import numpy as np
import cv2
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsTextItem, QInputDialog, QGraphicsPathItem, QGraphicsItem, QApplication
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QImage, QPixmap, QFont, QPainterPath, QCursor, QPainterPathStroker
from PyQt6.QtCore import Qt, QRect, QRectF, QTimer, QPointF
try:
    from PyQt6 import sip as _qt_sip
except Exception:
    _qt_sip = None

from ysb.engine.graphics_items import ToggleBoxItem, TypesettingItem
from ysb.core.brush_engine import PageBrushEngine


class MuleImageViewer(QGraphicsView):
    # 작업 화면 보조 UI 기준 해상도.
    # 현재 선/핸들 크기를 1086x1449 기준값으로 보고, 더 큰 이미지에서는 비례 확대한다.
    GUIDE_BASE_W = 1086.0
    GUIDE_BASE_H = 1449.0
    GUIDE_SCALE_MAX = 6.0

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
            self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
            # 텍스트/변형/Undo 복원은 정확한 전체 repaint가 우선이다.
            # MinimalViewportUpdate/CacheBackground는 일부 갱신 잔상을 만들 수 있어 정석 모드로 둔다.
            self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
            self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)
        except Exception:
            pass
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(QColor("#0B0C0E")))

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
        self._brush_cursor_preview_items = []
        self._brush_cursor_preview_scene_pos = None
        self._brush_cursor_preview_mode = None
        self._tool_cursor_cache = {}
        self._active_tool_cursor_key = None
        # Brush cursor preview is intentionally throttled/deferred.  Updating a
        # scene ellipse on every wheel/scroll repaint can make high-zoom
        # navigation feel sticky, so preview refresh is hidden only during active
        # view moves and coalesced during mouse motion.
        self._brush_cursor_preview_pending_scene_pos = None
        self._brush_cursor_preview_last_scene_pos = None
        self._brush_cursor_preview_suspended = False
        self._brush_cursor_preview_update_timer = QTimer(self)
        self._brush_cursor_preview_update_timer.setSingleShot(True)
        self._brush_cursor_preview_update_timer.timeout.connect(self._flush_brush_cursor_preview_request)
        self._brush_cursor_preview_resume_timer = QTimer(self)
        self._brush_cursor_preview_resume_timer.setSingleShot(True)
        self._brush_cursor_preview_resume_timer.timeout.connect(self._resume_brush_cursor_preview_after_suspend)
        self.history = []
        self.redo_history = []
        self.brush_engine = PageBrushEngine(self)
        try:
            if hasattr(self.main, "undo_bind_paint_viewer"):
                self.main.undo_bind_paint_viewer(self)
            elif hasattr(self.main, "get_undo_manager"):
                mgr = self.main.get_undo_manager()
                if mgr is not None:
                    mgr.bind_paint_viewer(self)
        except Exception:
            pass
        self._suppress_view_history = False
        self._scrollbar_view_undo_active = False
        # Scrollbar actions are page-local view operations.  They must be recorded
        # through the MainWindow/ViewEngine timeline, but never throw if the host
        # window is still booting or temporarily suppressing view history during
        # restore/Undo.
        try:
            self.horizontalScrollBar().actionTriggered.connect(lambda *_: self._begin_scroll_view_undo())
            self.verticalScrollBar().actionTriggered.connect(lambda *_: self._begin_scroll_view_undo())
            self.horizontalScrollBar().valueChanged.connect(lambda *_: self._schedule_scroll_view_undo_finish())
            self.verticalScrollBar().valueChanged.connect(lambda *_: self._schedule_scroll_view_undo_finish())
        except Exception:
            pass
        self.is_mask_painting = False
        self.magic_preview_items = []
        self.paste_preview_items = []
        # CAD 최종화면 텍스트 다중선택 런타임.
        # draw_mode=None 상태에서 배경 클릭으로 사각형/자유형 선택을 만들고,
        # 선택 변경은 작업 데이터가 아니라 UI 상태이므로 viewer-local undo stack으로 관리한다.
        self._cad_text_select_rect_start = None
        self._cad_text_select_rect_preview_item = None
        self._cad_text_select_path_points = []
        self._cad_text_select_path_preview_item = None
        self._cad_text_select_mouse_press_scene = None
        self._cad_text_select_mouse_press_view = None
        self._cad_text_select_mouse_shift = False
        self._cad_text_select_mode = None  # None | rect_pending | free_drag
        self._cad_text_selection_undo_stack = []
        self._cad_text_selection_undo_limit = 80
        self._cad_text_group_drag_items = []
        self._cad_text_group_drag_single_click_item = None
        self._cad_text_group_drag_collapse_on_click = False
        self._cad_text_group_drag_press_scene = None
        self._cad_text_group_drag_start_positions = {}
        self._cad_text_group_drag_started = False
        self._cad_text_group_drag_old_offsets = {}
        self._active_transform_item = None
        self._direct_text_drag_item = None
        self._direct_text_drag_scene_press = None
        self._direct_text_drag_item_press = None
        self._direct_text_drag_started = False
        self._direct_text_drag_old_xoff = 0
        self._direct_text_drag_old_yoff = 0
        self._direct_text_drag_before_geometry = None
        # Small pixmap cache for same-page tab switching.  Source/final bases are
        # expensive to convert repeatedly on large pages, so keep the latest few
        # keyed base pixmaps and reuse them while the page/content key matches.
        self._layer_base_pixmap_cache = {}
        self._layer_base_pixmap_cache_order = []
        # Hide-background helper items are owned by the current QGraphicsScene.
        # scene.clear() deletes them on the C++ side, so Python references must
        # be nulled before/after full scene rebuilds to avoid touching deleted
        # QGraphicsItem wrappers during batch page refresh.
        self._background_hidden_fill_item = None
        self._background_hidden_fade_item = None
        self._background_hidden_last_image_rect = None
        self._background_hidden_fade_cache_key = None
        self._view_pan_undo_key = None
        self._view_pan_start_state = None
        self._middle_pan_active = False
        self._middle_pan_last_pos = None
        self._paint_undo_key = None
        self._stroke_preview_item = None
        self._stroke_preview_items = []
        self._stroke_preview_path = None
        self._stroke_preview_paths = []
        self._stroke_preview_last_pos = None
        self._stroke_preview_segment_count = 0
        self._stroke_preview_target = None
        self._stroke_preview_final_mode = False
        self._stroke_preview_color = None
        self._stroke_preview_dirty_rect = None
        self.mask_wrap_shape = "rect"
        self.mask_wrap_start = None
        self.mask_wrap_points = []
        self.mask_wrap_checkpoint_indexes = []
        self.mask_wrap_preview_item = None
        self.is_mask_wrapping = False

        self.mask_cut_shape = "rect"
        self.mask_cut_start = None
        self.mask_cut_points = []
        self.mask_cut_checkpoint_indexes = []
        self.mask_cut_preview_item = None
        self.is_mask_cutting = False

        self.color_outline_mask_shape = "rect"
        self.color_outline_mask_start = None
        self.color_outline_mask_points = []
        self.color_outline_mask_checkpoint_indexes = []
        self.color_outline_mask_preview_item = None
        self.is_color_outline_masking = False

        self.ocr_region_shape = "rect"
        self.ocr_region_start = None
        self.ocr_region_points = []
        self.ocr_region_checkpoint_indexes = []
        self.ocr_region_preview_item = None
        self.ocr_region_overlay_items = []
        self.inpaint_group_preview_items = []
        self.is_ocr_region_drawing = False

        self.quick_ocr_start = None
        self.quick_ocr_preview_item = None
        self.is_quick_ocr_drawing = False
        self.quick_ocr_current_rect_norm = None
        self.quick_ocr_revision = 0
        self.quick_ocr_last_requested_revision = -1
        self.quick_ocr_hold_timer = QTimer(self)
        self.quick_ocr_hold_timer.setSingleShot(True)
        self.quick_ocr_hold_timer.timeout.connect(self._trigger_quick_ocr_if_still_holding)

        self.area_paint_shape = "rect"
        self.original_restore_shape = "rect"
        self.area_paint_start = None
        self.area_paint_points = []
        self.area_paint_checkpoint_indexes = []
        self.original_restore_points = []
        self.original_restore_checkpoint_indexes = []
        self.area_paint_preview_item = None
        self.original_restore_preview_item = None
        self.is_area_painting = False
        self._area_paint_undo_key = None

        self.raster_erase_start = None
        self.raster_erase_preview_item = None
        self.is_raster_erasing = False
        self.is_raster_text_brush_erasing = False

        # 객체화 텍스트는 페인팅 레이어/뷰 드래그 모드에 클릭이 막힐 수 있어
        # QGraphicsItem 이벤트에 맡기지 않고 View 레벨에서 직접 hit-test/드래그한다.
        self._raster_view_drag_item = None
        self._raster_view_drag_scene_press = None
        self._raster_view_drag_item_press = None
        self._raster_view_drag_old_offsets = None
        self._raster_view_drag_moved = False

        # VIEW_ZOOM_PAN_FASTPATH_FIX:
        # 확대/스크롤/팬 조작 중에는 고해상도 배경/오버레이를 매 프레임
        # 고품질로 다시 그리지 않도록 렌더 힌트와 viewport update mode를
        # 잠깐 가볍게 낮추고, 조작이 멈춘 뒤 원래 품질로 복원한다.
        self._view_interaction_fast_path_active = False
        self._view_interaction_fast_path_finish_pending = False
        self._view_interaction_fast_path_reason = None
        self._view_interaction_fast_path_old_hints = None
        self._view_interaction_fast_path_old_viewport_mode = None
        self._view_interaction_fast_path_old_cache_mode = None
        self._view_interaction_fast_path_timer = QTimer(self)
        self._view_interaction_fast_path_timer.setSingleShot(True)
        self._view_interaction_fast_path_timer.timeout.connect(self._finish_view_interaction_fast_path)
        try:
            self.horizontalScrollBar().valueChanged.connect(lambda *_: self._begin_view_interaction_fast_path('scroll', delay_ms=160))
            self.verticalScrollBar().valueChanged.connect(lambda *_: self._begin_view_interaction_fast_path('scroll', delay_ms=160))
        except Exception:
            pass
        try:
            self.sync_drag_mode_from_operation()
        except Exception:
            pass

    def current_operation_mode(self):
        try:
            return normalize_operation_mode(getattr(self.main, "operation_mode", DEFAULT_OPERATION_MODE))
        except Exception:
            v = str(getattr(self.main, "operation_mode", "paint") or "paint").lower()
            return "cad" if v == "cad" else "paint"

    def is_cad_operation_mode(self):
        return self.current_operation_mode() == "cad"

    def sync_drag_mode_from_operation(self):
        """Keep QGraphicsView drag behavior aligned with the global operation mode."""
        try:
            if getattr(self, "draw_mode", None):
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
            elif self.is_cad_operation_mode():
                # CAD 방식은 좌클릭 이동을 쓰지 않는다. 화면 이동은 휠 클릭 드래그 전용.
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
            else:
                # 그림판 방식은 이동 모드에서 좌클릭 드래그로 화면 이동.
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        except Exception:
            pass

    def _area_click_click_modes(self):
        return {
            "raster_erase",
            "area_paint",
            "original_restore",
            "ocr_region_select",
            "quick_ocr",
            "color_outline_mask",
            "mask_wrap",
            "mask_cut",
        }

    def _area_shape_for_mode(self, mode=None):
        try:
            mode = str(mode if mode is not None else getattr(self, "draw_mode", None) or "")
            attr = {
                "area_paint": "area_paint_shape",
                "original_restore": "original_restore_shape",
                "ocr_region_select": "ocr_region_shape",
                "color_outline_mask": "color_outline_mask_shape",
                "mask_wrap": "mask_wrap_shape",
                "mask_cut": "mask_cut_shape",
            }.get(mode)
            shape = str(getattr(self, attr, "rect") if attr else "rect").lower()
            return shape if shape in ("rect", "free", "polygon") else "rect"
        except Exception:
            return "rect"

    def _area_shape_points_attr(self, mode=None):
        mode = str(mode if mode is not None else getattr(self, "draw_mode", None) or "")
        return {
            "area_paint": "area_paint_points",
            "original_restore": "original_restore_points",
            "ocr_region_select": "ocr_region_points",
            "color_outline_mask": "color_outline_mask_points",
            "mask_wrap": "mask_wrap_points",
            "mask_cut": "mask_cut_points",
        }.get(mode)

    def _area_shape_checkpoints_attr(self, mode=None):
        mode = str(mode if mode is not None else getattr(self, "draw_mode", None) or "")
        return {
            "area_paint": "area_paint_checkpoint_indexes",
            "original_restore": "original_restore_checkpoint_indexes",
            "ocr_region_select": "ocr_region_checkpoint_indexes",
            "color_outline_mask": "color_outline_mask_checkpoint_indexes",
            "mask_wrap": "mask_wrap_checkpoint_indexes",
            "mask_cut": "mask_cut_checkpoint_indexes",
        }.get(mode)

    def _area_shape_start_attr(self, mode=None):
        mode = str(mode if mode is not None else getattr(self, "draw_mode", None) or "")
        return {
            "area_paint": "area_paint_start",
            "original_restore": "original_restore_start",
            "ocr_region_select": "ocr_region_start",
            "color_outline_mask": "color_outline_mask_start",
            "mask_wrap": "mask_wrap_start",
            "mask_cut": "mask_cut_start",
        }.get(mode)

    def _area_shape_active_attr(self, mode=None):
        mode = str(mode if mode is not None else getattr(self, "draw_mode", None) or "")
        return {
            "area_paint": "is_area_painting",
            "original_restore": "is_original_restoring",
            "ocr_region_select": "is_ocr_region_drawing",
            "color_outline_mask": "is_color_outline_masking",
            "mask_wrap": "is_mask_wrapping",
            "mask_cut": "is_mask_cutting",
        }.get(mode)

    def _draw_area_shape_preview_for_mode(self, mode, scene_pos):
        try:
            if mode == "area_paint":
                self._draw_area_paint_preview(scene_pos)
            elif mode == "original_restore":
                self._draw_original_restore_preview(scene_pos)
            elif mode == "ocr_region_select":
                self._draw_ocr_region_preview(scene_pos)
            elif mode == "color_outline_mask":
                self._draw_color_outline_mask_preview(scene_pos)
            elif mode == "mask_wrap":
                self._draw_mask_wrap_preview(scene_pos)
            elif mode == "mask_cut":
                self._draw_mask_cut_preview(scene_pos)
        except Exception:
            pass

    def _is_polygon_area_tool(self, mode=None):
        try:
            mode = str(mode if mode is not None else getattr(self, "draw_mode", None) or "")
            return mode in self._area_click_click_modes() and self._area_shape_for_mode(mode) == "polygon"
        except Exception:
            return False

    def _is_cad_free_area_tool(self, mode=None):
        """CAD 방식의 자유형 영역: 커서 이동 경로를 체크포인트 단위로 저장한다."""
        try:
            mode = str(mode if mode is not None else getattr(self, "draw_mode", None) or "")
            return self.is_cad_operation_mode() and mode in self._area_click_click_modes() and self._area_shape_for_mode(mode) == "free"
        except Exception:
            return False

    def _append_scene_point_if_moved(self, points, scene_pos, min_sq=9.0):
        pts = list(points or [])
        if scene_pos is None:
            return pts
        if not pts:
            return [scene_pos]
        try:
            last = pts[-1]
            dx = float(scene_pos.x() - last.x())
            dy = float(scene_pos.y() - last.y())
            if (dx * dx + dy * dy) >= float(min_sq):
                pts.append(scene_pos)
        except Exception:
            pts.append(scene_pos)
        return pts

    def _set_cad_free_checkpoints(self, mode, checkpoints):
        ck_attr = self._area_shape_checkpoints_attr(mode)
        if ck_attr:
            try:
                setattr(self, ck_attr, list(checkpoints or []))
            except Exception:
                pass

    def _clear_cad_free_checkpoints(self, mode):
        self._set_cad_free_checkpoints(mode, [])

    def _area_path_preview_should_close(self, mode, points, now):
        shape = self._area_shape_for_mode(mode)
        if shape == "polygon" or (shape == "free" and self._is_cad_free_area_tool(mode)):
            return self._polygon_preview_should_close(points, now)
        return False

    def _polygon_close_threshold_sq(self):
        try:
            v = float(self.ui_handle_size(11.0, minimum=8.0))
        except Exception:
            v = 11.0
        return v * v

    def _polygon_click_closes(self, points, scene_pos):
        try:
            if len(points or []) < 3 or scene_pos is None:
                return False
            first = points[0]
            dx = float(scene_pos.x() - first.x())
            dy = float(scene_pos.y() - first.y())
            return (dx * dx + dy * dy) <= self._polygon_close_threshold_sq()
        except Exception:
            return False

    def is_click_click_area_tool(self, mode=None):
        try:
            if mode is None:
                mode = getattr(self, "draw_mode", None)
            if self._area_shape_for_mode(mode) in ("polygon", "free"):
                return False
            return self.is_cad_operation_mode() and str(mode or "") in self._area_click_click_modes()
        except Exception:
            return False

    def _is_any_click_click_area_active(self):
        return bool(
            getattr(self, "is_raster_erasing", False)
            or getattr(self, "is_area_painting", False)
            or getattr(self, "is_original_restoring", False)
            or getattr(self, "is_ocr_region_drawing", False)
            or getattr(self, "is_quick_ocr_drawing", False)
            or getattr(self, "is_color_outline_masking", False)
            or getattr(self, "is_mask_wrapping", False)
            or getattr(self, "is_mask_cutting", False)
        )

    def cancel_click_click_area_interaction(self, *, clear_tool=False):
        """Cancel a pending CAD-style first-point area operation without applying it."""
        had_active = self._is_any_click_click_area_active()
        try:
            self.is_raster_erasing = False
            self.raster_erase_start = None
            self.clear_raster_erase_preview()
        except Exception:
            pass
        try:
            self.is_area_painting = False
            self.area_paint_start = None
            self.area_paint_points = []
            self.area_paint_checkpoint_indexes = []
            self._area_paint_undo_key = None
            self.clear_area_paint_preview()
        except Exception:
            pass
        try:
            self.is_original_restoring = False
            self.original_restore_start = None
            self.original_restore_points = []
            self.original_restore_checkpoint_indexes = []
            self.clear_original_restore_preview()
        except Exception:
            pass
        try:
            self.is_ocr_region_drawing = False
            self.ocr_region_start = None
            self.ocr_region_points = []
            self.ocr_region_checkpoint_indexes = []
            self.clear_ocr_region_preview()
        except Exception:
            pass
        try:
            self.is_quick_ocr_drawing = False
            self.quick_ocr_start = None
            self.quick_ocr_current_rect_norm = None
            self.quick_ocr_hold_timer.stop()
            self.clear_quick_ocr_preview()
            if had_active and hasattr(self.main, "cancel_quick_ocr_drag"):
                self.main.cancel_quick_ocr_drag()
        except Exception:
            pass
        try:
            self.is_color_outline_masking = False
            self.color_outline_mask_start = None
            self.color_outline_mask_points = []
            self.color_outline_mask_checkpoint_indexes = []
            self.clear_color_outline_mask_preview()
        except Exception:
            pass
        try:
            self.is_mask_wrapping = False
            self.mask_wrap_start = None
            self.mask_wrap_points = []
            self.mask_wrap_checkpoint_indexes = []
            self.clear_mask_wrap_preview()
        except Exception:
            pass
        try:
            self.is_mask_cutting = False
            self.mask_cut_start = None
            self.mask_cut_points = []
            self.mask_cut_checkpoint_indexes = []
            self.clear_mask_cut_preview()
        except Exception:
            pass
        if clear_tool:
            try:
                self.draw_mode = None
                self.sync_drag_mode_from_operation()
                self.force_tool_cursor_refresh(delay_followups=True)
            except Exception:
                pass
        return had_active

    def _start_click_click_area_tool_at(self, scene_pos, event):
        """Start CAD-style area input at the first clicked point."""
        mode = getattr(self, "draw_mode", None)
        if mode == "raster_erase":
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() != 4:
                return True
            self.is_raster_erasing = True
            self.raster_erase_start = scene_pos
            self._draw_raster_erase_preview(scene_pos)
            return True
        if mode == "area_paint":
            tab_mode = self.main.cb_mode.currentIndex() if getattr(self.main, "cb_mode", None) is not None else 4
            if tab_mode not in (2, 3, 4):
                return True
            self.is_area_painting = True
            self.area_paint_start = scene_pos
            self.area_paint_points = [scene_pos]
            self._area_paint_undo_key = None
            self._draw_area_paint_preview(scene_pos)
            return True
        if mode == "original_restore":
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() != 4:
                return True
            self.is_original_restoring = True
            self.original_restore_start = scene_pos
            self.original_restore_points = [scene_pos]
            self._draw_original_restore_preview(scene_pos)
            return True
        if mode == "ocr_region_select":
            self.is_ocr_region_drawing = True
            self.ocr_region_start = scene_pos
            self.ocr_region_points = [scene_pos]
            self._draw_ocr_region_preview(scene_pos)
            return True
        if mode == "quick_ocr":
            self.is_quick_ocr_drawing = True
            self.quick_ocr_start = scene_pos
            self.quick_ocr_current_rect_norm = None
            self.quick_ocr_revision += 1
            self.quick_ocr_last_requested_revision = -1
            try:
                self.quick_ocr_hold_timer.stop()
            except Exception:
                pass
            if hasattr(self.main, "begin_quick_ocr_drag"):
                self.main.begin_quick_ocr_drag()
            self._draw_quick_ocr_preview(scene_pos)
            return True
        if mode == "color_outline_mask":
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() not in (2, 3):
                return True
            if event is not None and event.modifiers() & Qt.KeyboardModifier.AltModifier:
                if hasattr(self.main, "pick_color_outline_mask_from_scene"):
                    self.main.pick_color_outline_mask_from_scene(int(scene_pos.x()), int(scene_pos.y()))
                return True
            self.is_color_outline_masking = True
            self.color_outline_mask_start = scene_pos
            self.color_outline_mask_points = [scene_pos]
            self._draw_color_outline_mask_preview(scene_pos)
            return True
        if mode == "mask_wrap":
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() not in (2, 3):
                return True
            self.is_mask_wrapping = True
            self.mask_wrap_start = scene_pos
            self.mask_wrap_points = [scene_pos]
            self._draw_mask_wrap_preview(scene_pos)
            return True
        if mode == "mask_cut":
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() not in (2, 3):
                return True
            self.is_mask_cutting = True
            self.mask_cut_start = scene_pos
            self.mask_cut_points = [scene_pos]
            self._draw_mask_cut_preview(scene_pos)
            return True
        return False

    def _finish_click_click_area_tool_at(self, scene_pos):
        """Finish CAD-style area input at the second clicked point."""
        mode = getattr(self, "draw_mode", None)
        if mode == "raster_erase" and getattr(self, "is_raster_erasing", False):
            rect = QRectF(self.raster_erase_start, scene_pos).normalized() if self.raster_erase_start is not None else QRectF()
            self.is_raster_erasing = False
            self.raster_erase_start = None
            self.clear_raster_erase_preview()
            if hasattr(self.main, "apply_raster_text_erase_rect"):
                self.main.apply_raster_text_erase_rect(rect)
            try:
                self.main.set_tool(None)
            except Exception:
                self.draw_mode = None
            return True
        if mode == "area_paint" and getattr(self, "is_area_painting", False):
            self.is_area_painting = False
            applied = self._apply_area_paint_rect(scene_pos)
            self.area_paint_start = None
            self.area_paint_points = []
            self.clear_area_paint_preview()
            if applied:
                tab_mode = self.main.cb_mode.currentIndex() if getattr(self.main, "cb_mode", None) is not None else 4
                if hasattr(self.main, "undo_commit_paint_layer"):
                    self.main.undo_commit_paint_layer("mask" if tab_mode in (2, 3) else "final_paint", delay_ms=1200)
                elif hasattr(self.main, "schedule_deferred_view_layer_commit"):
                    self.main.schedule_deferred_view_layer_commit("mask" if tab_mode in (2, 3) else "final_paint", delay_ms=1200)
            self._area_paint_undo_key = None
            return True
        if mode == "ocr_region_select" and getattr(self, "is_ocr_region_drawing", False):
            if getattr(self, "ocr_region_shape", "rect") == "free":
                pts = getattr(self, "ocr_region_points", []) or []
                if not pts:
                    self.ocr_region_points = [scene_pos]
                else:
                    last = pts[-1]
                    dx = scene_pos.x() - last.x()
                    dy = scene_pos.y() - last.y()
                    if (dx * dx + dy * dy) >= 9:
                        pts.append(scene_pos)
                        self.ocr_region_points = pts
            payload = self.current_ocr_region_payload(scene_pos)
            self.is_ocr_region_drawing = False
            self.ocr_region_start = None
            self.ocr_region_points = []
            self.clear_ocr_region_preview()
            if payload is not None and hasattr(self.main, "add_ocr_analysis_region_payload"):
                self.main.add_ocr_analysis_region_payload(payload)
            return True
        if mode == "quick_ocr" and getattr(self, "is_quick_ocr_drawing", False):
            self.is_quick_ocr_drawing = False
            self.quick_ocr_start = None
            self.quick_ocr_current_rect_norm = None
            try:
                self.quick_ocr_hold_timer.stop()
            except Exception:
                pass
            self.clear_quick_ocr_preview()
            if hasattr(self.main, "finish_quick_ocr_drag"):
                self.main.finish_quick_ocr_drag()
            return True
        if mode == "color_outline_mask" and getattr(self, "is_color_outline_masking", False):
            region = self._color_outline_mask_region_np(scene_pos)
            self.is_color_outline_masking = False
            self.color_outline_mask_start = None
            self.color_outline_mask_points = []
            self.clear_color_outline_mask_preview()
            if region is not None and hasattr(self.main, "apply_color_outline_mask"):
                self.main.apply_color_outline_mask(region)
            return True
        if mode == "mask_wrap" and getattr(self, "is_mask_wrapping", False):
            region = self._mask_wrap_region_np(scene_pos)
            self.is_mask_wrapping = False
            self.mask_wrap_start = None
            self.mask_wrap_points = []
            self.clear_mask_wrap_preview()
            if region is not None and hasattr(self.main, "apply_mask_wrapping"):
                self.main.apply_mask_wrapping(region)
            return True
        if mode == "mask_cut" and getattr(self, "is_mask_cutting", False):
            region = self._mask_cut_region_np(scene_pos)
            self.is_mask_cutting = False
            self.mask_cut_start = None
            self.mask_cut_points = []
            self.clear_mask_cut_preview()
            if region is not None and hasattr(self.main, "apply_mask_cutting"):
                self.main.apply_mask_cutting(region)
            return True
        if mode == "original_restore" and getattr(self, "is_original_restoring", False):
            if getattr(self, "original_restore_shape", "rect") == "free":
                pts = getattr(self, "original_restore_points", []) or []
                if not pts:
                    self.original_restore_points = [scene_pos]
                else:
                    last = pts[-1]
                    dx = scene_pos.x() - last.x()
                    dy = scene_pos.y() - last.y()
                    if (dx * dx + dy * dy) >= 9:
                        pts.append(scene_pos)
                        self.original_restore_points = pts
            region_path = self._original_restore_region_path(scene_pos)
            region_mask = None
            try:
                scene_rect = self.scene.sceneRect()
                region_mask = self._original_restore_region_mask_np(region_path, int(scene_rect.width()), int(scene_rect.height()))
            except Exception:
                region_mask = None
            self.is_original_restoring = False
            self.original_restore_start = None
            self.original_restore_points = []
            if region_path is not None:
                self.show_original_restore_selection(region_path)
            else:
                self.clear_original_restore_preview()
            if hasattr(self.main, "set_original_restore_selection"):
                self.main.set_original_restore_selection(region_mask, region_path)
            return True
        return False

    def _start_polygon_area_tool_at(self, scene_pos, event=None):
        """Start a click-based closed area. Polygon uses straight segments; CAD free uses cursor-path segments."""
        mode = str(getattr(self, "draw_mode", None) or "")
        if not (self._is_polygon_area_tool(mode) or self._is_cad_free_area_tool(mode)):
            return False
        # Keep the same tab/Alt-spo이드 guards as the existing area tools.
        if mode == "area_paint":
            tab_mode = self.main.cb_mode.currentIndex() if getattr(self.main, "cb_mode", None) is not None else 4
            if tab_mode not in (2, 3, 4):
                return True
            self._area_paint_undo_key = None
        elif mode == "original_restore":
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() != 4:
                return True
        elif mode == "color_outline_mask":
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() not in (2, 3):
                return True
            if event is not None and event.modifiers() & Qt.KeyboardModifier.AltModifier:
                if hasattr(self.main, "pick_color_outline_mask_from_scene"):
                    self.main.pick_color_outline_mask_from_scene(int(scene_pos.x()), int(scene_pos.y()))
                return True
        elif mode in ("mask_wrap", "mask_cut"):
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() not in (2, 3):
                return True

        start_attr = self._area_shape_start_attr(mode)
        points_attr = self._area_shape_points_attr(mode)
        active_attr = self._area_shape_active_attr(mode)
        if not (start_attr and points_attr and active_attr):
            return False
        setattr(self, active_attr, True)
        setattr(self, start_attr, scene_pos)
        setattr(self, points_attr, [scene_pos])
        if self._is_cad_free_area_tool(mode):
            self._set_cad_free_checkpoints(mode, [0])
        else:
            self._clear_cad_free_checkpoints(mode)
        self._draw_area_shape_preview_for_mode(mode, scene_pos)
        return True

    def _finish_polygon_area_tool_at(self):
        """Close the active polygon/CAD-free area and apply it as the current area tool's region."""
        mode = str(getattr(self, "draw_mode", None) or "")
        if not (self._is_polygon_area_tool(mode) or self._is_cad_free_area_tool(mode)):
            return False
        points_attr = self._area_shape_points_attr(mode)
        active_attr = self._area_shape_active_attr(mode)
        start_attr = self._area_shape_start_attr(mode)
        points = list(getattr(self, points_attr, []) or []) if points_attr else []
        if len(points) < 3:
            return True

        if mode == "area_paint":
            setattr(self, active_attr, False)
            applied = self._apply_area_paint_rect(None)
            setattr(self, start_attr, None)
            setattr(self, points_attr, [])
            self._clear_cad_free_checkpoints(mode)
            self.clear_area_paint_preview()
            if applied:
                tab_mode = self.main.cb_mode.currentIndex() if getattr(self.main, "cb_mode", None) is not None else 4
                if hasattr(self.main, "undo_commit_paint_layer"):
                    self.main.undo_commit_paint_layer("mask" if tab_mode in (2, 3) else "final_paint", delay_ms=1200)
                elif hasattr(self.main, "schedule_deferred_view_layer_commit"):
                    self.main.schedule_deferred_view_layer_commit("mask" if tab_mode in (2, 3) else "final_paint", delay_ms=1200)
            self._area_paint_undo_key = None
            return True

        if mode == "original_restore":
            region_path = self._original_restore_region_path(None)
            region_mask = None
            try:
                scene_rect = self.scene.sceneRect()
                region_mask = self._original_restore_region_mask_np(region_path, int(scene_rect.width()), int(scene_rect.height()))
            except Exception:
                region_mask = None
            setattr(self, active_attr, False)
            setattr(self, start_attr, None)
            setattr(self, points_attr, [])
            self._clear_cad_free_checkpoints(mode)
            if region_path is not None:
                self.show_original_restore_selection(region_path)
            else:
                self.clear_original_restore_preview()
            if hasattr(self.main, "set_original_restore_selection"):
                self.main.set_original_restore_selection(region_mask, region_path)
            return True

        if mode == "ocr_region_select":
            payload = self.current_ocr_region_payload(None)
            setattr(self, active_attr, False)
            setattr(self, start_attr, None)
            setattr(self, points_attr, [])
            self._clear_cad_free_checkpoints(mode)
            self.clear_ocr_region_preview()
            if payload is not None and hasattr(self.main, "add_ocr_analysis_region_payload"):
                self.main.add_ocr_analysis_region_payload(payload)
            return True

        if mode == "color_outline_mask":
            region = self._color_outline_mask_region_np(None)
            setattr(self, active_attr, False)
            setattr(self, start_attr, None)
            setattr(self, points_attr, [])
            self._clear_cad_free_checkpoints(mode)
            self.clear_color_outline_mask_preview()
            if region is not None and hasattr(self.main, "apply_color_outline_mask"):
                self.main.apply_color_outline_mask(region)
            return True

        if mode == "mask_wrap":
            region = self._mask_wrap_region_np(None)
            setattr(self, active_attr, False)
            setattr(self, start_attr, None)
            setattr(self, points_attr, [])
            self._clear_cad_free_checkpoints(mode)
            self.clear_mask_wrap_preview()
            if region is not None and hasattr(self.main, "apply_mask_wrapping"):
                self.main.apply_mask_wrapping(region)
            return True

        if mode == "mask_cut":
            region = self._mask_cut_region_np(None)
            setattr(self, active_attr, False)
            setattr(self, start_attr, None)
            setattr(self, points_attr, [])
            self._clear_cad_free_checkpoints(mode)
            self.clear_mask_cut_preview()
            if region is not None and hasattr(self.main, "apply_mask_cutting"):
                self.main.apply_mask_cutting(region)
            return True
        return False

    def _handle_polygon_area_click_at(self, scene_pos, event=None):
        mode = str(getattr(self, "draw_mode", None) or "")
        if not (self._is_polygon_area_tool(mode) or self._is_cad_free_area_tool(mode)):
            return False
        active_attr = self._area_shape_active_attr(mode)
        points_attr = self._area_shape_points_attr(mode)
        if not (active_attr and points_attr):
            return False
        if not bool(getattr(self, active_attr, False)):
            return self._start_polygon_area_tool_at(scene_pos, event)
        points = list(getattr(self, points_attr, []) or [])
        if self._is_cad_free_area_tool(mode):
            points = self._append_scene_point_if_moved(points, scene_pos, min_sq=1.0)
            if self._polygon_click_closes(points, scene_pos):
                setattr(self, points_attr, points)
                return self._finish_polygon_area_tool_at()
            setattr(self, points_attr, points)
            ck_attr = self._area_shape_checkpoints_attr(mode)
            checkpoints = list(getattr(self, ck_attr, []) or [0]) if ck_attr else [0]
            new_idx = len(points) - 1
            if new_idx >= 0 and (not checkpoints or new_idx > checkpoints[-1]):
                checkpoints.append(new_idx)
            if ck_attr:
                setattr(self, ck_attr, checkpoints)
            self._draw_area_shape_preview_for_mode(mode, scene_pos)
            return True

        if self._polygon_click_closes(points, scene_pos):
            return self._finish_polygon_area_tool_at()
        points.append(scene_pos)
        setattr(self, points_attr, points)
        self._draw_area_shape_preview_for_mode(mode, scene_pos)
        return True

    def undo_polygon_area_point(self):
        """Undo one polygon point or one CAD-free checkpoint segment while a closed area is being drawn."""
        mode = str(getattr(self, "draw_mode", None) or "")
        if not (self._is_polygon_area_tool(mode) or self._is_cad_free_area_tool(mode)):
            return False
        active_attr = self._area_shape_active_attr(mode)
        points_attr = self._area_shape_points_attr(mode)
        start_attr = self._area_shape_start_attr(mode)
        if not (active_attr and points_attr and bool(getattr(self, active_attr, False))):
            return False
        points = list(getattr(self, points_attr, []) or [])

        if self._is_cad_free_area_tool(mode):
            ck_attr = self._area_shape_checkpoints_attr(mode)
            checkpoints = list(getattr(self, ck_attr, []) or [0]) if ck_attr else [0]
            checkpoints = [int(i) for i in checkpoints if isinstance(i, int) or str(i).isdigit()] or [0]
            checkpoints = [max(0, min(int(i), max(0, len(points) - 1))) for i in checkpoints]
            checkpoints = sorted(set(checkpoints))
            if not points or len(checkpoints) <= 1 and len(points) <= 1:
                self.cancel_click_click_area_interaction(clear_tool=False)
                return True
            last_checkpoint = checkpoints[-1] if checkpoints else 0
            if len(points) > last_checkpoint + 1:
                points = points[:last_checkpoint + 1]
            elif len(checkpoints) > 1:
                checkpoints.pop()
                keep_idx = checkpoints[-1]
                points = points[:keep_idx + 1]
            else:
                self.cancel_click_click_area_interaction(clear_tool=False)
                return True
            setattr(self, points_attr, points)
            if ck_attr:
                setattr(self, ck_attr, checkpoints)
            if start_attr:
                setattr(self, start_attr, points[0] if points else None)
            self._draw_area_shape_preview_for_mode(mode, points[-1] if points else None)
            return True

        if len(points) <= 1:
            self.cancel_click_click_area_interaction(clear_tool=False)
            return True
        points.pop()
        setattr(self, points_attr, points)
        if start_attr:
            setattr(self, start_attr, points[0] if points else None)
        self._draw_area_shape_preview_for_mode(mode, points[-1] if points else None)
        return True

    def _make_area_polyline_path(self, points, now=None, close=False):
        pts = list(points or [])
        if not pts and now is not None:
            pts = [now]
        if not pts:
            return None
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        if now is not None:
            try:
                if not pts or (float(now.x() - pts[-1].x()) ** 2 + float(now.y() - pts[-1].y()) ** 2) > 0.5:
                    path.lineTo(now)
            except Exception:
                path.lineTo(now)
        if close:
            path.closeSubpath()
        return path

    def _polygon_preview_should_close(self, points, now):
        return bool(now is not None and self._polygon_click_closes(list(points or []), now))

    def ui_visual_scale(self):
        """Return a scene-pixel scale for non-output guide UI.

        This affects only editor overlays such as analysis boxes, OCR regions,
        magic-wand outlines, selection rectangles and preview borders.
        It must not be used for real text stroke / mask / paint output.

        Webtoon pages can be extremely tall while keeping a normal page width.
        Scaling guide UI from max(width, height) makes outlines and number boxes
        far too large on those pages, so automatic guide scaling is based on
        image width only.
        """
        try:
            rect = self.scene.sceneRect()
            w = float(rect.width())
            if w <= 1:
                base_item = getattr(self, "_layer_base_item", None)
                if base_item is not None and not base_item.pixmap().isNull():
                    w = float(base_item.pixmap().width())
            if w <= 1:
                items_rect = self.scene.itemsBoundingRect()
                w = float(items_rect.width())
            scale = w / self.GUIDE_BASE_W
            return max(1.0, min(float(scale), self.GUIDE_SCALE_MAX))
        except Exception:
            return 1.0

    def analysis_box_manual_size_enabled(self):
        try:
            return str(getattr(self.main, "analysis_box_size_mode", "auto") or "auto").lower() == "manual"
        except Exception:
            return False

    def analysis_number_box_size(self):
        try:
            base = max(1, int(getattr(self.main, "analysis_number_box_width", 40) or 40))
        except Exception:
            base = 40
        if self.analysis_box_manual_size_enabled():
            return max(1, int(base))
        try:
            return max(1, int(round(float(base) * self.ui_visual_scale())))
        except Exception:
            return max(1, int(base))

    def ui_pen_width(self, base=2.0, minimum=1.0):
        try:
            if self.analysis_box_manual_size_enabled():
                manual = max(1.0, float(getattr(self.main, "analysis_outline_width", base) or base))
                return max(float(minimum), manual)
            return max(float(minimum), float(base) * self.ui_visual_scale())
        except Exception:
            return float(base or minimum or 1.0)

    def ui_handle_size(self, base=14.0, minimum=8.0):
        try:
            return max(float(minimum), float(base) * self.ui_visual_scale())
        except Exception:
            return float(base or minimum or 8.0)

    def _make_tool_cursor(self, kind):
        """Create small custom cursors so the active editor tool is visible at a glance."""
        kind = str(kind or "")
        cached = self._tool_cursor_cache.get(kind) if isinstance(getattr(self, "_tool_cursor_cache", None), dict) else None
        if cached is not None:
            return cached
        try:
            pix = QPixmap(32, 32)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            shadow = QPen(QColor(0, 0, 0, 230), 4)
            line = QPen(QColor(255, 255, 255, 245), 2)
            accent = QPen(QColor(0, 210, 255, 245), 2)
            if kind == "brush":
                painter.setPen(shadow)
                painter.drawLine(7, 25, 22, 10)
                painter.drawEllipse(5, 23, 5, 5)
                painter.setPen(accent)
                painter.drawLine(7, 25, 22, 10)
                painter.drawEllipse(5, 23, 5, 5)
                painter.setPen(line)
                painter.drawLine(19, 8, 25, 2)
                cursor = QCursor(pix, 7, 25)
            elif kind == "eraser":
                painter.setPen(shadow)
                painter.drawRect(7, 17, 14, 9)
                painter.drawLine(7, 17, 16, 8)
                painter.drawLine(21, 17, 25, 8)
                painter.drawLine(16, 8, 25, 8)
                painter.setPen(QPen(QColor(255, 150, 150, 245), 2))
                painter.drawRect(7, 17, 14, 9)
                painter.drawLine(7, 17, 16, 8)
                painter.drawLine(21, 17, 25, 8)
                painter.drawLine(16, 8, 25, 8)
                painter.setPen(line)
                painter.drawLine(8, 26, 24, 26)
                cursor = QCursor(pix, 7, 25)
            else:
                cursor = QCursor(Qt.CursorShape.ArrowCursor)
            painter.end()
            try:
                self._tool_cursor_cache[kind] = cursor
            except Exception:
                pass
            return cursor
        except Exception:
            if kind == "brush":
                return QCursor(Qt.CursorShape.CrossCursor)
            if kind == "eraser":
                return QCursor(Qt.CursorShape.ForbiddenCursor)
            return QCursor(Qt.CursorShape.ArrowCursor)

    def _apply_tool_cursor_to_view(self, cursor):
        """Apply tool cursor to both the view and its viewport.

        QGraphicsView displays mouse input on the viewport child widget, and
        QGraphicsItem cursors can also override the view cursor.  Applying the
        same cursor to both widgets keeps tool switching stable after undo/redo
        or scene rebuilds.
        """
        try:
            self.setCursor(cursor)
        except Exception:
            pass
        try:
            vp = self.viewport()
            if vp is not None:
                vp.setCursor(cursor)
        except Exception:
            pass

    def _unset_tool_cursor_from_view(self):
        try:
            self.unsetCursor()
        except Exception:
            pass
        try:
            vp = self.viewport()
            if vp is not None:
                vp.unsetCursor()
        except Exception:
            pass

    def _cursor_audit(self, event_name, **payload):
        """Lightweight cursor trace for stuck/stale cursor bugs."""
        try:
            main = getattr(self, "main", None)
            if main is not None and hasattr(main, "audit_boundary_event"):
                main.audit_boundary_event(event_name, **payload)
        except Exception:
            pass

    def _tool_mode_key(self, mode=None):
        try:
            if mode is None:
                mode = getattr(self, "draw_mode", None)
            return str(mode) if mode is not None else "move"
        except Exception:
            return "move"

    def clear_scene_item_cursors_for_tool_mode(self, mode=None, force=False):
        """Clear QGraphicsItem cursors that can mask the active tool cursor.

        Text/transform/inline editor items can keep their own cursor after the
        actual tool has changed.  Those item-level cursors win over the
        QGraphicsView/viewport cursor, so the tool cursor can look frozen.
        This function is intentionally conservative during normal final_text
        hover, but force=True is used at tool switches, editor close, page
        rebuild and drag end to remove every stale item cursor.
        """
        cleared = 0
        try:
            if mode is None:
                mode = getattr(self, "draw_mode", None)
            mode_s = str(mode) if mode is not None else "move"
            if (not force) and mode_s == "final_text":
                return 0
            # Forced cursor cleanups can be requested repeatedly by editor-close,
            # selection and delayed follow-up paths.  Once the scene item cursors
            # were just cleared for the same mode, another full scene scan in the
            # next few milliseconds only adds UI stalls.
            try:
                now_ms = int(QApplication.instance().property("ysb_cursor_clear_clock") or 0)
            except Exception:
                now_ms = 0
            try:
                import time as _time
                now_real_ms = int(_time.monotonic() * 1000)
            except Exception:
                now_real_ms = now_ms
            try:
                last_ms = int(getattr(self, "_last_cursor_item_clear_ms", 0) or 0)
                last_mode = str(getattr(self, "_last_cursor_item_clear_mode", "") or "")
                if force and last_mode == mode_s and (now_real_ms - last_ms) < 80:
                    return 0
            except Exception:
                pass
            scene = self.scene
            if scene is None:
                return 0
            for item in list(scene.items()):
                try:
                    item.unsetCursor()
                    cleared += 1
                except Exception:
                    pass
            if cleared:
                try:
                    self._last_cursor_item_clear_ms = now_real_ms
                    self._last_cursor_item_clear_mode = mode_s
                except Exception:
                    pass
                self._cursor_audit("CURSOR_ITEM_CLEAR", mode=mode_s, force=bool(force), count=cleared)
        except Exception as exc:
            try:
                self._cursor_audit("CURSOR_ITEM_CLEAR_ERROR", error=repr(exc))
            except Exception:
                pass
        return cleared

    def text_item_mouse_interaction_allowed_for_mode(self, mode=None):
        try:
            if mode is None:
                mode = getattr(self, "draw_mode", None)
            return (
                getattr(self.main, "cb_mode", None) is not None
                and int(self.main.cb_mode.currentIndex()) == 4
                and (mode is None or mode == "final_text")
            )
        except Exception:
            return False

    def refresh_text_item_interaction_for_tool_mode(self, mode=None, reason="tool_mode"):
        """Keep text/raster text objects click-through outside move/final_text modes."""
        try:
            if mode is None:
                mode = getattr(self, "draw_mode", None)
            allowed = bool(self.text_item_mouse_interaction_allowed_for_mode(mode))
            scene = self.scene
            if scene is None:
                return 0
            changed = 0
            selected_cleared = False
            for item in list(scene.items()):
                try:
                    if not isinstance(item, TypesettingItem) or getattr(item, "is_paste_preview", False):
                        continue
                    if hasattr(item, "set_tool_interaction_enabled"):
                        item.set_tool_interaction_enabled(allowed)
                    else:
                        item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton if allowed else Qt.MouseButton.NoButton)
                        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, allowed)
                        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, allowed)
                        if not allowed:
                            item.setSelected(False)
                    changed += 1
                    if not allowed:
                        selected_cleared = True
                except Exception:
                    continue
            if selected_cleared and getattr(self.main, "on_scene_selection_changed", None):
                try:
                    self.main.on_scene_selection_changed()
                except Exception:
                    pass
            try:
                if getattr(self.main, "audit_boundary_event", None):
                    self.main.audit_boundary_event(
                        "TEXT_ITEM_INTERACTION_MODE_SYNC",
                        mode=str(mode) if mode is not None else "move",
                        allowed=bool(allowed),
                        count=int(changed),
                        reason=str(reason or ""),
                        throttle_ms=80,
                    )
            except Exception:
                pass
            return changed
        except Exception:
            return 0

    def _brush_cursor_preview_is_suspended(self):
        """Return True while view/undo navigation should not repaint the size ring."""
        try:
            if bool(getattr(self, "_brush_cursor_preview_suspended", False)):
                return True
            if bool(getattr(self, "_view_interaction_fast_path_active", False)):
                return True
            if bool(getattr(self, "_middle_pan_active", False)):
                return True
        except Exception:
            return False
        return False

    def suspend_brush_cursor_preview(self, reason='view', delay_ms=180):
        """Hide and pause the brush/eraser size ring during heavy view operations.

        The real tool cursor remains active; only the scene overlay ring is delayed.
        This prevents the preview item from forcing extra repaints while scrolling,
        zooming, middle-button panning, or applying Undo/Redo.
        """
        try:
            delay_ms = int(delay_ms or 180)
        except Exception:
            delay_ms = 180
        delay_ms = max(60, min(delay_ms, 1000))
        try:
            timer = getattr(self, "_brush_cursor_preview_update_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
        except Exception:
            pass
        try:
            self._brush_cursor_preview_suspended = True
            self.clear_brush_cursor_preview(reset_position=False)
        except Exception:
            pass
        try:
            timer = getattr(self, "_brush_cursor_preview_resume_timer", None)
            if timer is not None:
                timer.stop()
                timer.start(delay_ms)
        except Exception:
            pass

    def _resume_brush_cursor_preview_after_suspend(self):
        try:
            self._brush_cursor_preview_suspended = False
        except Exception:
            pass
        try:
            if getattr(self, "draw_mode", None) in ("draw", "erase"):
                scene_pos = (
                    getattr(self, "_brush_cursor_preview_pending_scene_pos", None)
                    or getattr(self, "_brush_cursor_preview_scene_pos", None)
                    or getattr(self, "_brush_cursor_preview_last_scene_pos", None)
                )
                self.request_brush_cursor_preview(scene_pos=scene_pos, delay_ms=20)
        except Exception:
            pass

    def request_brush_cursor_preview(self, scene_pos=None, delay_ms=120, restart=False, immediate=False):
        """Coalesce brush/eraser preview updates.

        Normal hover motion should not repaint the scene on every mouse move.
        The ring appears after the mouse becomes idle.  During an actual brush
        stroke, callers can use immediate=True so the size ring stays at the real
        paint position while the user is drawing.
        """
        try:
            if getattr(self, "draw_mode", None) not in ("draw", "erase"):
                self.clear_brush_cursor_preview()
                return
            if scene_pos is not None:
                self._brush_cursor_preview_pending_scene_pos = QPointF(scene_pos)
                self._brush_cursor_preview_last_scene_pos = QPointF(scene_pos)
            if self._brush_cursor_preview_is_suspended():
                if getattr(self, "_brush_cursor_preview_items", None):
                    self.clear_brush_cursor_preview(reset_position=False)
                return
            timer = getattr(self, "_brush_cursor_preview_update_timer", None)
            if immediate:
                try:
                    if timer is not None and timer.isActive():
                        timer.stop()
                except Exception:
                    pass
                self.update_brush_cursor_preview(self._brush_cursor_preview_pending_scene_pos)
                return
            if timer is None:
                self.update_brush_cursor_preview(self._brush_cursor_preview_pending_scene_pos)
                return
            try:
                delay_ms = int(delay_ms or 120)
            except Exception:
                delay_ms = 120
            delay_ms = max(0, min(delay_ms, 300))
            if restart and timer.isActive():
                timer.stop()
            if restart or not timer.isActive():
                timer.start(delay_ms)
        except Exception:
            pass

    def _flush_brush_cursor_preview_request(self):
        try:
            if getattr(self, "draw_mode", None) not in ("draw", "erase"):
                self.clear_brush_cursor_preview()
                return
            if self._brush_cursor_preview_is_suspended():
                if getattr(self, "_brush_cursor_preview_items", None):
                    self.clear_brush_cursor_preview(reset_position=False)
                return
            scene_pos = getattr(self, "_brush_cursor_preview_pending_scene_pos", None)
            if scene_pos is None:
                scene_pos = getattr(self, "_brush_cursor_preview_scene_pos", None)
            if scene_pos is None:
                scene_pos = getattr(self, "_brush_cursor_preview_last_scene_pos", None)
            if scene_pos is None:
                return
            self.update_brush_cursor_preview(scene_pos)
        except Exception:
            pass

    def clear_brush_cursor_preview(self, reset_position=True):
        """Remove the on-canvas brush/eraser size ring without touching real paint data.

        reset_position=False is used for temporary view scrolling/zooming pauses so
        the size ring can reappear at the same real paint position as soon as the
        view settles.
        """
        items = list(getattr(self, "_brush_cursor_preview_items", []) or [])
        self._brush_cursor_preview_items = []
        if reset_position:
            self._brush_cursor_preview_scene_pos = None
            self._brush_cursor_preview_pending_scene_pos = None
            self._brush_cursor_preview_last_scene_pos = None
        self._brush_cursor_preview_mode = None
        for item in items:
            try:
                if not self._qgraphics_item_is_alive(item):
                    continue
                scene = item.scene()
                if scene is not None:
                    scene.removeItem(item)
            except Exception:
                pass
        try:
            self._remove_scene_items_by_tags("brush_cursor_preview")
        except Exception:
            pass

    def _brush_cursor_preview_pen_pair(self, mode):
        try:
            outer_width = max(1.0, self.ui_pen_width(3.0, 1.0))
            inner_width = max(1.0, self.ui_pen_width(1.3, 1.0))
        except Exception:
            outer_width = 3.0
            inner_width = 1.3
        outer = QPen(QColor(0, 0, 0, 230), outer_width, Qt.PenStyle.SolidLine)
        if str(mode) == "erase":
            inner = QPen(QColor(255, 120, 120, 245), inner_width, Qt.PenStyle.SolidLine)
        else:
            inner = QPen(QColor(0, 210, 255, 245), inner_width, Qt.PenStyle.SolidLine)
        return outer, inner

    def update_brush_cursor_preview(self, scene_pos=None):
        """Show the real scene-pixel brush/eraser radius at the current mouse point."""
        mode = getattr(self, "draw_mode", None)
        if mode not in ("draw", "erase"):
            self.clear_brush_cursor_preview()
            return
        if scene_pos is not None:
            try:
                self._brush_cursor_preview_pending_scene_pos = QPointF(scene_pos)
                self._brush_cursor_preview_last_scene_pos = QPointF(scene_pos)
            except Exception:
                pass
        if self._brush_cursor_preview_is_suspended():
            if getattr(self, "_brush_cursor_preview_items", None):
                self.clear_brush_cursor_preview(reset_position=False)
            return
        if scene_pos is None:
            scene_pos = getattr(self, "_brush_cursor_preview_scene_pos", None)
        if scene_pos is None:
            scene_pos = getattr(self, "_brush_cursor_preview_pending_scene_pos", None)
        if scene_pos is None:
            scene_pos = getattr(self, "_brush_cursor_preview_last_scene_pos", None)
        if scene_pos is None:
            return
        try:
            scene_pos = QPointF(scene_pos)
            preview_mode_before = getattr(self, "_brush_cursor_preview_mode", None)
            self._brush_cursor_preview_scene_pos = QPointF(scene_pos)
            self._brush_cursor_preview_mode = mode
            size = max(1.0, float(getattr(self, "brush_size", 25) or 25))
            half = size / 2.0
            rect = QRectF(scene_pos.x() - half, scene_pos.y() - half, size, size)
            items = list(getattr(self, "_brush_cursor_preview_items", []) or [])
            alive = [x for x in items if self._qgraphics_item_is_alive(x)]
            outer_pen, inner_pen = self._brush_cursor_preview_pen_pair(mode)
            if len(alive) < 2 or str(preview_mode_before) != str(mode):
                self.clear_brush_cursor_preview()
                self._brush_cursor_preview_scene_pos = QPointF(scene_pos)
                self._brush_cursor_preview_mode = mode
                outer = self.scene.addEllipse(rect, outer_pen, QBrush(Qt.BrushStyle.NoBrush))
                inner = self.scene.addEllipse(rect, inner_pen, QBrush(Qt.BrushStyle.NoBrush))
                for item in (outer, inner):
                    item.setZValue(100000)
                    item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                    self._set_layer_tag(item, "brush_cursor_preview")
                self._brush_cursor_preview_items = [outer, inner]
            else:
                outer, inner = alive[0], alive[1]
                try:
                    outer.setRect(rect)
                    inner.setRect(rect)
                    outer.setPen(outer_pen)
                    inner.setPen(inner_pen)
                    outer.setVisible(True)
                    inner.setVisible(True)
                    outer.setZValue(100000)
                    inner.setZValue(100000)
                except Exception:
                    self.clear_brush_cursor_preview()
        except Exception:
            pass

    def update_tool_cursor(self, mode=None, force=False):
        """Apply and re-apply the current tool cursor.

        Cursor ownership is split between QGraphicsView, its viewport child and
        hovered QGraphicsItems.  Therefore this method deliberately re-applies
        the QWidget cursor even when the tool key is unchanged.  Otherwise an
        I-beam/SizeAll/ClosedHand cursor left by inline editing, text transform
        or middle-panning can survive and make the tool cursor look frozen.
        """
        try:
            if mode is None:
                mode = getattr(self, "draw_mode", None)
            key = self._tool_mode_key(mode)

            if getattr(self, "_middle_pan_active", False) and not force:
                self._cursor_audit("CURSOR_APPLY_BLOCKED_MIDDLE_PAN", mode=key, force=False)
                return

            prev_key = getattr(self, "_active_tool_cursor_key", None)
            key_changed = (key != prev_key)

            # On a tool switch, forced refresh, or any real editing tool, remove
            # item-level cursors first.  Item cursors have priority over the
            # viewport cursor and are the main source of stale cursor display.
            try:
                if force or key_changed or key not in ("move", "final_text"):
                    self.clear_scene_item_cursors_for_tool_mode(mode, force=bool(force or key_changed or key not in ("move", "final_text")))
            except Exception:
                pass

            self._active_tool_cursor_key = key
            try:
                if force or key_changed:
                    self.refresh_text_item_interaction_for_tool_mode(mode, reason='cursor_tool_change')
            except Exception:
                pass

            if mode in ("draw", "erase"):
                self._apply_tool_cursor_to_view(self._make_tool_cursor("eraser" if mode == "erase" else "brush"))
                if getattr(self, "_brush_cursor_preview_items", None):
                    pos = getattr(self, "_brush_cursor_preview_scene_pos", None) or getattr(self, "_brush_cursor_preview_last_scene_pos", None)
                    self.request_brush_cursor_preview(scene_pos=pos, immediate=True)
                self._cursor_audit("CURSOR_APPLY", mode=key, force=bool(force), changed=bool(key_changed), cursor=("eraser" if mode == "erase" else "brush"))
                return

            self.clear_brush_cursor_preview()
            if mode is None:
                self._apply_tool_cursor_to_view(QCursor(Qt.CursorShape.OpenHandCursor))
                cursor_name = "OpenHandCursor"
            elif mode in ("area_paint", "original_restore", "ocr_region_select", "quick_ocr", "color_outline_mask", "mask_wrap", "mask_cut", "raster_erase", "magic_wand", "paste_text"):
                self._apply_tool_cursor_to_view(QCursor(Qt.CursorShape.CrossCursor))
                cursor_name = "CrossCursor"
            elif mode == "final_text":
                self._apply_tool_cursor_to_view(QCursor(Qt.CursorShape.IBeamCursor))
                cursor_name = "IBeamCursor"
            elif mode == "text_style_clone":
                self._apply_tool_cursor_to_view(QCursor(Qt.CursorShape.PointingHandCursor))
                cursor_name = "PointingHandCursor"
            else:
                self._unset_tool_cursor_from_view()
                cursor_name = "unset"
            self._cursor_audit("CURSOR_APPLY", mode=key, force=bool(force), changed=bool(key_changed), cursor=cursor_name)
        except Exception as exc:
            try:
                self._cursor_audit("CURSOR_APPLY_ERROR", error=repr(exc))
            except Exception:
                pass


    def _run_deferred_tool_cursor_refresh(self, generation):
        """Run only the newest delayed cursor refresh request.

        Several code paths request 0/40/120ms cursor repairs after editor close,
        drag end and page rebuild.  If all of them execute, QGraphicsItem cursor
        clearing runs many times in a row and can create small UI stalls.  A
        generation token makes older scheduled repairs no-op.
        """
        try:
            if int(generation) != int(getattr(self, "_tool_cursor_refresh_generation", 0) or 0):
                return
        except Exception:
            return
        try:
            self._active_tool_cursor_key = None
        except Exception:
            pass
        try:
            self.update_tool_cursor(force=True)
        except Exception:
            pass

    def force_tool_cursor_refresh(self, delay_followups=True):
        """Re-apply the current tool cursor even if the tool key did not change.

        Inline text editing temporarily sets an I-beam cursor on a QGraphicsItem.
        When that editor is removed under the mouse, Qt may keep showing the
        item cursor until the next hover change.  Reset both the view and
        viewport cursors and then apply the active tool cursor again.  Delayed
        follow-ups are coalesced so only the latest refresh batch survives.
        """
        try:
            self._inline_editor_mouse_grab_active = False
        except Exception:
            pass
        try:
            gen = int(getattr(self, "_tool_cursor_refresh_generation", 0) or 0) + 1
        except Exception:
            gen = 1
        try:
            self._tool_cursor_refresh_generation = gen
        except Exception:
            pass
        try:
            self._active_tool_cursor_key = None
        except Exception:
            pass
        try:
            self._unset_tool_cursor_from_view()
        except Exception:
            pass
        try:
            self.clear_scene_item_cursors_for_tool_mode(getattr(self, "draw_mode", None), force=True)
        except Exception:
            pass
        try:
            self.update_tool_cursor(force=True)
        except Exception:
            pass
        if delay_followups:
            try:
                QTimer.singleShot(35, lambda gen=gen, self=self: self._run_deferred_tool_cursor_refresh(gen))
                QTimer.singleShot(120, lambda gen=gen, self=self: self._run_deferred_tool_cursor_refresh(gen))
            except Exception:
                pass

    def ui_font_size(self, base=11.0, minimum=8.0):
        try:
            return max(int(minimum), int(round(float(base) * self.ui_visual_scale())))
        except Exception:
            return int(base or minimum or 8)

    def ui_pad(self, base=4.0, minimum=2.0):
        try:
            return max(float(minimum), float(base) * self.ui_visual_scale())
        except Exception:
            return float(base or minimum or 2.0)

    def _view_fast_path_log(self, event_name, **payload):
        try:
            main = getattr(self, "main", None)
            if main is not None and hasattr(main, "audit_boundary_event"):
                main.audit_boundary_event(event_name, **payload)
        except Exception:
            pass

    def _begin_view_interaction_fast_path(self, reason='view', delay_ms=180):
        """Temporarily use cheap render settings while zooming/scrolling/panning.

        This is intentionally view-only.  It does not change page data, Undo payloads,
        mask caches, text data or project state.  It only reduces expensive repaint
        cost while the user is actively moving the view over a high-resolution page.
        """
        try:
            delay_ms = int(delay_ms or 180)
        except Exception:
            delay_ms = 180
        delay_ms = max(80, min(delay_ms, 800))

        try:
            self.suspend_brush_cursor_preview(reason=str(reason or 'view'), delay_ms=delay_ms + 80)
        except Exception:
            pass

        try:
            main = getattr(self, "main", None)
            if main is not None and getattr(main, "_text_scene_mutation_lock", False):
                self._view_interaction_fast_path_finish_pending = True
                self._view_fast_path_log(
                    'TEXT_SCENE_MUTATION_TIMER_GUARD_BLOCKED_VIEW_FASTPATH',
                    action='begin',
                    reason=str(reason or 'view'),
                    throttle_ms=100,
                )
                return
        except Exception:
            pass

        if not getattr(self, '_view_interaction_fast_path_active', False):
            self._view_interaction_fast_path_active = True
            self._view_interaction_fast_path_reason = str(reason or 'view')
            try:
                self._view_interaction_fast_path_old_hints = self.renderHints()
            except Exception:
                self._view_interaction_fast_path_old_hints = None
            try:
                self._view_interaction_fast_path_old_viewport_mode = self.viewportUpdateMode()
            except Exception:
                self._view_interaction_fast_path_old_viewport_mode = None
            try:
                self._view_interaction_fast_path_old_cache_mode = self.cacheMode()
            except Exception:
                self._view_interaction_fast_path_old_cache_mode = None

            try:
                # 확대/스크롤 중에는 품질보다 응답성이 우선이다.  정지 후 원복한다.
                self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                self.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
            except Exception:
                pass
            try:
                # 기존 기본값이 FullViewportUpdate인 경우 고해상도 화면 전체 repaint가 무겁다.
                # 조작 중에는 변경 영역 중심으로 줄이고, 종료 시 원래 모드로 복원한다.
                self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
            except Exception:
                pass
            try:
                # 배경 brush/scene background는 이동 중 재사용되도록 시도한다.
                # 문제 발생 시 종료 시점에 원래 CacheNone 등으로 복구된다.
                self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
            except Exception:
                pass
            self._view_fast_path_log(
                'VIEW_FAST_PATH_BEGIN',
                reason=str(reason or 'view'),
                delay_ms=delay_ms,
                smooth_pixmap=False,
                antialiasing=False,
                viewport='BoundingRectViewportUpdate',
                cache='CacheBackground',
            )
        else:
            # 연속 휠/스크롤 입력은 같은 fast path burst로 묶는다.
            self._view_interaction_fast_path_reason = str(reason or getattr(self, '_view_interaction_fast_path_reason', None) or 'view')

        try:
            self._view_interaction_fast_path_timer.start(delay_ms)
        except Exception:
            pass

    def _finish_view_interaction_fast_path(self, force=False):
        if not getattr(self, '_view_interaction_fast_path_active', False):
            return
        reason = getattr(self, '_view_interaction_fast_path_reason', None) or 'view'
        try:
            main = getattr(self, "main", None)
            if main is not None and getattr(main, "_text_scene_mutation_lock", False):
                self._view_interaction_fast_path_finish_pending = True
                try:
                    timer = getattr(self, "_view_interaction_fast_path_timer", None)
                    if timer is not None and timer.isActive():
                        timer.stop()
                except Exception:
                    pass
                self._view_fast_path_log(
                    'TEXT_SCENE_MUTATION_TIMER_GUARD_BLOCKED_VIEW_FASTPATH',
                    action='finish',
                    reason=str(reason),
                    throttle_ms=100,
                )
                return
        except Exception:
            pass
        try:
            old_hints = getattr(self, '_view_interaction_fast_path_old_hints', None)
            if old_hints is not None:
                self.setRenderHints(old_hints)
            else:
                self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        except Exception:
            pass
        try:
            old_mode = getattr(self, '_view_interaction_fast_path_old_viewport_mode', None)
            if old_mode is not None:
                self.setViewportUpdateMode(old_mode)
        except Exception:
            pass
        try:
            old_cache = getattr(self, '_view_interaction_fast_path_old_cache_mode', None)
            if old_cache is not None:
                self.setCacheMode(old_cache)
            else:
                self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)
        except Exception:
            pass

        self._view_interaction_fast_path_active = False
        self._view_interaction_fast_path_reason = None
        self._view_interaction_fast_path_old_hints = None
        self._view_interaction_fast_path_old_viewport_mode = None
        self._view_interaction_fast_path_old_cache_mode = None
        try:
            self.viewport().update()
        except Exception:
            pass
        self._view_fast_path_log('VIEW_FAST_PATH_END', reason=str(reason))
        try:
            if getattr(self, "draw_mode", None) in ("draw", "erase"):
                scene_pos = (
                    getattr(self, "_brush_cursor_preview_pending_scene_pos", None)
                    or getattr(self, "_brush_cursor_preview_scene_pos", None)
                    or getattr(self, "_brush_cursor_preview_last_scene_pos", None)
                )
                self.request_brush_cursor_preview(scene_pos=scene_pos, delay_ms=10)
        except Exception:
            pass

    def fit_image_to_current_viewport(self):
        """현재 QGraphicsView 뷰포트 크기에 맞춰 이미지를 최대 크기로 맞춘다.

        마우스 휠 버튼(가운데 버튼) 더블클릭용. 현재 창/분할 영역 크기를 기준으로
        scene 안의 실제 이미지/작업물 영역을 KeepAspectRatio로 맞춘다.
        """
        try:
            rect = self.scene.itemsBoundingRect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                rect = self.scene.sceneRect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                return False

            try:
                if not self._view_undo_is_suppressed() and hasattr(self.main, "begin_page_view_undo"):
                    self.main.begin_page_view_undo("화면 확대/축소")
            except Exception:
                pass

            self._begin_view_interaction_fast_path('fit', delay_ms=140)
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

            try:
                if hasattr(self.main, "remember_current_view_state"):
                    self.main.remember_current_view_state()
                if hasattr(self.main, "schedule_source_compare_sync"):
                    self.main.schedule_source_compare_sync(180)
            except Exception:
                pass
            try:
                if not self._view_undo_is_suppressed() and hasattr(self.main, "finish_page_view_undo"):
                    self.main.finish_page_view_undo(force=True)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _active_transform_item_obj(self):
        active = self.main.current_transform_data_item() if hasattr(self.main, 'current_transform_data_item') else None
        if active is None:
            return None
        active_id = active.get('id')
        for item in self.scene.items():
            if isinstance(item, TypesettingItem) and not getattr(item, "is_paste_preview", False):
                if item.data is active or str(item.data.get('id')) == str(active_id):
                    return item
        return None

    def _text_item_saved_work_polygon(self, item):
        """Return the current text interaction polygon in scene coordinates.

        This must match TypesettingItem.interaction_hit_rect(), which is the same
        rectangle used by the red guide box, item shape(), click selection, move,
        and double-click editing.  Do not read data['rect'] directly here; older
        OCR/work rects can remain larger than the currently visible adjusted box.
        """
        try:
            if item is None or not isinstance(item, TypesettingItem):
                return None
            if getattr(item, "is_paste_preview", False):
                return None
            try:
                if hasattr(item, "isVisible") and not item.isVisible():
                    return None
            except Exception:
                pass

            try:
                if hasattr(item, "interaction_hit_rect"):
                    local_rect = item.interaction_hit_rect()
                else:
                    local_rect = item.text_area_rect()
            except Exception:
                local_rect = None
            if local_rect is None or local_rect.isNull() or local_rect.width() <= 0 or local_rect.height() <= 0:
                return None
            return item.mapToScene(QRectF(local_rect))
        except Exception:
            return None

    def _text_item_click_rect_contains(self, item, scene_pos):
        """Return True only inside the text selection guide polygon.

        This uses _text_item_saved_work_polygon(), so untouched OCR items remain
        strict OCR/work-rect hits, while manual/text-anchored items follow the
        same tight red guide box drawn by TypesettingItem.paint().  Qt's broad
        glyph/sceneBoundingRect hit-test is still deliberately ignored.
        """
        try:
            poly = self._text_item_saved_work_polygon(item)
            if poly is None or poly.count() <= 0:
                return False
            hit_path = QPainterPath()
            hit_path.addPolygon(poly)
            hit_path.closeSubpath()
            return bool(hit_path.contains(QPointF(scene_pos)))
        except Exception:
            return False

    def _iter_text_hit_items(self):
        """Lightweight top-to-bottom text hit list.

        The list is rebuilt on demand from scene items.  This is intentionally a
        simple QRectF hit path: even 100 text boxes only means 100 rect contains
        checks, which is cheaper and more predictable than path/shape hit-tests.
        """
        try:
            items = [
                item for item in self.scene.items()
                if isinstance(item, TypesettingItem) and not getattr(item, "is_paste_preview", False)
            ]
        except Exception:
            items = []
        try:
            items.sort(key=lambda it: float(it.zValue()), reverse=True)
        except Exception:
            pass
        return items

    def _scene_text_item_at(self, scene_pos):
        active_item = self._active_transform_item_obj()
        if active_item is not None:
            try:
                local = active_item.mapFromScene(scene_pos)
                action = active_item.transform_action_at(local) if active_item.data.get('_transform_mode', False) else None
                if not action and active_item.data.get('_skew_mode', False):
                    action = active_item.skew_action_at(local)
                if not action and active_item.data.get('_trapezoid_mode', False):
                    action = active_item.trapezoid_action_at(local)
                if not action and active_item.data.get('_arc_mode', False):
                    action = active_item.arc_action_at(local)
                if action or self._text_item_click_rect_contains(active_item, scene_pos):
                    return active_item
            except Exception:
                pass

        # First-class YSB hit-test: OCR/work rect is the clickable area.
        for item in self._iter_text_hit_items():
            if self._text_item_click_rect_contains(item, scene_pos):
                return item

        # Do not fall back to Qt's broad scene hit-test for text selection.  A
        # TypesettingItem's shape/bounding path can include painted overflow,
        # shadows, old caret repaint areas, or transform guide padding; accepting
        # that here would make text selectable outside its OCR/text rectangle.
        return None

    def _begin_direct_text_drag_candidate(self, item, scene_pos):
        """Prepare a YSB-owned text drag after consuming the press event.

        The post-edit selection lock must consume blank-slot clicks so Qt does not
        clear the selection, but a consumed press also prevents QGraphicsItem's
        default drag.  This lightweight path restores drag by storing the press and
        moving the already-rendered text item ourselves once the mouse passes the
        normal drag threshold.
        """
        if item is None or not isinstance(item, TypesettingItem):
            return False
        try:
            self._direct_text_drag_item = item
            self._direct_text_drag_scene_press = QPointF(scene_pos)
            self._direct_text_drag_item_press = QPointF(item.pos())
            self._direct_text_drag_started = False
            try:
                self._direct_text_drag_old_xoff = int(item.data.get('x_off', 0) or 0)
                self._direct_text_drag_old_yoff = int(item.data.get('y_off', 0) or 0)
            except Exception:
                self._direct_text_drag_old_xoff = 0
                self._direct_text_drag_old_yoff = 0
            try:
                self._direct_text_drag_before_geometry = {
                    "rect": {"exists": 'rect' in item.data, "value": copy.deepcopy(item.data.get('rect'))},
                    "x_off": {"exists": 'x_off' in item.data, "value": self._direct_text_drag_old_xoff},
                    "y_off": {"exists": 'y_off' in item.data, "value": self._direct_text_drag_old_yoff},
                    "manual_text_rect": {"exists": 'manual_text_rect' in item.data, "value": copy.deepcopy(item.data.get('manual_text_rect'))},
                    "text_anchor_mode": {"exists": 'text_anchor_mode' in item.data, "value": copy.deepcopy(item.data.get('text_anchor_mode'))},
                }
            except Exception:
                self._direct_text_drag_before_geometry = {
                    "x_off": {"exists": True, "value": self._direct_text_drag_old_xoff},
                    "y_off": {"exists": True, "value": self._direct_text_drag_old_yoff},
                }
            try:
                item._begin_text_move_fast_path()
            except Exception:
                pass
            try:
                self._text_select_trace('TEXT_DIRECT_DRAG_PENDING', text_id=item.data.get('id'))
            except Exception:
                pass
            return True
        except Exception:
            self._direct_text_drag_item = None
            self._direct_text_drag_scene_press = None
            self._direct_text_drag_item_press = None
            self._direct_text_drag_started = False
            return False

    def _clear_direct_text_drag_candidate(self):
        self._direct_text_drag_item = None
        self._direct_text_drag_scene_press = None
        self._direct_text_drag_item_press = None
        self._direct_text_drag_started = False
        self._direct_text_drag_before_geometry = None

    def _update_direct_text_drag_candidate(self, event):
        item = getattr(self, '_direct_text_drag_item', None)
        if item is None:
            return False
        try:
            press = QPointF(getattr(self, '_direct_text_drag_scene_press', None))
            item_press = QPointF(getattr(self, '_direct_text_drag_item_press', None))
            pt = self.mapToScene(event.pos())
            delta = QPointF(pt) - press
            threshold = 4
            try:
                threshold = QApplication.startDragDistance()
            except Exception:
                pass
            if not getattr(self, '_direct_text_drag_started', False):
                if abs(float(delta.x())) + abs(float(delta.y())) < max(1, int(threshold)):
                    event.accept()
                    return True
                self._direct_text_drag_started = True
                try:
                    if hasattr(self.main, 'clear_text_selection_restore_lock'):
                        self.main.clear_text_selection_restore_lock()
                except Exception:
                    pass
                try:
                    self._text_select_trace('TEXT_DIRECT_DRAG_BEGIN', text_id=item.data.get('id'))
                except Exception:
                    pass
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                try:
                    delta = item._axis_locked_delta_for_shift_drag(delta)
                except Exception:
                    pass
            item.setPos(item_press + delta)
            try:
                item.update()
            except Exception:
                pass
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()
            return True
        except Exception:
            return False

    def _finish_direct_text_drag_candidate(self, event):
        item = getattr(self, '_direct_text_drag_item', None)
        if item is None:
            return False
        started = bool(getattr(self, '_direct_text_drag_started', False))
        try:
            if not started:
                try:
                    item._finish_text_move_fast_path()
                except Exception:
                    pass
                self._clear_direct_text_drag_candidate()
                event.accept()
                return True

            try:
                new_x_off, new_y_off = item.current_text_offsets_from_item_pos(item.pos())
            except Exception:
                new_x_off = int(item.data.get('x_off', 0) or 0)
                new_y_off = int(item.data.get('y_off', 0) or 0)
            old_x_off = int(getattr(self, '_direct_text_drag_old_xoff', item.data.get('x_off', 0) or 0))
            old_y_off = int(getattr(self, '_direct_text_drag_old_yoff', item.data.get('y_off', 0) or 0))
            before_geometry = getattr(self, '_direct_text_drag_before_geometry', None)
            if new_x_off != old_x_off or new_y_off != old_y_off:
                main = getattr(self, 'main', None)
                use_command_undo = bool(main is not None and hasattr(main, 'push_text_geometry_command'))
                if not use_command_undo and main is not None and hasattr(main, 'undo_text_checkpoint'):
                    try:
                        main.undo_text_checkpoint('텍스트 이동')
                    except Exception:
                        pass
                try:
                    item.prepareGeometryChange()
                except Exception:
                    pass
                item.data['x_off'] = int(new_x_off)
                item.data['y_off'] = int(new_y_off)
                try:
                    item.update()
                except Exception:
                    pass
                if use_command_undo:
                    try:
                        if not isinstance(before_geometry, dict):
                            before_geometry = {
                                "x_off": {"exists": 'x_off' in item.data, "value": old_x_off},
                                "y_off": {"exists": 'y_off' in item.data, "value": old_y_off},
                            }
                        main.push_text_geometry_command(
                            item.data,
                            before_values=before_geometry,
                            after_values={
                                "x_off": {"exists": True, "value": int(new_x_off)},
                                "y_off": {"exists": True, "value": int(new_y_off)},
                            },
                            reason='텍스트 이동',
                            fields=['x_off', 'y_off'],
                            component_type='text_position',
                        )
                    except Exception:
                        pass
                if main is not None:
                    try:
                        main._text_move_direct_data_flushed = True
                        main._text_move_direct_data_flushed_ids = {str(item.data.get('id'))}
                    except Exception:
                        pass
                    try:
                        if hasattr(main, 'on_text_item_moved'):
                            main.on_text_item_moved(f"📍 텍스트 이동됨 (ID: {item.data.get('id')})")
                    except Exception:
                        pass
                try:
                    self._text_select_trace('TEXT_DIRECT_DRAG_DONE', text_id=item.data.get('id'), x_off=int(new_x_off), y_off=int(new_y_off))
                except Exception:
                    pass
            try:
                item._finish_text_move_fast_path()
            except Exception:
                pass
            self._clear_direct_text_drag_candidate()
            self.force_tool_cursor_refresh(delay_followups=True)
            event.accept()
            return True
        except Exception:
            try:
                if item is not None:
                    item._finish_text_move_fast_path()
            except Exception:
                pass
            self._clear_direct_text_drag_candidate()
            self.force_tool_cursor_refresh(delay_followups=True)
            return False

    def _final_text_hit_debug_enabled(self):
        try:
            return bool(getattr(self.main, "debug_text_hit_test", False) or getattr(self, "debug_text_hit_test", False))
        except Exception:
            return False

    def _log_final_text_hit_debug(self, message):
        if not self._final_text_hit_debug_enabled():
            return
        try:
            if hasattr(self.main, "log"):
                self.main.log(message)
        except Exception:
            pass

    def _text_select_trace(self, event, **fields):
        """Always-on lightweight trace for the remaining post-edit selection drop bug."""
        try:
            if getattr(self.main, 'audit_boundary_event', None) is None:
                return
            selected = []
            try:
                for item in self.scene.selectedItems():
                    if isinstance(item, TypesettingItem):
                        selected.append(str(item.data.get('id')))
            except Exception:
                pass
            active = self.main.current_transform_data_item() if hasattr(self.main, 'current_transform_data_item') else None
            active_id = active.get('id') if isinstance(active, dict) else None
            self.main.audit_boundary_event(event, selected_ids=','.join(selected), active_id=active_id, **fields)
        except Exception:
            pass

    def _is_final_move_mode(self):
        try:
            return (
                getattr(self.main, "cb_mode", None) is not None
                and self.main.cb_mode.currentIndex() == 4
                and self.draw_mode is None
            )
        except Exception:
            return False

    def _cad_text_selection_enabled(self):
        """CAD 방식의 기본 선택 문법: 최종화면 + 이동 모드(draw_mode 없음)에서만 동작한다."""
        try:
            return (
                self.is_cad_operation_mode()
                and getattr(self.main, "cb_mode", None) is not None
                and self.main.cb_mode.currentIndex() == 4
                and getattr(self, "draw_mode", None) is None
            )
        except Exception:
            return False

    def _cad_text_items(self):
        try:
            return [item for item in self.scene.items() if isinstance(item, TypesettingItem) and not getattr(item, "is_paste_preview", False)]
        except Exception:
            return []

    def _cad_text_item_work_polygon(self, item):
        """Return the scene-space guide polygon used for text selection.

        Both click selection and left-to-right window selection use the same
        polygon as _text_item_saved_work_polygon().  Untouched OCR rows stay on
        the strict OCR/work rect, while manual/text-anchored rows follow the red
        guide box from TypesettingItem.text_area_rect().
        """
        return self._text_item_saved_work_polygon(item)

    def _cad_text_item_hit_path(self, item):
        """CAD 텍스트 선택용 절대 hit path.

        텍스트 클릭/누적선택/드래그 시작은 화면의 빨간 작업 박스와 같은 polygon 안에서만
        허용한다.  transform_rect(), sceneBoundingRect(), Qt shape 같은 넓은 fallback은
        여기서 절대 쓰지 않는다.
        """
        path = QPainterPath()
        try:
            poly = self._cad_text_item_work_polygon(item)
            if poly is None or poly.count() <= 0:
                return path
            path.addPolygon(poly)
            path.closeSubpath()
        except Exception:
            return QPainterPath()
        return path

    def _cad_selection_rect_contains_work_polygon(self, sel_rect, poly):
        """True when the selection rectangle fully covers the OCR/work polygon."""
        try:
            if poly is None or poly.count() <= 0:
                return False
            for i in range(poly.count()):
                if not sel_rect.contains(poly.at(i)):
                    return False
            return True
        except Exception:
            return False

    def _cad_text_item_rect(self, item):
        """CAD 영역 선택용 bounding rect.

        반환값도 strict OCR/work hit path의 boundingRect일 뿐이다.
        직접 클릭 판정은 이 boundingRect가 아니라 _cad_text_item_hit_path().contains()를 쓴다.
        """
        try:
            path = self._cad_text_item_hit_path(item)
            if path is not None and not path.isEmpty():
                return path.boundingRect()
        except Exception:
            pass
        return QRectF()

    def _cad_text_item_at(self, scene_pos):
        try:
            pt = QPointF(scene_pos)
        except Exception:
            return None
        candidates = []
        for item in self._cad_text_items():
            try:
                path = self._cad_text_item_hit_path(item)
                if path is not None and (not path.isEmpty()) and path.contains(pt):
                    candidates.append(item)
            except Exception:
                pass
        if not candidates:
            return None
        try:
            candidates.sort(key=lambda it: float(it.zValue()), reverse=True)
        except Exception:
            pass
        return candidates[0]

    def _cad_selected_text_ids(self):
        ids = []
        try:
            for item in self.scene.selectedItems():
                if isinstance(item, TypesettingItem):
                    tid = getattr(item, "data", {}).get("id")
                    if tid is not None:
                        ids.append(str(tid))
        except Exception:
            pass
        return ids

    def _cad_set_preferred_text_style_source(self, item=None, item_id=None):
        """Remember which selected text should drive style/number controls."""
        try:
            if item_id is None and item is not None:
                item_id = getattr(item, "data", {}).get("id")
            if item_id is None:
                setattr(self.main, "_last_text_style_source_id", None)
            else:
                setattr(self.main, "_last_text_style_source_id", str(item_id))
        except Exception:
            pass

    def _cad_pick_selected_style_source_after_change(self):
        try:
            preferred = getattr(self.main, "_last_text_style_source_id", None)
            selected = [it for it in self.scene.selectedItems() if isinstance(it, TypesettingItem)]
            if preferred is not None:
                for it in selected:
                    try:
                        if str(getattr(it, "data", {}).get("id")) == str(preferred):
                            return
                    except Exception:
                        pass
            if selected:
                self._cad_set_preferred_text_style_source(selected[-1])
            else:
                self._cad_set_preferred_text_style_source(item_id=None)
        except Exception:
            pass

    def _cad_push_text_selection_undo(self):
        try:
            ids = self._cad_selected_text_ids()
            stack = getattr(self, "_cad_text_selection_undo_stack", None)
            if stack is None:
                self._cad_text_selection_undo_stack = []
                stack = self._cad_text_selection_undo_stack
            if stack and stack[-1] == ids:
                return
            stack.append(list(ids))
            limit = int(getattr(self, "_cad_text_selection_undo_limit", 80) or 80)
            if len(stack) > limit:
                del stack[0:len(stack) - limit]
        except Exception:
            pass

    def _cad_apply_text_selection_ids(self, ids, *, notify=True):
        idset = {str(x) for x in (ids or []) if x is not None}
        try:
            old = self.scene.blockSignals(True)
        except Exception:
            old = False
        try:
            for item in self._cad_text_items():
                try:
                    item.setSelected(str(getattr(item, "data", {}).get("id")) in idset)
                except Exception:
                    pass
        finally:
            try:
                self.scene.blockSignals(old)
            except Exception:
                pass
        try:
            if idset:
                preferred = getattr(self.main, "_last_text_style_source_id", None)
                if preferred is None or str(preferred) not in idset:
                    self._cad_set_preferred_text_style_source(item_id=list(idset)[-1])
            else:
                self._cad_set_preferred_text_style_source(item_id=None)
        except Exception:
            pass
        if notify:
            try:
                if hasattr(self.main, "on_scene_selection_changed"):
                    self.main.on_scene_selection_changed()
            except Exception:
                pass

    def undo_cad_text_selection_step(self):
        """Ctrl+Z: 직전 CAD 선택 누적/해제 상태로만 되돌린다."""
        try:
            if not self._cad_text_selection_enabled():
                return False
            stack = getattr(self, "_cad_text_selection_undo_stack", []) or []
            if not stack:
                return False
            prev_ids = stack.pop()
            self._cad_apply_text_selection_ids(prev_ids, notify=True)
            return True
        except Exception:
            return False

    def clear_cad_text_selection_undo_stack(self):
        try:
            self._cad_text_selection_undo_stack = []
        except Exception:
            pass

    def _cad_set_selection_from_items(self, items, *, subtract=False, push_undo=True, active_item=None, replace=False):
        items = [it for it in (items or []) if isinstance(it, TypesettingItem)]
        if push_undo:
            self._cad_push_text_selection_undo()
        try:
            old = self.scene.blockSignals(True)
        except Exception:
            old = False
        try:
            if subtract:
                for item in items:
                    try:
                        item.setSelected(False)
                    except Exception:
                        pass
            else:
                if replace:
                    keep = set(items)
                    for item in self._cad_text_items():
                        try:
                            item.setSelected(item in keep)
                        except Exception:
                            pass
                else:
                    for item in items:
                        try:
                            item.setSelected(True)
                        except Exception:
                            pass
        finally:
            try:
                self.scene.blockSignals(old)
            except Exception:
                pass
        try:
            if active_item is not None and (not subtract) and active_item.isSelected():
                self._cad_set_preferred_text_style_source(active_item)
            else:
                self._cad_pick_selected_style_source_after_change()
        except Exception:
            pass
        try:
            if hasattr(self.main, "on_scene_selection_changed"):
                self.main.on_scene_selection_changed()
        except Exception:
            pass

    def _cad_items_for_rect_selection(self, rect, crossing=False):
        try:
            sel_rect = QRectF(rect).normalized()
        except Exception:
            return []
        sel_path = QPainterPath()
        try:
            sel_path.addRect(sel_rect)
        except Exception:
            pass
        out = []
        for item in self._cad_text_items():
            try:
                hit_path = self._cad_text_item_hit_path(item)
                if hit_path is None or hit_path.isEmpty():
                    continue
                if crossing:
                    ok = sel_path.intersects(hit_path)
                else:
                    # 좌->우 window 선택은 빨간 작업 박스 polygon 전체가 선택 사각형 안에
                    # 들어올 때만 선택한다. 클릭 판정과 드래그 판정이 같은 기준을 본다.
                    poly = self._cad_text_item_work_polygon(item)
                    ok = self._cad_selection_rect_contains_work_polygon(sel_rect, poly)
                if ok:
                    out.append(item)
            except Exception:
                pass
        return out

    def _cad_path_from_points(self, points):
        pts = list(points or [])
        path = QPainterPath()
        if not pts:
            return path
        try:
            path.moveTo(QPointF(pts[0]))
            for p in pts[1:]:
                path.lineTo(QPointF(p))
        except Exception:
            pass
        return path

    def _cad_items_for_free_selection(self, points):
        pts = list(points or [])
        if len(pts) < 2:
            return []
        path = self._cad_path_from_points(pts)
        try:
            stroker = QPainterPathStroker()
            # 텍스트를 지나가며 쓸어 선택하는 도구라 너무 얇으면 체감이 나쁘다.
            stroker.setWidth(max(6.0, float(self.ui_handle_size(8.0, minimum=6.0))))
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            area = stroker.createStroke(path)
        except Exception:
            area = path
        out = []
        for item in self._cad_text_items():
            try:
                rp = self._cad_text_item_hit_path(item)
                if rp is None or rp.isEmpty():
                    continue
                center = rp.boundingRect().center()
                if area.intersects(rp) or area.contains(center):
                    out.append(item)
            except Exception:
                pass
        return out

    def _cad_clear_text_selection_previews(self):
        for attr in ("_cad_text_select_rect_preview_item", "_cad_text_select_path_preview_item"):
            try:
                item = getattr(self, attr, None)
                if item is not None and item.scene() is not None:
                    self.scene.removeItem(item)
            except Exception:
                pass
            try:
                setattr(self, attr, None)
            except Exception:
                pass

    def _cad_draw_text_selection_rect_preview(self, now):
        try:
            start = getattr(self, "_cad_text_select_rect_start", None)
            if start is None or now is None:
                return
            rect = QRectF(start, QPointF(now)).normalized()
            path = QPainterPath()
            path.addRect(rect)
            item = getattr(self, "_cad_text_select_rect_preview_item", None)
            if item is None or item.scene() is None:
                item = QGraphicsPathItem()
                item.setZValue(100000)
                item.setPen(QPen(QColor(80, 180, 255, 220), max(1.0, self.ui_handle_size(1.0, minimum=1.0)), Qt.PenStyle.DashLine))
                item.setBrush(QBrush(QColor(80, 180, 255, 36)))
                self.scene.addItem(item)
                self._cad_text_select_rect_preview_item = item
            item.setPath(path)
        except Exception:
            pass

    def _cad_draw_text_selection_free_preview(self):
        try:
            points = list(getattr(self, "_cad_text_select_path_points", []) or [])
            if len(points) < 2:
                return
            path = self._cad_path_from_points(points)
            item = getattr(self, "_cad_text_select_path_preview_item", None)
            if item is None or item.scene() is None:
                item = QGraphicsPathItem()
                item.setZValue(100000)
                item.setPen(QPen(QColor(80, 255, 160, 230), max(1.0, self.ui_handle_size(2.0, minimum=1.0)), Qt.PenStyle.SolidLine))
                item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                self.scene.addItem(item)
                self._cad_text_select_path_preview_item = item
            item.setPath(path)
        except Exception:
            pass

    def cancel_cad_text_selection_interaction(self, *, clear_preview=True):
        had = bool(
            getattr(self, "_cad_text_select_rect_start", None) is not None
            or getattr(self, "_cad_text_select_path_points", None)
            or getattr(self, "_cad_text_group_drag_items", None)
        )
        self._cad_text_select_rect_start = None
        self._cad_text_select_path_points = []
        self._cad_text_select_mouse_press_scene = None
        self._cad_text_select_mouse_press_view = None
        self._cad_text_select_mouse_shift = False
        self._cad_text_select_mode = None
        self._cad_text_group_drag_items = []
        self._cad_text_group_drag_press_scene = None
        self._cad_text_group_drag_start_positions = {}
        self._cad_text_group_drag_old_offsets = {}
        self._cad_text_group_drag_started = False
        if clear_preview:
            self._cad_clear_text_selection_previews()
        return had

    def _cad_begin_group_drag(self, hit_item, scene_pos, event, collapse_on_click=False):
        try:
            selected = [x for x in self.scene.selectedItems() if isinstance(x, TypesettingItem)]
        except Exception:
            selected = []
        if hit_item is not None and hit_item not in selected:
            selected.append(hit_item)
        if not selected:
            return False
        self._cad_text_group_drag_items = list(selected)
        self._cad_text_group_drag_single_click_item = hit_item
        self._cad_text_group_drag_collapse_on_click = bool(collapse_on_click)
        self._cad_text_group_drag_press_scene = QPointF(scene_pos)
        self._cad_text_group_drag_start_positions = {id(item): QPointF(item.pos()) for item in selected}
        self._cad_text_group_drag_old_offsets = {}
        for item in selected:
            try:
                self._cad_text_group_drag_old_offsets[id(item)] = (
                    int(round(float(item.data.get('x_off', 0) or 0))),
                    int(round(float(item.data.get('y_off', 0) or 0))),
                )
            except Exception:
                self._cad_text_group_drag_old_offsets[id(item)] = (0, 0)
        self._cad_text_group_drag_started = False
        try:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        except Exception:
            pass
        return True

    def _cad_update_group_drag(self, scene_pos):
        items = list(getattr(self, "_cad_text_group_drag_items", []) or [])
        press = getattr(self, "_cad_text_group_drag_press_scene", None)
        if not items or press is None or scene_pos is None:
            return False
        try:
            delta = QPointF(scene_pos) - QPointF(press)
        except Exception:
            return False
        try:
            if not getattr(self, "_cad_text_group_drag_started", False):
                if (delta.x() * delta.x() + delta.y() * delta.y()) < 9.0:
                    return True
                self._cad_text_group_drag_started = True
                # 콘텐츠 이동이 시작되면 선택 변경 undo와 섞이지 않도록 선택 undo stack은 비운다.
                self.clear_cad_text_selection_undo_stack()
                try:
                    if hasattr(self.main, 'push_page_text_undo'):
                        self.main.push_page_text_undo('텍스트 다중 이동')
                    elif hasattr(self.main, 'undo_text_checkpoint'):
                        self.main.undo_text_checkpoint('텍스트 다중 이동')
                except Exception:
                    pass
                try:
                    for item in items:
                        if hasattr(item, '_begin_text_move_fast_path'):
                            item._begin_text_move_fast_path()
                except Exception:
                    pass
            for item in items:
                start = self._cad_text_group_drag_start_positions.get(id(item), QPointF(item.pos()))
                item.setPos(QPointF(start.x() + delta.x(), start.y() + delta.y()))
                item.update()
            return True
        except Exception:
            return False

    def _cad_finish_group_drag(self):
        items = list(getattr(self, "_cad_text_group_drag_items", []) or [])
        if not items:
            self.cancel_cad_text_selection_interaction(clear_preview=False)
            return False
        moved = bool(getattr(self, "_cad_text_group_drag_started", False))
        ids = []
        if moved:
            for item in items:
                try:
                    old_x, old_y = self._cad_text_group_drag_old_offsets.get(id(item), (int(item.data.get('x_off', 0) or 0), int(item.data.get('y_off', 0) or 0)))
                    start = self._cad_text_group_drag_start_positions.get(id(item), QPointF(item.pos()))
                    dx = int(round(float(item.pos().x() - start.x())))
                    dy = int(round(float(item.pos().y() - start.y())))
                    item.data['x_off'] = int(old_x + dx)
                    item.data['y_off'] = int(old_y + dy)
                    ids.append(item.data.get('id'))
                    item.setSelected(True)
                    if hasattr(item, '_finish_text_move_fast_path'):
                        item._finish_text_move_fast_path()
                except Exception:
                    pass
            try:
                if hasattr(self.main, 'finalize_text_change'):
                    self.main.finalize_text_change(ids=ids, fields=['x_off', 'y_off'], reason='텍스트 다중 이동', delay_ms=900, update_table=True, refresh_scene=False)
                elif hasattr(self.main, 'schedule_deferred_auto_save_project'):
                    self.main.schedule_deferred_auto_save_project(900)
            except Exception:
                pass
            try:
                if hasattr(self.main, 'on_scene_selection_changed'):
                    self.main.on_scene_selection_changed()
            except Exception:
                pass
        else:
            for item in items:
                try:
                    if hasattr(item, '_finish_text_move_fast_path'):
                        item._finish_text_move_fast_path()
                except Exception:
                    pass
            # A plain click is not an area selection.  If overlapping boxes or a
            # previous area selection left several text items selected, the no-drag
            # release resolves the click to the single top hit item only.
            try:
                one = getattr(self, "_cad_text_group_drag_single_click_item", None)
                if bool(getattr(self, "_cad_text_group_drag_collapse_on_click", False)) and one is not None:
                    self._cad_set_selection_from_items([one], subtract=False, push_undo=True, active_item=one, replace=True)
            except Exception:
                pass
        self._cad_text_group_drag_items = []
        self._cad_text_group_drag_single_click_item = None
        self._cad_text_group_drag_collapse_on_click = False
        self._cad_text_group_drag_press_scene = None
        self._cad_text_group_drag_start_positions = {}
        self._cad_text_group_drag_old_offsets = {}
        self._cad_text_group_drag_started = False
        try:
            self.force_tool_cursor_refresh(delay_followups=True)
        except Exception:
            pass
        return moved

    def _cad_text_selection_mouse_press(self, e):
        if not self._cad_text_selection_enabled() or e.button() != Qt.MouseButton.LeftButton:
            return False
        try:
            if hasattr(self.main, 'current_transform_data_item') and self.main.current_transform_data_item() is not None:
                return False
        except Exception:
            pass
        pt = self.mapToScene(e.pos())
        # 사각형 click-click 선택이 진행 중이면 두 번째 클릭으로 확정한다.
        if getattr(self, "_cad_text_select_rect_start", None) is not None and getattr(self, "_cad_text_select_mode", None) == "rect_pending":
            start = QPointF(self._cad_text_select_rect_start)
            rect = QRectF(start, pt)
            crossing = float(pt.x()) < float(start.x())
            subtract = bool(getattr(self, "_cad_text_select_mouse_shift", False) or (e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            items = self._cad_items_for_rect_selection(rect, crossing=crossing)
            self._cad_set_selection_from_items(items, subtract=subtract, push_undo=True, active_item=(items[-1] if items and not subtract else None))
            self.cancel_cad_text_selection_interaction(clear_preview=True)
            e.accept()
            return True

        hit = self._cad_text_item_at(pt)
        subtract = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if hit is not None:
            if subtract:
                self._cad_set_selection_from_items([hit], subtract=True, push_undo=True, active_item=None)
                e.accept()
                return True
            # Plain individual click is still an accumulating CAD selection:
            # one click may add exactly one top OCR/work-hit text item.  It must
            # never collect every overlapping text item, but it also must not
            # replace the existing selection set unless the user explicitly clears
            # it or uses another selection operation.
            try:
                selected_now = [x for x in self.scene.selectedItems() if isinstance(x, TypesettingItem)]
            except Exception:
                selected_now = []
            already_selected = bool(hit in selected_now)
            if not already_selected:
                self._cad_set_selection_from_items([hit], subtract=False, push_undo=True, active_item=hit, replace=False)
            else:
                self._cad_set_preferred_text_style_source(hit)
                try:
                    if hasattr(self.main, "on_scene_selection_changed"):
                        self.main.on_scene_selection_changed()
                except Exception:
                    pass
            self._cad_begin_group_drag(hit, pt, e, collapse_on_click=False)
            e.accept()
            return True

        # 배경 클릭: 첫 점을 찍고, 클릭-클릭 사각형 선택 또는 누르고 끌기 자유형 선택 후보로 둔다.
        self._cad_text_select_mouse_press_scene = QPointF(pt)
        self._cad_text_select_mouse_press_view = e.pos()
        self._cad_text_select_mouse_shift = subtract
        self._cad_text_select_mode = "press_pending"
        e.accept()
        return True

    def _cad_text_selection_mouse_move(self, e):
        pt = self.mapToScene(e.pos())
        # A strict single-hit press can start a group/text drag even from the
        # final_text tool path.  Keep the drag candidate alive regardless of the
        # area-selection tool state.
        if getattr(self, "_cad_text_group_drag_items", None):
            if e.buttons() & Qt.MouseButton.LeftButton:
                if self._cad_update_group_drag(pt):
                    e.accept()
                    return True
            return False
        if not self._cad_text_selection_enabled():
            return False
        mode = getattr(self, "_cad_text_select_mode", None)
        if mode == "rect_pending" and getattr(self, "_cad_text_select_rect_start", None) is not None and not (e.buttons() & Qt.MouseButton.LeftButton):
            self._cad_draw_text_selection_rect_preview(pt)
            e.accept()
            return True
        if mode == "press_pending" and (e.buttons() & Qt.MouseButton.LeftButton):
            start = getattr(self, "_cad_text_select_mouse_press_scene", None)
            if start is None:
                return False
            points = getattr(self, "_cad_text_select_path_points", []) or []
            if not points:
                points = [QPointF(start)]
            points = self._append_scene_point_if_moved(points, pt, min_sq=9.0)
            self._cad_text_select_path_points = points
            # 3px 이상 움직였으면 클릭-클릭 사각형이 아니라 자유형 경로 선택이다.
            try:
                v0 = self._cad_text_select_mouse_press_view
                dist = (e.pos().x() - v0.x()) ** 2 + (e.pos().y() - v0.y()) ** 2 if v0 is not None else 999
            except Exception:
                dist = 999
            if dist >= 9:
                self._cad_text_select_mode = "free_drag"
                self._cad_draw_text_selection_free_preview()
                e.accept()
                return True
        if mode == "free_drag" and (e.buttons() & Qt.MouseButton.LeftButton):
            points = self._append_scene_point_if_moved(getattr(self, "_cad_text_select_path_points", []) or [], pt, min_sq=9.0)
            self._cad_text_select_path_points = points
            self._cad_draw_text_selection_free_preview()
            e.accept()
            return True
        return False

    def _cad_text_selection_mouse_release(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return False
        # Finish a strict single-hit/group drag even if it was started while the
        # final_text tool was active rather than the plain CAD move mode.
        if getattr(self, "_cad_text_group_drag_items", None):
            self._cad_finish_group_drag()
            e.accept()
            return True
        if not self._cad_text_selection_enabled():
            return False
        mode = getattr(self, "_cad_text_select_mode", None)
        if mode == "free_drag":
            items = self._cad_items_for_free_selection(getattr(self, "_cad_text_select_path_points", []) or [])
            self._cad_set_selection_from_items(items, subtract=bool(getattr(self, "_cad_text_select_mouse_shift", False) or (e.modifiers() & Qt.KeyboardModifier.ShiftModifier)), push_undo=True, active_item=(items[-1] if items and not bool(getattr(self, "_cad_text_select_mouse_shift", False) or (e.modifiers() & Qt.KeyboardModifier.ShiftModifier)) else None))
            self.cancel_cad_text_selection_interaction(clear_preview=True)
            e.accept()
            return True
        if mode == "press_pending":
            # 클릭만 했으면 사각형 click-click 선택 시작점으로 고정한다.
            self._cad_text_select_rect_start = QPointF(getattr(self, "_cad_text_select_mouse_press_scene", self.mapToScene(e.pos())))
            self._cad_text_select_mode = "rect_pending"
            self._cad_draw_text_selection_rect_preview(self._cad_text_select_rect_start)
            e.accept()
            return True
        return False

    def _raster_text_alpha_hit(self, item, scene_pos, radius=3):
        """객체화 텍스트의 실제 보이는 픽셀을 기준으로 hit-test한다.

        itemAt()/scene.items(scene_pos)는 최상단 페인팅 레이어나 아이템 shape 때문에
        실제 글자 클릭과 다르게 동작할 수 있다. 그래서 객체화 텍스트는 알파 채널을
        직접 검사한다. 얇은 획/안티앨리어싱을 고려해 작은 반경도 같이 본다.
        """
        if item is None or not getattr(item, "data", {}).get('rasterized_text'):
            return False
        img = getattr(item, '_raster_image', None)
        rect = getattr(item, '_raster_rect', QRectF())
        if img is None or img.isNull() or rect.isNull():
            return False
        try:
            local = item.mapFromScene(QPointF(scene_pos))
        except Exception:
            return False
        if not rect.adjusted(-radius, -radius, radius, radius).contains(local):
            return False
        w = img.width()
        h = img.height()
        cx = int(round(local.x()))
        cy = int(round(local.y()))
        r = max(0, int(radius or 0))
        for yy in range(max(0, cy - r), min(h - 1, cy + r) + 1):
            for xx in range(max(0, cx - r), min(w - 1, cx + r) + 1):
                try:
                    if img.pixelColor(xx, yy).alpha() > 8:
                        return True
                except Exception:
                    return False
        return False

    def _raster_text_rect_hit(self, item, scene_pos):
        if item is None or not getattr(item, "data", {}).get('rasterized_text'):
            return False
        rect = getattr(item, '_raster_rect', QRectF())
        if rect.isNull():
            return False
        try:
            return rect.contains(item.mapFromScene(QPointF(scene_pos)))
        except Exception:
            return False

    def _raster_text_item_at(self, scene_pos):
        """객체화 텍스트를 페인팅 레이어보다 먼저 직접 찾는다.

        기존 scene.items(scene_pos) / itemAt() 경로는 최종 페인팅 레이어, 배경 픽스맵,
        ScrollHandDrag 상태에 막혀 객체화 텍스트가 선택되지 않을 수 있다.
        그래서 모든 TypesettingItem을 직접 검사한다.
        """
        raster_items = []
        try:
            for item in self.scene.items():
                if isinstance(item, TypesettingItem) and not getattr(item, "is_paste_preview", False):
                    if bool(getattr(item, "data", {}).get('rasterized_text')):
                        raster_items.append(item)
        except Exception:
            return None

        # 이미 선택된 객체는 투명 영역 안쪽을 눌러도 다시 잡히게 한다.
        for item in raster_items:
            try:
                if item.isSelected() and self._raster_text_rect_hit(item, scene_pos):
                    return item
            except Exception:
                pass

        # 우선순위 1: 실제 보이는 알파 픽셀.
        for item in raster_items:
            if self._raster_text_alpha_hit(item, scene_pos, radius=3):
                return item

        # 우선순위 2: 투명 여백 포함 래스터 박스.
        # 얇은 글자나 완전히 지워진 객체도 선택/이동할 수 있게 마지막 폴백으로 둔다.
        for item in raster_items:
            if self._raster_text_rect_hit(item, scene_pos):
                return item
        return None

    def _begin_raster_text_view_drag(self, item, scene_pos, event):
        if item is None:
            return False
        try:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                for selected in list(self.scene.selectedItems()):
                    if selected is not item:
                        selected.setSelected(False)
            item.setSelected(True)
            if hasattr(self.main, "on_scene_selection_changed"):
                self.main.on_scene_selection_changed()
        except Exception:
            pass

        self._raster_view_drag_item = item
        self._raster_view_drag_scene_press = QPointF(scene_pos)
        self._raster_view_drag_item_press = QPointF(item.pos())
        try:
            self._raster_view_drag_old_offsets = (
                int(item.data.get('x_off', 0) or 0),
                int(item.data.get('y_off', 0) or 0),
            )
        except Exception:
            self._raster_view_drag_old_offsets = (0, 0)
        self._raster_view_drag_moved = False
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._log_final_text_hit_debug(f"🔎 객체 텍스트 선택: ID {item.data.get('id')}")
        return True

    def _finish_raster_text_view_drag(self):
        item = self._raster_view_drag_item
        if item is None:
            return
        old_offsets = self._raster_view_drag_old_offsets or (
            int(item.data.get('x_off', 0) or 0),
            int(item.data.get('y_off', 0) or 0),
        )
        self._raster_view_drag_item = None
        self._raster_view_drag_scene_press = None
        self._raster_view_drag_item_press = None
        self._raster_view_drag_old_offsets = None
        self._raster_view_drag_moved = False
        self.force_tool_cursor_refresh(delay_followups=True)

        try:
            rect = list(item.data.get('rect') or [0, 0, 1, 1])
            while len(rect) < 4:
                rect.append(1)
            new_x_off = int(round(float(item.pos().x()) - float(rect[0])))
            new_y_off = int(round(float(item.pos().y()) - float(rect[1])))
        except Exception:
            return

        old_x_off, old_y_off = old_offsets
        if new_x_off == old_x_off and new_y_off == old_y_off:
            return

        before_geometry = {
            "x_off": {"exists": 'x_off' in item.data, "value": old_x_off},
            "y_off": {"exists": 'y_off' in item.data, "value": old_y_off},
        }
        use_command_undo = bool(hasattr(self.main, 'push_text_geometry_command'))
        if not use_command_undo:
            try:
                if hasattr(self.main, 'undo_text_checkpoint'):
                    self.main.undo_text_checkpoint('텍스트 객체 이동')
            except Exception:
                pass

        item.data['x_off'] = new_x_off
        item.data['y_off'] = new_y_off
        try:
            item.update()
        except Exception:
            pass

        if use_command_undo:
            try:
                self.main.push_text_geometry_command(
                    item.data,
                    before_values=before_geometry,
                    after_values={
                        "x_off": {"exists": True, "value": new_x_off},
                        "y_off": {"exists": True, "value": new_y_off},
                    },
                    reason='텍스트 객체 이동',
                    fields=['x_off', 'y_off'],
                    component_type='text_position',
                )
            except Exception:
                pass

        try:
            if hasattr(self.main, 'sync_final_text_scene_to_data'):
                self.main.sync_final_text_scene_to_data()
        except Exception:
            pass

        if getattr(item, 'update_cb', None):
            try:
                item.update_cb(f"📍 텍스트 객체 이동됨 (ID: {item.data.get('id')})")
                return
            except Exception:
                pass

        try:
            if hasattr(self.main, 'schedule_deferred_auto_save_project'):
                self.main.schedule_deferred_auto_save_project()
            elif hasattr(self.main, 'auto_save_project'):
                self.main.auto_save_project()
        except Exception:
            pass


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

    def _clear_stroke_preview(self):
        # 실시간 브러시 미리보기는 여러 개의 작은 path chunk로 나눈다.
        # 하나의 큰 QPainterPath를 매 mouseMove마다 setPath하면 스트로크가 길어질수록 O(n) 복사가 반복되어 느려진다.
        items = []
        try:
            items.extend(list(getattr(self, "_stroke_preview_items", []) or []))
        except Exception:
            pass
        try:
            if self._stroke_preview_item is not None and self._stroke_preview_item not in items:
                items.append(self._stroke_preview_item)
        except Exception:
            pass
        for item in items:
            try:
                if item is not None and item.scene() is not None:
                    self.scene.removeItem(item)
            except Exception:
                pass
        self._stroke_preview_item = None
        self._stroke_preview_items = []
        self._stroke_preview_path = None
        self._stroke_preview_paths = []
        self._stroke_preview_last_pos = None
        self._stroke_preview_segment_count = 0
        self._stroke_preview_target = None
        self._stroke_preview_dirty_rect = None
        self._stroke_preview_color = None
        self._stroke_preview_final_mode = False

    def _make_stroke_preview_item(self, path, color, final_mode=False):
        item = QGraphicsPathItem(path)
        item.setPen(QPen(color, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        # 최종결과/마스크/가이드 전부 위에 떠야 "그리는 중" 체감이 바로 난다.
        item.setZValue(5000 if final_mode else 4900)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        try:
            item.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        except Exception:
            pass
        self.scene.addItem(item)
        return item

    def _start_stroke_preview(self, target_item, start_pos, color, final_mode=False):
        self._clear_stroke_preview()
        self._stroke_preview_target = target_item
        self._stroke_preview_final_mode = bool(final_mode)
        self._stroke_preview_color = QColor(color) if isinstance(color, QColor) else color
        path = QPainterPath(start_pos)
        # 한 점짜리 path는 실제로 그릴 선분이 없어 누른 직후 브러시가 보이지 않을 수 있다.
        # 아주 짧은 선분을 넣어 round-cap 점이 즉시 보이게 한다.
        path.lineTo(QPointF(start_pos) + QPointF(0.15, 0.0))
        self._stroke_preview_path = path
        self._stroke_preview_paths = [path]
        self._stroke_preview_last_pos = QPointF(start_pos)
        self._stroke_preview_segment_count = 0
        pad = max(2, int(self.brush_size or 1) + 4)
        self._stroke_preview_dirty_rect = QRectF(start_pos, start_pos).normalized().adjusted(-pad, -pad, pad, pad)
        try:
            item = self._make_stroke_preview_item(path, color, final_mode=final_mode)
            self._stroke_preview_item = item
            self._stroke_preview_items = [item]
            try:
                _r = self.mapFromScene(self._stroke_preview_dirty_rect).boundingRect().adjusted(-4, -4, 4, 4)
                self.viewport().update(_r)
            except Exception:
                self.viewport().update()
        except Exception:
            self._stroke_preview_item = None

    def _extend_stroke_preview(self, pos):
        if self._stroke_preview_path is None:
            return False
        try:
            now = QPointF(pos)
            last = QPointF(getattr(self, "_stroke_preview_last_pos", now) or now)
            # 너무 촘촘한 mouseMove는 같은 선분으로 보고 생략한다. 화면 반응은 유지하면서 path 폭증을 막는다.
            dx = now.x() - last.x()
            dy = now.y() - last.y()
            if (dx * dx + dy * dy) < 1.5:
                return True
            # 긴 스트로크는 작은 path chunk로 나눈다. setPath 비용이 누적되지 않게 하는 핵심.
            if int(getattr(self, "_stroke_preview_segment_count", 0) or 0) >= 24:
                new_path = QPainterPath(last)
                self._stroke_preview_path = new_path
                self._stroke_preview_paths.append(new_path)
                self._stroke_preview_segment_count = 0
                item = self._make_stroke_preview_item(new_path, self._stroke_preview_color, final_mode=self._stroke_preview_final_mode)
                self._stroke_preview_item = item
                self._stroke_preview_items.append(item)
            self._stroke_preview_path.lineTo(now)
            if self._stroke_preview_item is not None:
                self._stroke_preview_item.setPath(self._stroke_preview_path)
            self._stroke_preview_segment_count += 1
            self._stroke_preview_last_pos = now
            pad = max(2, int(self.brush_size or 1) + 4)
            r = QRectF(last, now).normalized().adjusted(-pad, -pad, pad, pad)
            self._stroke_preview_dirty_rect = self._stroke_preview_dirty_rect.united(r) if self._stroke_preview_dirty_rect is not None else r
            try:
                _r = self.mapFromScene(r).boundingRect().adjusted(-4, -4, 4, 4)
                self.viewport().update(_r)
            except Exception:
                self.viewport().update()
            return True
        except Exception:
            return False

    def _commit_stroke_preview_to_layer(self):
        target_item = self._stroke_preview_target
        paths = list(getattr(self, "_stroke_preview_paths", []) or [])
        if target_item is None or not paths:
            self._clear_stroke_preview()
            return False
        try:
            pix = target_item.pixmap()
            pix_rect = pix.rect()
            dirty = self._stroke_preview_dirty_rect
            if dirty is None:
                for path in paths:
                    dirty = path.boundingRect() if dirty is None else dirty.united(path.boundingRect())
            qrect = dirty.toAlignedRect().adjusted(-2, -2, 2, 2).intersected(pix_rect)
            if qrect.isEmpty():
                self._clear_stroke_preview()
                return False
            before_patch = pix.copy(qrect)
            painter = QPainter(pix)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(self._stroke_preview_color, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            for path in paths:
                painter.drawPath(path)
            painter.end()
            target_item.setPixmap(pix)
            target_item.update(QRectF(qrect))
            try:
                self.viewport().update(self.mapFromScene(QRectF(qrect)).boundingRect().adjusted(-4, -4, 4, 4))
            except Exception:
                self.viewport().update()
            if target_item is self.final_paint_above_item:
                self.final_paint_above_img = pix.toImage()
            elif target_item is self.final_paint_item:
                self.final_paint_img = pix.toImage()
            elif target_item is self.user_mask_item:
                self.user_mask_img = pix.toImage()
            rec = {"target_item": target_item, "dirty_rect": qrect, "patch": before_patch}
            kind = "final_paint" if self._stroke_preview_final_mode else "mask"
            reason = "최종 페인팅" if kind == "final_paint" else "마스크 브러시"
            try:
                if hasattr(self.main, "undo_push_paint_record"):
                    self.main.undo_push_paint_record(self, rec, kind=kind, reason=reason, max_history=40)
                else:
                    self.history.append(rec)
                    if len(self.history) > 40:
                        self.history.pop(0)
                    try:
                        self.redo_history.clear()
                    except Exception:
                        pass
                    self._append_paint_history_undo_marker(kind, reason)
            except Exception:
                pass
            return True
        except Exception:
            return False
        finally:
            self._clear_stroke_preview()

    def _view_undo_enabled(self):
        """Return whether pan/zoom view changes should be recorded to Undo.

        View navigation Undo is important for real editing, so the default is ON.
        Continuous wheel/scroll movement is still coalesced by MainWindow so one
        burst becomes one Undo step instead of many tiny records.
        """
        try:
            main = getattr(self, "main", None)
            if main is not None and hasattr(main, "view_navigation_undo_enabled"):
                return bool(getattr(main, "view_navigation_undo_enabled", True))
            opts = getattr(main, "app_options", {}) if main is not None else {}
            if isinstance(opts, dict) and "view_navigation_undo_enabled" in opts:
                return bool(opts.get("view_navigation_undo_enabled", True))
        except Exception:
            pass
        return True

    def _view_undo_is_suppressed(self):
        """Return True while view changes are being restored programmatically.

        Scrollbars emit valueChanged during Undo/Redo/view restoration.  Those
        signals must not create another ViewCommand, otherwise Ctrl+Z can recurse
        or keep adding phantom scroll actions.
        """
        try:
            if not self._view_undo_enabled():
                return True
            if bool(getattr(self, "_suppress_view_history", False)):
                return True
            ve = getattr(getattr(self, "main", None), "view_engine", None)
            if ve is not None and bool(getattr(ve, "suppress", False)):
                return True
            if bool(getattr(getattr(self, "main", None), "_is_rebuilding_text_layer", False)):
                return True
            if bool(getattr(getattr(self, "main", None), "_project_undo_restore_lock", False)):
                return True
            return False
        except Exception:
            return True

    def _begin_scroll_view_undo(self):
        try:
            if hasattr(self.main, 'note_ui_interaction_activity'):
                self.main.note_ui_interaction_activity(1200)
        except Exception:
            pass
        """Begin/coalesce a scrollbar view undo action.

        This method is connected directly to QScrollBar.actionTriggered.  It used
        to be referenced without an implementation, which caused AttributeError
        storms whenever the user scrolled or Qt restored a view state.
        """
        if self._view_undo_is_suppressed():
            return
        self._scrollbar_view_undo_active = True
        try:
            if not self._view_undo_is_suppressed() and hasattr(self.main, "begin_coalesced_view_undo"):
                self.main.begin_coalesced_view_undo("화면 이동", delay_ms=500)
            elif hasattr(self.main, "begin_page_view_undo"):
                self.main.begin_page_view_undo("화면 이동")
        except Exception:
            pass

    def _schedule_scroll_view_undo_finish(self):
        """Coalesce scrollbar value changes into one page-local ViewCommand."""
        if self._view_undo_is_suppressed():
            return
        try:
            if not self._scrollbar_view_undo_active:
                self._begin_scroll_view_undo()
            elif hasattr(self.main, "begin_coalesced_view_undo"):
                # Restart MainWindow's coalescing timer; finish_page_view_undo() will
                # be called by that timer after scrolling settles.
                self.main.begin_coalesced_view_undo("화면 이동", delay_ms=500)
            elif hasattr(self.main, "finish_page_view_undo"):
                self.main.finish_page_view_undo(force=False)
            if hasattr(self.main, "remember_current_view_state"):
                self.main.remember_current_view_state()
            if hasattr(self.main, "schedule_source_compare_sync"):
                self.main.schedule_source_compare_sync(180)
        except Exception:
            pass

    def _begin_view_pan_undo(self):
        try:
            if hasattr(self.main, 'note_ui_interaction_activity'):
                self.main.note_ui_interaction_activity(1200)
        except Exception:
            pass
        self._view_pan_undo_key = None
        self._view_pan_start_state = None
        try:
            if not self._view_undo_is_suppressed() and hasattr(self.main, "begin_page_view_undo"):
                self.main.begin_page_view_undo("화면 이동")
        except Exception:
            pass

    def _finish_view_pan_undo(self):
        self._view_pan_undo_key = None
        self._view_pan_start_state = None
        try:
            if not self._view_undo_is_suppressed() and hasattr(self.main, "finish_page_view_undo"):
                self.main.finish_page_view_undo(force=False)
            elif hasattr(self.main, "remember_current_view_state"):
                self.main.remember_current_view_state()
        except Exception:
            pass

    def _paint_history_kind_for_item(self, target_item):
        try:
            if target_item is self.final_paint_item or target_item is self.final_paint_above_item:
                return "final_paint"
            if target_item is self.user_mask_item:
                return "mask"
        except Exception:
            pass
        return None

    def _apply_paint_history_record(self, record):
        if isinstance(record, dict) and record.get("_brush_record"):
            try:
                return self.brush_engine.apply_record(record, "undo")
            except Exception:
                return None
        if isinstance(record, dict) and record.get("dirty_rect") is not None:
            target_item = record.get("target_item")
            patch = record.get("patch")
            rect = record.get("dirty_rect")
            if target_item is None or patch is None or rect is None:
                return None
            try:
                pix = target_item.pixmap()
                p = QPainter(pix)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                p.drawPixmap(rect.topLeft(), patch)
                p.end()
                target_item.setPixmap(pix)
                target_item.update(QRectF(rect))
                if self._paint_history_apply_is_active():
                    self._mark_paint_layer_cache_dirty()
                elif target_item is self.final_paint_above_item:
                    self.final_paint_above_img = pix.toImage()
                elif target_item is self.final_paint_item:
                    self.final_paint_img = pix.toImage()
                elif target_item is self.user_mask_item:
                    self.user_mask_img = pix.toImage()
                try:
                    self.viewport().update(self.mapFromScene(target_item.mapRectToScene(QRectF(rect))).boundingRect())
                except Exception:
                    pass
            except Exception:
                return None
            return self._paint_history_kind_for_item(target_item)

        if isinstance(record, tuple) and len(record) == 2:
            target_item, pixmap = record
        else:
            target_item = self.user_mask_item
            pixmap = record
        if target_item is None or pixmap is None:
            return None
        target_item.setPixmap(pixmap)
        try:
            if self._paint_history_apply_is_active():
                self._mark_paint_layer_cache_dirty()
            elif target_item is self.final_paint_above_item:
                self.final_paint_above_img = pixmap.toImage()
            elif target_item is self.final_paint_item:
                self.final_paint_img = pixmap.toImage()
            elif target_item is self.user_mask_item:
                self.user_mask_img = pixmap.toImage()
        except Exception:
            pass
        try:
            target_item.update()
            self.viewport().update()
        except Exception:
            pass
        return self._paint_history_kind_for_item(target_item)

    def _append_paint_history_undo_marker(self, kind=None, reason=None):
        """viewer.history에 직접 쌓은 patch record를 Ctrl+Z 타임라인에 연결한다.

        일반 브러시는 PageBrushEngine.commit()이 page undo marker를 추가하지만,
        영역 페인팅/영역 마스킹/요술봉 영역 칠하기는 viewer.py에서 직접 patch를 만들기 때문에
        같은 marker를 여기서 수동으로 넣어야 한다.
        """
        try:
            page_idx = int(getattr(self.main, "idx", 0) or 0)
            mode = int(self.main.cb_mode.currentIndex()) if hasattr(self.main, "cb_mode") else 0
            reason_s = str(reason or ("최종 페인팅" if kind == "final_paint" else "마스크 편집"))
            if hasattr(self.main, "undo_push_paint_marker"):
                ok = self.main.undo_push_paint_marker(kind=kind, reason=reason_s, page_idx=page_idx, mode=mode)
            elif hasattr(self.main, "undo_push_page"):
                ok = self.main.undo_push_page({
                    "reason": reason_s,
                    "page_idx": page_idx,
                    "mode": mode,
                    "paint_history": True,
                    "_undo_scope": "page",
                }, page_idx=page_idx)
            else:
                ok = False
            try:
                if hasattr(self.main, "audit_boundary_event"):
                    self.main.audit_boundary_event("PAINT_UNDO_MARKER_PUSH", reason=reason_s, ok=bool(ok), page_idx=page_idx, mode=mode, throttle_ms=100)
            except Exception:
                pass
            try:
                if hasattr(self.main, "update_undo_redo_buttons"):
                    self.main.update_undo_redo_buttons()
            except Exception:
                pass
        except Exception:
            pass

    def _begin_paint_history_apply(self, reason="undo_redo"):
        try:
            if hasattr(self.main, "note_paint_undo_redo_activity"):
                self.main.note_paint_undo_redo_activity(2200)
        except Exception:
            pass
        try:
            setattr(self.main, "_paint_history_apply_active", True)
        except Exception:
            pass
        try:
            self.suspend_brush_cursor_preview(reason=reason, delay_ms=180)
        except Exception:
            pass

    def _end_paint_history_apply(self):
        try:
            setattr(self.main, "_paint_history_apply_active", False)
        except Exception:
            pass

    def _paint_history_apply_is_active(self):
        try:
            return bool(getattr(self.main, "_paint_history_apply_active", False))
        except Exception:
            return False

    def _mark_paint_layer_cache_dirty(self):
        try:
            self._paint_layer_cache_dirty = True
        except Exception:
            pass

    def _current_paint_history_record_for(self, target_item, like_record=None):
        try:
            if target_item is None:
                target_item = self.user_mask_item
            if target_item is None:
                return None
            if isinstance(like_record, dict) and like_record.get("dirty_rect") is not None:
                rect = like_record.get("dirty_rect")
                patch = target_item.pixmap().copy(rect)
                return {
                    "target_item": target_item,
                    "dirty_rect": rect,
                    "patch": patch,
                }
            return (target_item, target_item.pixmap().copy())
        except Exception:
            pass
        return None

    def undo(self):
        try:
            if hasattr(self.main, "undo_bind_paint_viewer"):
                self.main.undo_bind_paint_viewer(self)
        except Exception:
            pass
        if not self.history:
            self.main.log("⚠️ 실행 취소할 내역이 없습니다.")
            if hasattr(self.main, "update_undo_redo_buttons"):
                self.main.update_undo_redo_buttons()
            return False

        record = self.history.pop()
        self._begin_paint_history_apply("paint_undo")
        try:
            if isinstance(record, dict) and record.get("_brush_record"):
                redo_record = record
                try:
                    kind = self.brush_engine.apply_record(record, "undo")
                except Exception:
                    kind = None
            else:
                if isinstance(record, tuple) and len(record) == 2:
                    target_item, _last_pixmap = record
                else:
                    target_item = self.user_mask_item
                redo_record = self._current_paint_history_record_for(target_item, record)
                kind = self._apply_paint_history_record(record)
        finally:
            self._end_paint_history_apply()
        if redo_record is not None:
            self.redo_history.append(redo_record)
            if len(self.redo_history) > 20:
                self.redo_history.pop(0)

        if kind == "final_paint":
            self.main.log("↩️ 최종 페인팅 실행 취소됨")
        elif kind == "mask":
            self.main.log("↩️ 마스크 브러시 실행 취소됨")
        else:
            self.main.log("↩️ 실행 취소됨")
        try:
            if hasattr(self.main, "schedule_deferred_view_layer_commit"):
                # Undo/Redo may be pressed repeatedly; mark dirty now but defer the
                # expensive PNG/data/workspace commit until the burst becomes idle.
                self.main.schedule_deferred_view_layer_commit(kind, delay_ms=1800)
        except Exception:
            pass
        if hasattr(self.main, "update_undo_redo_buttons"):
            self.main.update_undo_redo_buttons()
        try:
            self.force_tool_cursor_refresh(delay_followups=True)
        except Exception:
            pass
        return True

    def redo(self):
        try:
            if hasattr(self.main, "undo_bind_paint_viewer"):
                self.main.undo_bind_paint_viewer(self)
        except Exception:
            pass
        if not getattr(self, "redo_history", None):
            self.main.log("⚠️ 다시 실행할 내역이 없습니다.")
            if hasattr(self.main, "update_undo_redo_buttons"):
                self.main.update_undo_redo_buttons()
            return False

        record = self.redo_history.pop()
        self._begin_paint_history_apply("paint_redo")
        try:
            if isinstance(record, dict) and record.get("_brush_record"):
                undo_record = record
                try:
                    kind = self.brush_engine.apply_record(record, "redo")
                except Exception:
                    kind = None
            else:
                if isinstance(record, tuple) and len(record) == 2:
                    target_item, _pixmap = record
                else:
                    target_item = self.user_mask_item
                undo_record = self._current_paint_history_record_for(target_item, record)
                kind = self._apply_paint_history_record(record)
        finally:
            self._end_paint_history_apply()
        if undo_record is not None:
            self.history.append(undo_record)
            if len(self.history) > 20:
                self.history.pop(0)

        if kind == "final_paint":
            self.main.log("↷ 최종 페인팅 다시 실행됨")
        elif kind == "mask":
            self.main.log("↷ 마스크 브러시 다시 실행됨")
        else:
            self.main.log("↷ 다시 실행됨")
        try:
            if hasattr(self.main, "schedule_deferred_view_layer_commit"):
                # Undo/Redo may be pressed repeatedly; mark dirty now but defer the
                # expensive PNG/data/workspace commit until the burst becomes idle.
                self.main.schedule_deferred_view_layer_commit(kind, delay_ms=1800)
        except Exception:
            pass
        if hasattr(self.main, "update_undo_redo_buttons"):
            self.main.update_undo_redo_buttons()
        try:
            self.force_tool_cursor_refresh(delay_followups=True)
        except Exception:
            pass
        return True


    def _set_layer_tag(self, item, tag):
        try:
            item.setData(0, str(tag))
        except Exception:
            pass
        return item

    def _item_layer_tag(self, item):
        """Return the QGraphicsItem layer tag without being fooled by TypesettingItem.data.

        TypesettingItem intentionally stores its text-line dictionary as ``self.data``.
        That shadows QGraphicsItem.data(index), so calling ``item.data(0)`` raises
        ``dict is not callable`` and old text items are not removed.  Use the
        unbound QGraphicsItem.data() API for layer tags.
        """
        try:
            return QGraphicsItem.data(item, 0)
        except Exception:
            try:
                return item.data(0)
            except Exception:
                return None

    def _qgraphics_item_is_alive(self, item):
        if item is None:
            return False
        try:
            if _qt_sip is not None and _qt_sip.isdeleted(item):
                return False
        except Exception:
            pass
        return True

    def _remove_scene_items_by_tags(self, *tags):
        tags = {str(t) for t in tags if t is not None}
        if not tags:
            return
        try:
            items = list(self.scene.items())
        except Exception:
            items = []
        for item in items:
            try:
                if not self._qgraphics_item_is_alive(item):
                    continue
                if str(self._item_layer_tag(item)) in tags:
                    self.scene.removeItem(item)
            except Exception:
                pass

    def clear_mode_layers(self, *, clear_boxes=True, clear_text=True, clear_mask=True, clear_final_paint=True):
        """Remove page-mode overlay layers without rebuilding the base image.

        LayerEngine 2nd pass: tab changes inside the same page should not
        force scene.clear()/set_image() every time.  Keep the base pixmap and
        only replace mode-specific layers.
        """
        before_text_ids = []
        try:
            if getattr(self, 'main', None) is not None and hasattr(self.main, 'audit_boundary_event'):
                try:
                    for obj in list(self.scene.items()):
                        if isinstance(obj, TypesettingItem):
                            data = getattr(obj, 'data', {}) or {}
                            before_text_ids.append(str(data.get('id')))
                except Exception:
                    before_text_ids = []
                self.main.audit_boundary_event(
                    'VIEW_CLEAR_MODE_LAYERS_ENTER',
                    clear_boxes=bool(clear_boxes),
                    clear_text=bool(clear_text),
                    clear_mask=bool(clear_mask),
                    clear_final_paint=bool(clear_final_paint),
                    before_text_count=len(before_text_ids),
                    before_text_ids=','.join(before_text_ids[:30]),
                    stack=True,
                )
        except Exception:
            pass
        tags = []
        if clear_boxes:
            tags.extend(["analysis_box", "analysis_label"])
        if clear_text:
            tags.append("movable_text")
        if clear_mask:
            tags.append("mask_overlay")
            self.user_mask_item = None
            self.user_mask_img = None
        if clear_final_paint:
            tags.extend(["final_paint_below", "final_paint_above"])
            self.final_paint_item = None
            self.final_paint_above_item = None
            self.final_paint_img = None
            self.final_paint_above_img = None
        self._remove_scene_items_by_tags(*tags)
        try:
            if getattr(self, 'main', None) is not None and hasattr(self.main, 'audit_boundary_event'):
                after_text_ids = []
                try:
                    for obj in list(self.scene.items()):
                        if isinstance(obj, TypesettingItem):
                            data = getattr(obj, 'data', {}) or {}
                            after_text_ids.append(str(data.get('id')))
                except Exception:
                    after_text_ids = []
                self.main.audit_boundary_event(
                    'VIEW_CLEAR_MODE_LAYERS_DONE',
                    removed_text_count=max(0, len(before_text_ids) - len(after_text_ids)),
                    after_text_count=len(after_text_ids),
                    after_text_ids=','.join(after_text_ids[:30]),
                )
        except Exception:
            pass
        # Transient previews are mode-local; keep the base layer but drop them.
        try:
            self.clear_mask_wrap_preview()
            self.clear_mask_cut_preview()
            self.clear_ocr_region_preview()
            self.clear_quick_ocr_preview()
            self.clear_paste_preview()
        except Exception:
            pass

    def is_background_hidden(self):
        try:
            return bool(getattr(self.main, "hide_background_enabled", False))
        except Exception:
            return False

    def _background_hidden_image_rect(self):
        """Return the real image/canvas rect used by the hide-background overlay.

        The page image size itself must remain visible even when the base pixmap
        is hidden.  Prefer the base pixmap item bounds because sceneRect may be
        temporarily expanded outward to show the outside fade border.
        """
        try:
            item = getattr(self, "_layer_base_item", None)
            if item is not None and item.scene() is self.scene:
                rect = item.mapRectToScene(item.boundingRect())
                if rect is not None and not rect.isNull():
                    return QRectF(rect)
        except Exception:
            pass
        try:
            rect = getattr(self, "_background_hidden_last_image_rect", None)
            if rect is not None and not rect.isNull():
                return QRectF(rect)
        except Exception:
            pass
        try:
            rect = self.scene.sceneRect()
            if rect is not None and not rect.isNull():
                return QRectF(rect)
        except Exception:
            pass
        return QRectF()

    def _clear_background_hidden_helper_refs(self):
        """Forget hide-background helper references without touching Qt objects.

        Full scene rebuilds call QGraphicsScene.clear(), which deletes helper
        items on the C++ side.  After that point, even item.scene() can crash on
        some PyQt/Qt paths during fast batch page refresh.  Use this whenever a
        scene.clear() may have invalidated the helper items.
        """
        try:
            self._background_hidden_fill_item = None
            self._background_hidden_fade_item = None
            self._background_hidden_fade_cache_key = None
        except Exception:
            pass

    def _remove_background_hidden_helpers(self):
        # Detach stored references first.  If removeItem triggers nested events,
        # later code must not see stale helper pointers.
        items = []
        try:
            for attr in ("_background_hidden_fill_item", "_background_hidden_fade_item"):
                item = getattr(self, attr, None)
                if item is not None:
                    items.append(item)
                try:
                    setattr(self, attr, None)
                except Exception:
                    pass
            self._background_hidden_fade_cache_key = None
        except Exception:
            items = []

        for item in items:
            try:
                if not self._qgraphics_item_is_alive(item):
                    continue
                scene = item.scene()
                if scene is not None:
                    scene.removeItem(item)
            except RuntimeError:
                pass
            except Exception:
                pass

        # Last-resort cleanup for tagged helpers that are still alive in the
        # current scene.  This iterates scene.items(), so it never touches old
        # Python references deleted by a previous scene.clear().
        try:
            self._remove_scene_items_by_tags("background_hidden_fill", "background_hidden_fade")
        except Exception:
            pass

    def _build_background_hidden_outside_fade_pixmap(self, w, h, pad):
        """Build an outside-only fade border for the hidden image canvas.

        Nothing is painted inside the actual image rect.  The bright edge starts
        just outside the page boundary and fades outward, so the visible page size
        is readable without covering text/mask pixels inside the canvas.
        """
        try:
            w = int(max(1, w))
            h = int(max(1, h))
            pad = int(max(1, pad))
            pix = QPixmap(w + pad * 2, h + pad * 2)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            base_rgb = (216, 216, 216)
            max_alpha = 190
            for i in range(pad):
                alpha = int(max_alpha * (1.0 - (i / float(max(1, pad)))))
                if alpha <= 0:
                    continue
                pen = QPen(QColor(base_rgb[0], base_rgb[1], base_rgb[2], alpha))
                pen.setWidth(1)
                painter.setPen(pen)
                # Outside-only strokes.  The inner image rect is
                # [pad, pad, pad+w, pad+h), so these lines never enter it.
                painter.drawLine(pad, pad - 1 - i, pad + w - 1, pad - 1 - i)
                painter.drawLine(pad, pad + h + i, pad + w - 1, pad + h + i)
                painter.drawLine(pad - 1 - i, pad, pad - 1 - i, pad + h - 1)
                painter.drawLine(pad + w + i, pad, pad + w + i, pad + h - 1)
                # Corners are also outside-only; keep them square and light.
                painter.drawPoint(pad - 1 - i, pad - 1 - i)
                painter.drawPoint(pad + w + i, pad - 1 - i)
                painter.drawPoint(pad - 1 - i, pad + h + i)
                painter.drawPoint(pad + w + i, pad + h + i)
            painter.end()
            return pix
        except Exception:
            try:
                pix = QPixmap(max(1, int(w)), max(1, int(h)))
                pix.fill(Qt.GlobalColor.transparent)
                return pix
            except Exception:
                return QPixmap()

    def _background_hidden_helper_alive_in_scene(self, item):
        try:
            if not self._qgraphics_item_is_alive(item):
                return False
            return item.scene() is self.scene
        except RuntimeError:
            return False
        except Exception:
            return False

    def _ensure_background_hidden_helpers(self):
        rect = self._background_hidden_image_rect()
        if rect is None or rect.isNull():
            return
        try:
            self._background_hidden_last_image_rect = QRectF(rect)
        except Exception:
            pass
        pad = 10
        try:
            if rect.width() >= 3000 or rect.height() >= 3000:
                pad = 14
        except Exception:
            pass

        # Do not remove/recreate helpers on every page refresh.  Batch auto-wrap
        # rapidly calls set_layer_base_image()/mode_chg(), and aggressive Qt item
        # deletion here can leave dangling QGraphicsItem wrappers.  Reuse live
        # helpers and update their geometry/pixmap instead.
        fill_item = getattr(self, "_background_hidden_fill_item", None)
        if not self._background_hidden_helper_alive_in_scene(fill_item):
            fill_item = None
            try:
                self._background_hidden_fill_item = None
            except Exception:
                pass
        try:
            if fill_item is None:
                fill_item = self.scene.addRect(rect, QPen(Qt.PenStyle.NoPen), QBrush(QColor("#242424")))
                self._set_layer_tag(fill_item, "background_hidden_fill")
                self._background_hidden_fill_item = fill_item
            else:
                fill_item.setRect(rect)
                fill_item.setPen(QPen(Qt.PenStyle.NoPen))
                fill_item.setBrush(QBrush(QColor("#242424")))
                fill_item.setVisible(True)
            fill_item.setZValue(-120.0)
            fill_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        except Exception:
            try:
                self._background_hidden_fill_item = None
            except Exception:
                pass

        fade_item = getattr(self, "_background_hidden_fade_item", None)
        if not self._background_hidden_helper_alive_in_scene(fade_item):
            fade_item = None
            try:
                self._background_hidden_fade_item = None
                self._background_hidden_fade_cache_key = None
            except Exception:
                pass
        try:
            fade_key = (int(rect.width()), int(rect.height()), int(pad))
            if fade_item is None:
                fade_pix = self._build_background_hidden_outside_fade_pixmap(fade_key[0], fade_key[1], fade_key[2])
                fade_item = self.scene.addPixmap(fade_pix)
                self._set_layer_tag(fade_item, "background_hidden_fade")
                self._background_hidden_fade_item = fade_item
                self._background_hidden_fade_cache_key = fade_key
            else:
                if getattr(self, "_background_hidden_fade_cache_key", None) != fade_key:
                    fade_pix = self._build_background_hidden_outside_fade_pixmap(fade_key[0], fade_key[1], fade_key[2])
                    fade_item.setPixmap(fade_pix)
                    self._background_hidden_fade_cache_key = fade_key
                fade_item.setVisible(True)
            fade_item.setPos(rect.left() - pad, rect.top() - pad)
            fade_item.setZValue(-110.0)
            fade_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        except Exception:
            try:
                self._background_hidden_fade_item = None
                self._background_hidden_fade_cache_key = None
            except Exception:
                pass

        try:
            self.scene.setSceneRect(rect.adjusted(-pad, -pad, pad, pad))
        except Exception:
            pass

    def apply_background_visibility(self):
        """Apply the main-window background-hide view option to this work viewer only.

        Hidden mode keeps the real image rect readable: the page area is filled
        with dark gray and an outside-only light fade border is drawn around the
        canvas.  The border is deliberately outside the image bounds, never on
        top of the page interior.  Overlay layers such as masks, text boxes, text
        items, and final paint layers stay visible.  Source-compare/clone windows
        do not use this viewer method, so they continue to show the original image.
        """
        hidden = self.is_background_hidden()
        try:
            # Keep the workspace behind the page darker than the hidden page fill
            # so the actual image/canvas area remains distinguishable.
            self.setBackgroundBrush(QBrush(QColor("#0B0C0E")))
        except Exception:
            pass
        try:
            item = getattr(self, "_layer_base_item", None)
            if item is not None:
                item.setVisible(not hidden)
        except Exception:
            pass
        try:
            if hidden:
                self._ensure_background_hidden_helpers()
            else:
                rect = self._background_hidden_image_rect()
                self._remove_background_hidden_helpers()
                if rect is not None and not rect.isNull():
                    self.scene.setSceneRect(rect)
        except Exception:
            pass
        try:
            vp = self.viewport()
            if vp is not None:
                vp.update()
        except Exception:
            pass

    def _fit_current_scene_for_background_option(self):
        try:
            rect = self.scene.sceneRect() if self.is_background_hidden() else self.scene.itemsBoundingRect()
            if rect is None or rect.isNull():
                rect = self.scene.sceneRect()
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        except Exception:
            try:
                self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            except Exception:
                pass

    def set_layer_base_image(self, img, key=None, fit=True, clear_paint_history=True):
        """Set or reuse the base pixmap layer.

        If the requested key matches the current base, the scene is not cleared.
        This is the core fast path for same-page tab switching.
        """
        if img is None:
            self._clear_background_hidden_helper_refs()
            self.clear_brush_cursor_preview()
            self.clear_inpaint_group_preview_overlay()
            self.scene.clear()
            self.inpaint_group_preview_items = []
            self._clear_background_hidden_helper_refs()
            self._layer_base_key = None
            self._layer_base_item = None
            self.user_mask_item = None
            self.final_paint_item = None
            self.final_paint_above_item = None
            return False

        key = str(key or "")
        base_item = getattr(self, "_layer_base_item", None)
        try:
            if base_item is not None and _qt_sip is not None and _qt_sip.isdeleted(base_item):
                base_item = None
                self._layer_base_item = None
                self._layer_base_key = None
        except Exception:
            # sip 상태 확인 자체가 실패하면 C++ 객체가 의심스러운 상태이므로
            # fast reuse를 포기하고 안전하게 새 base item을 만든다.
            base_item = None
            self._layer_base_item = None
            self._layer_base_key = None
        main_obj = getattr(self, "main", None)
        unsafe_fast_reuse = bool(
            getattr(main_obj, "_batch_export_streaming", False)
            or getattr(main_obj, "is_batch_running", False)
            or getattr(self, "_force_layer_base_rebuild", False)
        )
        if (
            key
            and not unsafe_fast_reuse
            and getattr(self, "_layer_base_key", None) == key
            and base_item is not None
        ):
            try:
                if base_item.scene() is self.scene:
                    self.apply_background_visibility()
                    if fit:
                        self._fit_current_scene_for_background_option()
                    return False
            except Exception:
                # Qt C++ item wrapper가 이미 삭제됐거나 scene에서 떨어진 경우.
                # 여기서 재사용을 고집하면 access violation으로 죽을 수 있으므로
                # 참조를 끊고 일반 재구성 경로로 내려간다.
                try:
                    self._layer_base_item = None
                    self._layer_base_key = None
                except Exception:
                    pass

        self._clear_background_hidden_helper_refs()
        self.clear_brush_cursor_preview()
        self.clear_inpaint_group_preview_overlay()
        self.scene.clear()
        self.inpaint_group_preview_items = []
        self._clear_background_hidden_helper_refs()
        self.user_mask_item = None
        self.final_paint_item = None
        self.final_paint_above_item = None
        self.final_paint_img = None
        self.final_paint_above_img = None
        self.magic_preview_items = []
        self.clear_mask_wrap_preview()
        self.clear_mask_cut_preview()
        self.clear_ocr_region_preview()
        self.clear_ocr_region_overlay()
        self.clear_quick_ocr_preview()
        self.clear_paste_preview()
        try:
            self.brush_engine.clear_runtime()
        except Exception:
            pass
        # A true page/base change may invalidate legacy viewer-local paint
        # histories.  Same-page work-tab switching uses this method too, but that
        # is only a display-base swap; clearing paint history there is slow and
        # can make mask Undo look stale.  The caller can therefore suppress it.
        if clear_paint_history:
            try:
                if hasattr(self.main, "undo_clear_paint_history"):
                    self.main.undo_clear_paint_history(self, undo=True, redo=True, reason="base image changed")
                else:
                    self.history.clear()
                    self.redo_history.clear()
            except Exception:
                try:
                    self.history.clear()
                    self.redo_history.clear()
                except Exception:
                    pass
            if hasattr(self.main, "update_undo_redo_buttons"):
                self.main.update_undo_redo_buttons()

        pix = None
        try:
            cache = getattr(self, "_layer_base_pixmap_cache", None)
            if isinstance(cache, dict) and key and key in cache:
                cached = cache.get(key)
                if isinstance(cached, QPixmap) and not cached.isNull():
                    pix = cached
        except Exception:
            pix = None
        if pix is None:
            if isinstance(img, bytes):
                q_img = QImage.fromData(img)
            else:
                q_img = self._np2pix(img).toImage()
            pix = QPixmap.fromImage(q_img)
            try:
                if key:
                    cache = getattr(self, "_layer_base_pixmap_cache", None)
                    order = getattr(self, "_layer_base_pixmap_cache_order", None)
                    if not isinstance(cache, dict):
                        cache = {}
                    if not isinstance(order, list):
                        order = []
                    cache[key] = pix
                    if key in order:
                        order.remove(key)
                    order.append(key)
                    while len(order) > 6:
                        old_key = order.pop(0)
                        cache.pop(old_key, None)
                    self._layer_base_pixmap_cache = cache
                    self._layer_base_pixmap_cache_order = order
            except Exception:
                pass
        item = self.scene.addPixmap(pix)
        item.setZValue(0)
        self._set_layer_tag(item, "base")
        self._layer_base_item = item
        self._layer_base_key = key
        self.scene.setSceneRect(QRectF(pix.rect()))
        self.apply_background_visibility()
        if fit:
            self._fit_current_scene_for_background_option()
        return True

    def set_mask_overlay_layer(self, mask, color):
        """Replace only the mask overlay layer on the current base image."""
        self._remove_scene_items_by_tags("mask_overlay")
        self.user_mask_item = None
        rect = self.scene.sceneRect()
        w, h = int(rect.width()), int(rect.height())
        if w <= 0 or h <= 0:
            return
        self.user_mask_img = QImage(w, h, QImage.Format.Format_ARGB32)
        self.user_mask_img.fill(Qt.GlobalColor.transparent)
        if mask is not None:
            m_qimg = self._np2pix(mask).toImage().convertToFormat(QImage.Format.Format_Grayscale8)
            if m_qimg.width() != w or m_qimg.height() != h:
                m_qimg = m_qimg.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
            target_color_img = QImage(w, h, QImage.Format.Format_ARGB32)
            target_color_img.fill(color)
            target_color_img.setAlphaChannel(m_qimg)
            p = QPainter(self.user_mask_img)
            p.drawImage(0, 0, target_color_img)
            p.end()
        self.user_mask_item = self.scene.addPixmap(QPixmap.fromImage(self.user_mask_img))
        self.user_mask_item.setZValue(10)
        self.user_mask_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._set_layer_tag(self.user_mask_item, "mask_overlay")

    def set_image(self, img, fit=True):
        """2.3.1 안정 방식: 화면 탭 갱신은 scene을 통째로 비우고 다시 만든다.

        2.4.0의 레이어 재사용(set_layer_base_image/clear_mode_layers)은 성능상 유리하지만,
        텍스트 객체 변환/삭제/변형 직후 남아 있는 QGraphicsItem 참조와 충돌하기 쉽다.
        B단계에서는 사용자가 직접 만지는 화면 반응 로직을 2.3.1처럼 전체 재구성으로 되돌린다.
        """
        self._clear_background_hidden_helper_refs()
        self.clear_brush_cursor_preview()
        self.clear_inpaint_group_preview_overlay()
        self.scene.clear()
        self.inpaint_group_preview_items = []
        self._clear_background_hidden_helper_refs()
        self.user_mask_item = None
        self.final_paint_item = None
        self.final_paint_above_item = None
        self.final_paint_img = None
        self.final_paint_above_img = None
        self.magic_preview_items = []
        self.paste_preview_items = []
        self._layer_base_item = None
        self._layer_base_key = None
        self._layer_items = {}
        try:
            self._active_transform_item = None
        except Exception:
            pass
        self.clear_mask_wrap_preview()
        self.clear_mask_cut_preview()
        self.clear_ocr_region_preview()
        self.clear_ocr_region_overlay()
        self.clear_quick_ocr_preview()
        self.clear_paste_preview()
        try:
            self.clear_raster_erase_preview()
        except Exception:
            pass
        try:
            self.clear_area_paint_preview()
        except Exception:
            pass
        try:
            if hasattr(self.main, "undo_clear_paint_history"):
                self.main.undo_clear_paint_history(self, undo=True, redo=True, reason="set_image rebuild")
            else:
                self.history.clear()
                self.redo_history.clear()
        except Exception:
            try:
                self.history.clear()
                self.redo_history.clear()
            except Exception:
                pass
        if hasattr(self.main, "update_undo_redo_buttons"):
            self.main.update_undo_redo_buttons()
        if img is None:
            return

        if isinstance(img, bytes):
            q_img = QImage.fromData(img)
        else:
            q_img = self._np2pix(img).toImage()

        pix = QPixmap.fromImage(q_img)
        item = self.scene.addPixmap(pix)
        item.setZValue(0)
        try:
            self._set_layer_tag(item, "base")
        except Exception:
            pass
        self._layer_base_item = item
        self.scene.setSceneRect(QRectF(pix.rect()))
        self.apply_background_visibility()
        if fit:
            self._fit_current_scene_for_background_option()
        try:
            self.force_tool_cursor_refresh(delay_followups=True)
        except Exception:
            pass

    def set_overlay(self, bg, mask, color, fit=True):
        """2.3.1 안정 방식: 마스크 화면도 통째로 다시 만든다."""
        self._clear_background_hidden_helper_refs()
        self.clear_brush_cursor_preview()
        self.clear_inpaint_group_preview_overlay()
        self.scene.clear()
        self.inpaint_group_preview_items = []
        self._clear_background_hidden_helper_refs()
        self.user_mask_item = None
        self.final_paint_item = None
        self.final_paint_above_item = None
        self.final_paint_img = None
        self.final_paint_above_img = None
        self.magic_preview_items = []
        self.paste_preview_items = []
        self._layer_base_item = None
        self._layer_base_key = None
        self._layer_items = {}
        self.clear_mask_wrap_preview()
        self.clear_mask_cut_preview()
        self.clear_ocr_region_preview()
        self.clear_ocr_region_overlay()
        self.clear_quick_ocr_preview()
        try:
            self.clear_raster_erase_preview()
        except Exception:
            pass
        try:
            self.clear_area_paint_preview()
        except Exception:
            pass
        if bg is None:
            return

        if isinstance(bg, bytes):
            bg_pix = QPixmap.fromImage(QImage.fromData(bg))
        else:
            bg_pix = self._np2pix(bg)
        bg_item = self.scene.addPixmap(bg_pix)
        bg_item.setZValue(0)
        try:
            self._set_layer_tag(bg_item, "base")
        except Exception:
            pass
        self._layer_base_item = bg_item
        self.apply_background_visibility()

        w, h = bg_pix.width(), bg_pix.height()
        self.user_mask_img = QImage(w, h, QImage.Format.Format_ARGB32)
        self.user_mask_img.fill(Qt.GlobalColor.transparent)

        if mask is not None:
            m_qimg = self._np2pix(mask).toImage().convertToFormat(QImage.Format.Format_Grayscale8)
            if m_qimg.width() != w or m_qimg.height() != h:
                m_qimg = m_qimg.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
            target_color_img = QImage(w, h, QImage.Format.Format_ARGB32)
            target_color_img.fill(color)
            target_color_img.setAlphaChannel(m_qimg)

            p = QPainter(self.user_mask_img)
            p.drawImage(0, 0, target_color_img)
            p.end()

        self.user_mask_item = self.scene.addPixmap(QPixmap.fromImage(self.user_mask_img))
        self.user_mask_item.setZValue(10)
        self.user_mask_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        try:
            self._set_layer_tag(self.user_mask_item, "mask_overlay")
        except Exception:
            pass

        self.scene.setSceneRect(QRectF(bg_pix.rect()))
        self.apply_background_visibility()
        if fit:
            self._fit_current_scene_for_background_option()
        try:
            self.force_tool_cursor_refresh(delay_followups=True)
        except Exception:
            pass

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
        self._set_layer_tag(self.final_paint_item, "final_paint_below")
        self.final_paint_item.setZValue(8)
        # 페인팅 레이어는 화면에는 보이지만 선택/이동 클릭을 잡아먹으면 안 된다.
        # 특히 위쪽 페인팅 레이어(z=80)는 텍스트보다 위에 있어서,
        # 마우스를 받으면 객체화된 텍스트가 클릭/선택/이동되지 않는다.
        self.final_paint_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.final_paint_above_img = above_qimg
        self.final_paint_above_item = self.scene.addPixmap(QPixmap.fromImage(above_qimg))
        self._set_layer_tag(self.final_paint_above_item, "final_paint_above")
        self.final_paint_above_item.setZValue(80)
        self.final_paint_above_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def copy_final_paint_layer_qimage(self, above=False):
        """Return a detached QImage snapshot of a final paint layer.

        QPixmap/QGraphicsItem must stay on the UI thread, but PNG encoding and
        file I/O can run in a worker once this detached QImage copy is made.
        """
        item = self.final_paint_above_item if above else self.final_paint_item
        if not item:
            return None
        try:
            return item.pixmap().toImage().convertToFormat(QImage.Format.Format_ARGB32).copy()
        except Exception:
            return None

    def copy_user_mask_qimage(self):
        """Return a detached QImage snapshot of the visible user mask overlay."""
        if not self.user_mask_item:
            return None
        try:
            return self.user_mask_item.pixmap().toImage().convertToFormat(QImage.Format.Format_ARGB32).copy()
        except Exception:
            return None

    def get_final_paint_layer_png_bytes(self, above=False):
        item = self.final_paint_above_item if above else self.final_paint_item
        if not item:
            return None
        qimg = self.copy_final_paint_layer_qimage(above=above)
        if qimg is None or qimg.isNull():
            return None
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
        base_w = int(self.analysis_number_box_size())
        font_size = max(1, int(base_w * 0.40))
        font = QFont("Arial", font_size, QFont.Weight.Bold)

        visible_items = [d for d in data]
        total_items = len(visible_items)
        for order_idx, d in enumerate(visible_items):
            is_active = d.get('use_inpaint', True)
            x, y, w, h = d['rect']

            pen_w = self.ui_pen_width(2)
            pen_box = QPen(QColor(255, 0, 0), pen_w) if is_active else QPen(QColor(150, 150, 150), pen_w, Qt.PenStyle.DotLine)

            rect_item = ToggleBoxItem(
                [x, y, w, h],
                d,
                self.main,
                pen_box,
                brush=QBrush(Qt.BrushStyle.NoBrush),
                z_value=20,
            )
            self._set_layer_tag(rect_item, "analysis_box")
            self.scene.addItem(rect_item)

            id_str = str(d.get('id', ''))
            bg_w = max(1, base_w + (len(id_str) - 1) * max(1, int(base_w * 0.4)))
            bg_h = max(1, int(base_w * 0.9))

            bx, by = x, y - bg_h
            if by < 0:
                by = y

            if is_active:
                brush_bg = QBrush(QColor(255, 215, 0))
                text_color = Qt.GlobalColor.black
            else:
                brush_bg = QBrush(QColor(100, 100, 100))
                text_color = Qt.GlobalColor.white

            if bool(getattr(self.main, "text_number_boxes_hidden", False)):
                continue

            handle_item = ToggleBoxItem(
                [bx, by, bg_w, bg_h],
                d,
                self.main,
                QPen(Qt.PenStyle.NoPen),
                brush=brush_bg,
                z_value=21,
            )
            self._set_layer_tag(handle_item, "analysis_box")
            self.scene.addItem(handle_item)

            t_item = self.scene.addText(id_str, font)
            t_item.setDefaultTextColor(text_color)
            br = t_item.boundingRect()
            t_item.setPos(bx + (bg_w - br.width()) / 2, by + (bg_h - br.height()) / 2)
            t_item.setZValue(22)
            t_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self._set_layer_tag(t_item, "analysis_label")

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
        data = list(data or [])
        visible_items = []
        rejected_items = []
        for d in data:
            try:
                if not d.get('use_inpaint', True):
                    rejected_items.append({'id': d.get('id'), 'reason': 'use_inpaint_false'})
                    continue
                if not str(d.get('translated_text', '') or '').strip() and not d.get('force_show'):
                    rejected_items.append({'id': d.get('id'), 'reason': 'empty_translated_text'})
                    continue
                visible_items.append(d)
            except Exception:
                rejected_items.append({'id': None, 'reason': 'row_error'})
        try:
            if getattr(self, 'main', None) is not None and hasattr(self.main, 'audit_boundary_event'):
                self.main.audit_boundary_event(
                    'VIEW_DRAW_MOVABLE_TEXTS_ENTER',
                    show_text=bool(show_text),
                    data_count=len(data),
                    renderable_count=len(visible_items),
                    rejected_count=len(rejected_items),
                    renderable_ids=','.join(str(x.get('id')) for x in visible_items[:30]),
                    rejected_items=rejected_items[:20],
                    font=str(font),
                    size_px=int(size_px or 0),
                    stroke=int(stroke or 0),
                    stack=True,
                )
        except Exception:
            pass
        if not show_text:
            try:
                if getattr(self, 'main', None) is not None and hasattr(self.main, 'audit_boundary_event'):
                    self.main.audit_boundary_event(
                        'VIEW_DRAW_MOVABLE_TEXTS_SKIPPED_SHOW_OFF',
                        renderable_count=len(visible_items),
                        data_count=len(data),
                        policy='user_view_toggle_only_no_repair',
                        stack=bool(visible_items),
                    )
            except Exception:
                pass
            return

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
            self._set_layer_tag(item, "movable_text")
            self.scene.addItem(item)
            try:
                if getattr(self, 'main', None) is not None and hasattr(self.main, 'audit_boundary_event'):
                    br = item.sceneBoundingRect()
                    self.main.audit_boundary_event(
                        'VIEW_DRAW_MOVABLE_TEXT_ITEM_ADDED',
                        item_id=d.get('id'),
                        order_idx=order_idx,
                        z_value=float(item.zValue()),
                        scene_rect=[round(br.x(), 2), round(br.y(), 2), round(br.width(), 2), round(br.height(), 2)],
                        preview=str(d.get('translated_text', '') or '').replace('\n', '\\n')[:60],
                    )
            except Exception:
                pass
        try:
            self.refresh_text_item_interaction_for_tool_mode(reason='draw_movable_texts')
        except Exception:
            pass
        try:
            if getattr(self, 'main', None) is not None and hasattr(self.main, 'audit_boundary_event'):
                scene_text_ids = []
                for obj in list(self.scene.items()):
                    if isinstance(obj, TypesettingItem):
                        data_obj = getattr(obj, 'data', {}) or {}
                        scene_text_ids.append(str(data_obj.get('id')))
                self.main.audit_boundary_event(
                    'VIEW_DRAW_MOVABLE_TEXTS_DONE',
                    added_count=total_items,
                    scene_text_count=len(scene_text_ids),
                    scene_text_ids=','.join(scene_text_ids[:30]),
                )
        except Exception:
            pass

    def clear_mask_wrap_preview(self):
        item = getattr(self, "mask_wrap_preview_item", None)
        if item is not None:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.mask_wrap_preview_item = None

    def _mask_wrap_pen(self):
        return QPen(QColor(255, 230, 0), self.ui_pen_width(2), Qt.PenStyle.SolidLine)

    def _draw_mask_wrap_preview(self, now):
        self.clear_mask_wrap_preview()
        if self.mask_wrap_start is None:
            return
        pen = self._mask_wrap_pen()
        brush = QBrush(Qt.BrushStyle.NoBrush)
        if getattr(self, "mask_wrap_shape", "rect") == "rect":
            rect = QRectF(self.mask_wrap_start, now).normalized()
            self.mask_wrap_preview_item = self.scene.addRect(rect, pen, brush)
        else:
            points = list(getattr(self, "mask_wrap_points", []) or [])
            close = self._area_path_preview_should_close("mask_wrap", points, now)
            path = self._make_area_polyline_path(points or [self.mask_wrap_start], now, close=close)
            if path is not None:
                self.mask_wrap_preview_item = self.scene.addPath(path, pen, brush)
        if self.mask_wrap_preview_item is not None:
            self.mask_wrap_preview_item.setZValue(42)
            self.mask_wrap_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _mask_wrap_region_np(self, end_pos):
        if self.user_mask_img is None or self.mask_wrap_start is None:
            return None
        import cv2
        h = int(self.user_mask_img.height())
        w = int(self.user_mask_img.width())
        if w <= 0 or h <= 0:
            return None
        region = np.zeros((h, w), dtype=np.uint8)
        if getattr(self, "mask_wrap_shape", "rect") == "rect":
            x1 = int(round(min(self.mask_wrap_start.x(), end_pos.x())))
            y1 = int(round(min(self.mask_wrap_start.y(), end_pos.y())))
            x2 = int(round(max(self.mask_wrap_start.x(), end_pos.x())))
            y2 = int(round(max(self.mask_wrap_start.y(), end_pos.y())))
            x1 = max(0, min(w - 1, x1)); x2 = max(0, min(w - 1, x2))
            y1 = max(0, min(h - 1, y1)); y2 = max(0, min(h - 1, y2))
            if x2 <= x1 or y2 <= y1:
                return None
            cv2.rectangle(region, (x1, y1), (x2, y2), 255, thickness=-1)
            return region

        points = list(getattr(self, "mask_wrap_points", []) or [])
        if end_pos is not None:
            points.append(end_pos)
        if len(points) < 3:
            return None
        arr = []
        for pt in points:
            x = max(0, min(w - 1, int(round(pt.x()))))
            y = max(0, min(h - 1, int(round(pt.y()))))
            arr.append([x, y])
        if len(arr) < 3:
            return None
        cv2.fillPoly(region, [np.array(arr, dtype=np.int32)], 255)
        return region


    def clear_mask_cut_preview(self):
        item = getattr(self, "mask_cut_preview_item", None)
        if item is not None:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.mask_cut_preview_item = None

    def _mask_cut_pen(self):
        return QPen(QColor(255, 80, 40), self.ui_pen_width(2), Qt.PenStyle.SolidLine)

    def _draw_mask_cut_preview(self, now):
        self.clear_mask_cut_preview()
        if self.mask_cut_start is None:
            return
        pen = self._mask_cut_pen()
        brush = QBrush(Qt.BrushStyle.NoBrush)
        if getattr(self, "mask_cut_shape", "rect") == "rect":
            rect = QRectF(self.mask_cut_start, now).normalized()
            self.mask_cut_preview_item = self.scene.addRect(rect, pen, brush)
        else:
            points = list(getattr(self, "mask_cut_points", []) or [])
            close = self._area_path_preview_should_close("mask_cut", points, now)
            path = self._make_area_polyline_path(points or [self.mask_cut_start], now, close=close)
            if path is not None:
                self.mask_cut_preview_item = self.scene.addPath(path, pen, brush)
        if self.mask_cut_preview_item is not None:
            self.mask_cut_preview_item.setZValue(43)
            self.mask_cut_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _mask_cut_region_np(self, end_pos):
        if self.user_mask_img is None or self.mask_cut_start is None:
            return None
        import cv2
        h = int(self.user_mask_img.height())
        w = int(self.user_mask_img.width())
        if w <= 0 or h <= 0:
            return None
        region = np.zeros((h, w), dtype=np.uint8)
        if getattr(self, "mask_cut_shape", "rect") == "rect":
            x1 = int(round(min(self.mask_cut_start.x(), end_pos.x())))
            y1 = int(round(min(self.mask_cut_start.y(), end_pos.y())))
            x2 = int(round(max(self.mask_cut_start.x(), end_pos.x())))
            y2 = int(round(max(self.mask_cut_start.y(), end_pos.y())))
            x1 = max(0, min(w - 1, x1)); x2 = max(0, min(w - 1, x2))
            y1 = max(0, min(h - 1, y1)); y2 = max(0, min(h - 1, y2))
            if x2 <= x1 or y2 <= y1:
                return None
            cv2.rectangle(region, (x1, y1), (x2, y2), 255, thickness=-1)
            return region

        points = list(getattr(self, "mask_cut_points", []) or [])
        if end_pos is not None:
            points.append(end_pos)
        if len(points) < 3:
            return None
        arr = []
        for pt in points:
            x = max(0, min(w - 1, int(round(pt.x()))))
            y = max(0, min(h - 1, int(round(pt.y()))))
            arr.append([x, y])
        if len(arr) < 3:
            return None
        cv2.fillPoly(region, [np.array(arr, dtype=np.int32)], 255)
        return region

    def clear_color_outline_mask_preview(self):
        item = getattr(self, "color_outline_mask_preview_item", None)
        if item is not None:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.color_outline_mask_preview_item = None

    def _color_outline_mask_pen(self):
        return QPen(QColor(0, 210, 255), self.ui_pen_width(2), Qt.PenStyle.SolidLine)

    def _draw_color_outline_mask_preview(self, now):
        self.clear_color_outline_mask_preview()
        if self.color_outline_mask_start is None:
            return
        pen = self._color_outline_mask_pen()
        brush = QBrush(Qt.BrushStyle.NoBrush)
        if getattr(self, "color_outline_mask_shape", "rect") == "rect":
            rect = QRectF(self.color_outline_mask_start, now).normalized()
            self.color_outline_mask_preview_item = self.scene.addRect(rect, pen, brush)
        else:
            points = list(getattr(self, "color_outline_mask_points", []) or [])
            close = self._area_path_preview_should_close("color_outline_mask", points, now)
            path = self._make_area_polyline_path(points or [self.color_outline_mask_start], now, close=close)
            if path is not None:
                self.color_outline_mask_preview_item = self.scene.addPath(path, pen, brush)
        if self.color_outline_mask_preview_item is not None:
            self.color_outline_mask_preview_item.setZValue(44)
            self.color_outline_mask_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _color_outline_mask_region_np(self, end_pos):
        if self.user_mask_img is None or self.color_outline_mask_start is None:
            return None
        import cv2
        h = int(self.user_mask_img.height())
        w = int(self.user_mask_img.width())
        if w <= 0 or h <= 0:
            return None
        region = np.zeros((h, w), dtype=np.uint8)
        if getattr(self, "color_outline_mask_shape", "rect") == "rect":
            x1 = int(round(min(self.color_outline_mask_start.x(), end_pos.x())))
            y1 = int(round(min(self.color_outline_mask_start.y(), end_pos.y())))
            x2 = int(round(max(self.color_outline_mask_start.x(), end_pos.x())))
            y2 = int(round(max(self.color_outline_mask_start.y(), end_pos.y())))
            x1 = max(0, min(w - 1, x1)); x2 = max(0, min(w - 1, x2))
            y1 = max(0, min(h - 1, y1)); y2 = max(0, min(h - 1, y2))
            if x2 <= x1 or y2 <= y1:
                return None
            cv2.rectangle(region, (x1, y1), (x2, y2), 255, thickness=-1)
            return region

        points = list(getattr(self, "color_outline_mask_points", []) or [])
        if end_pos is not None:
            points.append(end_pos)
        if len(points) < 3:
            return None
        arr = []
        for pt in points:
            x = max(0, min(w - 1, int(round(pt.x()))))
            y = max(0, min(h - 1, int(round(pt.y()))))
            arr.append([x, y])
        if len(arr) < 3:
            return None
        cv2.fillPoly(region, [np.array(arr, dtype=np.int32)], 255)
        return region

    def clear_ocr_region_preview(self):
        item = getattr(self, "ocr_region_preview_item", None)
        if item is not None:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.ocr_region_preview_item = None

    def clear_quick_ocr_preview(self):
        item = getattr(self, "quick_ocr_preview_item", None)
        if item is not None:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.quick_ocr_preview_item = None

    def clear_ocr_region_overlay(self):
        if not hasattr(self, "ocr_region_overlay_items"):
            self.ocr_region_overlay_items = []
        for item in list(self.ocr_region_overlay_items):
            try:
                if item.scene() is not None:
                    self.scene.removeItem(item)
            except Exception:
                pass
        self.ocr_region_overlay_items = []

    def _ocr_region_preview_pen(self):
        return QPen(QColor(199, 138, 144, 220), self.ui_pen_width(2), Qt.PenStyle.SolidLine)

    def _draw_ocr_region_preview(self, now):
        self.clear_ocr_region_preview()
        if self.ocr_region_start is None:
            return
        pen = self._ocr_region_preview_pen()
        brush = QBrush(QColor(138, 74, 82, 55))
        if getattr(self, "ocr_region_shape", "rect") == "rect":
            rect = QRectF(self.ocr_region_start, now).normalized()
            self.ocr_region_preview_item = self.scene.addRect(rect, pen, brush)
        else:
            points = list(getattr(self, "ocr_region_points", []) or [])
            close = self._area_path_preview_should_close("ocr_region_select", points, now)
            path = self._make_area_polyline_path(points or [self.ocr_region_start], now, close=close)
            if path is not None:
                self.ocr_region_preview_item = self.scene.addPath(path, pen, brush)
        if self.ocr_region_preview_item is not None:
            self.ocr_region_preview_item.setZValue(86)
            self.ocr_region_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _draw_quick_ocr_preview(self, now):
        self.clear_quick_ocr_preview()
        if self.quick_ocr_start is None:
            return
        rect = QRectF(self.quick_ocr_start, now).normalized()
        pen = QPen(QColor(168, 93, 102, 215), self.ui_pen_width(2), Qt.PenStyle.DashLine)
        brush = QBrush(QColor(138, 74, 82, 55))
        self.quick_ocr_preview_item = self.scene.addRect(rect, pen, brush)
        self.quick_ocr_preview_item.setZValue(87)
        self.quick_ocr_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def clear_raster_erase_preview(self):
        item = getattr(self, "raster_erase_preview_item", None)
        if item is not None:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.raster_erase_preview_item = None

    def _draw_raster_erase_preview(self, now):
        self.clear_raster_erase_preview()
        if self.raster_erase_start is None:
            return
        rect = QRectF(self.raster_erase_start, now).normalized()
        pen = QPen(QColor(255, 80, 80), self.ui_pen_width(2), Qt.PenStyle.DashLine)
        brush = QBrush(QColor(255, 80, 80, 45))
        self.raster_erase_preview_item = self.scene.addRect(rect, pen, brush)
        self.raster_erase_preview_item.setZValue(91)
        self.raster_erase_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def clear_area_paint_preview(self):
        item = getattr(self, "area_paint_preview_item", None)
        if item is not None:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.area_paint_preview_item = None
        self.original_restore_preview_item = None

    def _draw_area_paint_preview(self, now):
        self.clear_area_paint_preview()
        if self.area_paint_start is None:
            return
        mode = self.main.cb_mode.currentIndex() if getattr(self.main, "cb_mode", None) is not None else 4
        if mode in (2, 3):
            color = self.main.current_mask_overlay_color(mode) if hasattr(self.main, "current_mask_overlay_color") else (QColor(0, 0, 255, 220) if mode == 3 else QColor(168, 93, 102, 220))
        else:
            color = QColor(str(getattr(self.main, "final_paint_color", "#FFFFFF") or "#FFFFFF"))
            if not color.isValid():
                color = QColor("#FFFFFF")
        preview = QColor(color)
        preview.setAlpha(90)
        pen = QPen(QColor(255, 215, 0, 220), self.ui_pen_width(2), Qt.PenStyle.DashLine)
        brush = QBrush(preview)

        if getattr(self, "area_paint_shape", "rect") in ("free", "polygon"):
            points = list(getattr(self, "area_paint_points", []) or [])
            if len(points) < 1:
                points = [self.area_paint_start]
            close = self._area_path_preview_should_close("area_paint", points, now)
            path = self._make_area_polyline_path(points, now, close=close)
            if path is None:
                return
            self.area_paint_preview_item = self.scene.addPath(path, pen, brush)
        else:
            rect = QRectF(self.area_paint_start, now).normalized()
            if rect.width() < 1 or rect.height() < 1:
                return
            self.area_paint_preview_item = self.scene.addRect(rect, pen, brush)
        self.area_paint_preview_item.setZValue(88)
        self.area_paint_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _area_paint_region_path(self, end_pos):
        if self.area_paint_start is None:
            return None
        if getattr(self, "area_paint_shape", "rect") in ("free", "polygon"):
            points = list(getattr(self, "area_paint_points", []) or [])
            if not points:
                points = [self.area_paint_start]
            if end_pos is not None:
                points.append(end_pos)
            if len(points) < 3:
                return None
            path = self._make_area_polyline_path(points, None, close=True)
            if path is None or path.boundingRect().width() < 2 or path.boundingRect().height() < 2:
                return None
            return path

        rect = QRectF(self.area_paint_start, end_pos).normalized()
        if rect.width() < 2 or rect.height() < 2:
            return None
        path = QPainterPath()
        path.addRect(rect)
        return path

    def _area_paint_region_mask_np(self, region_path, width, height):
        """QPainterPath 영역을 uint8 mask로 rasterize한다."""
        if region_path is None or width <= 0 or height <= 0:
            return None
        qimg = QImage(int(width), int(height), QImage.Format.Format_Grayscale8)
        qimg.fill(0)
        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillPath(region_path, QBrush(QColor(255, 255, 255)))
        painter.end()
        ptr = qimg.bits()
        ptr.setsize(qimg.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((qimg.height(), qimg.bytesPerLine()))
        return arr[:, :qimg.width()].copy()

    def clear_original_restore_preview(self):
        item = getattr(self, "original_restore_preview_item", None)
        if item is not None:
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        self.original_restore_preview_item = None

    def _draw_original_restore_preview(self, now):
        self.clear_original_restore_preview()
        if self.original_restore_start is None:
            return
        preview = QColor(37, 99, 235, 70)
        pen = QPen(QColor(59, 130, 246, 230), self.ui_pen_width(2), Qt.PenStyle.DashLine)
        brush = QBrush(preview)
        if getattr(self, "original_restore_shape", "rect") in ("free", "polygon"):
            points = list(getattr(self, "original_restore_points", []) or [])
            if len(points) < 1:
                points = [self.original_restore_start]
            close = self._area_path_preview_should_close("original_restore", points, now)
            path = self._make_area_polyline_path(points, now, close=close)
            if path is None:
                return
            self.original_restore_preview_item = self.scene.addPath(path, pen, brush)
        else:
            rect = QRectF(self.original_restore_start, now).normalized()
            if rect.width() < 1 or rect.height() < 1:
                return
            self.original_restore_preview_item = self.scene.addRect(rect, pen, brush)
        self.original_restore_preview_item.setZValue(89)
        self.original_restore_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _original_restore_region_path(self, end_pos):
        if self.original_restore_start is None:
            return None
        if getattr(self, "original_restore_shape", "rect") in ("free", "polygon"):
            points = list(getattr(self, "original_restore_points", []) or [])
            if not points:
                points = [self.original_restore_start]
            if end_pos is not None:
                points.append(end_pos)
            if len(points) < 3:
                return None
            path = self._make_area_polyline_path(points, None, close=True)
            if path is None or path.boundingRect().width() < 2 or path.boundingRect().height() < 2:
                return None
            return path
        rect = QRectF(self.original_restore_start, end_pos).normalized()
        if rect.width() < 2 or rect.height() < 2:
            return None
        path = QPainterPath()
        path.addRect(rect)
        return path

    def _original_restore_region_mask_np(self, region_path, width, height):
        return self._area_paint_region_mask_np(region_path, width, height)

    def show_original_restore_selection(self, region_path):
        self.clear_original_restore_preview()
        if region_path is None:
            return
        preview = QColor(37, 99, 235, 70)
        pen = QPen(QColor(59, 130, 246, 230), self.ui_pen_width(2), Qt.PenStyle.DashLine)
        brush = QBrush(preview)
        self.original_restore_preview_item = self.scene.addPath(region_path, pen, brush)
        self.original_restore_preview_item.setZValue(89)
        self.original_restore_preview_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _apply_area_paint_rect(self, end_pos):
        if self.area_paint_start is None:
            return False
        mode = self.main.cb_mode.currentIndex() if getattr(self.main, "cb_mode", None) is not None else 4
        if mode not in (2, 3, 4):
            return False
        region_path = self._area_paint_region_path(end_pos)
        if region_path is None:
            return False

        if mode in (2, 3):
            if self.user_mask_item is None:
                return False
            before_mask = self.get_mask_np()
            if before_mask is None:
                rect = self.scene.sceneRect()
                before_mask = np.zeros((max(1, int(rect.height())), max(1, int(rect.width()))), dtype=np.uint8)
            h, w = before_mask.shape[:2]
            region_mask = self._area_paint_region_mask_np(region_path, w, h)
            if region_mask is None:
                return False
            try:
                qrect = region_path.boundingRect().toAlignedRect().adjusted(-2, -2, 2, 2).intersected(self.user_mask_item.pixmap().rect())
            except Exception:
                qrect = self.user_mask_item.pixmap().rect()
            if qrect is None or qrect.isEmpty():
                return False
            before_patch = self.user_mask_item.pixmap().copy(qrect)

            combined = cv2.bitwise_or(before_mask.astype(np.uint8), region_mask.astype(np.uint8))
            color = self.main.current_mask_overlay_color(mode) if hasattr(self.main, "current_mask_overlay_color") else (QColor(0, 0, 255, 220) if mode == 3 else QColor(168, 93, 102, 220))
            self.set_user_mask_np(combined, color)
            after_patch = self.user_mask_item.pixmap().copy(qrect)
            try:
                record = {
                    "_brush_record": True,
                    "target_item": self.user_mask_item,
                    "kind": "mask",
                    "patches": [{"rect": qrect, "before": before_patch, "after": after_patch}],
                }
                if hasattr(self.main, "undo_push_paint_record"):
                    self.main.undo_push_paint_record(self, record, kind="mask", reason="영역 마스킹", max_history=80)
                else:
                    self.history.append(record)
                    if len(self.history) > 80:
                        self.history.pop(0)
                    self.redo_history.clear()
                    self._append_paint_history_undo_marker("mask", "영역 마스킹")
            except Exception:
                pass
            try:
                curr = self.main.data.get(self.main.idx)
                if isinstance(curr, dict):
                    self.main.set_active_mask(curr, combined, mode)
            except Exception:
                pass
            return True

        target_item = self.final_paint_above_item if getattr(self.main, "final_paint_above_text", False) else self.final_paint_item
        if target_item is None:
            return False
        pix = target_item.pixmap()
        if pix.isNull():
            return False

        # 영역 페인팅은 일반 브러시와 달리 PageBrushEngine을 거치지 않기 때문에,
        # 여기서 직접 before/after 패치 히스토리를 만들어야 Ctrl+Z/Ctrl+Y가 동작한다.
        # 전체 레이어를 복사하면 큰 페이지에서 무겁기 때문에, 선택 path의 bounding rect만 patch로 잡는다.
        try:
            qrect = region_path.boundingRect().toAlignedRect().adjusted(-2, -2, 2, 2).intersected(pix.rect())
        except Exception:
            qrect = pix.rect()
        if qrect is None or qrect.isEmpty():
            return False
        before_patch = pix.copy(qrect)

        color = QColor(str(getattr(self.main, "final_paint_color", "#FFFFFF") or "#FFFFFF"))
        if not color.isValid():
            color = QColor("#FFFFFF")
        opacity = max(1, min(100, int(getattr(self.main, "final_paint_opacity", 100) or 100)))
        color.setAlpha(int(round(255 * opacity / 100)))
        p = QPainter(pix)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillPath(region_path, QBrush(color))
        p.end()
        after_patch = pix.copy(qrect)
        target_item.setPixmap(pix)
        if target_item is self.final_paint_above_item:
            self.final_paint_above_img = pix.toImage()
        else:
            self.final_paint_img = pix.toImage()

        try:
            record = {
                "_brush_record": True,
                "target_item": target_item,
                "kind": "final_paint",
                "patches": [{"rect": qrect, "before": before_patch, "after": after_patch}],
            }
            if hasattr(self.main, "undo_push_paint_record"):
                self.main.undo_push_paint_record(self, record, kind="final_paint", reason="영역 페인팅", max_history=80)
            else:
                self.history.append(record)
                if len(self.history) > 80:
                    self.history.pop(0)
                self.redo_history.clear()
                self._append_paint_history_undo_marker("final_paint", "영역 페인팅")
        except Exception:
            pass
        return True

    def apply_magic_wand_final_paint(self, mask):
        """요술봉 선택 영역을 현재 최종 페인팅 색상으로 칠한다."""
        if mask is None:
            return False
        target_item = self.final_paint_above_item if getattr(self.main, "final_paint_above_text", False) else self.final_paint_item
        if target_item is None:
            return False
        pix = target_item.pixmap()
        if pix.isNull():
            return False
        try:
            m = (mask.astype(np.uint8) > 0).astype(np.uint8) * 255
        except Exception:
            return False
        h, w = m.shape[:2]
        if w != pix.width() or h != pix.height():
            try:
                m = cv2.resize(m, (pix.width(), pix.height()), interpolation=cv2.INTER_NEAREST)
                h, w = m.shape[:2]
            except Exception:
                return False
        ys, xs = np.where(m > 0)
        if xs.size == 0 or ys.size == 0:
            return False
        qrect = QRect(int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)).adjusted(-2, -2, 2, 2).intersected(pix.rect())
        if qrect.isEmpty():
            return False
        before_patch = pix.copy(qrect)

        color = QColor(str(getattr(self.main, "final_paint_color", "#FFFFFF") or "#FFFFFF"))
        if not color.isValid():
            color = QColor("#FFFFFF")
        opacity = max(1, min(100, int(getattr(self.main, "final_paint_opacity", 100) or 100)))
        color.setAlpha(int(round(255 * opacity / 100)))

        overlay = QImage(w, h, QImage.Format.Format_ARGB32)
        overlay.fill(color)
        qmask = QImage(m.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        overlay.setAlphaChannel(qmask)

        painter = QPainter(pix)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(0, 0, overlay)
        painter.end()

        after_patch = pix.copy(qrect)
        target_item.setPixmap(pix)
        if target_item is self.final_paint_above_item:
            self.final_paint_above_img = pix.toImage()
        else:
            self.final_paint_img = pix.toImage()
        try:
            record = {
                "_brush_record": True,
                "target_item": target_item,
                "kind": "final_paint",
                "patches": [{"rect": qrect, "before": before_patch, "after": after_patch}],
            }
            if hasattr(self.main, "undo_push_paint_record"):
                self.main.undo_push_paint_record(self, record, kind="final_paint", reason="요술봉 영역 칠하기", max_history=80)
            else:
                self.history.append(record)
                if len(self.history) > 80:
                    self.history.pop(0)
                self.redo_history.clear()
                self._append_paint_history_undo_marker("final_paint", "요술봉 영역 칠하기")
        except Exception:
            pass
        return True

    def apply_original_restore_patch(self, mask):
        """선택 영역에 원본 이미지 조각을 다시 덧씌운다."""
        if mask is None:
            return False
        target_item = self.final_paint_item
        if target_item is None:
            return False
        pix = target_item.pixmap()
        if pix.isNull():
            return False
        try:
            m = (mask.astype(np.uint8) > 0).astype(np.uint8) * 255
        except Exception:
            return False
        h, w = m.shape[:2]
        if w != pix.width() or h != pix.height():
            try:
                m = cv2.resize(m, (pix.width(), pix.height()), interpolation=cv2.INTER_NEAREST)
                h, w = m.shape[:2]
            except Exception:
                return False
        ys, xs = np.where(m > 0)
        if xs.size == 0 or ys.size == 0:
            return False
        src_bgr = None
        try:
            if hasattr(self.main, "get_real_original_image"):
                src_bgr = self.main.get_real_original_image(int(getattr(self.main, "idx", 0) or 0))
        except Exception:
            src_bgr = None
        if src_bgr is None:
            return False
        try:
            if src_bgr.shape[1] != w or src_bgr.shape[0] != h:
                src_bgr = cv2.resize(src_bgr, (w, h), interpolation=cv2.INTER_CUBIC)
        except Exception:
            return False
        qrect = QRect(int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)).adjusted(-2, -2, 2, 2).intersected(pix.rect())
        if qrect.isEmpty():
            return False
        before_patch = pix.copy(qrect)

        src_rgb = cv2.cvtColor(src_bgr, cv2.COLOR_BGR2RGB)
        src_qimg = QImage(src_rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy().convertToFormat(QImage.Format.Format_ARGB32)
        qmask = QImage(m.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        src_qimg.setAlphaChannel(qmask)

        painter = QPainter(pix)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(0, 0, src_qimg)
        painter.end()

        after_patch = pix.copy(qrect)
        target_item.setPixmap(pix)
        self.final_paint_img = pix.toImage()
        try:
            record = {
                "_brush_record": True,
                "target_item": target_item,
                "kind": "final_paint",
                "patches": [{"rect": qrect, "before": before_patch, "after": after_patch}],
            }
            if hasattr(self.main, "undo_push_paint_record"):
                self.main.undo_push_paint_record(self, record, kind="final_paint", reason="영역 원본 복구", max_history=80)
            else:
                self.history.append(record)
                if len(self.history) > 80:
                    self.history.pop(0)
                self.redo_history.clear()
                self._append_paint_history_undo_marker("final_paint", "영역 원본 복구")
        except Exception:
            pass
        return True

    def _scene_rect_bounds(self):
        rect = self.scene.sceneRect()
        return max(1.0, float(rect.width())), max(1.0, float(rect.height()))

    def _norm_rect_from_scene(self, rect):
        w, h = self._scene_rect_bounds()
        x1 = max(0.0, min(w, float(rect.left())))
        y1 = max(0.0, min(h, float(rect.top())))
        x2 = max(0.0, min(w, float(rect.right())))
        y2 = max(0.0, min(h, float(rect.bottom())))
        if x2 <= x1 or y2 <= y1:
            return None
        return [x1 / w, y1 / h, x2 / w, y2 / h]

    def _norm_points_from_scene(self, points):
        w, h = self._scene_rect_bounds()
        out = []
        for pt in points or []:
            x = max(0.0, min(w, float(pt.x()))) / w
            y = max(0.0, min(h, float(pt.y()))) / h
            out.append([x, y])
        return out

    def current_ocr_region_payload(self, end_pos):
        if self.ocr_region_start is None:
            return None
        if getattr(self, "ocr_region_shape", "rect") == "rect":
            rect = QRectF(self.ocr_region_start, end_pos).normalized()
            norm_rect = self._norm_rect_from_scene(rect)
            if not norm_rect:
                return None
            return {"shape": "rect", "rect_norm": norm_rect}
        points = list(getattr(self, "ocr_region_points", []) or [])
        if end_pos is not None:
            points.append(end_pos)
        norm_points = self._norm_points_from_scene(points)
        if len(norm_points) < 3:
            return None
        # 저장/분석 엔진은 points_norm 기반 자유형 영역을 이미 이해한다.
        # 폴리곤도 같은 포맷으로 저장해 호환성을 유지한다.
        return {"shape": "free", "points_norm": norm_points}

    def quick_ocr_rect_payload(self, end_pos):
        if self.quick_ocr_start is None:
            return None
        rect = QRectF(self.quick_ocr_start, end_pos).normalized()
        return self._norm_rect_from_scene(rect)

    def _quick_ocr_rect_changed_significantly(self, old_rect, new_rect, tolerance=0.004):
        """빠른 OCR 드래그 중 손떨림 수준의 작은 이동은 같은 영역으로 본다.

        tolerance는 정규화 좌표 기준이다. 0.004면 1000px 이미지에서 약 4px 정도라
        사용자가 영역을 유지하고 있는 상태와 새 영역으로 옮긴 상태를 적당히 가른다.
        """
        if not old_rect or not new_rect:
            return True
        try:
            old_vals = [float(x) for x in old_rect]
            new_vals = [float(x) for x in new_rect]
            if len(old_vals) != 4 or len(new_vals) != 4:
                return True
            return max(abs(a - b) for a, b in zip(old_vals, new_vals)) > float(tolerance)
        except Exception:
            return True

    def _schedule_quick_ocr_hold_check(self, end_pos):
        rect_norm = self.quick_ocr_rect_payload(end_pos)
        old_rect = copy.deepcopy(getattr(self, "quick_ocr_current_rect_norm", None))
        if not rect_norm:
            if old_rect is not None:
                self.quick_ocr_current_rect_norm = None
                self.quick_ocr_revision += 1
            return

        if old_rect is not None and not self._quick_ocr_rect_changed_significantly(old_rect, rect_norm):
            # 미세한 손떨림은 같은 영역으로 보고 기존 결과/타이머를 유지한다.
            return

        self.quick_ocr_current_rect_norm = copy.deepcopy(rect_norm)
        self.quick_ocr_revision += 1
        # 이미 인식된 결과가 있다면 새 영역을 읽는 동안에도 마우스를 떼기 전까지 유지한다.
        try:
            latest = str(getattr(self.main, "quick_ocr_latest_text", "") or "").strip()
            if latest and hasattr(self.main, "show_quick_ocr_result_popup"):
                self.main.show_quick_ocr_result_popup(latest)
        except Exception:
            pass
        try:
            self.quick_ocr_hold_timer.start(200)
        except Exception:
            pass

    def _trigger_quick_ocr_if_still_holding(self):
        if self.draw_mode != 'quick_ocr' or not getattr(self, "is_quick_ocr_drawing", False):
            return
        rect_norm = copy.deepcopy(getattr(self, "quick_ocr_current_rect_norm", None))
        if not rect_norm:
            return
        revision = int(getattr(self, "quick_ocr_revision", 0) or 0)
        if revision == int(getattr(self, "quick_ocr_last_requested_revision", -1) or -1):
            return
        self.quick_ocr_last_requested_revision = revision
        if hasattr(self.main, "run_quick_ocr_region_live"):
            self.main.run_quick_ocr_region_live(rect_norm, request_id=revision)
        elif hasattr(self.main, "run_quick_ocr_region"):
            self.main.run_quick_ocr_region(rect_norm)

    def draw_ocr_analysis_regions(self, regions):
        self.clear_ocr_region_overlay()
        if not regions:
            return
        w, h = self._scene_rect_bounds()
        red_pen = QPen(QColor(199, 138, 144, 225), self.ui_pen_width(3), Qt.PenStyle.SolidLine)
        no_brush = QBrush(Qt.BrushStyle.NoBrush)
        label_font = QFont("Arial", self.ui_font_size(11), QFont.Weight.Bold)
        for region in regions or []:
            if not isinstance(region, dict):
                continue
            shape = str(region.get("shape") or "rect")
            item = None
            label_x = 0.0
            label_y = 0.0
            if shape == "free":
                pts = region.get("points_norm") or []
                if len(pts) < 3:
                    continue
                path = QPainterPath()
                try:
                    first = pts[0]
                    path.moveTo(float(first[0]) * w, float(first[1]) * h)
                    label_x = float(first[0]) * w
                    label_y = float(first[1]) * h
                    for pt in pts[1:]:
                        path.lineTo(float(pt[0]) * w, float(pt[1]) * h)
                    path.closeSubpath()
                except Exception:
                    continue
                item = self.scene.addPath(path, red_pen, no_brush)
            else:
                r = region.get("rect_norm") or []
                if len(r) < 4:
                    continue
                try:
                    x1, y1, x2, y2 = [float(v) for v in r[:4]]
                except Exception:
                    continue
                rect = QRectF(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h).normalized()
                if rect.width() < 1 or rect.height() < 1:
                    continue
                label_x, label_y = rect.left(), rect.top()
                item = self.scene.addRect(rect, red_pen, no_brush)
            if item is not None:
                item.setZValue(84)
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.ocr_region_overlay_items.append(item)

                text = self.scene.addText("OCR 분석 영역", label_font)
                text.setDefaultTextColor(Qt.GlobalColor.black)
                br = text.boundingRect()
                pad_x, pad_y = self.ui_pad(5.0), self.ui_pad(2.0)
                label_bg = self.scene.addRect(
                    QRectF(label_x, max(0.0, label_y - br.height() - pad_y * 2), br.width() + pad_x * 2, br.height() + pad_y * 2),
                    QPen(Qt.PenStyle.NoPen),
                    QBrush(QColor(165, 245, 120, 235))
                )
                label_bg.setZValue(85)
                label_bg.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                text.setPos(label_bg.rect().left() + pad_x, label_bg.rect().top() + pad_y)
                text.setZValue(86)
                text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.ocr_region_overlay_items.append(label_bg)
                self.ocr_region_overlay_items.append(text)

    def clear_inpaint_group_preview_overlay(self):
        if not hasattr(self, "inpaint_group_preview_items"):
            self.inpaint_group_preview_items = []
        # scene.clear()/base-image rebuild may delete the C++ QGraphicsItems
        # underneath the Python wrappers.  Detach the list first and only remove
        # items that are still alive and still attached to this scene.  This
        # prevents preview-mode page changes from touching stale wrappers.
        items = list(self.inpaint_group_preview_items or [])
        self.inpaint_group_preview_items = []
        for item in items:
            try:
                if not self._qgraphics_item_is_alive(item):
                    continue
                if item.scene() is self.scene:
                    self.scene.removeItem(item)
            except Exception:
                pass

    def draw_inpaint_group_preview_regions(self, groups):
        """Draw mask-group based inpainting crop preview overlays.

        Groups are passed as normalized final crop rectangles.  The mask is the
        beacon, but the displayed rectangle is the actual image area that would
        be sent to the inpainting backend after context padding.
        """
        self.clear_inpaint_group_preview_overlay()
        if not groups:
            return
        w, h = self._scene_rect_bounds()
        orange_pen = QPen(QColor(255, 132, 0, 245), self.ui_pen_width(4), Qt.PenStyle.SolidLine)
        fill_brush = QBrush(QColor(255, 236, 64, 58))
        label_brush = QBrush(QColor(255, 236, 64, 235))
        label_font = QFont("Arial", self.ui_font_size(12), QFont.Weight.Bold)
        for group in groups or []:
            if not isinstance(group, dict):
                continue
            r = group.get("rect_norm") or []
            if len(r) < 4:
                continue
            try:
                x1, y1, x2, y2 = [float(v) for v in r[:4]]
            except Exception:
                continue
            rect = QRectF(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h).normalized()
            if rect.width() < 1 or rect.height() < 1:
                continue
            box = self.scene.addRect(rect, orange_pen, fill_brush)
            box.setZValue(88)
            box.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            try:
                self._set_layer_tag(box, "inpaint_group_preview")
            except Exception:
                pass
            self.inpaint_group_preview_items.append(box)

            label_text = str(group.get("index") or group.get("group") or "?")
            text_item = self.scene.addText(label_text, label_font)
            text_item.setDefaultTextColor(Qt.GlobalColor.black)
            br = text_item.boundingRect()
            pad_x, pad_y = self.ui_pad(6.0), self.ui_pad(2.5)
            label_rect = QRectF(
                rect.left(),
                rect.top(),
                max(br.width() + pad_x * 2, self.ui_pad(22.0)),
                br.height() + pad_y * 2,
            )
            label_bg = self.scene.addRect(label_rect, QPen(Qt.PenStyle.NoPen), label_brush)
            label_bg.setZValue(89)
            label_bg.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            text_item.setPos(label_rect.left() + pad_x, label_rect.top() + pad_y)
            text_item.setZValue(90)
            text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            try:
                self._set_layer_tag(label_bg, "inpaint_group_preview")
                self._set_layer_tag(text_item, "inpaint_group_preview")
            except Exception:
                pass
            self.inpaint_group_preview_items.append(label_bg)
            self.inpaint_group_preview_items.append(text_item)

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

        pen = QPen(QColor(255, 230, 0), self.ui_pen_width(2), Qt.PenStyle.SolidLine)
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

    def _build_mask_overlay_qimage(self, mask, color, width, height):
        """Build a semi-transparent ARGB overlay from a binary/gray mask.

        Qt의 setAlphaChannel()은 채널을 그대로 덮어써서 color.alpha()를 잃기 쉬우므로,
        화면 표시용 마스크는 색상 알파와 마스크 알파를 곱해서 항상 같은 농도로 보이게 한다.
        """
        if mask is None:
            img = QImage(int(width), int(height), QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
            return img
        m = mask
        if getattr(m, "ndim", 2) == 3:
            import cv2
            m = cv2.cvtColor(m, cv2.COLOR_RGB2GRAY)
        m = np.asarray(m, dtype=np.uint8)
        if m.shape[:2] != (int(height), int(width)):
            import cv2
            m = cv2.resize(m, (int(width), int(height)), interpolation=cv2.INTER_NEAREST)
        alpha_base = max(0, min(255, int(color.alpha())))
        alpha = ((m.astype(np.uint16) * alpha_base) // 255).astype(np.uint8)
        bgra = np.zeros((int(height), int(width), 4), dtype=np.uint8)
        bgra[..., 0] = int(color.blue())
        bgra[..., 1] = int(color.green())
        bgra[..., 2] = int(color.red())
        bgra[..., 3] = alpha
        return QImage(bgra.data, int(width), int(height), int(width) * 4, QImage.Format.Format_ARGB32).copy()

    def set_mask_overlay_layer(self, mask, color):
        """Add/replace only the mask overlay on the current base layer.

        This is the lightweight path for same-page tab switching. Unlike
        set_overlay(), it does not clear the whole scene or rebuild the base
        image.
        """
        try:
            if self.user_mask_item is not None:
                self.scene.removeItem(self.user_mask_item)
        except Exception:
            pass
        self.user_mask_item = None
        self.user_mask_img = None

        rect = self.scene.sceneRect()
        w = int(rect.width())
        h = int(rect.height())
        if w <= 0 or h <= 0:
            try:
                base_item = getattr(self, "_layer_base_item", None)
                if base_item is not None and not base_item.pixmap().isNull():
                    w = int(base_item.pixmap().width())
                    h = int(base_item.pixmap().height())
            except Exception:
                pass
        if w <= 0 or h <= 0:
            return False

        try:
            self.user_mask_img = self._build_mask_overlay_qimage(mask, color, w, h)
        except Exception:
            self.user_mask_img = QImage(w, h, QImage.Format.Format_ARGB32)
            self.user_mask_img.fill(Qt.GlobalColor.transparent)

        self.user_mask_item = self.scene.addPixmap(QPixmap.fromImage(self.user_mask_img))
        self.user_mask_item.setZValue(10)
        self.user_mask_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        try:
            self._set_layer_tag(self.user_mask_item, "mask_overlay")
        except Exception:
            pass
        return True

    def set_user_mask_np(self, mask, color):
        if self.user_mask_item is None or mask is None:
            return

        if mask.ndim == 3:
            import cv2
            mask = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY)

        h, w = mask.shape[:2]
        color_img = self._build_mask_overlay_qimage(mask, color, w, h)

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

        try:
            base_x, base_y = self.main.text_clipboard_visible_anchor(src_items)
        except Exception:
            first = src_items[0].get('rect') or [0, 0, 1, 1]
            try:
                base_x = float(first[0]) + float(src_items[0].get('x_off', 0) or 0)
                base_y = float(first[1]) + float(src_items[0].get('y_off', 0) or 0)
            except Exception:
                base_x, base_y = 0.0, 0.0
        try:
            px, py = self.main.text_clipboard_paste_origin_from_cursor(src_items, scene_pos)
        except Exception:
            px -= 263.0
            py -= 83.0

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


    def _analysis_toggle_target_at(self, scene_pos):
        """분석도에서 단일 클릭으로 ON/OFF 토글할 대상 박스를 찾는다.

        QGraphicsItem 이벤트만 믿으면 텍스트 번호 라벨이나 ScrollHandDrag 상태에 따라
        첫 클릭이 뷰 쪽으로 흘러가서 더블클릭처럼 느껴지는 경우가 생길 수 있다.
        그래서 분석도에서는 뷰 레벨에서 먼저 hit-test를 수행해 단일 클릭을 확정 처리한다.
        """
        if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() != 1:
            return None
        try:
            curr = self.main.data.get(self.main.idx)
            rows = curr.get('data', []) if curr else []
        except Exception:
            return None
        if not rows:
            return None

        try:
            base_w = int(self.analysis_number_box_size())
        except Exception:
            base_w = 40
        bg_h = max(1, int(base_w * 0.9))

        x0 = float(scene_pos.x())
        y0 = float(scene_pos.y())

        # 위에 그려진 번호 박스/나중에 추가된 박스가 우선 잡히도록 역순으로 검사한다.
        for d in reversed(rows):
            try:
                x, y, w, h = d['rect']
            except Exception:
                continue

            # 텍스트 본체 박스
            if x <= x0 <= x + w and y <= y0 <= y + h:
                return d

            # 번호 라벨 박스. draw_static_boxes와 같은 계산을 사용한다.
            id_str = str(d.get('id', ''))
            bg_w = max(1, base_w + (len(id_str) - 1) * max(1, int(base_w * 0.4)))
            bx, by = x, y - bg_h
            if by < 0:
                by = y
            if bx <= x0 <= bx + bg_w and by <= y0 <= by + bg_h:
                return d
        return None

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


    def _inline_editor_at_view_pos(self, view_pos):
        """Return the active inline editor if the view position is inside it.

        While the direct inline editor is open, mouse events inside its bounds must
        belong only to the editor.  Otherwise CAD text selection / text-drag logic
        can also consume the same press/move/release and turn a caret click into a
        fake text move.
        """
        try:
            editor = getattr(self.main, "inline_text_editor", None)
        except Exception:
            editor = None
        if editor is None:
            return None
        try:
            if bool(getattr(editor, "_closing", False)):
                return None
        except Exception:
            pass
        try:
            if editor.scene() is None:
                return None
        except RuntimeError:
            return None
        except Exception:
            pass

        try:
            clicked = self.itemAt(view_pos)
            item = clicked
            while item is not None:
                if item is editor:
                    return editor
                try:
                    item = item.parentItem()
                except Exception:
                    break
        except Exception:
            pass

        try:
            scene_pos = self.mapToScene(view_pos)
            local = editor.mapFromScene(scene_pos)
            rect = editor.boundingRect().adjusted(-4, -4, 4, 4)
            if rect.contains(local):
                return editor
        except Exception:
            pass
        return None

    def _finish_inline_editor_on_external_text_click(self, e):
        """Commit an active inline text editor when the user clicks outside it.

        CAD/text editing rule: once an inline editor is open, a left click on the
        background or another text object means "finish the current text edit".
        The click must not be routed into the old editor, and a blank click must
        not immediately create a new text box.  If another text box was clicked,
        the current edit is committed first, then only that top-hit text is
        selected for the next operation.
        """
        try:
            if e.button() != Qt.MouseButton.LeftButton:
                return False
        except Exception:
            return False
        try:
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() != 4:
                return False
        except Exception:
            return False
        try:
            editor = getattr(self.main, "inline_text_editor", None)
        except Exception:
            editor = None
        if editor is None:
            return False
        try:
            if bool(getattr(editor, "_closing", False)):
                return False
        except Exception:
            pass

        # Inside-editor clicks are handled by _route_active_inline_editor_mouse_event().
        try:
            if self._inline_editor_at_view_pos(e.pos()) is not None:
                return False
        except Exception:
            pass

        try:
            pt = self.mapToScene(e.pos())
        except Exception:
            return False

        try:
            self._text_select_trace(
                'INLINE_EDITOR_EXTERNAL_CLICK_COMMIT_BEGIN',
                scene_x=round(float(pt.x()), 2),
                scene_y=round(float(pt.y()), 2),
            )
        except Exception:
            pass

        try:
            self.main.finish_inline_text_edit(commit=True, refresh=True, reselect=False, commit_reason='external_click')
        except TypeError:
            try:
                self.main.finish_inline_text_edit(commit=True, refresh=True, reselect=False)
            except TypeError:
                self.main.finish_inline_text_edit(commit=True, refresh=True)
        except Exception as exc:
            try:
                self._text_select_trace('INLINE_EDITOR_EXTERNAL_CLICK_COMMIT_ERROR', error=repr(exc))
            except Exception:
                pass

        try:
            self._inline_editor_mouse_grab_active = False
        except Exception:
            pass
        try:
            self._clear_direct_text_drag_candidate()
        except Exception:
            pass
        try:
            self._cad_text_group_drag_active = False
            self._cad_text_group_drag_items = []
            self._cad_text_group_drag_before = {}
        except Exception:
            pass

        hit_after_commit = None
        try:
            hit_after_commit = self._scene_text_item_at(pt)
        except Exception:
            hit_after_commit = None

        if hit_after_commit is not None:
            try:
                selected_now = [x for x in self.scene.selectedItems() if isinstance(x, TypesettingItem)]
                if hit_after_commit not in selected_now:
                    self._cad_set_selection_from_items([hit_after_commit], subtract=False, push_undo=True, active_item=hit_after_commit, replace=False)
                else:
                    self._cad_set_preferred_text_style_source(hit_after_commit)
                    if hasattr(self.main, "on_scene_selection_changed"):
                        self.main.on_scene_selection_changed()
                try:
                    self._cad_begin_group_drag(hit_after_commit, pt, e, collapse_on_click=False)
                except Exception:
                    pass
            except Exception:
                try:
                    scene_obj = self.scene()
                    if scene_obj is not None:
                        scene_obj.clearSelection()
                    hit_after_commit.setSelected(True)
                    if hasattr(self.main, "on_scene_selection_changed"):
                        self.main.on_scene_selection_changed()
                except Exception:
                    pass
            try:
                self._text_select_trace('INLINE_EDITOR_EXTERNAL_CLICK_COMMIT_SELECT_TEXT', text_id=getattr(hit_after_commit, 'data', {}).get('id'))
            except Exception:
                pass
            try:
                e.accept()
            except Exception:
                pass
            return True

        # Blank background click completes the edit only.  It must not create a
        # fresh text object just because the text tool is still active.
        try:
            scene_obj = self.scene()
            if scene_obj is not None:
                scene_obj.clearSelection()
        except Exception:
            pass
        try:
            if hasattr(self.main, "end_active_text_transform"):
                self.main.end_active_text_transform(refresh=False)
        except Exception:
            pass
        try:
            if hasattr(self.main, "on_scene_selection_changed"):
                self.main.on_scene_selection_changed()
        except Exception:
            pass
        try:
            self.force_tool_cursor_refresh(delay_followups=True)
        except Exception:
            try:
                self.update_tool_cursor(force=True)
            except Exception:
                pass
        try:
            self._text_select_trace('INLINE_EDITOR_EXTERNAL_CLICK_COMMIT_BACKGROUND')
        except Exception:
            pass
        try:
            e.accept()
        except Exception:
            pass
        return True

    def _route_active_inline_editor_mouse_event(self, e, phase="press"):
        """Let the active inline editor consume internal mouse events first."""
        try:
            pos = e.pos()
        except Exception:
            pos = None
        editor = self._inline_editor_at_view_pos(pos) if pos is not None else None
        phase = str(phase or "")
        if phase == "press":
            if editor is None:
                self._inline_editor_mouse_grab_active = False
                return False
            try:
                self._inline_editor_mouse_grab_active = True
            except Exception:
                pass
        else:
            if editor is None and not bool(getattr(self, "_inline_editor_mouse_grab_active", False)):
                return False

        try:
            if editor is not None:
                editor.setCursor(Qt.CursorShape.IBeamCursor)
        except Exception:
            pass
        try:
            super(MuleImageViewer, self).mousePressEvent(e) if phase == "press" else (
                super(MuleImageViewer, self).mouseMoveEvent(e) if phase == "move" else (
                    super(MuleImageViewer, self).mouseDoubleClickEvent(e) if phase == "double" else super(MuleImageViewer, self).mouseReleaseEvent(e)
                )
            )
        except Exception:
            pass
        if phase in ("release", "double"):
            try:
                self._inline_editor_mouse_grab_active = False
            except Exception:
                pass
        try:
            e.accept()
        except Exception:
            pass
        return True

    def mousePressEvent(self, e):
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and self._route_active_inline_editor_mouse_event(e, "press"):
            return
        if self._finish_inline_editor_on_external_text_click(e):
            return

        try:
            if (
                e.button() == Qt.MouseButton.LeftButton
                and getattr(self.main, "cb_mode", None) is not None
                and self.main.cb_mode.currentIndex() == 4
                and hasattr(self.main, "focus_final_text_canvas_for_shortcut")
            ):
                self.main.focus_final_text_canvas_for_shortcut(reason='final_canvas_mouse_press')
        except Exception:
            pass

        # 휠 클릭 드래그: 어떤 도구/탭에서도 부담 없이 화면을 이동한다.
        # Qt ScrollHandDrag는 기본적으로 좌클릭 흐름과 섞이기 쉬워서,
        # 휠 버튼은 viewer가 직접 스크롤바를 움직인다.
        if e.button() == Qt.MouseButton.MiddleButton:
            self._middle_pan_active = True
            try:
                self._middle_pan_last_pos = e.pos()
            except Exception:
                self._middle_pan_last_pos = None
            try:
                self._apply_tool_cursor_to_view(QCursor(Qt.CursorShape.ClosedHandCursor))
            except Exception:
                pass
            try:
                self._begin_view_pan_undo()
                self._begin_view_interaction_fast_path('middle_pan', delay_ms=220)
                self._view_fast_path_log('VIEW_FAST_PATH_MIDDLE_PAN_BEGIN')
            except Exception:
                pass
            e.accept()
            return

        # 분석도에서는 영역/번호 라벨을 한 번 클릭하면 즉시 사용 여부를 토글한다.
        # 이 처리는 분석도에만 한정해 마스크 편집/최종 식질 클릭 동작에는 영향을 주지 않는다.
        if e.button() == Qt.MouseButton.LeftButton:
            target = self._analysis_toggle_target_at(self.mapToScene(e.pos()))
            if target is not None:
                self.main.toggle_check_from_box(target)
                e.accept()
                return


        # Final tab eyedropper must win over text transform/move handling.
        # Otherwise Alt+click on a selected text box can be interpreted as a move.
        if (
            e.button() == Qt.MouseButton.LeftButton
            and getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
            and e.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            pt = self.mapToScene(e.pos())
            self.main.pick_final_paint_color_from_scene(int(pt.x()), int(pt.y()), global_pos=e.globalPosition().toPoint())
            e.accept()
            return

        if self._cad_text_selection_mouse_press(e):
            return

        if (
            e.button() == Qt.MouseButton.LeftButton
            and self._is_final_move_mode()
            and not (e.modifiers() & Qt.KeyboardModifier.AltModifier)
        ):
            pt = self.mapToScene(e.pos())
            raster_item = self._raster_text_item_at(pt)
            if raster_item is not None:
                if self._begin_raster_text_view_drag(raster_item, pt, e):
                    e.accept()
                    return
            else:
                try:
                    if self._final_text_hit_debug_enabled():
                        clicked = self.itemAt(e.pos())
                        clicked_name = type(clicked).__name__ if clicked is not None else 'None'
                        stack = []
                        for item in self.scene.items(pt):
                            stack.append(f"{type(item).__name__}:z={item.zValue()}")
                        self._log_final_text_hit_debug(f"🔎 객체 텍스트 선택 실패: itemAt={clicked_name}, stack={', '.join(stack[:8])}")
                except Exception:
                    pass

        if (
            getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
            and getattr(self, "draw_mode", None) in (None, 'final_text')
        ):
            active_transform = self.main.current_transform_data_item() if hasattr(self.main, 'current_transform_data_item') else None
            if active_transform is not None:
                pt = self.mapToScene(e.pos())
                active_item = self._active_transform_item_obj()
                hit_item = self._scene_text_item_at(pt)
                active_id = active_transform.get('id')

                # 핸들/테두리/회전 핸들이 QGraphicsView 기본 hit-test에 안 잡히는 경우를 직접 처리한다.
                if active_item is not None and e.button() == Qt.MouseButton.LeftButton:
                    local = active_item.mapFromScene(pt)
                    if active_item.data.get('_skew_mode', False):
                        action = active_item.skew_action_at(local)
                        if action and active_item.begin_skew_action(action, local, pt):
                            self._active_transform_item = active_item
                            self.setCursor(self._cursor_for_transform_action(action))
                            e.accept()
                            return
                    elif active_item.data.get('_trapezoid_mode', False):
                        action = active_item.trapezoid_action_at(local)
                        if action and active_item.begin_trapezoid_action(action, local, pt):
                            self._active_transform_item = active_item
                            self.setCursor(self._cursor_for_transform_action(action))
                            e.accept()
                            return
                    elif active_item.data.get('_arc_mode', False):
                        action = active_item.arc_action_at(local)
                        if not action:
                            action = active_item.create_or_replace_arc_handle_at(local)
                        if action and active_item.begin_arc_action(action, local, pt):
                            self._active_transform_item = active_item
                            self.setCursor(self._cursor_for_transform_action(action))
                            e.accept()
                            return
                    else:
                        action = active_item.transform_action_at(local)

                        if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                            hit_pad = active_item._guide_pad(10.0) if hasattr(active_item, "_guide_pad") else 10.0
                            if active_item.transform_rect().adjusted(-hit_pad, -hit_pad, hit_pad, hit_pad).contains(local):
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
                    hit_id = getattr(hit_item, 'data', {}).get('id') if hit_item is not None else None
                    active_id_s = str(active_id) if active_id is not None else ''
                    hit_id_s = str(hit_id) if hit_id is not None else ''
                    self._text_select_trace(
                        'TEXT_SELECT_TRACE_ACTIVE_MOUSE_PRESS',
                        scene_x=round(float(pt.x()), 2), scene_y=round(float(pt.y()), 2),
                        hit_id=hit_id, active_item_id=(getattr(active_item, 'data', {}) or {}).get('id') if active_item is not None else None,
                        same=(hit_item is not None and hit_id_s == active_id_s),
                    )
                    if hit_item is None or hit_id_s != active_id_s:
                        # 직접 수정/재렌더 후 같은 텍스트라도 id 타입(int/str)이나 data dict가 달라질 수 있다.
                        # 여기서 탈락하면 클릭 순간 변형/선택이 바로 풀리는 토글 버그가 난다.
                        self._text_select_trace('TEXT_SELECT_TRACE_END_ACTIVE_MISMATCH', hit_id=hit_id, active_id=active_id)
                        self.main.end_active_text_transform(refresh=True)
                        e.accept()
                        return
                    # 같은 텍스트를 다시 누른 경우에는 더 이상 viewer가 붙잡지 않는다.
                    # TypesettingItem.shape()/boundingRect()가 OCR/work 박스 전체를 포함하므로
                    # Qt 기본 ItemIsMovable/ItemIsSelectable 흐름에 맡겨야 클릭-드래그-릴리즈가 정상으로 닫힌다.
                    # 여기서 이벤트를 consume하거나 직접 drag 후보를 만들면 클릭 한 번이 계속 붙잡히는 문제가 재발한다.
                    self._text_select_trace('TEXT_SELECT_TRACE_KEEP_ACTIVE_QT_DEFAULT', hit_id=hit_id, active_id=active_id)
                    # fall through to the normal final-text/super mousePress path

        if self.draw_mode == 'paste_text' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
                pt = self.mapToScene(e.pos())
                self.main.finish_text_paste_at(pt)
                return

        if self.draw_mode == 'text_style_clone' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
                pt = self.mapToScene(e.pos())
                hit_text = self._scene_text_item_at(pt)
                if hit_text is not None and hasattr(self.main, "handle_text_style_clone_click"):
                    self.main.handle_text_style_clone_click(hit_text)
                else:
                    try:
                        self.main.log("⚠️ 스타일을 복제할 텍스트를 클릭하세요. ESC로 해제.")
                    except Exception:
                        pass
                e.accept()
                return

        if self.draw_mode == 'final_text' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
                # 텍스트 작성 중에도 배경 클릭은 "현재 텍스트 확정 + 새 텍스트 박스 생성"까지
                # 한 번에 이어져야 한다. 기존 코드는 편집기 밖 클릭을 현재 편집 종료로만 처리하고
                # return해서 포커스/선택이 직전 텍스트에 남는 체감이 생겼다.
                editor = getattr(self.main, "inline_text_editor", None)
                if editor is not None:
                    clicked = self.itemAt(e.pos())
                    inside_editor = clicked is editor
                    try:
                        p = clicked
                        while p is not None and not inside_editor:
                            p = p.parentItem()
                            inside_editor = p is editor
                    except Exception:
                        pass
                    if inside_editor:
                        super().mousePressEvent(e)
                        return
                    pt = self.mapToScene(e.pos())
                    try:
                        self.main.finish_inline_text_edit(commit=True, refresh=True, reselect=False)
                    except TypeError:
                        self.main.finish_inline_text_edit(commit=True, refresh=True)
                    try:
                        self._clear_direct_text_drag_candidate()
                    except Exception:
                        pass
                    try:
                        scene_obj = self.scene()
                        if scene_obj is not None:
                            scene_obj.clearSelection()
                    except Exception:
                        pass
                    hit_after_commit = self._scene_text_item_at(pt)
                    if hit_after_commit is not None:
                        try:
                            selected_now = [x for x in self.scene.selectedItems() if isinstance(x, TypesettingItem)]
                            if hit_after_commit not in selected_now:
                                self._cad_set_selection_from_items([hit_after_commit], subtract=False, push_undo=True, active_item=hit_after_commit, replace=False)
                            else:
                                self._cad_set_preferred_text_style_source(hit_after_commit)
                                if hasattr(self.main, "on_scene_selection_changed"):
                                    self.main.on_scene_selection_changed()
                            self._cad_begin_group_drag(hit_after_commit, pt, e, collapse_on_click=False)
                        except Exception:
                            try:
                                hit_after_commit.setSelected(True)
                                if hasattr(self.main, "on_scene_selection_changed"):
                                    self.main.on_scene_selection_changed()
                            except Exception:
                                pass
                        e.accept()
                        return
                    self.main.create_final_text_at(int(pt.x()), int(pt.y()))
                    e.accept()
                    return

                pt = self.mapToScene(e.pos())
                hit_item = self._scene_text_item_at(pt)
                if hit_item is not None:
                    # 텍스트 도구가 켜진 상태에서도 기존 텍스트를 바로 선택/드래그 이동한다.
                    # 개별 클릭은 반드시 하나의 top hit 텍스트만 선택한다. Qt 기본
                    # mousePressEvent를 타면 겹친 OCR/work 박스가 같이 선택될 수 있어
                    # YSB 선택/드래그 경로로만 처리한다.
                    selected_now = [x for x in self.scene.selectedItems() if isinstance(x, TypesettingItem)]
                    if hit_item not in selected_now:
                        self._cad_set_selection_from_items([hit_item], subtract=False, push_undo=True, active_item=hit_item, replace=False)
                    else:
                        self._cad_set_preferred_text_style_source(hit_item)
                        if hasattr(self.main, "on_scene_selection_changed"):
                            self.main.on_scene_selection_changed()
                    self._cad_begin_group_drag(hit_item, pt, e, collapse_on_click=False)
                    e.accept()
                    return

                self.main.create_final_text_at(int(pt.x()), int(pt.y()))
                return

        if self._is_polygon_area_tool() and e.button() == Qt.MouseButton.LeftButton:
            pt = self.mapToScene(e.pos())
            self._handle_polygon_area_click_at(pt, e)
            e.accept()
            return

        if self._is_cad_free_area_tool() and e.button() == Qt.MouseButton.LeftButton:
            pt = self.mapToScene(e.pos())
            self._handle_polygon_area_click_at(pt, e)
            e.accept()
            return

        if self.is_click_click_area_tool() and e.button() == Qt.MouseButton.LeftButton:
            pt = self.mapToScene(e.pos())
            if self._is_any_click_click_area_active():
                self._finish_click_click_area_tool_at(pt)
            else:
                self._start_click_click_area_tool_at(pt, e)
            e.accept()
            return

        if self.draw_mode == 'raster_erase' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() != 4:
                e.accept()
                return
            self.is_raster_erasing = True
            self.raster_erase_start = self.mapToScene(e.pos())
            self._draw_raster_erase_preview(self.raster_erase_start)
            e.accept()
            return

        if self.draw_mode == 'area_paint' and e.button() == Qt.MouseButton.LeftButton:
            mode = self.main.cb_mode.currentIndex() if getattr(self.main, "cb_mode", None) is not None else 4
            if mode not in (2, 3, 4):
                e.accept()
                return
            self.is_area_painting = True
            self.area_paint_start = self.mapToScene(e.pos())
            self.area_paint_points = [self.area_paint_start]
            # 영역 페인팅/마스킹은 QPixmap patch history로 Undo한다.
            # project undo를 같이 만들면 Ctrl+Z가 paint patch가 아니라 project snapshot을 먼저 타서
            # 실제 칠한 픽셀이 되돌아가지 않는 문제가 생긴다.
            self._area_paint_undo_key = None
            self._draw_area_paint_preview(self.area_paint_start)
            e.accept()
            return

        if self.draw_mode == 'original_restore' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() != 4:
                e.accept()
                return
            self.is_original_restoring = True
            self.original_restore_start = self.mapToScene(e.pos())
            self.original_restore_points = [self.original_restore_start]
            self._draw_original_restore_preview(self.original_restore_start)
            e.accept()
            return

        if self.draw_mode == 'ocr_region_select' and e.button() == Qt.MouseButton.LeftButton:
            self.is_ocr_region_drawing = True
            self.ocr_region_start = self.mapToScene(e.pos())
            self.ocr_region_points = [self.ocr_region_start]
            self._draw_ocr_region_preview(self.ocr_region_start)
            e.accept()
            return

        if self.draw_mode == 'quick_ocr' and e.button() == Qt.MouseButton.LeftButton:
            self.is_quick_ocr_drawing = True
            self.quick_ocr_start = self.mapToScene(e.pos())
            self.quick_ocr_current_rect_norm = None
            self.quick_ocr_revision += 1
            self.quick_ocr_last_requested_revision = -1
            try:
                self.quick_ocr_hold_timer.stop()
            except Exception:
                pass
            if hasattr(self.main, "begin_quick_ocr_drag"):
                self.main.begin_quick_ocr_drag()
            self._draw_quick_ocr_preview(self.quick_ocr_start)
            e.accept()
            return

        if self.draw_mode == 'color_outline_mask' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() not in (2, 3):
                e.accept()
                return
            pt = self.mapToScene(e.pos())
            if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                if hasattr(self.main, "pick_color_outline_mask_from_scene"):
                    self.main.pick_color_outline_mask_from_scene(int(pt.x()), int(pt.y()))
                e.accept()
                return
            self.is_color_outline_masking = True
            self.color_outline_mask_start = pt
            self.color_outline_mask_points = [pt]
            self._draw_color_outline_mask_preview(pt)
            e.accept()
            return

        if self.draw_mode == 'mask_wrap' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() not in (2, 3):
                e.accept()
                return
            self.is_mask_wrapping = True
            self.mask_wrap_start = self.mapToScene(e.pos())
            self.mask_wrap_points = [self.mask_wrap_start]
            self._draw_mask_wrap_preview(self.mask_wrap_start)
            e.accept()
            return

        if self.draw_mode == 'mask_cut' and e.button() == Qt.MouseButton.LeftButton:
            if getattr(self.main, "cb_mode", None) is None or self.main.cb_mode.currentIndex() not in (2, 3):
                e.accept()
                return
            self.is_mask_cutting = True
            self.mask_cut_start = self.mapToScene(e.pos())
            self.mask_cut_points = [self.mask_cut_start]
            self._draw_mask_cut_preview(self.mask_cut_start)
            e.accept()
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
            if final_mode and self.draw_mode == 'erase':
                # 최종화면 지우개는 배경 페인팅 레이어와 텍스트 객체 레이어를 같이 지나갈 수 있어야 한다.
                # 이전 방식은 첫 클릭 지점이 객체 위일 때만 객체 지우개로 전환되어,
                # 바깥에서 글자 쪽으로 긁으면 래스터 텍스트가 지워지지 않았다.
                # 이제는 지우개 스트로크 전체가 항상 객체화 텍스트도 함께 검사한다.
                pt = self.mapToScene(e.pos())
                self.is_raster_text_brush_erasing = True
                if hasattr(self.main, "erase_raster_text_brush_line"):
                    self.main.erase_raster_text_brush_line(pt, pt, self.brush_size)

            if final_mode:
                target_item = self.final_paint_above_item if getattr(self.main, "final_paint_above_text", False) else self.final_paint_item
            else:
                target_item = self.user_mask_item

            if target_item:
                self._paint_undo_key = None
                self.last_pt = self.mapToScene(e.pos())
                if final_mode:
                    color = QColor(str(getattr(self.main, "final_paint_color", "#FFFFFF") or "#FFFFFF"))
                    if not color.isValid():
                        color = QColor("#FFFFFF")
                    opacity = max(1, min(100, int(getattr(self.main, "final_paint_opacity", 100) or 100)))
                    color.setAlpha(int(round(255 * opacity / 100)))
                else:
                    idx = self.main.cb_mode.currentIndex()
                    color = self.main.current_mask_overlay_color(idx) if hasattr(self.main, "current_mask_overlay_color") else (QColor(0, 0, 255, 220) if idx == 3 else QColor(168, 93, 102, 220))
                try:
                    self.brush_engine.begin(target_item, self.last_pt, self.draw_mode, color, self.brush_size, final_mode=final_mode)
                except Exception:
                    pass
                try:
                    if hasattr(self.main, "undo_clear_page_redo"):
                        self.main.undo_clear_page_redo(int(getattr(self.main, 'idx', 0) or 0), reason="paint begin")
                except Exception:
                    pass
                if hasattr(self.main, "update_undo_redo_buttons"):
                    self.main.update_undo_redo_buttons()
            else:
                self.last_pt = self.mapToScene(e.pos())
            return
        elif (
            e.button() == Qt.MouseButton.LeftButton
            and getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
        ):
            # 최종 화면에서는 OCR/작업 박스 전체를 텍스트 클릭 영역으로 본다.
            # Qt itemAt()/shape()는 실제 path에 끌려가 빈 OCR 영역을 배경으로 오판할 수 있으므로
            # 먼저 YSB 사각형 hit-test로 텍스트 대상을 확정한다.
            pt = self.mapToScene(e.pos())
            hit_text = self._scene_text_item_at(pt)
            if hit_text is None:
                # 배경 클릭으로 기존 텍스트 선택을 지우지 않는다.
                # 단, 배경을 누른 채 드래그하면 이미지 이동은 되어야 하므로 super()는 통과시킨다.
                selected = [x for x in self.scene.selectedItems() if isinstance(x, TypesettingItem)]
                self._begin_view_pan_undo()
                self.scene.blockSignals(True)
                try:
                    # 절대 인터락: strict OCR/work hit 밖에서 누른 클릭은 Qt 기본
                    # itemAt/shape 경로가 텍스트를 잡더라도 선택 상태에 반영하지 않는다.
                    # 배경 팬 처리는 통과시키되, 텍스트 선택은 press 전 스냅샷으로 복원한다.
                    selected_set = set(selected)
                    super().mousePressEvent(e)
                    for item in self._cad_text_items():
                        try:
                            item.setSelected(item in selected_set)
                        except Exception:
                            pass
                finally:
                    self.scene.blockSignals(False)
                if selected:
                    self.main.on_scene_selection_changed()
                return
            else:
                # Individual final-text click is resolved by YSB strict hit-test,
                # not by Qt default selection.  Qt may see multiple overlapping
                # selectable text shapes and select more than one; here only the
                # top OCR/work hit item is allowed.
                try:
                    self._text_select_trace('TEXT_HIT_SINGLE_PRESS', text_id=hit_text.data.get('id'))
                except Exception:
                    pass
                self._begin_view_pan_undo()
                try:
                    selected_now = [x for x in self.scene.selectedItems() if isinstance(x, TypesettingItem)]
                except Exception:
                    selected_now = []
                already_selected = bool(hit_text in selected_now)
                if not already_selected:
                    self._cad_set_selection_from_items([hit_text], subtract=False, push_undo=True, active_item=hit_text, replace=False)
                else:
                    self._cad_set_preferred_text_style_source(hit_text)
                    try:
                        if hasattr(self.main, "on_scene_selection_changed"):
                            self.main.on_scene_selection_changed()
                    except Exception:
                        pass
                self._cad_begin_group_drag(hit_text, pt, e, collapse_on_click=False)
                e.accept()
                return

        if e.button() == Qt.MouseButton.LeftButton:
            self._begin_view_pan_undo()
        super().mousePressEvent(e)


    def mouseDoubleClickEvent(self, e):
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and self._route_active_inline_editor_mouse_event(e, "double"):
            return

        if e.button() == Qt.MouseButton.MiddleButton:
            # 마우스 휠 버튼 더블클릭: 현재 창/뷰포트 크기에 맞춰 이미지 전체를 최대 크기로 표시한다.
            if self.fit_image_to_current_viewport():
                e.accept()
                return

        # 분석도 박스는 단일 클릭 토글이 원칙이다.
        # 더블클릭 이벤트는 추가 토글 없이 소비해서 상태가 두 번 바뀌는 일을 막는다.
        if e.button() == Qt.MouseButton.LeftButton:
            target = self._analysis_toggle_target_at(self.mapToScene(e.pos()))
            if target is not None:
                e.accept()
                return

            if (
                getattr(self.main, "cb_mode", None) is not None
                and self.main.cb_mode.currentIndex() == 4
                and getattr(self, "draw_mode", None) in (None, 'final_text')
            ):
                active_item = self._active_transform_item_obj()
                if active_item is not None and active_item.data.get('_skew_mode', False):
                    pt = self.mapToScene(e.pos())
                    local = active_item.mapFromScene(pt)
                    action = active_item.skew_action_at(local)
                    if action:
                        current_pct = float(active_item.data.get('skew_x' if action in ('top', 'bottom') else 'skew_y', 0) or 0)
                        current_angle = math.degrees(math.atan(current_pct / 100.0))
                        angle, ok = QInputDialog.getDouble(self, "평행사변형 변형", "기울임 각도(도):", current_angle, -45.0, 45.0, 1)
                        if ok:
                            try:
                                if hasattr(self.main, 'undo_text_checkpoint'):
                                    self.main.undo_text_checkpoint('평행사변형 변형 각도 지정')
                            except Exception:
                                pass
                            active_item.set_text_skew_angle(action, angle)
                            try:
                                if hasattr(self.main, 'schedule_deferred_auto_save_project'):
                                    self.main.schedule_deferred_auto_save_project()
                                else:
                                    self.main.auto_save_project()
                                self.main.reselect_text_items([active_item.data.get('id')])
                                self.main.log(f"🔷 평행사변형 변형 각도 지정: {angle}°")
                            except Exception:
                                pass
                        e.accept()
                        return
                if active_item is not None and active_item.data.get('_trapezoid_mode', False):
                    pt = self.mapToScene(e.pos())
                    local = active_item.mapFromScene(pt)
                    action = active_item.trapezoid_action_at(local)
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
                        current_pct = int(round(float(active_item.data.get(side_key, 0) or 0)))
                        value, ok = QInputDialog.getInt(self, '사다리꼴 변형', f'{side_name} 크기(%)', current_pct, -95, 95, 1)
                        if ok:
                            try:
                                if hasattr(self.main, 'undo_text_checkpoint'):
                                    self.main.undo_text_checkpoint('사다리꼴 변형 수치 지정')
                            except Exception:
                                pass
                            if side_key == 'trap_left':
                                active_item.set_text_trapezoid_values(left_pct=value)
                            elif side_key == 'trap_right':
                                active_item.set_text_trapezoid_values(right_pct=value)
                            elif side_key == 'trap_top':
                                active_item.set_text_trapezoid_values(top_pct=value)
                            else:
                                active_item.set_text_trapezoid_values(bottom_pct=value)
                            try:
                                if hasattr(self.main, 'schedule_deferred_auto_save_project'):
                                    self.main.schedule_deferred_auto_save_project()
                                else:
                                    self.main.auto_save_project()
                                self.main.reselect_text_items([active_item.data.get('id')])
                                self.main.log(f"🔷 사다리꼴 변형 수치 지정: {side_name} {value}%")
                            except Exception:
                                pass
                        e.accept()
                        return
                if active_item is not None and active_item.data.get('_arc_mode', False):
                    pt = self.mapToScene(e.pos())
                    local = active_item.mapFromScene(pt)
                    action = active_item.arc_action_at(local)
                    if action:
                        idx = active_item._arc_index_from_action(action) if hasattr(active_item, '_arc_index_from_action') else -1
                        handles = active_item._arc_handles() if hasattr(active_item, '_arc_handles') else []
                        if 0 <= idx < len(handles):
                            handle = handles[idx]
                            side = str(handle.get('side') or '')
                            side_name = {'top':'위쪽','bottom':'아래쪽','left':'왼쪽','right':'오른쪽'}.get(side, side)
                            current_pct = int(round(float(handle.get('value', 0) or 0)))
                            value, ok = QInputDialog.getInt(self, '부채꼴 변형', f'{side_name} 제어점 휘어짐(%)', current_pct, -100, 100, 1)
                            if ok:
                                try:
                                    if hasattr(self.main, 'undo_text_checkpoint'):
                                        self.main.undo_text_checkpoint('부채꼴 변형 수치 지정')
                                except Exception:
                                    pass
                                active_item.set_text_arc_handle_value(idx, value)
                                try:
                                    if hasattr(self.main, 'schedule_deferred_auto_save_project'):
                                        self.main.schedule_deferred_auto_save_project()
                                    else:
                                        self.main.auto_save_project()
                                    self.main.reselect_text_items([active_item.data.get('id')])
                                    self.main.log(f"🔷 부채꼴 변형 수치 지정: {side_name} 제어점 {value}%")
                                except Exception:
                                    pass
                        e.accept()
                        return
            # 최종 화면 텍스트 더블클릭은 Qt shape가 아니라 YSB OCR/work rect hit-test로 확정한다.
            # 단, 브러시/마스크/요술봉 같은 다른 도구 모드에서는 텍스트 편집을 열지 않는다.
            if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
                draw_mode = getattr(self, "draw_mode", None)
                if draw_mode is None or draw_mode == 'final_text':
                    pt = self.mapToScene(e.pos())
                    hit_item = self._scene_text_item_at(pt)
                    if hit_item is not None and not getattr(hit_item, "is_paste_preview", False):
                        try:
                            # 더블클릭 편집은 현재 다중선택을 해당 텍스트 1개로 바꾸고 들어간다.
                            # 단순 클릭/영역 선택은 누적, 더블클릭은 편집 대상 단독 선택이 기대 동작이다.
                            if self._cad_text_selection_enabled():
                                self._cad_push_text_selection_undo()
                                tid = getattr(hit_item, 'data', {}).get('id')
                                self._cad_apply_text_selection_ids([tid], notify=True)
                            if not bool(getattr(hit_item, 'data', {}).get('rasterized_text')) and hasattr(self.main, "start_inline_text_edit"):
                                self.main.start_inline_text_edit(hit_item, click_scene_pos=pt)
                                e.accept()
                                return
                        except Exception:
                            pass

        super().mouseDoubleClickEvent(e)

    def mouseMoveEvent(self, e):
        if self._route_active_inline_editor_mouse_event(e, "move"):
            return

        try:
            if e.buttons() and hasattr(self.main, 'note_ui_interaction_activity'):
                self.main.note_ui_interaction_activity(900)
        except Exception:
            pass
        if getattr(self, '_middle_pan_active', False):
            if not (e.buttons() & Qt.MouseButton.MiddleButton):
                self._middle_pan_active = False
                self._middle_pan_last_pos = None
                try:
                    self.force_tool_cursor_refresh(delay_followups=True)
                except Exception:
                    pass
            else:
                try:
                    pos = e.pos()
                    last = getattr(self, '_middle_pan_last_pos', None)
                    if last is not None:
                        delta = pos - last
                        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
                        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
                    self._middle_pan_last_pos = pos
                    self._begin_view_interaction_fast_path('middle_pan', delay_ms=220)
                    self._view_fast_path_log('VIEW_FAST_PATH_MIDDLE_PAN_MOVE')
                except Exception:
                    pass
                e.accept()
                return

        if self._cad_text_selection_mouse_move(e):
            return

        if getattr(self, "draw_mode", None) in ("draw", "erase"):
            try:
                scene_pos = self.mapToScene(e.pos())
                if e.buttons() & Qt.MouseButton.LeftButton:
                    # During an actual stroke the preview must stay attached to
                    # the real paint position.
                    self.request_brush_cursor_preview(scene_pos, immediate=True)
                else:
                    # Hover movement should be cheap: hide while the cursor is
                    # moving and show the px-size ring only after the mouse rests.
                    if getattr(self, "_brush_cursor_preview_items", None):
                        self.clear_brush_cursor_preview(reset_position=False)
                    self.request_brush_cursor_preview(scene_pos, delay_ms=150, restart=True)
            except Exception:
                pass
        elif getattr(self, "_brush_cursor_preview_items", None):
            try:
                self.clear_brush_cursor_preview()
            except Exception:
                pass

        if (
            e.buttons() & Qt.MouseButton.LeftButton
            and getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
            and e.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            try:
                pt = self.mapToScene(e.pos())
                self.main.pick_final_paint_color_from_scene(int(pt.x()), int(pt.y()), global_pos=e.globalPosition().toPoint())
            except Exception:
                pass
            e.accept()
            return

        # 텍스트 객체 이동은 TypesettingItem 자체의 ItemIsMovable 경로에 맡긴다.
        # 이전의 viewer 직접 드래그 후보는 선택 고정 땜빵과 충돌해 mouse release 후에도
        # text_drag 상태가 남는 원인이 되었으므로 사용하지 않는다.

        if self._raster_view_drag_item is not None:
            item = self._raster_view_drag_item
            try:
                pt = self.mapToScene(e.pos())
                delta = QPointF(pt) - QPointF(self._raster_view_drag_scene_press)
                item.setPos(QPointF(self._raster_view_drag_item_press) + delta)
                item.update()
                self._raster_view_drag_moved = True
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            except Exception:
                pass
            e.accept()
            return

        if self._active_transform_item is not None:
            item = self._active_transform_item
            pt = self.mapToScene(e.pos())
            try:
                if getattr(item, '_skew_action', None):
                    item.update_skew_action(item.mapFromScene(pt), pt)
                    self.setCursor(self._cursor_for_transform_action(getattr(item, '_skew_action', None)))
                elif getattr(item, '_trapezoid_action', None):
                    item.update_trapezoid_action(item.mapFromScene(pt), pt)
                    self.setCursor(self._cursor_for_transform_action(getattr(item, '_trapezoid_action', None)))
                elif getattr(item, '_arc_action', None):
                    item.update_arc_action(item.mapFromScene(pt), pt)
                    self.setCursor(self._cursor_for_transform_action(getattr(item, '_arc_action', None)))
                else:
                    item.update_transform_action(item.mapFromScene(pt), pt)
                    self.setCursor(self._cursor_for_transform_action(getattr(item, '_transform_action', None)))
            except Exception:
                pass
            e.accept()
            return

        if (
            getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
            and getattr(self, "draw_mode", None) in (None, 'final_text')
        ):
            active_item = self._active_transform_item_obj()
            if active_item is not None and (active_item.data.get('_transform_mode', False) or active_item.data.get('_skew_mode', False) or active_item.data.get('_trapezoid_mode', False) or active_item.data.get('_arc_mode', False)):
                pt = self.mapToScene(e.pos())
                local = active_item.mapFromScene(pt)
                if active_item.data.get('_skew_mode', False):
                    action = active_item.skew_action_at(local)
                elif active_item.data.get('_trapezoid_mode', False):
                    action = active_item.trapezoid_action_at(local)
                elif active_item.data.get('_arc_mode', False):
                    action = active_item.arc_action_at(local)
                else:
                    action = active_item.transform_action_at(local)
                    if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                        hit_pad = active_item._guide_pad(10.0) if hasattr(active_item, "_guide_pad") else 10.0
                        if active_item.transform_rect().adjusted(-hit_pad, -hit_pad, hit_pad, hit_pad).contains(local):
                            action = 'move'
                if action:
                    self.setCursor(self._cursor_for_transform_action(action))
                else:
                    self.update_tool_cursor()

        if self.draw_mode == 'raster_erase' and getattr(self, "is_raster_erasing", False):
            now = self.mapToScene(e.pos())
            self._draw_raster_erase_preview(now)
            e.accept()
            return


        if self.draw_mode == 'area_paint' and getattr(self, "is_area_painting", False):
            now = self.mapToScene(e.pos())
            if getattr(self, "area_paint_shape", "rect") == "free":
                self.area_paint_points = self._append_scene_point_if_moved(getattr(self, "area_paint_points", []) or [], now, min_sq=9.0)
            self._draw_area_paint_preview(now)
            e.accept()
            return

        if self.draw_mode == 'original_restore' and getattr(self, "is_original_restoring", False):
            now = self.mapToScene(e.pos())
            if getattr(self, "original_restore_shape", "rect") == "free":
                self.original_restore_points = self._append_scene_point_if_moved(getattr(self, "original_restore_points", []) or [], now, min_sq=9.0)
            self._draw_original_restore_preview(now)
            e.accept()
            return

        if self.draw_mode == 'ocr_region_select' and getattr(self, "is_ocr_region_drawing", False):
            now = self.mapToScene(e.pos())
            if getattr(self, "ocr_region_shape", "rect") == "free":
                self.ocr_region_points = self._append_scene_point_if_moved(getattr(self, "ocr_region_points", []) or [], now, min_sq=9.0)
            self._draw_ocr_region_preview(now)
            e.accept()
            return

        if self.draw_mode == 'quick_ocr' and getattr(self, "is_quick_ocr_drawing", False):
            now = self.mapToScene(e.pos())
            self._draw_quick_ocr_preview(now)
            self._schedule_quick_ocr_hold_check(now)
            e.accept()
            return

        if self.draw_mode == 'ocr_region_select' and getattr(self, "is_ocr_region_drawing", False):
            end_pos = self.mapToScene(e.pos())
            payload = self.current_ocr_region_payload(end_pos)
            self.is_ocr_region_drawing = False
            self.ocr_region_start = None
            self.ocr_region_points = []
            self.clear_ocr_region_preview()
            if payload is not None and hasattr(self.main, "add_ocr_analysis_region_payload"):
                self.main.add_ocr_analysis_region_payload(payload)
            e.accept()
            return

        if self.draw_mode == 'quick_ocr' and getattr(self, "is_quick_ocr_drawing", False):
            self.is_quick_ocr_drawing = False
            self.quick_ocr_start = None
            self.quick_ocr_current_rect_norm = None
            try:
                self.quick_ocr_hold_timer.stop()
            except Exception:
                pass
            self.clear_quick_ocr_preview()
            if hasattr(self.main, "finish_quick_ocr_drag"):
                self.main.finish_quick_ocr_drag()
            e.accept()
            return

        if self.draw_mode == 'color_outline_mask' and getattr(self, "is_color_outline_masking", False):
            now = self.mapToScene(e.pos())
            if getattr(self, "color_outline_mask_shape", "rect") == "free":
                self.color_outline_mask_points = self._append_scene_point_if_moved(getattr(self, "color_outline_mask_points", []) or [], now, min_sq=9.0)
            self._draw_color_outline_mask_preview(now)
            e.accept()
            return

        if self.draw_mode == 'mask_wrap' and getattr(self, "is_mask_wrapping", False):
            now = self.mapToScene(e.pos())
            if getattr(self, "mask_wrap_shape", "rect") == "free":
                self.mask_wrap_points = self._append_scene_point_if_moved(getattr(self, "mask_wrap_points", []) or [], now, min_sq=9.0)
            self._draw_mask_wrap_preview(now)
            e.accept()
            return

        if self.draw_mode == 'mask_cut' and getattr(self, "is_mask_cutting", False):
            now = self.mapToScene(e.pos())
            if getattr(self, "mask_cut_shape", "rect") == "free":
                self.mask_cut_points = self._append_scene_point_if_moved(getattr(self, "mask_cut_points", []) or [], now, min_sq=9.0)
            self._draw_mask_cut_preview(now)
            e.accept()
            return

        if (
            self.draw_mode == 'paste_text'
            and getattr(self.main, "cb_mode", None) is not None
            and self.main.cb_mode.currentIndex() == 4
        ):
            self.show_paste_preview(getattr(self.main, "text_clipboard", []), self.mapToScene(e.pos()))
            return

        if self.draw_mode == 'erase' and getattr(self, "is_raster_text_brush_erasing", False) and self.last_pt:
            now = self.mapToScene(e.pos())
            if hasattr(self.main, "erase_raster_text_brush_line"):
                self.main.erase_raster_text_brush_line(self.last_pt, now, self.brush_size)
            # 여기서 return하지 않는다. 같은 스트로크가 기존 최종 페인팅 레이어도
            # 계속 지울 수 있어야 지우개 동작이 자연스럽다. last_pt 갱신은 아래
            # 일반 draw/erase 처리에서 한 번만 한다.

        if self.draw_mode in ('draw', 'erase') and self.last_pt:
            now = self.mapToScene(e.pos())
            try:
                if getattr(self, "brush_engine", None) is not None and self.brush_engine.active:
                    self.brush_engine.extend(now)
                    self.last_pt = now
                    e.accept()
                    return
            except Exception:
                pass

        # 아무 버튼도 누르지 않은 단순 마우스 이동은 QGraphicsScene hover/hit-test를 깨우지 않는다.
        # 큰 텍스트 path가 많은 최종결과 탭에서 이 super() 호출이 마우스 이동 렉의 주범이 될 수 있다.
        if e.buttons() == Qt.MouseButton.NoButton and self.draw_mode is None:
            e.accept()
            return

        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and self._route_active_inline_editor_mouse_event(e, "release"):
            return

        if e.button() == Qt.MouseButton.LeftButton:
            try:
                if hasattr(self.main, '_hide_eyedropper_color_feedback'):
                    self.main._hide_eyedropper_color_feedback()
            except Exception:
                pass

        if self._cad_text_selection_mouse_release(e):
            return

        if e.button() == Qt.MouseButton.LeftButton and self._is_polygon_area_tool() and self._is_any_click_click_area_active():
            # 폴리곤 영역은 시작점 근처를 다시 클릭해야 닫힌다.
            # 일반 release 확정 로직으로 새면 점 하나 찍자마자 영역이 끝나버린다.
            e.accept()
            return

        if e.button() == Qt.MouseButton.LeftButton and self._is_cad_free_area_tool() and self._is_any_click_click_area_active():
            # CAD 자유형은 마우스 이동 경로를 체크포인트로 저장하고, 시작점 근처 클릭 때만 닫는다.
            # release가 기존 누르고 끌기 확정 로직으로 새면 안 된다.
            e.accept()
            return

        if e.button() == Qt.MouseButton.LeftButton and self.is_click_click_area_tool() and self._is_any_click_click_area_active():
            # CAD 방식의 영역 지정은 두 번째 클릭에서 확정한다.
            # 첫 클릭의 mouseRelease가 기존 누르고 끌기 확정 로직으로 새면 안 된다.
            e.accept()
            return

        if e.button() == Qt.MouseButton.MiddleButton and getattr(self, '_middle_pan_active', False):
            self._middle_pan_active = False
            self._middle_pan_last_pos = None
            try:
                self.force_tool_cursor_refresh(delay_followups=True)
            except Exception:
                pass
            try:
                if hasattr(self.main, "remember_current_view_state"):
                    self.main.remember_current_view_state()
                if hasattr(self.main, "schedule_source_compare_sync"):
                    self.main.schedule_source_compare_sync(180)
            except Exception:
                pass
            try:
                self._view_fast_path_log('VIEW_FAST_PATH_MIDDLE_PAN_END')
            except Exception:
                pass
            self._finish_view_pan_undo()
            e.accept()
            return

        # Safety: old direct-text-drag path is no longer used. If a stale candidate remains
        # from a previous press/move path, clear it on release so text_drag cannot stay latched.
        if getattr(self, '_direct_text_drag_item', None) is not None:
            try:
                item = getattr(self, '_direct_text_drag_item', None)
                if item is not None:
                    item._finish_text_move_fast_path()
            except Exception:
                pass
            try:
                self._clear_direct_text_drag_candidate()
            except Exception:
                pass

        if self._raster_view_drag_item is not None:
            self._finish_raster_text_view_drag()
            e.accept()
            return

        if self._active_transform_item is not None:
            try:
                if getattr(self._active_transform_item, '_transform_action', None):
                    self._active_transform_item.finish_transform_action()
                elif getattr(self._active_transform_item, '_skew_action', None):
                    self._active_transform_item.finish_skew_action()
                elif getattr(self._active_transform_item, '_trapezoid_action', None):
                    self._active_transform_item.finish_trapezoid_action()
                elif getattr(self._active_transform_item, '_arc_action', None):
                    self._active_transform_item.finish_arc_action()
            except Exception:
                pass
            self._active_transform_item = None
            self.force_tool_cursor_refresh(delay_followups=True)
            e.accept()
            return

        if self.draw_mode == 'erase' and getattr(self, "is_raster_text_brush_erasing", False):
            self.is_raster_text_brush_erasing = False
            if hasattr(self.main, "finish_raster_text_brush_erase"):
                self.main.finish_raster_text_brush_erase()
            # return하지 않는다. 같은 지우개 스트로크에서 일반 최종 페인팅 레이어도
            # 지웠다면 아래 was_painting 정리/Undo 확정까지 같이 지나가야 한다.


        if self.draw_mode == 'raster_erase' and getattr(self, "is_raster_erasing", False):
            end_pos = self.mapToScene(e.pos())
            rect = QRectF(self.raster_erase_start, end_pos).normalized() if self.raster_erase_start is not None else QRectF()
            self.is_raster_erasing = False
            self.raster_erase_start = None
            self.clear_raster_erase_preview()
            if hasattr(self.main, "apply_raster_text_erase_rect"):
                self.main.apply_raster_text_erase_rect(rect)
            try:
                self.main.set_tool(None)
            except Exception:
                self.draw_mode = None
            e.accept()
            return

        if self.draw_mode == 'area_paint' and getattr(self, "is_area_painting", False):
            end_pos = self.mapToScene(e.pos())
            self.is_area_painting = False
            applied = self._apply_area_paint_rect(end_pos)
            self.area_paint_start = None
            self.area_paint_points = []
            self.clear_area_paint_preview()
            if applied:
                mode = self.main.cb_mode.currentIndex() if getattr(self.main, "cb_mode", None) is not None else 4
                if hasattr(self.main, "undo_commit_paint_layer"):
                    self.main.undo_commit_paint_layer("mask" if mode in (2, 3) else "final_paint", delay_ms=1200)
                elif hasattr(self.main, "schedule_deferred_view_layer_commit"):
                    self.main.schedule_deferred_view_layer_commit("mask" if mode in (2, 3) else "final_paint", delay_ms=1200)
            self._area_paint_undo_key = None
            e.accept()
            return

        if self.draw_mode == 'ocr_region_select' and getattr(self, "is_ocr_region_drawing", False):
            end_pos = self.mapToScene(e.pos())
            if getattr(self, "ocr_region_shape", "rect") == "free":
                pts = getattr(self, "ocr_region_points", []) or []
                if not pts:
                    self.ocr_region_points = [end_pos]
                else:
                    last = pts[-1]
                    dx = end_pos.x() - last.x()
                    dy = end_pos.y() - last.y()
                    if (dx * dx + dy * dy) >= 9:
                        pts.append(end_pos)
                        self.ocr_region_points = pts
            payload = self.current_ocr_region_payload(end_pos)
            self.is_ocr_region_drawing = False
            self.ocr_region_start = None
            self.ocr_region_points = []
            self.clear_ocr_region_preview()
            if payload is not None and hasattr(self.main, "add_ocr_analysis_region_payload"):
                self.main.add_ocr_analysis_region_payload(payload)
            e.accept()
            return

        if self.draw_mode == 'quick_ocr' and getattr(self, "is_quick_ocr_drawing", False):
            self.is_quick_ocr_drawing = False
            self.quick_ocr_start = None
            self.quick_ocr_current_rect_norm = None
            try:
                self.quick_ocr_hold_timer.stop()
            except Exception:
                pass
            self.clear_quick_ocr_preview()
            if hasattr(self.main, "finish_quick_ocr_drag"):
                self.main.finish_quick_ocr_drag()
            e.accept()
            return

        if self.draw_mode == 'color_outline_mask' and getattr(self, "is_color_outline_masking", False):
            end_pos = self.mapToScene(e.pos())
            region = self._color_outline_mask_region_np(end_pos)
            self.is_color_outline_masking = False
            self.color_outline_mask_start = None
            self.color_outline_mask_points = []
            self.clear_color_outline_mask_preview()
            if region is not None and hasattr(self.main, "apply_color_outline_mask"):
                self.main.apply_color_outline_mask(region)
            e.accept()
            return

        if self.draw_mode == 'mask_wrap' and getattr(self, "is_mask_wrapping", False):
            end_pos = self.mapToScene(e.pos())
            region = self._mask_wrap_region_np(end_pos)
            self.is_mask_wrapping = False
            self.mask_wrap_start = None
            self.mask_wrap_points = []
            self.clear_mask_wrap_preview()
            if region is not None and hasattr(self.main, "apply_mask_wrapping"):
                self.main.apply_mask_wrapping(region)
            e.accept()
            return

        if self.draw_mode == 'mask_cut' and getattr(self, "is_mask_cutting", False):
            end_pos = self.mapToScene(e.pos())
            region = self._mask_cut_region_np(end_pos)
            self.is_mask_cutting = False
            self.mask_cut_start = None
            self.mask_cut_points = []
            self.clear_mask_cut_preview()
            if region is not None and hasattr(self.main, "apply_mask_cutting"):
                self.main.apply_mask_cutting(region)
            e.accept()
            return

        if self.draw_mode == 'original_restore' and getattr(self, "is_original_restoring", False):
            end_pos = self.mapToScene(e.pos())
            if getattr(self, "original_restore_shape", "rect") == "free":
                pts = getattr(self, "original_restore_points", []) or []
                if not pts:
                    self.original_restore_points = [end_pos]
                else:
                    last = pts[-1]
                    dx = end_pos.x() - last.x()
                    dy = end_pos.y() - last.y()
                    if (dx * dx + dy * dy) >= 9:
                        pts.append(end_pos)
                        self.original_restore_points = pts
            region_path = self._original_restore_region_path(end_pos)
            region_mask = None
            try:
                scene_rect = self.scene.sceneRect()
                region_mask = self._original_restore_region_mask_np(region_path, int(scene_rect.width()), int(scene_rect.height()))
            except Exception:
                region_mask = None
            self.is_original_restoring = False
            self.original_restore_start = None
            self.original_restore_points = []
            if region_path is not None:
                self.show_original_restore_selection(region_path)
            else:
                self.clear_original_restore_preview()
            if hasattr(self.main, "set_original_restore_selection"):
                self.main.set_original_restore_selection(region_mask, region_path)
            e.accept()
            return

        was_painting = self.is_mask_painting
        self.is_mask_painting = False
        self.last_pt = None

        if was_painting:
            try:
                if getattr(self, "brush_engine", None) is not None and self.brush_engine.active:
                    self.brush_engine.commit()
                elif self._stroke_preview_path is not None:
                    self._commit_stroke_preview_to_layer()
            except Exception:
                pass
            if getattr(self.main, "cb_mode", None) is not None and self.main.cb_mode.currentIndex() == 4:
                if hasattr(self.main, "undo_commit_paint_layer"):
                    self.main.undo_commit_paint_layer("final_paint", delay_ms=1200)
                elif hasattr(self.main, "schedule_deferred_view_layer_commit"):
                    self.main.schedule_deferred_view_layer_commit("final_paint", delay_ms=1200)
                elif hasattr(self.main, "on_final_paint_edited"):
                    self.main.on_final_paint_edited()
            elif self.user_mask_item:
                if hasattr(self.main, "undo_commit_paint_layer"):
                    self.main.undo_commit_paint_layer("mask", delay_ms=1200)
                elif hasattr(self.main, "schedule_deferred_view_layer_commit"):
                    self.main.schedule_deferred_view_layer_commit("mask", delay_ms=1200)
                elif hasattr(self.main, "on_view_mask_edited"):
                    self.main.on_view_mask_edited()
            self._paint_undo_key = None
            try:
                if getattr(self, "draw_mode", None) in ("draw", "erase"):
                    self.request_brush_cursor_preview(self.mapToScene(e.pos()), delay_ms=80, restart=True)
            except Exception:
                pass

        super().mouseReleaseEvent(e)
        self._finish_view_pan_undo()
        

    def leaveEvent(self, e):
        try:
            self.clear_brush_cursor_preview()
        except Exception:
            pass
        try:
            super().leaveEvent(e)
        except Exception:
            pass

    def wheelEvent(self, e):
        try:
            if hasattr(self.main, 'note_ui_interaction_activity'):
                self.main.note_ui_interaction_activity(1200)
        except Exception:
            pass
        mods = e.modifiers()
        ctrl_pressed = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt_pressed = bool(mods & Qt.KeyboardModifier.AltModifier)

        if ctrl_pressed and not alt_pressed and not self.is_cad_operation_mode():
            # 그림판 방식: Ctrl+휠은 확대/축소가 아니라 가로 스크롤로 사용한다.
            # Alt+휠은 기존 확대/축소 조작으로 유지하고, CAD 방식은 일반 휠 확대/축소를 유지한다.
            try:
                if hasattr(self.main, "begin_coalesced_view_undo"):
                    self.main.begin_coalesced_view_undo("화면 가로 이동", delay_ms=500)
            except Exception:
                pass
            self._begin_view_interaction_fast_path('horizontal_scroll', delay_ms=160)
            ad = e.angleDelta()
            pd = e.pixelDelta()
            delta_y = int(ad.y())
            delta_x = int(ad.x())
            pixel_y = int(pd.y()) if not pd.isNull() else 0
            pixel_x = int(pd.x()) if not pd.isNull() else 0
            raw_delta = pixel_y or pixel_x or delta_y or delta_x
            hbar = self.horizontalScrollBar()
            if not pd.isNull() and (pixel_y or pixel_x):
                amount = int(raw_delta)
            else:
                try:
                    step = max(40, int(hbar.singleStep()) * 8)
                except Exception:
                    step = 120
                amount = int((float(raw_delta) / 120.0) * float(step)) if raw_delta else 0
            if amount:
                hbar.setValue(int(hbar.value()) - int(amount))
            self._view_fast_path_log(
                'VIEW_FAST_PATH_HORIZONTAL_SCROLL',
                source='ctrl_wheel',
                raw_delta=int(raw_delta),
                amount=int(amount),
                delta_y=int(delta_y),
                delta_x=int(delta_x),
                pixel_y=int(pixel_y),
                pixel_x=int(pixel_x),
            )
            try:
                if hasattr(self.main, "remember_current_view_state"):
                    self.main.remember_current_view_state()
                if hasattr(self.main, "schedule_source_compare_sync"):
                    self.main.schedule_source_compare_sync(180)
            except Exception:
                pass
            e.accept()
            return

        wheel_zoom_requested = bool(alt_pressed) or self.is_cad_operation_mode()
        if wheel_zoom_requested:
            # 그림판 방식: Alt+휠 확대/축소.
            # CAD 방식: 일반 휠만 굴려도 확대/축소. Alt+휠은 기존 도구 단축키와 충돌하지 않는
            # 보기 전용 조작으로 유지한다.
            # 연속 휠 입력은 하나의 Ctrl+Z 단계가 되도록 coalesce한다.
            try:
                if not self._view_undo_is_suppressed() and hasattr(self.main, "begin_coalesced_view_undo"):
                    self.main.begin_coalesced_view_undo("화면 확대/축소", delay_ms=500)
            except Exception:
                pass
            self._begin_view_interaction_fast_path('zoom', delay_ms=180)
            ad = e.angleDelta()
            pd = e.pixelDelta()
            delta_y = int(ad.y())
            delta_x = int(ad.x())
            pixel_y = int(pd.y()) if not pd.isNull() else 0
            pixel_x = int(pd.x()) if not pd.isNull() else 0
            delta = delta_y or pixel_y
            # On some Windows/driver combinations Alt+wheel is delivered as a horizontal
            # wheel event.  The previous code only looked at angleDelta().y(), so delta==0
            # always became shrink.  Use the active axis instead so Alt+wheel can both
            # zoom in and zoom out.
            if delta == 0 and (e.modifiers() & Qt.KeyboardModifier.AltModifier):
                delta = delta_x or pixel_x
            if delta == 0:
                delta = delta_y or delta_x or pixel_y or pixel_x
            factor = 1.25 if delta > 0 else 0.8
            self._view_fast_path_log(
                'VIEW_FAST_PATH_ZOOM',
                factor=float(factor),
                delta=int(delta),
                delta_y=int(delta_y),
                delta_x=int(delta_x),
                pixel_y=int(pixel_y),
                pixel_x=int(pixel_x),
                alt=bool(e.modifiers() & Qt.KeyboardModifier.AltModifier),
                ctrl=bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier),
            )
            self.scale(factor, factor)
            try:
                if hasattr(self.main, "remember_current_view_state"):
                    self.main.remember_current_view_state()
                if hasattr(self.main, "schedule_source_compare_sync"):
                    self.main.schedule_source_compare_sync(220)
            except Exception:
                pass
            e.accept()
            return

        # 그림판 방식의 일반 휠 스크롤도 사용자의 보기 조작이다. Ctrl+Z 타임라인에
        # "화면 이동"으로 묶어 넣되, 연속 휠은 하나의 Undo 단계로 합친다.
        try:
            if hasattr(self.main, "begin_coalesced_view_undo"):
                self.main.begin_coalesced_view_undo("화면 이동", delay_ms=500)
        except Exception:
            pass
        self._begin_view_interaction_fast_path('wheel_scroll', delay_ms=160)
        self._view_fast_path_log('VIEW_FAST_PATH_SCROLL', source='wheel', delta=int(e.angleDelta().y()))
        super().wheelEvent(e)
        try:
            if hasattr(self.main, "remember_current_view_state"):
                self.main.remember_current_view_state()
            if hasattr(self.main, "schedule_source_compare_sync"):
                self.main.schedule_source_compare_sync(180)
        except Exception:
            pass
