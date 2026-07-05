
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsEllipseItem
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPixmap, QPainterPath
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF


class PageBrushEngine:
    """Runtime-only brush engine for the active page.

    This engine deliberately knows only the current viewer layer. It does not
    save project.json, does not encode PNG/NPY, and does not touch project-level
    state while the mouse is moving. A stroke creates one small patch-based
    history record on mouse release.
    """

    def __init__(self, viewer):
        self.viewer = viewer
        self.active = False
        self.target_item = None
        self.mode = None
        self.final_mode = False
        self.brush_size = 1
        self.color = QColor("#ffffff")
        self.last_pos = None
        self.preview_items: List[Any] = []
        self.preview_path: Optional[QPainterPath] = None
        self.preview_path_item: Optional[QGraphicsPathItem] = None
        self.paths: List[QPainterPath] = []
        self.dirty_scene_rect: Optional[QRectF] = None
        self.stroke_patches: List[Dict[str, Any]] = []
        # Backward compatibility name for older erase path code.
        self.erase_patches: List[Dict[str, Any]] = self.stroke_patches
        # BRUSH_TILE_LIGHT_PATH:
        # 브러시 Undo/실시간 표시용 원본은 전체 QPixmap을 복사하지 않는다.
        # 스트로크가 처음 건드린 tile만 before snapshot으로 보관하고, commit 때
        # 같은 tile들의 after snapshot을 만들어 하나의 Undo record로 닫는다.
        self.tile_size = 512
        self.stroke_tiles: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.stroke_tile_order: List[Tuple[int, int]] = []
        self.stroke_segment_count = 0
        # Legacy compatibility slot.  Older code may still look for this attr,
        # but the tile path deliberately avoids full-layer copies.
        self.draw_base_pixmap: Optional[QPixmap] = None

    def clear_preview(self) -> None:
        scene = getattr(self.viewer, "scene", None)
        for item in list(self.preview_items):
            try:
                if item is not None and item.scene() is not None and scene is not None:
                    scene.removeItem(item)
            except Exception:
                pass
        self.preview_items = []

    def clear_runtime(self) -> None:
        self.clear_preview()
        self.active = False
        self.target_item = None
        self.mode = None
        self.final_mode = False
        self.last_pos = None
        self.preview_path = None
        self.preview_path_item = None
        self.paths = []
        self.dirty_scene_rect = None
        self.stroke_patches = []
        self.erase_patches = self.stroke_patches
        self.stroke_tiles = {}
        self.stroke_tile_order = []
        self.stroke_segment_count = 0
        self.draw_base_pixmap = None

    def _view_update_scene_rect(self, rect: QRectF, *, force: bool = False) -> None:
        try:
            view_rect = self.viewer.mapFromScene(rect).boundingRect().adjusted(-6, -6, 6, 6)
            self.viewer.viewport().update(view_rect)
            if force:
                self.viewer.viewport().repaint(view_rect)
        except Exception:
            try:
                self.viewer.viewport().update()
                if force:
                    self.viewer.viewport().repaint()
            except Exception:
                pass

    def _add_dirty(self, rect: QRectF) -> None:
        if rect is None or rect.isNull():
            return
        self.dirty_scene_rect = QRectF(rect) if self.dirty_scene_rect is None else self.dirty_scene_rect.united(rect)

    def _note_brush_activity(self, ms: int = 900) -> None:
        """Keep non-brush background/UI work away from the brush hot path."""
        try:
            main = getattr(self.viewer, "main", None)
            if main is not None and hasattr(main, "note_ui_interaction_activity"):
                main.note_ui_interaction_activity(int(ms or 900))
        except Exception:
            pass
        try:
            main = getattr(self.viewer, "main", None)
            if main is not None:
                import time
                until = time.monotonic() + max(0.08, min(float(ms or 900) / 1000.0, 3.0))
                for attr in ("_source_compare_sync_block_until", "_heavy_preview_block_until"):
                    setattr(main, attr, max(float(getattr(main, attr, 0.0) or 0.0), until))
        except Exception:
            pass

    def _tile_size_px(self) -> int:
        try:
            main = getattr(self.viewer, "main", None)
            opts = getattr(main, "app_options", {}) if main is not None else {}
            value = int((opts or {}).get("brush_tile_size", self.tile_size) or self.tile_size)
        except Exception:
            value = int(self.tile_size or 512)
        return max(128, min(value, 1024))

    def _iter_tile_rects(self, qrect: QRect, pix_rect: QRect):
        if qrect is None or qrect.isEmpty():
            return
        try:
            qrect = QRect(qrect).intersected(pix_rect)
        except Exception:
            return
        if qrect.isEmpty():
            return
        tile = self._tile_size_px()
        left = max(0, int(qrect.left()) // tile)
        right = max(0, int(qrect.right()) // tile)
        top = max(0, int(qrect.top()) // tile)
        bottom = max(0, int(qrect.bottom()) // tile)
        for ty in range(top, bottom + 1):
            for tx in range(left, right + 1):
                r = QRect(tx * tile, ty * tile, tile, tile).intersected(pix_rect)
                if not r.isEmpty():
                    yield (tx, ty), r

    def _ensure_tile_snapshots(self, pix: QPixmap, qrect: QRect) -> None:
        if pix is None or pix.isNull() or qrect is None or qrect.isEmpty():
            return
        pix_rect = pix.rect()
        for key, rect in self._iter_tile_rects(qrect, pix_rect) or []:
            if key in self.stroke_tiles:
                continue
            self.stroke_tiles[key] = {"rect": QRect(rect), "before": pix.copy(rect)}
            self.stroke_tile_order.append(key)

    def _tile_patches_from_target(self, pix: QPixmap) -> List[Dict[str, Any]]:
        patches: List[Dict[str, Any]] = []
        if pix is None or pix.isNull():
            return patches
        pix_rect = pix.rect()
        seen = set()
        for key in list(self.stroke_tile_order):
            if key in seen:
                continue
            seen.add(key)
            info = self.stroke_tiles.get(key) or {}
            before = info.get("before")
            rect = info.get("rect")
            if before is None or rect is None:
                continue
            try:
                rect = QRect(rect).intersected(pix_rect)
            except Exception:
                continue
            if rect.isEmpty():
                continue
            patches.append({"rect": rect, "before": before, "after": pix.copy(rect)})
        return patches

    def _audit_tile_event(self, event: str, **kwargs) -> None:
        try:
            main = getattr(self.viewer, "main", None)
            if main is not None and hasattr(main, "audit_boundary_event"):
                main.audit_boundary_event(event, throttle_ms=250, **kwargs)
        except Exception:
            pass

    def _segment_rect(self, a: QPointF, b: QPointF) -> QRectF:
        pad = max(2, int(self.brush_size or 1) + 6)
        return QRectF(a, b).normalized().adjusted(-pad, -pad, pad, pad)

    def _target_rect(self, scene_rect: QRectF):
        pix = self.target_item.pixmap() if self.target_item is not None else QPixmap()
        if pix.isNull():
            return pix, None
        try:
            local_rect = self.target_item.mapFromScene(scene_rect).boundingRect()
            qrect = local_rect.toAlignedRect().adjusted(-2, -2, 2, 2).intersected(pix.rect())
        except Exception:
            try:
                qrect = scene_rect.toAlignedRect().adjusted(-2, -2, 2, 2).intersected(pix.rect())
            except Exception:
                qrect = None
        if qrect is None or qrect.isEmpty():
            return pix, None
        return pix, qrect

    def _map_path_to_target(self, path: QPainterPath) -> QPainterPath:
        try:
            inv, ok = self.target_item.sceneTransform().inverted()
            if ok:
                return inv.map(path)
        except Exception:
            pass
        return path

    def _map_point_to_target(self, pt: QPointF) -> QPointF:
        try:
            return self.target_item.mapFromScene(pt)
        except Exception:
            return pt

    def _paint_segment_patch(self, a_scene: QPointF, b_scene: QPointF, *, erase: bool = False, force: bool = False) -> bool:
        """Apply one brush segment directly to the target pixmap using a dirty rect.

        Earlier draw mode used a temporary QGraphicsPath preview and only committed
        the real pixmap on mouse release. In practice that could show only the
        initial dot on some scenes/layers. This path mirrors the working eraser
        logic: draw the small dirty rect immediately, but store only that rect as
        a patch for Undo/Redo.
        """
        if self.target_item is None:
            return False
        a_scene = QPointF(a_scene)
        b_scene = QPointF(b_scene)
        # A zero-length drawLine is not reliably rendered by every backend, so
        # nudge the endpoint enough for the round cap to make a visible dot.
        if abs(a_scene.x() - b_scene.x()) < 0.001 and abs(a_scene.y() - b_scene.y()) < 0.001:
            b_scene = QPointF(a_scene.x() + 0.15, a_scene.y())
        scene_rect = self._segment_rect(a_scene, b_scene)
        pix, qrect = self._target_rect(scene_rect)
        if qrect is None:
            return False
        try:
            self._note_brush_activity(700)
            self._ensure_tile_snapshots(pix, qrect)
            a_local = self._map_point_to_target(a_scene)
            b_local = self._map_point_to_target(b_scene)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if erase:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                pen = QPen(Qt.GlobalColor.transparent, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            else:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                pen = QPen(self.color, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawLine(a_local, b_local)
            p.end()
            self.target_item.setPixmap(pix)
            self.target_item.update(QRectF(qrect))
            self.stroke_segment_count += 1
            self._add_dirty(scene_rect)
            self._view_update_scene_rect(scene_rect, force=force)
            return True
        except Exception:
            return False

    def _render_draw_live_to_target(self, scene_rect: Optional[QRectF] = None, *, force: bool = False) -> bool:
        """Render only the tiles touched by the latest draw segment.

        The previous live draw path copied the whole layer at stroke start and
        rewound an ever-growing dirty union on every mouse move.  That preserved
        alpha blending quality, but long strokes made the brush hot path grow
        heavier every frame.  This tile path snapshots only touched tiles,
        restores only the currently touched tile(s), and redraws the current
        stroke path clipped to those tile(s).
        """
        if self.target_item is None or self.preview_path is None:
            return False
        pix = self.target_item.pixmap()
        if pix.isNull():
            return False
        if scene_rect is None or scene_rect.isNull():
            scene_rect = self.preview_path.boundingRect().adjusted(
                -self.brush_size - 4,
                -self.brush_size - 4,
                self.brush_size + 4,
                self.brush_size + 4,
            )
        pix_for_rect, qrect = self._target_rect(scene_rect)
        if qrect is None:
            return False
        try:
            self._note_brush_activity(700)
            self._ensure_tile_snapshots(pix, qrect)
            local_path = self._map_path_to_target(self.preview_path)
            pen = QPen(self.color, self.brush_size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            dirty_local = QRectF()
            for key, tile_rect in self._iter_tile_rects(qrect, pix.rect()) or []:
                info = self.stroke_tiles.get(key) or {}
                before = info.get("before")
                if before is None:
                    continue
                p.setClipping(False)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                p.drawPixmap(tile_rect.topLeft(), before)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                p.setClipRect(tile_rect.adjusted(-2, -2, 2, 2))
                p.setPen(pen)
                p.drawPath(local_path)
                dirty_local = QRectF(tile_rect) if dirty_local.isNull() else dirty_local.united(QRectF(tile_rect))
            p.setClipping(False)
            p.end()
            self.target_item.setPixmap(pix)
            if not dirty_local.isNull():
                self.target_item.update(dirty_local)
                try:
                    scene_dirty = self.target_item.mapRectToScene(dirty_local)
                except Exception:
                    scene_dirty = dirty_local
            else:
                scene_dirty = scene_rect
            self._view_update_scene_rect(scene_dirty, force=force)
            return True
        except Exception:
            try:
                p.end()
            except Exception:
                pass
            return False

    def begin(self, target_item, start_pos, mode: str, color, brush_size: int, *, final_mode: bool = False) -> bool:
        self.clear_runtime()
        if target_item is None:
            return False
        self.target_item = target_item
        self.mode = str(mode or "draw")
        self.final_mode = bool(final_mode)
        self.brush_size = max(1, int(brush_size or 1))
        self.color = QColor(color) if not isinstance(color, QColor) else QColor(color)
        self.last_pos = QPointF(start_pos)
        self.active = True

        self._note_brush_activity(1000)
        if self.mode == "draw":
            # Draw is visible immediately, but the before state is captured only
            # for tiles touched by the stroke.  No full-layer pixmap copy here.
            try:
                self.draw_base_pixmap = None
                self.preview_path = QPainterPath(self.last_pos)
                self.preview_path.lineTo(QPointF(self.last_pos.x() + 0.15, self.last_pos.y()))
                self.paths = [self.preview_path]
                r = self._segment_rect(self.last_pos, self.last_pos)
                self._add_dirty(r)
                self._render_draw_live_to_target(r, force=True)
            except Exception:
                pass
        elif self.mode == "erase":
            # Erase must affect the real layer immediately so removed pixels are
            # visible while dragging. Keep the working direct dirty-rect path.
            self._paint_segment_patch(self.last_pos, self.last_pos, erase=True, force=True)
        return True

    def extend(self, pos) -> bool:
        if not self.active or self.target_item is None:
            return False
        now = QPointF(pos)
        last = QPointF(self.last_pos or now)
        dx = now.x() - last.x()
        dy = now.y() - last.y()
        if (dx * dx + dy * dy) < 0.75:
            return True

        if self.mode == "draw":
            try:
                if self.preview_path is None:
                    self.preview_path = QPainterPath(last)
                self.preview_path.lineTo(now)
                r = self._segment_rect(last, now)
                self._add_dirty(r)
                # Mouse-move 중 viewport.repaint()까지 강제하면 브러시가 한 박자씩 막힌다.
                # 실시간 획은 update()로만 예약하고, 첫 점/명시 force 상황에서만 repaint를 허용한다.
                self._render_draw_live_to_target(r, force=False)
            except Exception:
                pass
        else:
            self._paint_segment_patch(last, now, erase=True, force=False)
        self.last_pos = now
        return True

    def _kind(self) -> Optional[str]:
        try:
            if self.target_item is self.viewer.final_paint_item or self.target_item is self.viewer.final_paint_above_item:
                return "final_paint"
            if self.target_item is self.viewer.user_mask_item:
                return "mask"
        except Exception:
            pass
        return None

    def _sync_cached_images(self) -> None:
        try:
            pix = self.target_item.pixmap()
            if self.target_item is self.viewer.final_paint_above_item:
                self.viewer.final_paint_above_img = pix.toImage()
            elif self.target_item is self.viewer.final_paint_item:
                self.viewer.final_paint_img = pix.toImage()
            elif self.target_item is self.viewer.user_mask_item:
                self.viewer.user_mask_img = pix.toImage()
        except Exception:
            pass

    def commit(self) -> bool:
        if not self.active or self.target_item is None:
            self.clear_runtime()
            return False
        target = self.target_item
        mode = self.mode
        kind = self._kind()
        record = None
        try:
            pix = target.pixmap()
            if pix.isNull():
                return False
            patches = self._tile_patches_from_target(pix)
            if not patches and self.stroke_patches:
                # Compatibility fallback for records created by older direct patch paths.
                patches = list(self.stroke_patches)
            if patches:
                record = {"_brush_record": True, "target_item": target, "kind": kind, "patches": patches}
                try:
                    dirty = None
                    for patch in patches:
                        r = QRectF(patch.get("rect"))
                        dirty = r if dirty is None else dirty.united(r)
                    if dirty is not None:
                        try:
                            scene_qrect = target.mapRectToScene(dirty)
                        except Exception:
                            scene_qrect = dirty
                        self._view_update_scene_rect(scene_qrect, force=False)
                except Exception:
                    pass
                self._audit_tile_event(
                    "BRUSH_TILE_STROKE_COMMIT",
                    mode=str(mode or ""),
                    kind=str(kind or ""),
                    tile_count=len(patches),
                    segment_count=int(getattr(self, "stroke_segment_count", 0) or 0),
                )
            if record is not None:
                reason = "최종 페인팅" if kind == "final_paint" else "마스크 브러시"
                try:
                    if hasattr(self.viewer.main, "undo_push_paint_record"):
                        self.viewer.main.undo_push_paint_record(self.viewer, record, kind=kind, reason=reason, max_history=80)
                    else:
                        self.viewer.history.append(record)
                        if len(self.viewer.history) > 80:
                            self.viewer.history.pop(0)
                        try:
                            self.viewer.redo_history.clear()
                        except Exception:
                            pass
                        if hasattr(self.viewer.main, "undo_push_page"):
                            self.viewer.main.undo_push_page({
                                "reason": reason,
                                "page_idx": int(getattr(self.viewer.main, "idx", 0) or 0),
                                "mode": int(self.viewer.main.cb_mode.currentIndex()) if hasattr(self.viewer.main, "cb_mode") else 0,
                                "paint_history": True,
                                "_undo_scope": "page",
                            }, page_idx=int(getattr(self.viewer.main, "idx", 0) or 0))
                except Exception:
                    pass
                # Do not force a full pixmap.toImage() copy on mouse release.
                # The delayed layer commit/save path reads the current layer item
                # later; keeping release O(tile_count) prevents the "손 뗄 때" spike.
                try:
                    setattr(self.viewer, "_paint_layer_cache_dirty", True)
                except Exception:
                    pass
                return True
            return False
        finally:
            self.clear_runtime()

    def apply_record(self, record: Dict[str, Any], direction: str = "undo") -> Optional[str]:
        if not isinstance(record, dict) or not record.get("_brush_record"):
            return None
        target = record.get("target_item")
        patches = record.get("patches") or []
        if target is None or not patches:
            return None
        pix = target.pixmap()
        if pix.isNull():
            return None
        key = "before" if direction == "undo" else "after"
        ordered = list(reversed(patches)) if direction == "undo" else list(patches)
        try:
            p = QPainter(pix)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            dirty = None
            for patch in ordered:
                rect = patch.get("rect")
                img = patch.get(key)
                if rect is None or img is None:
                    continue
                p.drawPixmap(rect.topLeft(), img)
                rf = QRectF(rect)
                dirty = rf if dirty is None else dirty.united(rf)
            p.end()
            target.setPixmap(pix)
            if dirty is not None:
                target.update(dirty)
                try:
                    scene_dirty = target.mapRectToScene(dirty)
                except Exception:
                    scene_dirty = dirty
                self._view_update_scene_rect(scene_dirty, force=False)
            self.target_item = target
            try:
                main = getattr(self.viewer, "main", None)
                if bool(getattr(main, "_paint_history_apply_active", False)):
                    setattr(self.viewer, "_paint_layer_cache_dirty", True)
                else:
                    self._sync_cached_images()
            except Exception:
                pass
            return str(record.get("kind") or self._kind() or "paint")
        except Exception:
            return None
