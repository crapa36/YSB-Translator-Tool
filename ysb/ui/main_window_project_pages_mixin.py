from ysb.ui.main_window_support import *
from ysb.core.project_store import PackageProjectCancelled, WORKSPACE_STATE_FILENAME, read_workspace_state, write_workspace_state, relpath, json_safe


class MainWindowProjectPagesMixin:

    def _remove_live_text_scene_items_by_identity_or_id(self, data_ref_ids=None, text_ids=None, reason=""):
        """Remove specific live TypesettingItem objects from the current scene.

        Text line deletion changes curr['data'] first and then renumbers ids.  If the
        old scene item remains alive, undo rebuild creates a second item while the old
        one becomes an unlinked ghost.  Match by original data object identity before
        renumber, and by original id as a fallback.
        """
        scene = self._safe_graphics_scene() if hasattr(self, "_safe_graphics_scene") else getattr(getattr(self, "view", None), "scene", None)
        if scene is None:
            return 0
        data_ref_ids = {int(x) for x in (data_ref_ids or set()) if x is not None}
        text_ids = {str(x) for x in (text_ids or set()) if x is not None}
        removed = 0
        old_block = None
        try:
            old_block = scene.blockSignals(True)
        except Exception:
            old_block = None
        try:
            for obj in list(scene.items()):
                try:
                    if not isinstance(obj, TypesettingItem):
                        continue
                    data = getattr(obj, "data", None)
                    sid = None
                    try:
                        sid = data.get("id") if isinstance(data, dict) else None
                    except Exception:
                        sid = None
                    match_identity = bool(isinstance(data, dict) and id(data) in data_ref_ids)
                    match_id = bool(sid is not None and str(sid) in text_ids)
                    if not (match_identity or match_id):
                        continue
                    try:
                        obj.setSelected(False)
                        obj.setCacheMode(QGraphicsItem.CacheMode.NoCache)
                        obj.setVisible(False)
                    except Exception:
                        pass
                    try:
                        scene.removeItem(obj)
                    except RuntimeError:
                        continue
                    removed += 1
                except RuntimeError:
                    continue
                except Exception:
                    continue
        finally:
            try:
                if old_block is not None:
                    scene.blockSignals(old_block)
            except Exception:
                pass
        try:
            if removed:
                self.audit_boundary_event(
                    "TEXT_SCENE_ITEMS_REMOVED_BY_IDENTITY",
                    reason=str(reason or ""),
                    count=removed,
                    ids=sorted(text_ids),
                    throttle_ms=100,
                )
        except Exception:
            pass
        return removed

    def _purge_orphan_text_scene_items(self, reason=""):
        """Remove TypesettingItems whose data dict is no longer present on this page.

        This is a safety net for text delete/undo/redo after the undo refactor.  A
        scene item can survive after its backing row was removed from curr['data']; if
        undo later recreates the row, the orphan remains as a duplicate unselectable
        text object.  Keep items only when their data object or id exists in page data.
        """
        scene = self._safe_graphics_scene() if hasattr(self, "_safe_graphics_scene") else getattr(getattr(self, "view", None), "scene", None)
        curr = self.data.get(self.idx) if isinstance(getattr(self, "data", None), dict) else None
        if scene is None or not isinstance(curr, dict):
            return 0
        data_list = curr.get("data", []) or []
        live_ref_ids = {id(d) for d in data_list if isinstance(d, dict)}
        live_ids = {str(d.get("id")) for d in data_list if isinstance(d, dict) and d.get("id") is not None}
        removed = 0
        old_block = None
        try:
            old_block = scene.blockSignals(True)
        except Exception:
            old_block = None
        try:
            for obj in list(scene.items()):
                try:
                    if not isinstance(obj, TypesettingItem):
                        continue
                    data = getattr(obj, "data", None)
                    sid = None
                    try:
                        sid = data.get("id") if isinstance(data, dict) else None
                    except Exception:
                        sid = None
                    is_live_ref = isinstance(data, dict) and id(data) in live_ref_ids
                    is_live_id = sid is not None and str(sid) in live_ids
                    if is_live_ref or is_live_id:
                        continue
                    try:
                        obj.setSelected(False)
                        obj.setCacheMode(QGraphicsItem.CacheMode.NoCache)
                        obj.setVisible(False)
                    except Exception:
                        pass
                    try:
                        scene.removeItem(obj)
                    except RuntimeError:
                        continue
                    removed += 1
                except RuntimeError:
                    continue
                except Exception:
                    continue
        finally:
            try:
                if old_block is not None:
                    scene.blockSignals(old_block)
            except Exception:
                pass
        try:
            if removed:
                self.audit_boundary_event(
                    "TEXT_ORPHAN_SCENE_ITEMS_PURGED",
                    reason=str(reason or ""),
                    count=removed,
                    data_count=len(data_list),
                    throttle_ms=100,
                )
        except Exception:
            pass
        return removed

    def _enter_text_scene_mutation_timer_guard(self, reason="text_scene_mutation"):
        """Block view/clone fast-path timers while text scene items are replaced.

        Qt access violations were observed when source-compare/view fast-path timer
        callbacks restored render hints while finish_inline_text_edit() was removing
        and recreating TypesettingItem objects.  Treat text-layer mutation as a
        short critical section: stop/coalesce timers first, then let the caller
        mutate the scene, and resume clone sync after the event loop turns.
        """
        try:
            depth = int(getattr(self, "_text_scene_mutation_guard_depth", 0) or 0) + 1
        except Exception:
            depth = 1
        self._text_scene_mutation_guard_depth = depth
        self._text_scene_mutation_lock = True
        try:
            self.audit_boundary_event(
                "TEXT_SCENE_MUTATION_TIMER_GUARD_ENTER",
                reason=str(reason or ""),
                depth=depth,
                throttle_ms=100,
            )
        except Exception:
            pass
        # Stop periodic/queued clone sync.  Already queued singleShot callbacks also
        # check _text_scene_mutation_lock before doing work.
        try:
            timer = getattr(self, "_source_compare_sync_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
                self._source_compare_sync_resume_after_text_mutation = True
        except Exception:
            pass
        try:
            timer = getattr(self, "_source_compare_fast_path_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
        except Exception:
            pass
        # Do NOT execute fast-path finish callbacks inside the mutation guard.
        # Finishing restores render hints/cache modes and may touch QGraphicsView
        # while text items are about to be removed/recreated.  Just mark them as
        # pending; _release_text_scene_mutation_timer_guard() restores them after
        # the scene mutation finishes and the event loop turns.
        try:
            state = getattr(self, "_source_compare_fast_path_state", None)
            if isinstance(state, dict) and state.get("active"):
                self._source_compare_fast_path_finish_pending = True
        except Exception:
            pass
        try:
            view = getattr(self, "view", None)
            if view is not None and getattr(view, "_view_interaction_fast_path_active", False):
                view._view_interaction_fast_path_finish_pending = True
        except Exception:
            pass
        try:
            timer = getattr(getattr(self, "view", None), "_view_interaction_fast_path_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
        except Exception:
            pass

    def _release_text_scene_mutation_timer_guard(self, reason="text_scene_mutation"):
        try:
            depth = int(getattr(self, "_text_scene_mutation_guard_depth", 0) or 0) - 1
        except Exception:
            depth = 0
        if depth > 0:
            self._text_scene_mutation_guard_depth = depth
            try:
                self.audit_boundary_event(
                    "TEXT_SCENE_MUTATION_TIMER_GUARD_HOLD",
                    reason=str(reason or ""),
                    depth=depth,
                    throttle_ms=100,
                )
            except Exception:
                pass
            return
        self._text_scene_mutation_guard_depth = 0
        self._text_scene_mutation_lock = False
        try:
            self.audit_boundary_event(
                "TEXT_SCENE_MUTATION_TIMER_GUARD_RELEASE",
                reason=str(reason or ""),
                throttle_ms=100,
            )
        except Exception:
            pass

        def _resume_after_text_mutation():
            try:
                if getattr(self, "_text_scene_mutation_lock", False):
                    return
                try:
                    view = getattr(self, "view", None)
                    if view is not None and getattr(view, "_view_interaction_fast_path_finish_pending", False):
                        view._view_interaction_fast_path_finish_pending = False
                        if hasattr(view, "_finish_view_interaction_fast_path"):
                            view._finish_view_interaction_fast_path(force=True)
                except Exception:
                    pass
                try:
                    if getattr(self, "_source_compare_fast_path_finish_pending", False):
                        self._source_compare_fast_path_finish_pending = False
                        if hasattr(self, "_finish_source_compare_clone_fast_path"):
                            self._finish_source_compare_clone_fast_path(force=True)
                except Exception:
                    pass
                try:
                    if getattr(self, "_source_compare_sync_resume_after_text_mutation", False):
                        self._source_compare_sync_resume_after_text_mutation = False
                        if hasattr(self, "start_source_compare_sync_timer"):
                            self.start_source_compare_sync_timer()
                        if hasattr(self, "schedule_source_compare_sync"):
                            self.schedule_source_compare_sync(30)
                except Exception:
                    pass
            except Exception:
                pass

        try:
            QTimer.singleShot(30, _resume_after_text_mutation)
        except Exception:
            _resume_after_text_mutation()


    def _is_renderable_text_data_item(self, data_item):
        """Return True only for text rows that should create a TypesettingItem in final mode.

        curr['data'] can contain OCR rows that are unchecked, empty, or otherwise table-only.
        Comparing the scene item count against the raw table length makes normal pages look
        broken (for example scene_count=4/data_count=12) and triggers unnecessary full
        resync after text effects.  The final scene is drawn with the same predicate as
        MuleImageViewer.draw_movable_texts(), so all sanity checks must use that predicate.
        """
        if not isinstance(data_item, dict):
            return False
        try:
            if not bool(data_item.get('use_inpaint', True)):
                return False
        except Exception:
            return False
        try:
            if not str(data_item.get('translated_text', '') or '').strip() and not data_item.get('force_show'):
                return False
        except Exception:
            return False
        try:
            return data_item.get('id') is not None
        except Exception:
            return False

    def _safe_text_scene_current_ids(self):
        """Return (scene_ids, renderable_data_ids, selected_ids) for final text layer checks."""
        scene_ids, data_ids, selected_ids = set(), set(), []
        try:
            scene = self._safe_graphics_scene() if hasattr(self, "_safe_graphics_scene") else getattr(getattr(self, "view", None), "scene", None)
        except Exception:
            scene = None
        if scene is not None:
            try:
                for obj in list(scene.items()):
                    try:
                        if not isinstance(obj, TypesettingItem):
                            continue
                        data = getattr(obj, "data", {}) or {}
                        sid = data.get("id") if isinstance(data, dict) else None
                        if sid is None:
                            continue
                        # Hidden TypesettingItems do not participate in the visible final layer.
                        # They can temporarily exist during refresh, but treating them as a real
                        # scene/data mismatch causes needless resync loops.
                        try:
                            if not obj.isVisible():
                                continue
                        except Exception:
                            pass
                        scene_ids.add(str(sid))
                        if obj.isSelected():
                            selected_ids.append(sid)
                    except RuntimeError:
                        continue
                    except Exception:
                        continue
            except Exception:
                pass
        try:
            curr = self.data.get(self.idx) if isinstance(getattr(self, "data", None), dict) else None
            for d in (curr.get("data", []) if isinstance(curr, dict) else []):
                if self._is_renderable_text_data_item(d):
                    data_ids.add(str(d.get("id")))
        except Exception:
            pass
        return scene_ids, data_ids, selected_ids

    def schedule_safe_text_scene_resync(self, reason="text_scene_resync", selected_ids=None, delay_ms=40, table_refresh=False):
        """Queue a single safe text scene/data resync on the next event loop turn.

        Text delete/paste/undo can temporarily leave live TypesettingItem objects out of
        sync with curr['data'].  Calling mode_chg(4) immediately from the same key/mouse
        event can crash Qt because stale selected QGraphicsItems may still be referenced.
        This barrier stores only text IDs, lets the current event unwind, then rebuilds
        the text layer from data in one guarded pass.
        """
        try:
            if int(self.cb_mode.currentIndex()) != 4:
                return False
        except Exception:
            return False
        ids = []
        try:
            ids.extend([x for x in (selected_ids or []) if x is not None])
        except Exception:
            pass
        try:
            _, _, live_selected = self._safe_text_scene_current_ids()
            ids.extend([x for x in live_selected if x is not None])
        except Exception:
            pass
        # De-duplicate while preserving order.
        seen = set()
        normalized = []
        for x in ids:
            key = str(x)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(x)

        try:
            pending = list(getattr(self, "_pending_safe_text_scene_resync_selected_ids", []) or [])
        except Exception:
            pending = []
        for x in normalized:
            if str(x) not in {str(y) for y in pending}:
                pending.append(x)
        self._pending_safe_text_scene_resync_selected_ids = pending
        self._pending_safe_text_scene_resync_reason = str(reason or "text_scene_resync")
        self._pending_safe_text_scene_resync_table_refresh = bool(
            getattr(self, "_pending_safe_text_scene_resync_table_refresh", False) or table_refresh
        )

        try:
            self.audit_boundary_event(
                "TEXT_SCENE_RESYNC_BARRIER_QUEUED",
                reason=self._pending_safe_text_scene_resync_reason,
                selected_count=len(pending),
                delay_ms=int(delay_ms or 0),
                throttle_ms=100,
            )
        except Exception:
            pass

        try:
            if getattr(self, "_text_item_drag_active", False):
                delay_ms = max(int(delay_ms or 0), 180)
                try:
                    self.audit_boundary_event(
                        "TEXT_SCENE_RESYNC_DEFERRED_DURING_TEXT_DRAG",
                        reason=self._pending_safe_text_scene_resync_reason,
                        selected_count=len(pending),
                        delay_ms=int(delay_ms or 0),
                        throttle_ms=120,
                    )
                except Exception:
                    pass
        except Exception:
            pass
        try:
            timer = getattr(self, "_safe_text_scene_resync_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._run_safe_text_scene_resync)
                self._safe_text_scene_resync_timer = timer
            timer.stop()
            timer.start(max(0, int(delay_ms or 0)))
            return True
        except Exception:
            try:
                QTimer.singleShot(max(0, int(delay_ms or 0)), self._run_safe_text_scene_resync)
                return True
            except Exception:
                return False

    def _run_safe_text_scene_resync(self):
        """Safely rebuild final text scene from curr['data'] after event handlers unwind."""
        if getattr(self, "_safe_text_scene_resync_active", False):
            try:
                self.schedule_safe_text_scene_resync("resync_reentrant", delay_ms=60)
            except Exception:
                pass
            return
        try:
            if int(self.cb_mode.currentIndex()) != 4:
                return
        except Exception:
            return
        if getattr(self, "_text_item_drag_active", False):
            try:
                self.audit_boundary_event(
                    "TEXT_SCENE_RESYNC_RUN_DEFERRED_DURING_TEXT_DRAG",
                    reason=str(getattr(self, "_pending_safe_text_scene_resync_reason", "text_scene_resync") or "text_scene_resync"),
                    throttle_ms=120,
                )
            except Exception:
                pass
            try:
                self.schedule_safe_text_scene_resync("resync_deferred_text_drag", delay_ms=180)
            except Exception:
                pass
            return
        if getattr(self, "is_page_loading", False) or getattr(self, "is_batch_running", False):
            try:
                self.schedule_safe_text_scene_resync("resync_deferred_loading", delay_ms=80)
            except Exception:
                pass
            return

        selected_ids = list(getattr(self, "_pending_safe_text_scene_resync_selected_ids", []) or [])
        reason = str(getattr(self, "_pending_safe_text_scene_resync_reason", "text_scene_resync") or "text_scene_resync")
        table_refresh = bool(getattr(self, "_pending_safe_text_scene_resync_table_refresh", False))
        self._pending_safe_text_scene_resync_selected_ids = []
        self._pending_safe_text_scene_resync_table_refresh = False

        self._safe_text_scene_resync_active = True
        old_suppress = getattr(self, "_suppress_mode_undo", False)
        old_rebuild = getattr(self, "_is_rebuilding_text_layer", False)
        try:
            try:
                self.audit_boundary_event("TEXT_SCENE_RESYNC_BARRIER_ENTER", reason=reason, selected_count=len(selected_ids), throttle_ms=100)
            except Exception:
                pass
            try:
                self._enter_text_scene_mutation_timer_guard(reason="safe_text_scene_resync")
            except Exception:
                pass
            try:
                timer = getattr(self, "_final_text_light_refresh_timer", None)
                if timer is not None and timer.isActive():
                    timer.stop()
            except Exception:
                pass
            try:
                if hasattr(self, "_remove_inline_text_editor_from_scene"):
                    self._remove_inline_text_editor_from_scene()
            except Exception:
                pass
            scene = None
            try:
                scene = self._safe_graphics_scene() if hasattr(self, "_safe_graphics_scene") else getattr(getattr(self, "view", None), "scene", None)
            except Exception:
                scene = None
            removed = 0
            old_block = None
            if scene is not None:
                try:
                    old_block = scene.blockSignals(True)
                except Exception:
                    old_block = None
                try:
                    try:
                        scene.clearSelection()
                    except Exception:
                        pass
                    for obj in list(scene.items()):
                        try:
                            if not isinstance(obj, TypesettingItem):
                                continue
                            obj.setSelected(False)
                            obj.setCacheMode(QGraphicsItem.CacheMode.NoCache)
                            obj.setVisible(False)
                            scene.removeItem(obj)
                            removed += 1
                        except RuntimeError:
                            continue
                        except Exception:
                            continue
                finally:
                    try:
                        if old_block is not None:
                            scene.blockSignals(old_block)
                    except Exception:
                        pass
            try:
                self.audit_boundary_event("TEXT_SCENE_RESYNC_BARRIER_PURGE", reason=reason, removed=removed, throttle_ms=100)
            except Exception:
                pass
            self._suppress_mode_undo = True
            self._is_rebuilding_text_layer = True
            try:
                self.mode_chg(4)
            except Exception:
                pass
            try:
                if table_refresh:
                    self.ref_tab()
                    try:
                        self.audit_boundary_event(
                            "TEXT_TABLE_REFRESH_AFTER_RASTER_MODE_RESYNC",
                            reason=reason,
                            ids=','.join(str(x) for x in selected_ids),
                            throttle_ms=100,
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            if selected_ids:
                try:
                    self.reselect_text_items(selected_ids)
                except Exception:
                    pass
            try:
                self.force_update_final_scene_region()
            except Exception:
                try:
                    scene = self._safe_graphics_scene()
                    if scene is not None:
                        scene.update()
                except Exception:
                    pass
            try:
                scene_ids, data_ids, _ = self._safe_text_scene_current_ids()
                still_mismatch = set(scene_ids) != set(data_ids)
                self.audit_boundary_event(
                    "TEXT_SCENE_RESYNC_BARRIER_DONE",
                    reason=reason,
                    scene_count=len(scene_ids),
                    data_count=len(data_ids),
                    selected_count=len(selected_ids),
                    still_mismatch=bool(still_mismatch),
                    throttle_ms=100,
                )
                if still_mismatch:
                    self.audit_boundary_event(
                        "TEXT_SCENE_RESYNC_BARRIER_STILL_MISMATCH",
                        reason=reason,
                        scene_ids=sorted(scene_ids),
                        data_ids=sorted(data_ids),
                        throttle_ms=500,
                    )
            except Exception:
                pass
        finally:
            self._is_rebuilding_text_layer = old_rebuild
            self._suppress_mode_undo = old_suppress
            self._safe_text_scene_resync_active = False
            try:
                self._release_text_scene_mutation_timer_guard(reason="safe_text_scene_resync")
            except Exception:
                pass

    def _prepare_text_scene_mutation_safety(self, reason="text_scene_mutation", selected_ids=None):
        """Quiesce view/scene state before replacing live text items.

        Inline text commit can remove/recreate QGraphicsItems while the viewport,
        clone view fast path, selectionChanged signal, or item cache is still in
        flight.  Native Qt access violations happen in that tiny window, so keep
        this helper deliberately conservative and best-effort.
        """
        try:
            self.audit_boundary_event(
                "TEXT_SCENE_MUTATION_SAFETY_ENTER",
                reason=str(reason or ""),
                selected_ids=list(selected_ids or []),
                throttle_ms=100,
            )
        except Exception:
            pass
        try:
            self._enter_text_scene_mutation_timer_guard(reason=reason)
        except Exception:
            pass
        # Do not run view/source-compare fast-path finish callbacks here.  They
        # restore QGraphicsView render state and can re-enter painting while text
        # scene items are being replaced.  _enter_text_scene_mutation_timer_guard()
        # only marks pending restores; release resumes them after mutation.
        try:
            view = getattr(self, "view", None)
            if view is not None and getattr(view, "_view_interaction_fast_path_active", False):
                view._view_interaction_fast_path_finish_pending = True
        except Exception:
            pass
        try:
            state = getattr(self, "_source_compare_fast_path_state", None)
            if isinstance(state, dict) and state.get("active"):
                self._source_compare_fast_path_finish_pending = True
        except Exception:
            pass
        scene = None
        try:
            scene = self._safe_graphics_scene() if hasattr(self, "_safe_graphics_scene") else getattr(getattr(self, "view", None), "scene", None)
        except Exception:
            scene = None
        old_block = None
        if scene is not None:
            try:
                old_block = scene.blockSignals(True)
            except Exception:
                old_block = None
            try:
                scene.clearSelection()
            except Exception:
                pass
            try:
                for obj in list(scene.items()):
                    try:
                        if isinstance(obj, TypesettingItem):
                            obj.setSelected(False)
                            obj.setCacheMode(QGraphicsItem.CacheMode.NoCache)
                    except RuntimeError:
                        continue
                    except Exception:
                        continue
            except Exception:
                pass
            try:
                if old_block is not None:
                    scene.blockSignals(old_block)
            except Exception:
                pass
        try:
            editor = getattr(self, "inline_text_editor", None)
            if editor is not None:
                editor._closing = True
                try:
                    editor.clearFocus()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.audit_boundary_event("TEXT_SCENE_MUTATION_SAFETY_DONE", reason=str(reason or ""), throttle_ms=100)
        except Exception:
            pass

    def _file_dialog_log(self, event, **fields):
        try:
            self.audit_boundary_event(event, **fields)
        except Exception:
            pass

    def file_dialog_last_dirs_path(self):
        try:
            return get_cache_file("file_dialog_last_dirs.json")
        except Exception:
            return Path(os.path.join(str(get_cache_dir()), "file_dialog_last_dirs.json"))

    def load_file_dialog_last_dirs(self):
        try:
            p = self.file_dialog_last_dirs_path()
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def save_file_dialog_last_dirs(self, data):
        try:
            p = self.file_dialog_last_dirs_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data if isinstance(data, dict) else {}, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def file_dialog_reason_key(self, reason):
        reason = str(reason or "default")
        # 같은 성격의 열기는 같은 마지막 위치를 공유한다.
        mapping = {
            "open_project_ysbt": "open_project",
            "open_project_json": "open_project_json",
            "import_images_action": "import_images",
            "new_project_from_images": "import_images",
            "import_clean_background": "import_clean_background",
            "import_translation_txt": "import_translation_txt",
            "import_page_preset": "import_page_preset",
            "import_item_preset": "import_item_preset",
        }
        return mapping.get(reason, reason)

    def resolve_file_dialog_start_dir(self, reason, fallback_dir):
        key = self.file_dialog_reason_key(reason)
        data = self.load_file_dialog_last_dirs()
        saved = str(data.get(key) or "").strip()
        if saved and os.path.isdir(saved):
            self._file_dialog_log("FILE_DIALOG_LAST_DIR_USED", reason=str(reason), key=key, directory=saved, source="last")
            return saved
        fallback = str(fallback_dir or "").strip()
        if fallback and os.path.isdir(fallback):
            self._file_dialog_log("FILE_DIALOG_LAST_DIR_USED", reason=str(reason), key=key, directory=fallback, source="fallback")
            return fallback
        self._file_dialog_log("FILE_DIALOG_LAST_DIR_USED", reason=str(reason), key=key, directory=fallback, source="empty")
        return fallback

    def update_file_dialog_last_dir(self, reason, selected):
        if not selected:
            return False
        try:
            first = selected[0] if isinstance(selected, (list, tuple)) else selected
            path = str(first or "").strip()
            if not path:
                return False
            directory = path if os.path.isdir(path) else os.path.dirname(path)
            if not directory or not os.path.isdir(directory):
                return False
            key = self.file_dialog_reason_key(reason)
            data = self.load_file_dialog_last_dirs()
            old = data.get(key)
            data[key] = directory
            ok = self.save_file_dialog_last_dirs(data)
            self._file_dialog_log("FILE_DIALOG_LAST_DIR_SAVED", reason=str(reason), key=key, directory=directory, changed=(old != directory), ok=bool(ok))
            return ok
        except Exception as e:
            self._file_dialog_log("FILE_DIALOG_LAST_DIR_SAVE_ERROR", reason=str(reason), error=str(e))
            return False

    def file_dialog_options_for_current_setting(self):
        try:
            if bool(getattr(self, "use_light_file_dialog", True)):
                return QFileDialog.Option.DontUseNativeDialog
        except Exception:
            pass
        try:
            return QFileDialog.Option(0)
        except Exception:
            return QFileDialog.Option()

    def _use_light_qt_file_dialog(self):
        try:
            return bool(getattr(self, "use_light_file_dialog", True))
        except Exception:
            return True

    def _file_dialog_tr(self, ko_text, en_text=None):
        try:
            if str(getattr(self, "ui_language", LANG_KO)).lower().startswith("en"):
                return str(en_text if en_text is not None else ko_text)
        except Exception:
            pass
        return str(ko_text)

    def _file_dialog_sidebar_urls(self):
        urls = []
        seen = set()

        def add_path(path):
            try:
                path = str(path or "").strip()
                if not path or not os.path.isdir(path):
                    return
                norm = os.path.normcase(os.path.abspath(path))
                if norm in seen:
                    return
                seen.add(norm)
                urls.append(QUrl.fromLocalFile(path))
            except Exception:
                pass

        try:
            # 사용자가 바로 접근하는 위치를 먼저 둔다.
            add_path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation))
            add_path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
            add_path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation))
            add_path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.HomeLocation))
        except Exception:
            pass
        try:
            # 현재 작업 폴더도 있으면 편의 위치로 추가한다.
            add_path(str(default_package_dir()))
        except Exception:
            pass
        return urls

    def _configure_light_file_dialog(self, dialog, *, accept_mode="open", directory_mode=False):
        try:
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        except Exception:
            pass
        try:
            dialog.setLabelText(QFileDialog.DialogLabel.LookIn, self._file_dialog_tr("위치:", "Look in:"))
            dialog.setLabelText(QFileDialog.DialogLabel.FileName, self._file_dialog_tr("파일 이름:", "File name:"))
            dialog.setLabelText(QFileDialog.DialogLabel.FileType, self._file_dialog_tr("파일 형식:", "Files of type:"))
            dialog.setLabelText(QFileDialog.DialogLabel.Accept, self._file_dialog_tr("열기" if accept_mode == "open" else "선택", "Open" if accept_mode == "open" else "Select"))
            dialog.setLabelText(QFileDialog.DialogLabel.Reject, self._file_dialog_tr("취소", "Cancel"))
        except Exception:
            pass
        try:
            sidebar = self._file_dialog_sidebar_urls()
            if sidebar:
                dialog.setSidebarUrls(sidebar)
        except Exception:
            pass
        try:
            if directory_mode:
                dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        except Exception:
            pass
        return dialog

    def _get_open_file_name_light(self, parent, caption, directory, filter_text):
        dlg = QFileDialog(parent, caption, directory, filter_text)
        self._configure_light_file_dialog(dlg, accept_mode="open")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
        try:
            if filter_text:
                dlg.selectNameFilter(str(filter_text).split(";;")[0])
        except Exception:
            pass
        if dlg.exec():
            files = dlg.selectedFiles()
            return (files[0] if files else ""), dlg.selectedNameFilter()
        return "", dlg.selectedNameFilter()

    def _get_open_file_names_light(self, parent, caption, directory, filter_text):
        dlg = QFileDialog(parent, caption, directory, filter_text)
        self._configure_light_file_dialog(dlg, accept_mode="open")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setFileMode(QFileDialog.FileMode.ExistingFiles)
        try:
            if filter_text:
                dlg.selectNameFilter(str(filter_text).split(";;")[0])
        except Exception:
            pass
        if dlg.exec():
            return dlg.selectedFiles(), dlg.selectedNameFilter()
        return [], dlg.selectedNameFilter()

    def _get_existing_directory_light(self, parent, caption, directory):
        dlg = QFileDialog(parent, caption, directory)
        self._configure_light_file_dialog(dlg, accept_mode="select", directory_mode=True)
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setFileMode(QFileDialog.FileMode.Directory)
        if dlg.exec():
            files = dlg.selectedFiles()
            return files[0] if files else ""
        return ""

    def _file_dialog_process_events_logged(self, dialog_id, reason):
        try:
            t = time.time()
            self._file_dialog_log("FILE_DIALOG_PROCESS_EVENTS_ENTER", dialog_id=dialog_id, reason=str(reason))
            try:
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            except Exception:
                QApplication.processEvents()
            self._file_dialog_log("FILE_DIALOG_PROCESS_EVENTS_DONE", dialog_id=dialog_id, reason=str(reason), elapsed_ms=int((time.time() - t) * 1000))
        except Exception:
            pass

    def get_open_file_name_logged(self, reason, parent, caption, directory, filter_text):
        dialog_id = f"{reason}_{int(time.time() * 1000)}"
        t0 = time.time()
        directory = self.resolve_file_dialog_start_dir(reason, directory)
        options = self.file_dialog_options_for_current_setting()
        self._file_dialog_log("FILE_DIALOG_OPEN_ENTER", dialog_id=dialog_id, reason=str(reason), caption=str(caption), directory=str(directory), light_dialog=bool(getattr(self, "use_light_file_dialog", True)))
        self._file_dialog_process_events_logged(dialog_id, reason)
        try:
            self._file_dialog_log("FILE_DIALOG_NATIVE_CALL_ENTER", dialog_id=dialog_id, reason=str(reason))
            call_t = time.time()
            if self._use_light_qt_file_dialog():
                path, selected_filter = self._get_open_file_name_light(parent, caption, directory, filter_text)
            else:
                path, selected_filter = QFileDialog.getOpenFileName(parent, caption, directory, filter_text, "", options)
            self._file_dialog_log("FILE_DIALOG_NATIVE_CALL_RETURN", dialog_id=dialog_id, reason=str(reason), elapsed_ms=int((time.time() - call_t) * 1000), selected=bool(path))
            if path:
                self.update_file_dialog_last_dir(reason, path)
            elapsed = int((time.time() - t0) * 1000)
            self._file_dialog_log("FILE_DIALOG_OPEN_DONE", dialog_id=dialog_id, reason=str(reason), elapsed_ms=elapsed, selected=bool(path), path_ext=os.path.splitext(str(path or ""))[1])
            return path, selected_filter
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            self._file_dialog_log("FILE_DIALOG_OPEN_ERROR", dialog_id=dialog_id, reason=str(reason), elapsed_ms=elapsed, error=str(e))
            raise

    def get_open_file_names_logged(self, reason, parent, caption, directory, filter_text):
        dialog_id = f"{reason}_{int(time.time() * 1000)}"
        t0 = time.time()
        directory = self.resolve_file_dialog_start_dir(reason, directory)
        options = self.file_dialog_options_for_current_setting()
        self._file_dialog_log("FILE_DIALOG_OPEN_ENTER", dialog_id=dialog_id, reason=str(reason), caption=str(caption), directory=str(directory), multi=True, light_dialog=bool(getattr(self, "use_light_file_dialog", True)))
        self._file_dialog_process_events_logged(dialog_id, reason)
        try:
            self._file_dialog_log("FILE_DIALOG_NATIVE_CALL_ENTER", dialog_id=dialog_id, reason=str(reason), multi=True)
            call_t = time.time()
            if self._use_light_qt_file_dialog():
                paths, selected_filter = self._get_open_file_names_light(parent, caption, directory, filter_text)
            else:
                paths, selected_filter = QFileDialog.getOpenFileNames(parent, caption, directory, filter_text, "", options)
            self._file_dialog_log("FILE_DIALOG_NATIVE_CALL_RETURN", dialog_id=dialog_id, reason=str(reason), elapsed_ms=int((time.time() - call_t) * 1000), selected=bool(paths), count=len(paths or []), multi=True)
            if paths:
                self.update_file_dialog_last_dir(reason, paths)
            elapsed = int((time.time() - t0) * 1000)
            self._file_dialog_log("FILE_DIALOG_OPEN_DONE", dialog_id=dialog_id, reason=str(reason), elapsed_ms=elapsed, selected=bool(paths), count=len(paths or []))
            return paths, selected_filter
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            self._file_dialog_log("FILE_DIALOG_OPEN_ERROR", dialog_id=dialog_id, reason=str(reason), elapsed_ms=elapsed, error=str(e))
            raise

    def get_existing_directory_logged(self, reason, parent, caption, directory):
        dialog_id = f"{reason}_{int(time.time() * 1000)}"
        t0 = time.time()
        directory = self.resolve_file_dialog_start_dir(reason, directory)
        options = self.file_dialog_options_for_current_setting()
        self._file_dialog_log("FILE_DIALOG_OPEN_ENTER", dialog_id=dialog_id, reason=str(reason), caption=str(caption), directory=str(directory), directory_mode=True, light_dialog=bool(getattr(self, "use_light_file_dialog", True)))
        self._file_dialog_process_events_logged(dialog_id, reason)
        try:
            self._file_dialog_log("FILE_DIALOG_NATIVE_CALL_ENTER", dialog_id=dialog_id, reason=str(reason), directory_mode=True)
            call_t = time.time()
            if self._use_light_qt_file_dialog():
                path = self._get_existing_directory_light(parent, caption, directory)
            else:
                path = QFileDialog.getExistingDirectory(parent, caption, directory, options)
            self._file_dialog_log("FILE_DIALOG_NATIVE_CALL_RETURN", dialog_id=dialog_id, reason=str(reason), elapsed_ms=int((time.time() - call_t) * 1000), selected=bool(path), directory_mode=True)
            if path:
                self.update_file_dialog_last_dir(reason, path)
            elapsed = int((time.time() - t0) * 1000)
            self._file_dialog_log("FILE_DIALOG_OPEN_DONE", dialog_id=dialog_id, reason=str(reason), elapsed_ms=elapsed, selected=bool(path), directory_mode=True)
            return path
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            self._file_dialog_log("FILE_DIALOG_OPEN_ERROR", dialog_id=dialog_id, reason=str(reason), elapsed_ms=elapsed, error=str(e), directory_mode=True)
            raise

    def selected_text_items(self):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return []
        scene = self._safe_graphics_scene()
        if scene is None:
            return []
        try:
            return [item for item in scene.selectedItems() if isinstance(item, TypesettingItem)]
        except RuntimeError:
            return []
        except Exception:
            return []

    def _set_widget_value_blocked(self, widget, value):
        """프로그램이 UI 값을 채울 때 valueChanged 재발동/포커스 튐을 막는다."""
        if widget is None:
            return
        blocker = None
        try:
            blocker = QSignalBlocker(widget)
        except Exception:
            blocker = None
        try:
            widget.setValue(value)
        except Exception:
            pass
        finally:
            try:
                del blocker
            except Exception:
                pass

    def _set_widget_checked_blocked(self, widget, checked):
        if widget is None:
            return
        blocker = None
        try:
            blocker = QSignalBlocker(widget)
        except Exception:
            blocker = None
        try:
            widget.setChecked(bool(checked))
        except Exception:
            pass
        finally:
            try:
                del blocker
            except Exception:
                pass

    def _live_text_content_scene_rect_for_data(self, data_item):
        """Return the currently visible TypesettingItem text bounds for this data row.

        The reset-text-rect action is explicitly based on the *current visible text*.
        After the undo/timeline refactor, some final-tab items can have live preview
        geometry that is newer than the pure data-based estimator.  Prefer the live
        TypesettingItem when it is available, and fall back to the 2.4.1 estimator for
        unloaded pages / batch work.
        """
        if not isinstance(data_item, dict):
            return None
        try:
            if int(self.cb_mode.currentIndex()) != 4:
                return None
        except Exception:
            return None
        # Live scene items only represent the currently loaded page.  During batch
        # processing other pages can reuse the same text ids, so never bind a
        # non-current page data row to the current scene item just because the id
        # matches.
        try:
            curr = self.data.get(self.idx) if hasattr(self, 'data') else None
            curr_items = curr.get('data', []) if isinstance(curr, dict) else []
            if all(data_item is not x for x in (curr_items or [])):
                return None
        except Exception:
            return None
        scene = self._safe_graphics_scene() if hasattr(self, "_safe_graphics_scene") else getattr(getattr(self, "view", None), "scene", None)
        if scene is None:
            return None
        target_id = data_item.get('id')
        candidates = []
        try:
            for item in list(scene.items()):
                try:
                    if not isinstance(item, TypesettingItem):
                        continue
                    item_data = getattr(item, 'data', None)
                    if item_data is data_item:
                        candidates.insert(0, item)
                        continue
                    if target_id is not None and isinstance(item_data, dict) and str(item_data.get('id')) == str(target_id):
                        candidates.append(item)
                except RuntimeError:
                    continue
                except Exception:
                    continue
        except Exception:
            candidates = []
        for item in candidates:
            try:
                if hasattr(item, 'text_content_scene_rect'):
                    rect = item.text_content_scene_rect()
                else:
                    rect = item.mapToScene(item.path().boundingRect()).boundingRect()
                if rect is not None and (not rect.isNull()) and rect.width() > 0 and rect.height() > 0:
                    return rect
            except RuntimeError:
                continue
            except Exception:
                continue
        return None

    def calculate_tight_text_scene_rect(self, data_item):
        """data_item의 현재 번역문/스타일이 실제로 차지하는 scene rect를 계산한다.

        OCR 원본 박스는 처음 배치용으로 유지하되, 사용자가 텍스트를 한 번 수정하면
        그 이후의 선택/변형 박스는 실제 텍스트 크기에 맞게 축소되어야 한다.
        Qt 문서 boundingRect 대신 TypesettingItem과 같은 QPainterPath 기준을 사용한다.
        """
        if not isinstance(data_item, dict):
            return None
        text = str(data_item.get('translated_text', '') or '')
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        if not lines:
            lines = ['']

        try:
            fallback_family = self.cb_font.currentFont().family() if hasattr(self, 'cb_font') else 'Arial'
        except Exception:
            fallback_family = 'Arial'
        try:
            fallback_size = int(self.sb_font_size.value()) if hasattr(self, 'sb_font_size') else 24
        except Exception:
            fallback_size = 24

        font = QFont(str(data_item.get('font_family') or fallback_family))
        try:
            font.setPixelSize(int(data_item.get('font_size', fallback_size) or fallback_size))
        except Exception:
            font.setPixelSize(fallback_size)
        try:
            font.setBold(bool(data_item.get('bold', False)))
            font.setItalic(bool(data_item.get('italic', False)))
            letter_spacing = int(data_item.get('letter_spacing', 0) or 0)
        except Exception:
            pass

        try:
            line_spacing_pct = max(50, min(300, int(data_item.get('line_spacing', 100) or 100)))
        except Exception:
            line_spacing_pct = 100
        try:
            char_width_pct = max(10, min(300, int(data_item.get('char_width', 100) or 100)))
        except Exception:
            char_width_pct = 100
        try:
            char_height_pct = max(10, min(300, int(data_item.get('char_height', 100) or 100)))
        except Exception:
            char_height_pct = 100

        align = (data_item.get('align') or getattr(self, 'default_align', 'center') or 'center').lower()
        if align not in ('left', 'center', 'right'):
            align = 'center'

        fm = QFontMetrics(font)
        line_height = max(1, int(fm.lineSpacing() * (line_spacing_pct / 100.0)))
        path, _line_rects = build_typesetting_text_path(lines, font, align, line_height, letter_spacing)

        if char_width_pct != 100 or char_height_pct != 100:
            tr = QTransform()
            tr.scale(char_width_pct / 100.0, char_height_pct / 100.0)
            path = tr.map(path)

        path_rect = path.boundingRect()
        if path_rect.isNull() or path_rect.width() <= 0 or path_rect.height() <= 0:
            path_rect = QRectF(0, 0, 1, max(1, fm.height()))

        rect = list(data_item.get('rect') or [0, 0, 1, 1])
        while len(rect) < 4:
            rect.append(1)
        x_off = float(data_item.get('x_off', 0) or 0)
        y_off = float(data_item.get('y_off', 0) or 0)
        rect_x = float(rect[0])
        rect_y = float(rect[1])
        rect_w = max(1.0, float(rect[2]))
        rect_h = max(1.0, float(rect[3]))
        text_w = max(1.0, float(path_rect.width()))
        text_h = max(1.0, float(path_rect.height()))

        if align == 'left':
            anchor_x = rect_x + x_off
            left = anchor_x
        elif align == 'right':
            anchor_x = rect_x + x_off + rect_w
            left = anchor_x - text_w
        else:
            anchor_x = rect_x + x_off + rect_w / 2.0
            left = anchor_x - text_w / 2.0

        # v1.6.3+: 텍스트는 영역의 세로 중심에 배치된다.
        anchor_y = rect_y + y_off + rect_h / 2.0
        top = anchor_y - text_h / 2.0

        return QRectF(left, top, text_w, text_h)

    def shrink_text_rect_to_content(self, data_item):
        """텍스트 수정 후 작업/변형 박스를 실제 텍스트 크기로 줄인다."""
        return self.ensure_text_anchor_rect(data_item, record_undo=False)

    def ensure_text_anchor_rect(self, data_item, record_undo=False, reason="텍스트 영역 자동 재생성"):
        """현재 보이는 실제 텍스트 bounds를 새 텍스트 영역으로 확정한다.

        초기 OCR 영역은 최초 배치용 기준일 뿐이다. 텍스트 직접 수정 또는
        텍스트 변형 모드 진입 시점에는 현재 화면에 보이는 실제 글자 영역을
        기준으로 rect를 다시 만들고, 이후 선택/변형 박스가 이 영역을 보게 한다.
        """
        if not isinstance(data_item, dict):
            return False
        # Prefer the live final-tab item because this action means "reset to the
        # currently visible text".  For batch/unloaded pages, fall back to the
        # data-based 2.4.1 estimator.
        rect = None
        try:
            rect = self._live_text_content_scene_rect_for_data(data_item)
        except Exception:
            rect = None
        if rect is None:
            rect = self.calculate_tight_text_scene_rect(data_item)
        if rect is None:
            return False

        new_rect = [
            int(round(rect.x())),
            int(round(rect.y())),
            max(1, int(round(rect.width()))),
            max(1, int(round(rect.height()))),
        ]
        old_rect = list(data_item.get('rect') or [])
        while len(old_rect) < 4:
            old_rect.append(0)
        try:
            old_rect4 = [int(round(float(v))) for v in old_rect[:4]]
        except Exception:
            old_rect4 = old_rect[:4]
        old_x = int(round(float(data_item.get('x_off', 0) or 0)))
        old_y = int(round(float(data_item.get('y_off', 0) or 0)))
        already_text_anchor = bool(data_item.get('manual_text_rect')) or str(data_item.get('text_anchor_mode') or '').lower() == 'text'
        changed = (
            old_rect4 != new_rect
            or old_x != 0
            or old_y != 0
            or not already_text_anchor
        )
        if not changed:
            return False

        if record_undo:
            try:
                self.push_page_text_undo(reason)
            except Exception:
                pass

        data_item['rect'] = new_rect
        data_item['x_off'] = 0
        data_item['y_off'] = 0
        data_item['manual_text_rect'] = True
        data_item['text_anchor_mode'] = 'text'
        return True

    def reset_text_rects_current(self):
        """현재 페이지의 모든 텍스트 영역을 현재 보이는 텍스트 bounds 기준으로 재생성한다."""
        if not self.paths or self.idx not in self.data:
            self.log("⚠️ 영역을 재설정할 현재 페이지가 없습니다.")
            return

        # 최종화면에서 드래그 이동한 좌표가 아직 data에 완전히 박히기 전일 수 있으므로
        # 먼저 현재 UI 상태를 data에 동기화한 뒤, 그 상태를 Undo 기준으로 저장한다.
        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass

        curr = self.data.get(self.idx) or {}
        items = [d for d in (curr.get('data', []) or []) if isinstance(d, dict)]
        if not items:
            self.log("⚠️ 영역을 재설정할 텍스트가 없습니다.")
            return

        selected_ids = []
        try:
            scene = self._safe_graphics_scene() if hasattr(self, "_safe_graphics_scene") else getattr(getattr(self, "view", None), "scene", None)
            if scene is not None:
                selected_ids = [getattr(x, 'data', {}).get('id') for x in scene.selectedItems() if isinstance(x, TypesettingItem)]
                selected_ids = [x for x in selected_ids if x is not None]
        except Exception:
            selected_ids = []

        # 2.4.1 안정 경로 유지: 영역 재설정은 page snapshot undo로 처리한다.
        # 화면 반영은 full rebuild/purge가 아니라 기존 TypesettingItem의 in-place refresh만 사용한다.
        # 이 작업은 텍스트 개수 변경이 아니라 rect/x_off/y_off 기준 변경이므로 scene item을 지우면 안 된다.
        undo_rec = self.make_project_undo_record("현재 텍스트 기준 영역 재설정")
        changed = 0
        changed_ids = []
        for d in items:
            try:
                if self.ensure_text_anchor_rect(d, record_undo=False, reason="현재 텍스트 기준 영역 재설정"):
                    changed += 1
                    sid = d.get('id')
                    if sid is not None:
                        changed_ids.append(sid)
            except Exception:
                continue

        if changed <= 0:
            self.log("↩️ 현재 텍스트 기준 영역 재설정: 변경된 영역이 없습니다.")
            return

        self.append_project_undo_record(undo_rec)
        try:
            self.mark_active_page_dirty('text')
        except Exception:
            try:
                if hasattr(self, 'project_engine') and self.project_engine is not None:
                    self.project_engine.mark_page_dirty(int(self.idx), 'text')
            except Exception:
                pass
        try:
            if hasattr(self, '_checkpoint_dirty_pages'):
                self._checkpoint_dirty_pages.add(int(self.idx))
            else:
                self._checkpoint_dirty_pages = {int(self.idx)}
            if not hasattr(self, '_checkpoint_dirty_kinds') or self._checkpoint_dirty_kinds is None:
                self._checkpoint_dirty_kinds = {}
            self._checkpoint_dirty_kinds.setdefault(int(self.idx), set()).add('text')
        except Exception:
            pass

        try:
            self.audit_boundary_event(
                "TEXT_REGION_RESET_APPLIED",
                changed=changed,
                changed_ids=','.join(str(x) for x in changed_ids),
                selected_count=len(selected_ids),
                page_idx=int(self.idx),
                refresh_path='in_place',
                throttle_ms=100,
            )
        except Exception:
            pass

        self.auto_save_project()
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            refreshed = False
            try:
                if changed_ids and hasattr(self, 'refresh_final_text_items_by_ids'):
                    refreshed = bool(self.refresh_final_text_items_by_ids(changed_ids))
            except Exception:
                refreshed = False
            try:
                if selected_ids:
                    self.reselect_text_items(selected_ids)
            except Exception:
                pass
            if not refreshed:
                try:
                    if hasattr(self, 'schedule_final_text_scene_refresh'):
                        self.schedule_final_text_scene_refresh(80)
                    else:
                        self.mode_chg(4)
                except Exception:
                    pass
        self.log(f"📐 현재 텍스트 기준 영역 재설정 완료: {changed}개")

    def reset_text_rects_batch(self):
        """선택한 페이지의 모든 텍스트 영역을 현재 텍스트 bounds 기준으로 일괄 재생성한다."""
        if not self.paths or not self.data:
            self.log("⚠️ 영역을 재설정할 프로젝트가 없습니다.")
            return

        title = "일괄 현재 텍스트 기준으로 영역 재설정"
        selected_indices, selected_label = self.choose_batch_page_indices_for_context(title, "reset_text_rects")
        if selected_indices is None:
            self.log("↩️ 일괄 텍스트 기준 영역 재설정 취소")
            return

        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass

        # 일괄 작업도 2.4.1처럼 각 페이지 data를 직접 수정하고, run_page_queue_batch의
        # 일괄 경계/워크캐시 흐름에 맡긴다. text_region_reset Command-Diff는 사용하지 않는다.
        current_page_changed_ids = []
        def process_page(page_idx):
            page_data = self.data.get(page_idx)
            if not isinstance(page_data, dict):
                return "skipped", "페이지 데이터 없음"
            items = [d for d in (page_data.get('data', []) or []) if isinstance(d, dict)]
            if not items:
                return "skipped", "텍스트 없음"
            page_changed = 0
            for d in items:
                try:
                    if self.ensure_text_anchor_rect(d, record_undo=False, reason=title):
                        page_changed += 1
                        try:
                            if int(page_idx) == int(self.idx) and d.get('id') is not None:
                                current_page_changed_ids.append(d.get('id'))
                        except Exception:
                            pass
                except Exception:
                    continue
            if page_changed <= 0:
                return "skipped", "변경된 영역 없음"
            try:
                if hasattr(self, 'project_engine') and self.project_engine is not None:
                    self.project_engine.mark_page_dirty(int(page_idx), 'text')
                pages = getattr(self, "_checkpoint_dirty_pages", None)
                if pages is None:
                    pages = set()
                    self._checkpoint_dirty_pages = pages
                pages.add(int(page_idx))
                kinds = getattr(self, "_checkpoint_dirty_kinds", None)
                if kinds is None:
                    kinds = {}
                    self._checkpoint_dirty_kinds = kinds
                kinds.setdefault(int(page_idx), set()).add("text")
            except Exception:
                pass
            return "done", f"{page_changed}개 재설정"

        result = self.run_page_queue_batch(title, "reset_text_rects", selected_indices, selected_label, process_page, visual=False, cancellable=True)
        try:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4 and current_page_changed_ids:
                refreshed = False
                try:
                    if hasattr(self, 'refresh_final_text_items_by_ids'):
                        refreshed = bool(self.refresh_final_text_items_by_ids(current_page_changed_ids))
                except Exception:
                    refreshed = False
                if not refreshed:
                    try:
                        if hasattr(self, 'schedule_final_text_scene_refresh'):
                            self.schedule_final_text_scene_refresh(80)
                        else:
                            self.mode_chg(4)
                    except Exception:
                        pass
        except Exception:
            pass


    def start_inline_text_edit(self, text_item, select_all=False):
        """최종 화면 텍스트를 더블클릭/F2 했을 때 그 자리에서 직접 편집한다."""
        if self.cb_mode.currentIndex() != 4:
            return

        if self.inline_text_editor is not None:
            self.finish_inline_text_edit(commit=True, refresh=False)

        if text_item is None:
            return
        if bool(getattr(text_item, 'data', {}).get('rasterized_text')):
            self.log("⚠️ " + self.tr_ui("객체로 변환된 텍스트는 내용을 직접 수정할 수 없습니다."))
            return

        self.inline_text_target = text_item
        text_item.setSelected(True)

        # 마지막 식자 단계의 직접 수정이므로, 기존 OCR 박스가 아니라 현재 실제 텍스트를 기준으로 편집을 시작한다.
        if hasattr(text_item, 'text_content_scene_rect'):
            scene_rect = text_item.text_content_scene_rect()
        else:
            local_rect = text_item.text_area_rect()
            scene_rect = text_item.mapToScene(local_rect).boundingRect()

        editor = InlineTextEditItem(self, text_item, scene_rect)
        self.inline_text_editor = editor

        text_item.setVisible(False)
        self.view.scene.addItem(editor)
        editor.setFocus(Qt.FocusReason.MouseFocusReason)

        cursor = editor.textCursor()
        cursor.clearSelection()
        if select_all:
            cursor.select(QTextCursor.SelectionType.Document)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)

        self.log(f"✏️ 텍스트 직접 편집 시작 (ID: {text_item.data.get('id')})")

    def finish_inline_text_edit(self, commit=True, refresh=True):
        editor = self.inline_text_editor
        target = self.inline_text_target
        if editor is None:
            return

        is_closing = bool(getattr(self, "_app_is_closing", False))
        try:
            editor._closing = True
        except Exception:
            pass

        # Qt 종료/탭 재구성 타이밍에 QGraphicsTextItem의 C++ 객체가 먼저 삭제될 수 있다.
        # 이 상태에서 toPlainText()/scene()/removeItem() 등을 호출하면
        # "wrapped C/C++ object ... has been deleted"가 나므로 조용히 포인터만 정리한다.
        try:
            _ = editor.toPlainText()
        except RuntimeError:
            self.inline_text_editor = None
            self.inline_text_target = None
            return
        except Exception:
            pass

        selected_id = target.data.get('id') if target is not None else None
        pending_new = bool(target is not None and target.data.get('pending_new_text'))

        changed = False
        added_new = False
        canceled_new = False

        if commit and target is not None:
            try:
                new_text = editor.toPlainText()
            except RuntimeError:
                self.inline_text_editor = None
                self.inline_text_target = None
                return
            changed = (new_text != getattr(editor, 'original_text', ''))

            if pending_new and not str(new_text or '').strip():
                canceled_new = True
                changed = False
                self.log(f"↩️ 새 텍스트 입력 취소 (ID: {target.data.get('id')})")
            elif changed or pending_new:
                command_fields = ['translated_text', 'rect', 'x_off', 'y_off', 'manual_text_rect', 'text_anchor_mode', 'force_show', 'pending_new_text']
                before_direct_values = None
                before_item_copy = None
                before_index = None
                try:
                    before_direct_values = self._snapshot_text_field_values(target.data, command_fields)
                except Exception:
                    before_direct_values = None
                try:
                    before_item_copy = copy.deepcopy(target.data)
                except Exception:
                    try:
                        before_item_copy = dict(target.data)
                    except Exception:
                        before_item_copy = None
                if not pending_new:
                    try:
                        curr_before = self.data.get(self.idx) or {}
                        for i, d in enumerate(curr_before.get('data', []) or []):
                            if isinstance(d, dict) and str(d.get('id')) == str(target.data.get('id')):
                                before_index = i
                                break
                    except Exception:
                        before_index = None
                # 2.4.1 안정 경로 복원:
                # 직접 텍스트 수정은 Command/Diff가 실패하거나 no-op 처리되면 Ctrl+Z 자체가
                # 사라지는 문제가 생겼다. 텍스트 내용/영역 직접 수정은 작은 필드 변경처럼
                # 보여도 편집기 focusOut/표 갱신/rect 재계산이 함께 얽히므로 2.4.1처럼
                # 수정 전 텍스트 라인 스냅샷을 먼저 남긴다.
                # 새 텍스트 추가만 lifecycle command를 유지한다.
                use_command_undo = False
                if pending_new:
                    use_command_undo = bool(hasattr(self, 'push_text_geometry_command') and hasattr(self, 'push_text_item_lifecycle_command'))
                if not use_command_undo:
                    try:
                        self.push_page_text_undo('텍스트 직접 수정' if not pending_new else '새 텍스트 추가')
                    except Exception:
                        try:
                            self.undo_text_checkpoint('텍스트 직접 수정' if not pending_new else '새 텍스트 추가')
                        except Exception:
                            pass

                target.data['translated_text'] = new_text
                target.data.pop('force_show', None)
                target.data.pop('pending_new_text', None)

                # 직접 수정한 경우에는 기존 OCR 박스가 아니라 현재 편집 텍스트 자체를 기준으로
                # 텍스트 영역을 다시 잡는다. 이 영역 변경도 같은 Command 안에 기록해야
                # Ctrl+Z 때 내용과 박스가 함께 원복된다.
                try:
                    edit_rect = editor.adjusted_scene_rect()
                    if edit_rect.width() > 1 and edit_rect.height() > 1:
                        target.data['rect'] = [
                            int(round(edit_rect.x())),
                            int(round(edit_rect.y())),
                            max(1, int(round(edit_rect.width()))),
                            max(1, int(round(edit_rect.height()))),
                        ]
                        target.data['x_off'] = 0
                        target.data['y_off'] = 0
                        target.data['manual_text_rect'] = True
                        target.data['text_anchor_mode'] = 'text'
                    else:
                        self.shrink_text_rect_to_content(target.data)
                except Exception:
                    try:
                        self.shrink_text_rect_to_content(target.data)
                    except Exception:
                        pass

                if pending_new:
                    curr = self.data.get(self.idx)
                    after_index = None
                    if curr is not None and target.data not in curr.setdefault('data', []):
                        after_index = len(curr.setdefault('data', []))
                        curr['data'].append(target.data)
                        added_new = True
                    changed = True
                    if use_command_undo:
                        try:
                            self.push_text_item_lifecycle_command(
                                target.data,
                                before_item=None,
                                after_item=target.data,
                                before_exists=False,
                                after_exists=True,
                                before_index=None,
                                after_index=after_index,
                                reason='새 텍스트 추가',
                                page_idx=self.idx,
                            )
                        except Exception:
                            pass
                        # 새 텍스트의 최초 위치/영역은 lifecycle command의 after_item에 이미 저장한다.
                        # 별도 text_position marker를 만들면 사용자가 실제로 이동하지 않았는데도
                        # Ctrl+Z 한 칸이 더 생겨 혼란스럽다. 위치 command는 실제 이동이
                        # 발생했을 때만 mousePress -> mouseRelease diff로 생성한다.
                    # 새 텍스트는 data 리스트 구조가 바뀌므로 텍스트 라인 표를 즉시 다시 만든다.
                    try:
                        self.ref_tab()
                        self.select_table_rows_by_ids([target.data.get('id')])
                    except Exception:
                        pass
                else:
                    if use_command_undo:
                        try:
                            after_direct_values = self._snapshot_text_field_values(target.data, command_fields)
                            self.push_text_geometry_command(
                                target.data,
                                before_values=before_direct_values,
                                after_values=after_direct_values,
                                reason='텍스트 직접 수정',
                                fields=command_fields,
                                page_idx=self.idx,
                                component_type='text_content',
                            )
                        except Exception:
                            pass
                    target_id = str(target.data.get('id'))
                    self.tab.blockSignals(True)
                    try:
                        for row in range(1, self.tab.rowCount()):
                            id_item = self.tab.item(row, 0)
                            if id_item and id_item.text().strip() == target_id:
                                self.tab.setItem(row, 3, QTableWidgetItem(new_text))
                                break
                    finally:
                        self.tab.blockSignals(False)

            if changed:
                # E단계: 화면 반영 전에 작업 캐시 저장을 끼우면 직접 편집 확정 체감이 늦어진다.
                # 표/화면은 먼저 갱신하고, 저장 표시는 아래에서 지연 처리한다.
                try:
                    self.tab.resizeRowsToContents()
                except Exception:
                    pass
                if added_new:
                    self.log(f"✅ 새 텍스트 추가 완료 (ID: {target.data.get('id')})")
                else:
                    self.log(f"✅ 텍스트 직접 수정 완료 (ID: {target.data.get('id')})")
            elif not canceled_new:
                self.log(f"↩️ 텍스트 직접 수정 변화 없음 (ID: {target.data.get('id')})")
        elif target is not None:
            if pending_new:
                canceled_new = True
                self.log(f"↩️ 새 텍스트 입력 취소 (ID: {target.data.get('id')})")
            else:
                self.log(f"↩️ 텍스트 직접 수정 취소 (ID: {target.data.get('id')})")

        try:
            if editor.scene() is not None:
                editor.scene().removeItem(editor)
        except Exception:
            pass

        if target is not None:
            try:
                if canceled_new and target.scene() is not None:
                    target.scene().removeItem(target)
                else:
                    target.setVisible(True)
            except Exception:
                pass

        self.inline_text_editor = None
        self.inline_text_target = None

        # 인라인 텍스트 편집 확정은 2.4.1의 안정 경로처럼
        # 기존 TypesettingItem을 살려둔 채 해당 텍스트만 갱신한다.
        # 직접 수정 직후 QGraphicsScene의 텍스트 레이어를 제거/재생성하면
        # Qt/C++ access violation이 날 수 있으므로 force rebuild는 금지한다.
        if (not is_closing) and commit and (changed or added_new) and self.cb_mode.currentIndex() == 4:
            try:
                if selected_id is not None:
                    if not self.refresh_final_text_items_by_ids([selected_id]):
                        self.schedule_final_text_scene_refresh(80)
                elif refresh:
                    self.schedule_final_text_scene_refresh(80)
            except Exception:
                try:
                    self.schedule_final_text_scene_refresh(80)
                except Exception:
                    pass
            if selected_id is not None and not canceled_new:
                self.reselect_text_items([selected_id])
        elif (not is_closing) and selected_id is not None and not canceled_new:
            self.reselect_text_items([selected_id])

        if (not is_closing) and commit and (changed or added_new):
            try:
                self.finalize_text_change(ids=[selected_id] if selected_id is not None else [], fields=['translated_text'], reason='인라인 텍스트 직접 수정', delay_ms=1800)
            except Exception:
                try:
                    self.mark_active_page_dirty('text')
                    self.schedule_deferred_auto_save_project(1800)
                except Exception:
                    pass
    def on_scene_selection_changed(self):
        # 프로그램 종료/씬 재생성 중 selectionChanged가 뒤늦게 들어오면
        # 삭제된 QGraphicsScene에 접근하지 않고 조용히 무시한다.
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        if self._safe_graphics_scene() is None:
            return

        active_transform = self.current_transform_data_item()
        if active_transform is not None:
            active_id = active_transform.get('id')
            items = self.selected_text_items()
            if not any(item.data.get('id') == active_id for item in items):
                self.reselect_text_items([active_id])
                items = self.selected_text_items()
        else:
            items = self.selected_text_items()
        ids = [item.data.get('id') for item in items]
        self.select_table_rows_by_ids(ids)
        if hasattr(self, 'final_edit_bar'):
            self.final_edit_bar.hide()
        self.update_text_style_control_state(items)
        try:
            if hasattr(self, "refresh_shared_option_bar"):
                self.refresh_shared_option_bar()
        except Exception:
            pass

        if not items or self._style_signal_lock:
            return

        d = items[0].data
        self._style_signal_lock = True
        try:
            self.cb_font.setCurrentFont(QFont(d.get('font_family') or self.cb_font.currentFont().family()))
            self._set_widget_value_blocked(self.sb_font_size, int(d.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()))
            self._set_widget_value_blocked(self.sb_strk, int(d.get('stroke_width', self.sb_strk.value()) or 0))
            if hasattr(self, 'final_item_font'):
                self.final_item_font.setCurrentFont(QFont(d.get('font_family') or self.final_item_font.currentFont().family()))
            if hasattr(self, 'final_item_size'):
                self._set_widget_value_blocked(self.final_item_size, int(d.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()))
            if hasattr(self, 'final_item_stroke'):
                self._set_widget_value_blocked(self.final_item_stroke, int(d.get('stroke_width', self.sb_strk.value()) or 0))
            self.default_text_color = d.get('text_color') or self.default_text_color
            self.default_stroke_color = d.get('stroke_color') or self.default_stroke_color
            self.default_align = d.get('align') or self.default_align
            if hasattr(self, "sb_line_spacing"):
                self._set_widget_value_blocked(self.sb_line_spacing, int(d.get('line_spacing', self.default_line_spacing) or self.default_line_spacing))
            if hasattr(self, "sb_letter_spacing"):
                self._set_widget_value_blocked(self.sb_letter_spacing, int(d.get('letter_spacing', self.default_letter_spacing) or self.default_letter_spacing))
            if hasattr(self, "sb_char_width"):
                self._set_widget_value_blocked(self.sb_char_width, int(d.get('char_width', self.default_char_width) or self.default_char_width))
            if hasattr(self, "sb_char_height"):
                self._set_widget_value_blocked(self.sb_char_height, int(d.get('char_height', self.default_char_height) or self.default_char_height))
            if hasattr(self, "btn_bold"):
                self._set_widget_checked_blocked(self.btn_bold, bool(d.get('bold', False)))
            if hasattr(self, "btn_italic"):
                self._set_widget_checked_blocked(self.btn_italic, bool(d.get('italic', False)))
            if hasattr(self, "btn_strike"):
                self._set_widget_checked_blocked(self.btn_strike, bool(d.get('strike', False)))
            if hasattr(self, "sb_text_opacity"):
                self._set_widget_value_blocked(self.sb_text_opacity, int(d.get('opacity', 100) or 100))
            self.update_color_button_styles()
            self.update_item_preset_combo_for_selected_texts()
            self.update_text_style_control_state(items)
        finally:
            self._style_signal_lock = False

    def apply_text_style_button_styles(self):
        if self.is_light_theme():
            base = (
                "QPushButton { background:#ffffff; color:#111827; border:1px solid #D1C9CE; border-radius:0px; }"
                "QPushButton:hover { background:#FBF5F6; border-color:#9bbce8; }"
                "QPushButton:checked { background:#F5E8EA; color:#141416; border:1px solid #A85D66; font-weight:700; }"
                "QPushButton:disabled { background:#F2EDEF; color:#A39BA1; border:1px solid #d9dee8; }"
            )
        else:
            base = (
                "QPushButton { background:#2f3540; color:#F4EEF2; border:1px solid #625A61; border-radius:0px; }"
                "QPushButton:hover { background:#374151; }"
                "QPushButton:checked { background:#8A4A52; color:#ffffff; border:1px solid #C78A90; font-weight:700; }"
                "QPushButton:disabled { background:#211F23; color:#736A71; border:1px solid #373136; }"
            )
        for btn in (getattr(self, 'btn_align_left', None), getattr(self, 'btn_align_center', None), getattr(self, 'btn_align_right', None)):
            if btn is not None:
                btn.setStyleSheet(base)
        bold = base.replace("QPushButton {", "QPushButton { font-weight:bold;")
        italic = base.replace("QPushButton {", "QPushButton { font-style:italic;")
        strike = base.replace("QPushButton {", "QPushButton { text-decoration: line-through;")
        if hasattr(self, 'btn_bold'):
            self.btn_bold.setStyleSheet(bold)
        if hasattr(self, 'btn_italic'):
            self.btn_italic.setStyleSheet(italic)
        if hasattr(self, 'btn_strike'):
            self.btn_strike.setStyleSheet(strike)

    def set_widget_interlock_visual(self, widget, enabled, disabled_opacity=0.42):
        if widget is None:
            return
        try:
            widget.setEnabled(bool(enabled))
        except Exception:
            pass
        try:
            eff = widget.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(eff)
            eff.setOpacity(1.0 if enabled else float(disabled_opacity))
        except Exception:
            pass

    def update_page_presence_interlocks(self):
        has_pages = bool(getattr(self, 'paths', []))
        for widget in getattr(self, 'page_required_widgets', []):
            self.set_widget_interlock_visual(widget, has_pages)
        for key in getattr(self, 'page_required_action_keys', []):
            action = self.actions.get(key) if hasattr(self, 'actions') else None
            if action is not None:
                try:
                    action.setEnabled(has_pages)
                except Exception:
                    pass
        # 로컬 라벨 변수까지 일일이 저장하지 않아도, 페이지 의존 문구는 같이 흐리게 만든다.
        label_texts = {
            "폰트", "크기", "획", "행간", "자간", "너비", "높이", "번역AI", "묶음",
            "Font", "Size", "Stroke", "Line", "Letter", "Width", "Height", "Translation AI", "Chunk",
        }
        try:
            for label in self.findChildren(QLabel):
                try:
                    if label.text().strip() in label_texts:
                        self.set_widget_interlock_visual(label, has_pages, disabled_opacity=0.35)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, 'page_tab_bar'):
                self.page_tab_bar.setEnabled(has_pages)
            if hasattr(self, 'btn_page_tab_menu'):
                self.set_widget_interlock_visual(self.btn_page_tab_menu, has_pages)
            for _btn in (getattr(self, 'btn_page_scroll_left', None), getattr(self, 'btn_page_scroll_right', None)):
                if _btn is not None:
                    self.set_widget_interlock_visual(_btn, has_pages)
            if hasattr(self, 'btn_page_add'):
                self.set_widget_interlock_visual(self.btn_page_add, bool(self.has_open_project()))
        except Exception:
            pass
        if not has_pages:
            self.update_text_style_control_state([])

    def update_text_style_control_state(self, selected_items=None):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        try:
            items = list(selected_items) if selected_items is not None else self.selected_text_items()
        except Exception:
            items = []
        enabled = bool(items) and hasattr(self, 'cb_mode') and self.cb_mode.currentIndex() == 4
        for widget in getattr(self, 'text_style_control_widgets', []):
            self.set_widget_interlock_visual(widget, enabled, disabled_opacity=0.35)
        self._style_signal_lock = True
        try:
            if not enabled:
                for btn in (getattr(self, 'btn_align_left', None), getattr(self, 'btn_align_center', None), getattr(self, 'btn_align_right', None), getattr(self, 'btn_bold', None), getattr(self, 'btn_italic', None), getattr(self, 'btn_strike', None)):
                    if btn is not None:
                        self._set_widget_checked_blocked(btn, False)
                if hasattr(self, 'sb_text_opacity'):
                    self._set_widget_value_blocked(self.sb_text_opacity, 100)
                return
            d = getattr(items[0], 'data', {}) or {}
            align = str(d.get('align') or getattr(self, 'default_align', 'center') or 'center').lower()
            if align not in ('left', 'center', 'right'):
                align = 'center'
            if hasattr(self, 'btn_align_left'):
                self._set_widget_checked_blocked(self.btn_align_left, align == 'left')
                self._set_widget_checked_blocked(self.btn_align_center, align == 'center')
                self._set_widget_checked_blocked(self.btn_align_right, align == 'right')
            if hasattr(self, 'btn_bold'):
                self._set_widget_checked_blocked(self.btn_bold, bool(d.get('bold', False)))
            if hasattr(self, 'btn_italic'):
                self._set_widget_checked_blocked(self.btn_italic, bool(d.get('italic', False)))
            if hasattr(self, 'btn_strike'):
                self._set_widget_checked_blocked(self.btn_strike, bool(d.get('strike', False)))
            if hasattr(self, 'sb_text_opacity'):
                self._set_widget_value_blocked(self.sb_text_opacity, int(d.get('opacity', 100) or 100))
        finally:
            self._style_signal_lock = False

    def _style_patch_from_sender(self, sender=None):
        """우측 텍스트 인터페이스의 사용자 조작을 field 단위 패치로 변환한다.

        AB단계: 여러 텍스트를 선택한 상태에서 한 컨트롤을 조작했을 때,
        대표 텍스트의 전체 스타일을 덮어쓰지 않고 사용자가 건드린 field만 전체 선택 항목에 적용한다.
        """
        try:
            sender = sender or self.sender()
        except Exception:
            sender = None
        try:
            if sender is getattr(self, 'cb_font', None):
                return {'font_family': self.cb_font.currentFont().family()}
            if sender is getattr(self, 'sb_font_size', None):
                return {'font_size': int(self.sb_font_size.value())}
            if sender is getattr(self, 'sb_strk', None):
                return {'stroke_width': int(self.sb_strk.value())}
            if sender is getattr(self, 'sb_line_spacing', None):
                return {'line_spacing': int(self.sb_line_spacing.value())}
            if sender is getattr(self, 'sb_letter_spacing', None):
                return {'letter_spacing': int(self.sb_letter_spacing.value())}
            if sender is getattr(self, 'sb_char_width', None):
                return {'char_width': int(self.sb_char_width.value())}
            if sender is getattr(self, 'sb_char_height', None):
                return {'char_height': int(self.sb_char_height.value())}
            if sender is getattr(self, 'btn_bold', None):
                return {'bold': bool(self.btn_bold.isChecked())}
            if sender is getattr(self, 'btn_italic', None):
                return {'italic': bool(self.btn_italic.isChecked())}
            if sender is getattr(self, 'btn_strike', None):
                return {'strike': bool(self.btn_strike.isChecked())}
        except Exception:
            pass
        return {}

    def _final_item_style_patch_from_sender(self, sender=None):
        try:
            sender = sender or self.sender()
        except Exception:
            sender = None
        try:
            if sender is getattr(self, 'final_item_font', None):
                return {'font_family': self.final_item_font.currentFont().family()}
            if sender is getattr(self, 'final_item_size', None):
                return {'font_size': int(self.final_item_size.value())}
            if sender is getattr(self, 'final_item_stroke', None):
                return {'stroke_width': int(self.final_item_stroke.value())}
        except Exception:
            pass
        return {}

    def on_final_item_style_changed(self, *args):
        if self._style_signal_lock:
            return
        if not self.selected_text_items():
            return
        patch = self._final_item_style_patch_from_sender()
        if not patch:
            return
        self.apply_style_to_selected(**patch)


    def on_text_opacity_changed(self, value):
        if getattr(self, '_style_signal_lock', False):
            return
        if not self.selected_text_items() or self.cb_mode.currentIndex() != 4:
            return
        self.apply_style_to_selected(opacity=max(0, min(100, int(value))))

    def selected_first_text_data_item(self):
        try:
            items = self.selected_text_items()
            if items:
                return items[0].data
        except Exception:
            pass
        try:
            rows = self.selected_text_data_items()
            if rows:
                return rows[0]
        except Exception:
            pass
        return None

    def open_selected_text_gradient_dialog(self):
        try:
            self.open_text_advanced_effect_dialog(self.selected_text_data_items())
        except Exception:
            pass

    def toggle_selected_text_transform_quick(self):
        d = self.selected_first_text_data_item()
        if d is not None:
            self.toggle_text_transform_mode(d)

    def toggle_selected_text_skew_quick(self):
        d = self.selected_first_text_data_item()
        if d is not None:
            self.toggle_text_skew_mode(d)

    def toggle_selected_text_trapezoid_quick(self):
        d = self.selected_first_text_data_item()
        if d is not None:
            self.toggle_text_trapezoid_mode(d)

    def toggle_selected_text_arc_quick(self):
        d = self.selected_first_text_data_item()
        if d is not None:
            self.toggle_text_arc_mode(d)

    def rasterize_selected_text_quick(self):
        try:
            self.convert_text_data_items_to_raster_objects(self.selected_text_data_items())
        except Exception:
            pass

    def rebuild_current_page_text_layer_from_data(self, selected_ids=None, clear_selection=False):
        """현재 최종결과 scene의 텍스트 아이템만 제자리에서 다시 그린다.

        예전 안정화 패치에서는 크래시 회피를 위해 mode_chg(4) 전체 재구성으로 우회했지만,
        텍스트 이동/수정/줌 때마다 배경과 텍스트 레이어 전체가 다시 만들어져 조작감이 크게 느려졌다.
        여기서는 기존 QGraphicsItem을 제거하지 않고 TypesettingItem 내부 path/style만 재계산한다.
        """
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return False
        try:
            if self.cb_mode.currentIndex() != 4:
                return False
        except Exception:
            return False
        scene = self._safe_graphics_scene()
        if scene is None:
            return False

        ids = [x for x in (selected_ids or []) if x is not None]
        if not ids and not clear_selection:
            try:
                ids = [getattr(x, 'data', {}).get('id') for x in scene.selectedItems() if isinstance(x, TypesettingItem)]
                ids = [x for x in ids if x is not None]
            except Exception:
                ids = []
        idset = {str(x) for x in ids if x is not None}

        # Undo/Redo에서 curr["data"] 리스트를 통째로 교체하면 scene 위 TypesettingItem.data는
        # 이전 dict 객체를 계속 바라볼 수 있다. 이 상태로 path만 다시 그리면 화면은 그대로라
        # "텍스트 Undo가 안 먹는" 것처럼 보인다. 현재 page data의 dict로 반드시 재결합한다.
        curr = self.data.get(self.idx)
        data_list = curr.get("data", []) if isinstance(curr, dict) else []
        data_by_id = {}
        try:
            for d in data_list:
                if isinstance(d, dict) and d.get("id") is not None:
                    data_by_id[str(d.get("id"))] = d
        except Exception:
            data_by_id = {}

        # scene/data의 ID 구성이 달라진 경우(붙여넣기 Undo, 삭제 Undo 등)는 in-place 갱신만으로는
        # 아이템 추가/삭제가 맞지 않는다. 단, 비교 대상은 전체 curr['data']가 아니라
        # 실제 최종화면에 그려질 renderable text id여야 한다.
        try:
            scene_ids = {
                str(getattr(obj, 'data', {}).get('id'))
                for obj in list(scene.items())
                if isinstance(obj, TypesettingItem)
                and getattr(obj, 'data', {}).get('id') is not None
                and (not hasattr(obj, 'isVisible') or obj.isVisible())
            }
            renderable_ids = {
                str(d.get('id'))
                for d in data_list
                if isinstance(d, dict) and self._is_renderable_text_data_item(d)
            }
            if scene_ids != renderable_ids:
                try:
                    self.audit_boundary_event(
                        "TEXT_LAYER_REBUILD_NEEDS_FULL_REFRESH",
                        scene_count=len(scene_ids),
                        data_count=len(renderable_ids),
                        raw_data_count=len(data_by_id),
                        selected_count=len(idset),
                        throttle_ms=200,
                    )
                except Exception:
                    pass
                try:
                    self.schedule_safe_text_scene_resync(
                        reason="scene_data_mismatch",
                        selected_ids=ids,
                        delay_ms=40,
                    )
                    return True
                except Exception:
                    return False
        except Exception:
            pass

        old_rebuild = getattr(self, "_is_rebuilding_text_layer", False)
        self._is_rebuilding_text_layer = True
        changed = False
        rebound = 0
        raster_mode_mismatch = False
        try:
            for obj in list(scene.items()):
                if not isinstance(obj, TypesettingItem):
                    continue
                sid = str(getattr(obj, 'data', {}).get('id'))
                if idset and sid not in idset:
                    continue
                try:
                    bound_data = data_by_id.get(sid)
                    if isinstance(bound_data, dict) and getattr(obj, "data", None) is not bound_data:
                        obj.data = bound_data
                        rebound += 1
                        try:
                            obj.main_window = self
                        except Exception:
                            pass
                    item_raster = bool(getattr(obj, "_is_rasterized_text", False))
                    data_raster = bool((getattr(obj, "data", {}) or {}).get("rasterized_text"))
                    if item_raster != data_raster:
                        # Text-object conversion changes the runtime item class behavior.
                        # In-place refresh cannot safely turn a rasterized item back into editable text,
                        # so queue a full text-layer rebuild after the current event unwinds.
                        raster_mode_mismatch = True
                        continue
                    if data_raster:
                        if hasattr(obj, "_init_rasterized_text_item"):
                            obj.prepareGeometryChange()
                            obj._init_rasterized_text_item()
                        else:
                            obj.update()
                    elif hasattr(obj, 'rebuild_text_render_for_live_preview'):
                        obj.rebuild_text_render_for_live_preview(force=True)
                    obj.update()
                    changed = True
                except RuntimeError:
                    return False
                except Exception:
                    pass
            if raster_mode_mismatch:
                try:
                    self.audit_boundary_event("TEXT_LAYER_REBUILD_RASTER_MODE_MISMATCH", selected_count=len(idset), throttle_ms=120)
                except Exception:
                    pass
                try:
                    self.schedule_safe_text_scene_resync(
                        reason="raster_mode_mismatch",
                        selected_ids=ids,
                        delay_ms=30,
                        table_refresh=True,
                    )
                    return True
                except Exception:
                    return False
            try:
                if rebound:
                    self.audit_boundary_event("TEXT_LAYER_REBOUND_DATA", rebound=rebound, changed=changed, throttle_ms=200)
            except Exception:
                pass
            if clear_selection:
                try:
                    scene.clearSelection()
                except Exception:
                    pass
            elif idset:
                try:
                    for obj in list(scene.items()):
                        if isinstance(obj, TypesettingItem) and str(getattr(obj, 'data', {}).get('id')) in idset:
                            obj.setSelected(True)
                except Exception:
                    pass
            try:
                self.force_update_final_scene_region()
            except Exception:
                try:
                    scene.update()
                except Exception:
                    pass
            return bool(changed)
        finally:
            self._is_rebuilding_text_layer = old_rebuild

    def refresh_selected_text_items_in_place(self, selected_items=None):
        ids = []
        for item in list(selected_items or self.selected_text_items() or []):
            try:
                sid = item.data.get('id')
                if sid is not None:
                    ids.append(sid)
            except Exception:
                pass
        return self.rebuild_current_page_text_layer_from_data(ids)

    def refresh_final_text_items_by_ids(self, text_ids):
        return self.rebuild_current_page_text_layer_from_data(text_ids)

    def force_rebuild_final_text_layer_from_data(self, selected_ids=None):
        """Queue a safe full text-scene resync from page data.

        This used to purge live TypesettingItems and call mode_chg(4) immediately.
        After the undo refactor that became unsafe because delete/paste/undo can call
        this while Qt still holds stale selected item references.  Route all full
        text-layer rebuild requests through the safe resync barrier instead.
        """
        try:
            if self.cb_mode.currentIndex() != 4:
                return False
        except Exception:
            return False
        try:
            ids = [x for x in (selected_ids or []) if x is not None]
        except Exception:
            ids = []
        try:
            return bool(self.schedule_safe_text_scene_resync(
                reason="force_rebuild_final_text_layer_from_data",
                selected_ids=ids,
                delay_ms=40,
            ))
        except Exception:
            return False

    def apply_style_to_selected(self, keep_selection=True, preset_name=None, record_undo=True, **style):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        items = self.selected_text_items()
        if not items:
            return
        try:
            self.flush_text_scene_geometry_to_data([getattr(item, 'data', {}) for item in items], mark_dirty=False, reason="before style apply")
        except Exception:
            pass
        selected_ids = [item.data.get('id') for item in items]
        page_idx = int(getattr(self, "idx", 0) or 0)
        mode_idx = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else 4

        if record_undo:
            try:
                self._ensure_live_text_style_undo(
                    items,
                    fields=list(dict.fromkeys(list(style.keys()) + ["item_text_preset_name"])),
                    reason='텍스트 스타일 변경',
                )
            except Exception:
                try:
                    before = self.text_engine.snapshot_from_scene_items(items)
                    rec = self.text_engine.make_diff_record(
                        page_idx=page_idx,
                        mode=mode_idx,
                        reason='텍스트 스타일 변경',
                        before_items=before,
                        selected_ids=selected_ids,
                        fields=list(dict.fromkeys(list(style.keys()) + ["item_text_preset_name"])),
                    )
                    self.undo_push_page(rec, page_idx=page_idx)
                except Exception:
                    self.undo_text_checkpoint('텍스트 스타일 변경')

        for item in items:
            for key, value in style.items():
                item.data[key] = value
            if preset_name:
                item.data['item_text_preset_name'] = str(preset_name)
            else:
                item.data.pop('item_text_preset_name', None)
            # 이미 직접 수정된 텍스트는 OCR 박스를 버린 상태이므로,
            # 스타일 변경 후에도 실제 글자 bounds를 기준으로 텍스트 영역을 다시 만든다.
            try:
                if bool(item.data.get('manual_text_rect')) or str(item.data.get('text_anchor_mode') or '').lower() == 'text':
                    self.shrink_text_rect_to_content(item.data)
            except Exception:
                pass

        # 스타일/수치 변경은 즉시 화면에 보여야 한다.
        # 살아 있는 선택 item은 직접 path/style만 재계산해 렉을 줄이고,
        # 실패할 때만 전체 텍스트 레이어 재구성으로 폴백한다.
        if self.cb_mode.currentIndex() == 4:
            refreshed = False
            try:
                refreshed = bool(self.refresh_text_items_live_in_place(items, keep_selection=keep_selection))
            except Exception:
                refreshed = False
            if not refreshed:
                try:
                    refreshed = bool(self.rebuild_current_page_text_layer_from_data(selected_ids if keep_selection else None, clear_selection=not keep_selection))
                except Exception:
                    refreshed = False
            if not refreshed:
                try:
                    refreshed = bool(self.force_rebuild_final_text_layer_from_data(selected_ids if keep_selection else None))
                    try:
                        self.audit_boundary_event("TEXT_STYLE_REFRESH_FORCE_REBUILD", selected_count=len(selected_ids), fields=",".join([str(k) for k in style.keys()]), ok=bool(refreshed), throttle_ms=120)
                    except Exception:
                        pass
                except Exception:
                    refreshed = False
            if not refreshed:
                try:
                    self.schedule_final_text_scene_refresh(40)
                except Exception:
                    pass
            try:
                if keep_selection and selected_ids:
                    self.reselect_text_items(selected_ids)
            except Exception:
                pass
            try:
                self.update_item_preset_combo_for_selected_texts()
            except Exception:
                pass
        try:
            if hasattr(self, "text_engine") and self.text_engine is not None:
                self.text_engine.mark_dirty(page_idx, selected_ids, list(style.keys()))
            self.mark_active_page_dirty("text")
        except Exception:
            pass
        try:
            self.schedule_deferred_auto_save_project(900)
        except Exception:
            self.auto_save_project()

    def reselect_text_items(self, selected_ids):
        ids = set(selected_ids or [])
        if not ids or getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        scene = self._safe_graphics_scene()
        if scene is None:
            return
        try:
            for item in scene.items():
                if isinstance(item, TypesettingItem) and item.data.get('id') in ids:
                    item.setSelected(True)
        except RuntimeError:
            return
        except Exception:
            return

    def select_table_rows_by_ids(self, selected_ids):
        if not hasattr(self, 'tab') or self._syncing_selection:
            return
        ids = {str(x) for x in (selected_ids or []) if x is not None}
        self._syncing_selection = True
        try:
            model = self.tab.model()
            sm = self.tab.selectionModel()
            if not sm:
                return
            sm.clearSelection()
            first_row = None
            for row in range(1, self.tab.rowCount()):
                id_item = self.tab.item(row, 0)
                if id_item and id_item.text().strip() in ids:
                    top = model.index(row, 0)
                    bottom = model.index(row, self.tab.columnCount() - 1)
                    sel = QItemSelection(top, bottom)
                    sm.select(sel, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    if first_row is None:
                        first_row = row
            if first_row is not None:
                # setCurrentCell()은 환경에 따라 선택을 마지막 한 줄로 줄일 수 있어서 사용하지 않는다.
                # 현재 인덱스만 조용히 옮기고 다중 선택 상태는 유지한다.
                sm.setCurrentIndex(model.index(first_row, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
        finally:
            self._syncing_selection = False

    def selected_table_text_ids(self):
        if not hasattr(self, 'tab'):
            return []
        rows = sorted({idx.row() for idx in self.tab.selectedIndexes() if idx.row() > 0})
        ids = []
        for row in rows:
            item = self.tab.item(row, 0)
            if item:
                ids.append(item.text().strip())
        return ids

    def on_table_selection_changed(self):
        if self._syncing_selection:
            return
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        if self.cb_mode.currentIndex() != 4:
            return
        scene = self._safe_graphics_scene()
        if scene is None:
            return
        active_transform = self.current_transform_data_item()
        if active_transform is not None:
            self.reselect_text_items([active_transform.get('id')])
            return
        ids = set(self.selected_table_text_ids())
        self._syncing_selection = True
        try:
            scene.blockSignals(True)
            try:
                for item in scene.items():
                    if isinstance(item, TypesettingItem):
                        item.setSelected(str(item.data.get('id')) in ids)
            finally:
                scene.blockSignals(False)
        except RuntimeError:
            pass
        except Exception:
            pass
        finally:
            self._syncing_selection = False
        # 우측 스타일 칸은 첫 선택 항목 기준으로 맞춘다.
        self.on_scene_selection_changed()

    def configure_live_text_numeric_inputs(self):
        """텍스트 스타일 숫자 입력은 조작 즉시 화면에 반영한다.

        전체 숫자 입력칸은 안정성을 위해 keyboardTracking=False를 쓰지만,
        텍스트 스타일 컨트롤은 작업자가 수치를 움직이며 결과를 봐야 하므로
        별도로 실시간 추적을 켠다. Undo는 아래 live style session이 묶어서 기록한다.
        """
        for attr in (
            "sb_font_size", "sb_strk", "sb_line_spacing", "sb_letter_spacing", "sb_char_width", "sb_char_height",
            "final_item_size", "final_item_stroke", "sb_text_opacity",
        ):
            try:
                spin = getattr(self, attr, None)
                if spin is None:
                    continue
                spin.setKeyboardTracking(True)
                spin.setProperty("ysb_live_text_style_spin", True)
            except Exception:
                pass

    def _live_text_style_selected_key(self, items=None):
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            page_idx = 0
        ids = []
        for item in list(items or self.selected_text_items() or []):
            try:
                sid = getattr(item, "data", {}).get("id")
                if sid is not None:
                    ids.append(str(sid))
            except Exception:
                pass
        return (page_idx, tuple(sorted(ids)))







































    def on_global_text_style_changed(self, *args):
        if self._style_signal_lock:
            return
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        selected = self.selected_text_items()
        if not selected or self.cb_mode.currentIndex() != 4:
            self.update_text_style_control_state([])
            return
        patch = self._style_patch_from_sender()
        if not patch:
            return
        self.set_preset_combo_to_last()
        self.set_item_preset_combo_custom()
        self.schedule_last_text_preset_save("__last__")
        self.apply_style_to_selected(**patch)

    def set_global_align(self, align):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        selected = self.selected_text_items()
        if not selected or self.cb_mode.currentIndex() != 4:
            self.update_text_style_control_state([])
            return
        self.default_align = align
        self.set_preset_combo_to_last()
        self.set_item_preset_combo_custom()
        self.schedule_last_text_preset_save("__last__")
        self.apply_style_to_selected(align=align)
        self.update_text_style_control_state(selected)

    def pick_color(self, target):
        if target in ("global_text", "global_stroke") and (not self.selected_text_items() or self.cb_mode.currentIndex() != 4):
            self.update_text_style_control_state([])
            return
        if target == "final_paint":
            current = self.final_paint_color
        else:
            current = self.default_text_color if "text" in target else self.default_stroke_color
        color = ysb_get_color_with_hex_focus(QColor(current), self, "색상 선택")
        if not color.isValid():
            return
        hex_color = color.name(QColor.NameFormat.HexRgb).upper()
        if target == "global_text":
            self.default_text_color = hex_color
            self.update_color_button_styles()
            if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
                self.set_preset_combo_to_last()
                self.set_item_preset_combo_custom()
                self.schedule_last_text_preset_save("__last__")
                self.apply_style_to_selected(text_color=hex_color)
        elif target == "global_stroke":
            self.default_stroke_color = hex_color
            self.update_color_button_styles()
            if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
                self.set_preset_combo_to_last()
                self.set_item_preset_combo_custom()
                self.schedule_last_text_preset_save("__last__")
                self.apply_style_to_selected(stroke_color=hex_color)
        elif target == "item_text":
            self.apply_style_to_selected(text_color=hex_color)
        elif target == "item_stroke":
            self.apply_style_to_selected(stroke_color=hex_color)
        elif target == "final_paint":
            self.final_paint_color = hex_color
            self.update_color_button_styles()
            self.log(f"🎨 최종 페인팅 색상: {hex_color}")

    def on_show_final_text_toggled(self, checked):
        old_state = bool(getattr(self, "_last_show_final_text_checked", not bool(checked)))
        new_state = bool(checked)
        if (
            old_state != new_state
            and not getattr(self, "_project_undo_restore_lock", False)
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
        ):
            try:
                rec = self.make_project_undo_record("텍스트 표시 ON/OFF")
                rec.setdefault("ui_state", self.current_project_ui_state())
                rec["ui_state"]["show_final_text"] = old_state
                self.undo_push_project(rec)
            except Exception:
                pass
        self._last_show_final_text_checked = new_state
        if self.cb_mode.currentIndex() == 4:
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress
        self.auto_save_project()

    def active_mask_key(self, mode_idx=None):
        mode_idx = self.cb_mode.currentIndex() if mode_idx is None else mode_idx
        if hasattr(self, "mask_engine") and self.mask_engine is not None:
            try:
                return self.mask_engine.active_key(mode_idx, bool(getattr(self, "mask_toggle_enabled", False)))
            except Exception:
                pass
        # Fallback for older startup states.
        if mode_idx == 2:
            return 'mask_merge'
        if mode_idx == 3:
            return 'mask_inpaint' if self.mask_toggle_enabled else 'mask_inpaint_off'
        return None

    def get_active_mask(self, curr, mode_idx=None):
        if hasattr(self, "mask_engine") and self.mask_engine is not None:
            try:
                mode_idx = self.cb_mode.currentIndex() if mode_idx is None else mode_idx
                return self.mask_engine.get_mask(curr, mode_idx=mode_idx, mask_toggle_enabled=bool(getattr(self, "mask_toggle_enabled", False)))
            except Exception:
                pass
        key = self.active_mask_key(mode_idx)
        if not key or not curr:
            return None
        return curr.get(key)

    def set_active_mask(self, curr, mask, mode_idx=None):
        mode_idx = self.cb_mode.currentIndex() if mode_idx is None else mode_idx
        if hasattr(self, "mask_engine") and self.mask_engine is not None:
            try:
                return self.mask_engine.set_mask(curr, mask, page_idx=int(getattr(self, "idx", 0) or 0), mode_idx=mode_idx, mask_toggle_enabled=bool(getattr(self, "mask_toggle_enabled", False)))
            except Exception:
                pass
        key = self.active_mask_key(mode_idx)
        if key and curr is not None:
            curr[key] = mask.copy() if isinstance(mask, np.ndarray) else mask
            curr[f"{key}_dirty"] = True
            try:
                self.mark_active_page_dirty("mask")
            except Exception:
                pass
        return key

    def on_mask_toggle_changed(self, checked):
        curr = self.data.get(self.idx)
        old_state = self.mask_toggle_enabled
        mode = self.cb_mode.currentIndex()
        if (
            mode == 3
            and not getattr(self, "_project_undo_restore_lock", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
        ):
            try:
                self.commit_current_page_ui_to_data(include_mask=True)
                self.push_project_undo("마스크 ON/OFF")
            except Exception:
                pass

        # 토글은 페인팅 마스크 전용이다.
        # 텍스트 마스크에서는 분석 마스크(mask_merge)만 쓰므로 ON/OFF 분리 저장을 하지 않는다.
        if curr is not None and mode == 3:
            # 토글을 바꾸기 직전, 화면에 떠 있는 현재 페인팅 마스크를 이전 토글 슬롯에 먼저 저장한다.
            m = self.view.get_mask_np()
            if m is not None:
                curr['mask_inpaint' if old_state else 'mask_inpaint_off'] = m.copy()

        self.mask_toggle_enabled = bool(checked)
        if hasattr(self, "act_mask_toggle"):
            self.act_mask_toggle.setText("☑" if checked else "☐")
        if curr is not None:
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
        state = "ON" if checked else "OFF"
        self.log(f"🎚️ 페인팅 마스크 토글: {state}")

        if mode == 3:
            # 토글은 탭 이동이 아니라 같은 페인팅 마스크 탭 안에서
            # mask_inpaint / mask_inpaint_off 슬롯만 바꾸는 작업이다.
            # 따라서 mode_chg(3)로 화면을 다시 그릴 때:
            # 1) 탭 변경 Undo를 만들지 않고
            # 2) 이전 화면 마스크를 새 토글 슬롯에 덮어쓰지 않도록 막는다.
            old_suppress_mode_undo = getattr(self, "_suppress_mode_undo", False)
            old_skip_mode_mask_commit = getattr(self, "_skip_mode_mask_commit", False)
            old_mask_toggle_refreshing = getattr(self, "_mask_toggle_refreshing", False)
            self._suppress_mode_undo = True
            self._skip_mode_mask_commit = True
            self._mask_toggle_refreshing = True
            try:
                self.mode_chg(3)
            finally:
                self._suppress_mode_undo = old_suppress_mode_undo
                self._skip_mode_mask_commit = old_skip_mode_mask_commit
                self._mask_toggle_refreshing = old_mask_toggle_refreshing
        self.auto_save_project()

    def set_mask_toggle_safely(self, checked):
        self.mask_toggle_enabled = bool(checked)
        if hasattr(self, 'cb_mask_toggle'):
            self.cb_mask_toggle.blockSignals(True)
            try:
                self.cb_mask_toggle.setChecked(bool(checked))
                if hasattr(self, "act_mask_toggle"):
                    self.act_mask_toggle.setText("☑" if checked else "☐")
            finally:
                self.cb_mask_toggle.blockSignals(False)

    def get_page_stem(self, page_idx):
        """
        TXT 추출/번역문 불러오기용 파일명 기준.

        이제 기준은 실제 프로젝트의 뿌리 이름인 original_name이다.
        원본 파일명 변경 기능이 original_name과 images 경로를 함께 갱신하므로,
        TXT 출력/일괄 불러오기도 같은 이름을 따라가야 한다.
        """
        try:
            curr = self.data.get(page_idx, {}) if isinstance(self.data, dict) else {}
            name = curr.get('original_name') if isinstance(curr, dict) else ""
            if name:
                return safe_page_file_stem(Path(str(name)).stem, fallback=f"page{int(page_idx) + 1:03d}")
        except Exception:
            pass
        try:
            return safe_page_file_stem(Path(os.path.basename(self.paths[page_idx])).stem, fallback=f"page{int(page_idx) + 1:03d}")
        except Exception:
            return f"page{int(page_idx) + 1:03d}"

    def get_output_root(self):
        if self.project_dir:
            return self.project_dir
        if self.paths:
            return os.path.dirname(os.path.abspath(self.paths[self.idx]))
        return os.getcwd()

    def ensure_subdir(self, name):
        root = self.get_output_root()
        path = os.path.join(root, name)
        os.makedirs(path, exist_ok=True)
        return path

    def output_cleanup_targets(self):
        """현재 프로젝트에서 삭제 가능한 출력물 목록을 모은다."""
        root = Path(self.get_output_root())
        targets = {
            "result": [],
            "script": [],
            "txt": [],
        }

        for result_dir in (root / "result", root / "Result"):
            if result_dir.exists():
                try:
                    targets["result"].extend([p for p in result_dir.iterdir() if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")])
                except Exception:
                    pass

        scripts_dir = root / "scripts"
        if scripts_dir.exists():
            try:
                targets["script"].extend([p for p in scripts_dir.iterdir() if p.is_file() and p.suffix.lower() in (".jsx", ".js", ".txt")])
            except Exception:
                pass

        for txt_dir in (root / "txt", root / "Txt"):
            if txt_dir.exists():
                try:
                    targets["txt"].extend([p for p in txt_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"])
                except Exception:
                    pass

        return targets

    def open_output_cleanup_dialog(self):
        """옵션: 현재 프로젝트 산출물 삭제."""
        if not self.project_dir:
            QMessageBox.information(self, self.tr_ui("출력물 삭제"), self.tr_ui("먼저 프로젝트를 열어주세요."))
            return False

        targets = self.output_cleanup_targets()
        counts = {k: len(v) for k, v in targets.items()}
        if not any(counts.values()):
            QMessageBox.information(self, self.tr_ui("출력물 삭제"), self.tr_ui("삭제할 출력물이 없습니다."))
            return False

        dlg = OutputCleanupDialog(counts, self)
        try:
            dlg.setStyleSheet(self.message_box_style())
        except Exception:
            pass
        if not dlg.exec():
            return False

        selected = dlg.selected()
        files = []
        labels = []
        if selected.get("result"):
            files.extend(targets.get("result", []))
            labels.append(f"{self.tr_ui('최종결과 이미지')} {len(targets.get('result', []))}개")
        if selected.get("script"):
            files.extend(targets.get("script", []))
            labels.append(f"{self.tr_ui('포토샵 스크립트')} {len(targets.get('script', []))}개")
        if selected.get("txt"):
            files.extend(targets.get("txt", []))
            labels.append(f"{self.tr_ui('TXT 지문')} {len(targets.get('txt', []))}개")

        if not files:
            return False

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("출력물 삭제 확인"))
        msg.setText(self.tr_ui("선택한 출력물을 삭제할까요?"))
        msg.setInformativeText("\n".join(labels))
        btn_delete = msg.addButton(self.tr_ui("삭제"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        for _btn in (btn_delete, btn_cancel):
            try:
                _btn.setMinimumWidth(96)
            except Exception:
                pass
        msg.setDefaultButton(btn_cancel)
        msg.setEscapeButton(btn_cancel)
        try:
            msg.setStyleSheet(self.message_box_style())
        except Exception:
            pass
        force_message_box_front(msg)
        msg.exec()
        if msg.clickedButton() is not btn_delete:
            self.log("↩️ 출력물 삭제 취소")
            return False

        deleted = 0
        failed = 0
        for p in files:
            try:
                p = Path(p)
                if p.exists() and p.is_file():
                    p.unlink()
                    deleted += 1
            except Exception:
                failed += 1

        self.log(f"🧹 출력물 삭제 완료: {deleted}개 삭제 / 실패 {failed}개")
        if failed:
            QMessageBox.warning(self, self.tr_ui("출력물 삭제"), f"{self.tr_ui('일부 파일을 삭제하지 못했습니다.')} 실패: {failed}개")
        return True

    def choose_text_extract_mode(self):
        ko_items = ["원문만", "번역문만", "원문+번역문"]
        display_items = [self.tr_ui(x) for x in ko_items]
        value, ok = QInputDialog.getItem(
            self,
            self.tr_ui("지문 추출"),
            self.tr_ui("추출할 내용:"),
            display_items,
            0,
            False
        )
        if not ok:
            return None
        try:
            idx = display_items.index(value)
            return ko_items[idx]
        except ValueError:
            return value

    def build_text_export_content(self, page_idx, mode):
        curr = self.data.get(page_idx, {})
        blocks = []
        for i, item in enumerate(curr.get('data', []), 1):
            text_id = str(item.get('id', i))
            original = str(item.get('text', '') or '')
            translated = str(item.get('translated_text', '') or '')
            marker = f"[{text_id}]"
            if mode == "원문만":
                blocks.append(f"{marker}\n\n{original}")
            elif mode == "번역문만":
                blocks.append(f"{marker}\n\n{translated}")
            else:
                blocks.append(f"{marker}\n\n{original}\n\n{translated}")
        return "\n\n".join(blocks).rstrip() + "\n"

    def extract_text_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        mode = self.choose_text_extract_mode()
        if not mode:
            return
        txt_dir = self.ensure_subdir("txt")
        out_path = os.path.join(txt_dir, f"{self.get_page_stem(self.idx)}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(self.build_text_export_content(self.idx, mode))
        self.log((f"📄 Extract text complete: {out_path}" if self.ui_language == LANG_EN else f"📄 지문 추출 완료: {out_path}"))
        self.auto_save_project()

    def extract_text_batch(self):
        if not self.paths:
            return
        title = "일괄 지문 추출"
        selected_indices, selected_label = self.choose_batch_page_indices_for_context(title, "extract_text")
        if selected_indices is None:
            self.log("↩️ Batch extract text canceled" if self.ui_language == LANG_EN else "↩️ 일괄 지문 추출 취소")
            return
        self.commit_current_page_ui_to_data()
        mode = self.choose_text_extract_mode()
        if not mode:
            return
        txt_dir = self.ensure_subdir("txt")

        def process_page(i):
            if i not in self.data or not self.data[i].get('data'):
                return "skipped", "텍스트 데이터 없음"
            out_path = os.path.join(txt_dir, f"{self.get_page_stem(i)}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(self.build_text_export_content(i, mode))
            return "done", os.path.basename(out_path)

        self.run_page_queue_batch(title, "extract_text", selected_indices, selected_label, process_page, visual=False, cancellable=True)



    def parse_translation_txt(self, path, valid_ids):
        valid = {str(x) for x in valid_ids}

        def marker_to_id(token):
            token = str(token or "").strip()
            if len(token) >= 3 and token.startswith("[") and token.endswith("]"):
                inner = token[1:-1].strip()
                if inner.isdigit() and inner in valid:
                    return inner
            return None

        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()

        result = {}
        i = 0
        while i < len(lines):
            text_id = marker_to_id(lines[i])
            if text_id:
                i += 1
                buf = []
                while i < len(lines):
                    # 다음 번호는 [1]처럼 대괄호 안의 숫자이고,
                    # 현재 페이지에 실제 존재하는 텍스트 번호일 때만 인정한다.
                    # 그래서 1131313, 421 같은 숫자 번역문은 안전하게 본문으로 들어간다.
                    if marker_to_id(lines[i]):
                        break
                    if lines[i].strip():
                        buf.append(lines[i].rstrip())
                    i += 1

                if buf:
                    result[text_id] = "\n".join(buf).strip()
                continue

            i += 1

        return result

    def apply_translation_map_to_page(self, page_idx, trans_map):
        curr = self.data.get(page_idx)
        if not curr:
            return 0
        count = 0
        for i, item in enumerate(curr.get('data', []), 1):
            text_id = str(item.get('id', i))
            if text_id in trans_map:
                new_text = str(trans_map[text_id] or '')
                old_text = str(item.get('translated_text', '') or '')
                if new_text != old_text:
                    item['translated_text'] = new_text
                    try:
                        self.shrink_text_rect_to_content(item)
                    except Exception:
                        pass
                    count += 1
        return count

    def filename_match_aliases(self, value):
        """클린본/TXT 일괄 불러오기에서 쓸 파일명 stem 별칭 후보를 만든다.

        원본 stem을 1순위로 유지하되, 페이지탭/출력명에 붙을 수 있는
        1p_, page001_, clean_, result_ 같은 접두어/번호형을 양방향으로 보정한다.
        """
        seen = set()
        result = []

        def norm(v):
            try:
                stem = safe_page_file_stem(Path(str(v)).stem, fallback="")
                return str(stem or "").strip()
            except Exception:
                return ""

        def add(v):
            s = norm(v)
            if not s:
                return
            key = s.casefold()
            if key not in seen:
                seen.add(key)
                result.append(s)

        base = norm(value)
        if not base:
            return result

        queue = [base]
        known_prefixes = (
            "clean", "cleaned", "clear", "cleared", "clean본", "cleanbon",
            "클린", "클린본", "result", "results", "output", "out", "final",
            "최종", "결과", "bg", "background", "inpaint", "inpainted",
            "no_text", "notext", "textless", "remove_text", "removed_text",
        )
        known_suffixes = known_prefixes

        steps = 0
        while queue and steps < 128:
            steps += 1
            current = queue.pop(0)
            before_len = len(result)
            add(current)

            variants = set()
            s = current.strip()

            # 1p_제목, 01p-제목, page001_제목, page0001_제목, p001_제목, 001_제목 같은 페이지 접두어 제거
            for pattern in (
                r"^\s*\d{1,4}\s*p\s*[_\-\s]+(.+)$",
                r"^\s*p\s*\d{1,4}\s*[_\-\s]+(.+)$",
                r"^\s*page\s*\d{1,4}\s*[_\-\s]+(.+)$",
                r"^\s*페이지\s*\d{1,4}\s*[_\-\s]+(.+)$",
                r"^\s*\d{1,4}\s*[_\-\s]+(.+)$",
            ):
                m = re.match(pattern, s, flags=re.IGNORECASE)
                if m:
                    variants.add(m.group(1).strip())

            # clean_제목 / result-제목 / 최종 제목 같은 작업명 접두어 제거
            for prefix in known_prefixes:
                m = re.match(rf"^\s*{re.escape(prefix)}\s*[_\-\s]+(.+)$", s, flags=re.IGNORECASE)
                if m:
                    variants.add(m.group(1).strip())

            # 제목_clean / 제목-result 같은 작업명 접미어 제거
            for suffix in known_suffixes:
                m = re.match(rf"^(.+?)\s*[_\-\s]+{re.escape(suffix)}\s*$", s, flags=re.IGNORECASE)
                if m:
                    variants.add(m.group(1).strip())

            # 기본 stem에 대해 흔한 외부 작업물 파일명도 후보로 추가
            # 예: 제목 ↔ clean_제목 / result_제목 / 1p_제목
            already_page_prefixed = re.match(r"^\s*(?:\d{1,4}\s*p|page\s*\d{1,4}|p\s*\d{1,4}|페이지\s*\d{1,4}|\d{1,4})\s*[_\-\s]+", s, flags=re.IGNORECASE)
            already_work_prefixed = any(
                re.match(rf"^\s*{re.escape(prefix)}\s*[_\-\s]+", s, flags=re.IGNORECASE)
                for prefix in known_prefixes
            )
            if not already_page_prefixed and not already_work_prefixed:
                for prefix in ("clean", "cleaned", "clean본", "클린본", "result", "output", "final", "최종", "결과", "inpainted"):
                    variants.add(f"{prefix}_{s}")

            for v in variants:
                nv = norm(v)
                if nv and nv.casefold() not in seen:
                    queue.append(nv)

            # 무한 변형 방지. 이번 라운드에서 추가가 없고 새 큐도 없으면 종료.
            if len(result) == before_len and not queue:
                break

        return result

    def add_page_number_name_candidates(self, candidates, seen, page_idx):
        """page001처럼 제목 없이 페이지 번호만 있는 파일명 후보를 강제로 추가한다."""
        try:
            page_no = int(page_idx) + 1
        except Exception:
            return

        def add_raw(value):
            try:
                stem = safe_page_file_stem(Path(str(value)).stem, fallback="")
                key = str(stem or "").casefold()
                if stem and key not in seen:
                    seen.add(key)
                    candidates.append(stem)
            except Exception:
                pass

        for stem in (
            f"page{page_no:03d}",
            f"page{page_no:04d}",
            f"p{page_no:03d}",
            f"p{page_no:04d}",
            f"{page_no:03d}",
            f"{page_no:04d}",
        ):
            add_raw(stem)

    def translation_txt_name_candidates(self, page_idx):
        """번역문 다중 불러오기에서 허용할 TXT 파일명 후보.

        원본 이미지 stem을 기본으로 하되, 페이지탭/출력명이 1p_원본명, page001,
        page0001, clean_원본명, result_원본명처럼 달라져도 같은 페이지로 매칭한다.
        """
        candidates = []
        seen = set()

        def add(value):
            for stem in self.filename_match_aliases(value):
                key = str(stem or "").casefold()
                if stem and key not in seen:
                    seen.add(key)
                    candidates.append(stem)

        add(self.get_page_stem(page_idx))
        try:
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_ORIGINAL, include_ext=False))
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_PAGE_ORIGINAL, include_ext=False))
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_PAGE_NUMBER, include_ext=False))
            add(self.output_display_stem(page_idx))
        except Exception:
            pass
        self.add_page_number_name_candidates(candidates, seen, page_idx)
        return candidates

    def find_translation_txt_in_folder(self, folder, page_stem=None, page_idx=None):
        """번역문 불러오기용 TXT 탐색.

        원본명.txt를 기본으로 찾고, 1p_원본명.txt / page001.txt / 출력 표시명.txt도 후보로 인정한다.
        선택한 폴더 바로 아래를 먼저 찾은 뒤 없으면 하위 폴더까지 한 번 더 찾는다.
        """
        if not folder:
            return None
        root = Path(folder)
        if not root.exists() or not root.is_dir():
            return None

        candidates = []
        if page_idx is not None:
            candidates.extend(self.translation_txt_name_candidates(page_idx))
        if page_stem:
            seen = {str(x or "").casefold() for x in candidates}
            for stem in self.filename_match_aliases(page_stem):
                key = str(stem or "").casefold()
                if stem and key not in seen:
                    seen.add(key)
                    candidates.append(stem)
        if not candidates:
            return None

        targets = {f"{stem}.txt".casefold() for stem in candidates}

        try:
            for child in root.iterdir():
                if child.is_file() and child.name.casefold() in targets:
                    return str(child)
        except Exception:
            pass

        try:
            for child in root.rglob("*.txt"):
                if child.is_file() and child.name.casefold() in targets:
                    return str(child)
        except Exception:
            pass
        return None

    def match_translation_txt_paths_to_pages(self, paths):
        """여러 TXT 파일을 파일명 stem 기준으로 프로젝트 페이지에 매칭한다."""
        by_stem = {}
        exact_items = []
        for path in paths or []:
            try:
                stem = safe_page_file_stem(Path(str(path)).stem, fallback="")
                key = str(stem or "").casefold()
                if key:
                    exact_items.append((path, stem))
                    if key not in by_stem:
                        by_stem[key] = path
            except Exception:
                pass

        # 정확한 파일명 매칭을 먼저 등록한 뒤, 별칭 매칭은 빈 키에만 채운다.
        # title.txt와 clean_title.txt가 동시에 있을 때 title.txt가 우선된다.
        for path, stem in exact_items:
            for alias in self.filename_match_aliases(stem):
                key = str(alias or "").casefold()
                if key and key not in by_stem:
                    by_stem[key] = path

        matched = {}
        for page_idx in range(len(getattr(self, "paths", []) or [])):
            for cand in self.translation_txt_name_candidates(page_idx):
                key = str(cand or "").casefold()
                if key in by_stem:
                    matched[page_idx] = by_stem[key]
                    break
        return matched

    def clean_image_name_candidates(self, page_idx):
        """클린본 불러오기용 이미지 파일명 후보."""
        candidates = []
        seen = set()

        def add(value):
            for stem in self.filename_match_aliases(value):
                key = str(stem or "").casefold()
                if stem and key not in seen:
                    seen.add(key)
                    candidates.append(stem)

        add(self.get_page_stem(page_idx))
        try:
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_ORIGINAL, include_ext=False))
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_PAGE_ORIGINAL, include_ext=False))
            add(self.page_display_name(page_idx, mode=PAGE_DISPLAY_MODE_PAGE_NUMBER, include_ext=False))
            add(self.output_display_stem(page_idx))
        except Exception:
            pass
        self.add_page_number_name_candidates(candidates, seen, page_idx)
        return candidates

    def read_clean_image_file(self, path, page_idx):
        try:
            img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return None
            return self.normalize_image_to_original_size(page_idx, img)
        except Exception:
            return None

    def pending_clean_import_root(self, base_dir=None):
        """클린본 불러오기 전용 경량 복구 캐시 폴더."""
        try:
            root = str(base_dir or getattr(self, "work_project_dir", None) or getattr(self, "project_dir", None) or "")
            if not root:
                return None
            return os.path.join(root, "pending_clean_import")
        except Exception:
            return None

    def pending_clean_import_manifest_path(self, base_dir=None):
        root = self.pending_clean_import_root(base_dir)
        return os.path.join(root, "pending_clean_import_map.json") if root else None

    def load_pending_clean_import_manifest(self, base_dir=None):
        path = self.pending_clean_import_manifest_path(base_dir)
        if not path or not os.path.exists(path):
            return {"version": 1, "type": "pending_clean_import", "pages": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data.setdefault("version", 1)
        data.setdefault("type", "pending_clean_import")
        if not isinstance(data.get("pages"), dict):
            data["pages"] = {}
        return data

    def save_pending_clean_import_manifest(self, manifest, base_dir=None):
        path = self.pending_clean_import_manifest_path(base_dir)
        if not path:
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(manifest or {}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 클린본 복구 맵 저장 실패: {e}")
            except Exception:
                pass
            return False

    def ensure_pending_clean_import_cache(self):
        """무거운 ProjectStore.save() 없이 클린본 복구용 pending 폴더만 준비한다."""
        try:
            if not getattr(self, "work_project_dir", None):
                # 일반 프로젝트 열기 직후에는 작업 캐시가 이미 있다.
                # 예외적으로 없으면 현재 상태 기준 캐시를 한 번만 만든다.
                self.start_work_cache_from_current(mark_dirty=True)
            root = self.pending_clean_import_root(getattr(self, "work_project_dir", None))
            if not root:
                return None
            os.makedirs(os.path.join(root, "files"), exist_ok=True)
            self.record_recovery_project_dir(getattr(self, "work_project_dir", None))
            return root
        except Exception as e:
            try:
                self.log(f"⚠️ 클린본 pending 캐시 준비 실패: {e}")
            except Exception:
                pass
            return None

    def record_pending_clean_import_page(self, page_idx, source_path):
        """page_idx에 적용한 클린본 파일을 가벼운 pending 복구 캐시에 기록한다.

        ProjectStore.save() 전체를 돌리지 않고, 원본 클린본 파일 복사본과 작은 JSON만 남긴다.
        """
        root = self.ensure_pending_clean_import_cache()
        if not root:
            return False
        try:
            page_idx = int(page_idx)
            src = Path(str(source_path))
            ext = src.suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                ext = ".png"
            files_dir = os.path.join(root, "files")
            os.makedirs(files_dir, exist_ok=True)
            stem = f"page{page_idx + 1:04d}"
            # 같은 페이지에 다시 적용하면 이전 확장자 파일은 남기지 않는다.
            try:
                for old in Path(files_dir).glob(stem + ".*"):
                    try:
                        old.unlink()
                    except Exception:
                        pass
            except Exception:
                pass
            dst = os.path.join(files_dir, stem + ext)
            shutil.copy2(str(src), dst)

            manifest = self.load_pending_clean_import_manifest(getattr(self, "work_project_dir", None))
            pages = manifest.setdefault("pages", {})
            try:
                rel = os.path.relpath(dst, str(getattr(self, "work_project_dir", None)))
            except Exception:
                rel = dst
            pages[str(page_idx)] = {
                "cache": rel.replace("\\", "/"),
                "source": str(source_path),
                "name": os.path.basename(str(source_path)),
            }
            try:
                manifest["project_dir"] = str(getattr(self, "project_dir", "") or "")
                manifest["work_project_dir"] = str(getattr(self, "work_project_dir", "") or "")
                manifest["updated_at"] = __import__("time").time()
            except Exception:
                pass
            ok = self.save_pending_clean_import_manifest(manifest, getattr(self, "work_project_dir", None))
            if ok:
                pending_base = str(getattr(self, "work_project_dir", "") or "")
                try:
                    # 폴더 mtime을 갱신해서 복구 후보 정렬에서도 최신 작업으로 잡히게 한다.
                    os.utime(pending_base, None)
                except Exception:
                    pass
                try:
                    # project.json 후보와 별도로, pending 클린본 복구 후보도 명시 기록한다.
                    self.app_options["last_pending_clean_import_dir"] = pending_base
                    save_app_options(self.app_options)
                except Exception:
                    pass
            return ok
        except Exception as e:
            try:
                self.log(f"⚠️ 클린본 pending 기록 실패: {e}")
            except Exception:
                pass
            return False

    def clear_pending_clean_import_cache(self, base_dir=None):
        try:
            root = self.pending_clean_import_root(base_dir or getattr(self, "work_project_dir", None) or getattr(self, "project_dir", None))
            if root and os.path.exists(root):
                shutil.rmtree(root, ignore_errors=True)
                return True
        except Exception:
            pass
        return False

    def is_recovery_work_project_dir(self, project_dir=None):
        try:
            p = Path(str(project_dir or getattr(self, "project_dir", "") or "")).resolve()
            roots = [self.project_cache_root(), temp_dir()]
            for root in roots:
                try:
                    r = Path(root).resolve()
                    if str(p).lower().startswith(str(r).lower()):
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def apply_pending_clean_import_if_available(self, base_dir=None):
        """복구용 pending 클린본 기록이 있으면 현재 data에 다시 반영한다."""
        base_dir = base_dir or getattr(self, "project_dir", None)
        manifest = self.load_pending_clean_import_manifest(base_dir)
        pages = manifest.get("pages") if isinstance(manifest, dict) else None
        if not isinstance(pages, dict) or not pages:
            return 0
        restored = 0
        for key, entry in list(pages.items()):
            try:
                page_idx = int(key)
            except Exception:
                continue
            if page_idx < 0 or page_idx >= len(getattr(self, "paths", []) or []):
                continue
            rel = ""
            if isinstance(entry, dict):
                rel = str(entry.get("cache") or "")
            if not rel:
                continue
            try:
                path = rel if os.path.isabs(rel) else os.path.join(str(base_dir), rel.replace("/", os.sep))
            except Exception:
                path = rel
            if not path or not os.path.exists(path):
                continue
            status, _message = self.apply_clean_image_to_page(page_idx, path)
            if str(status or "").lower() == "done":
                restored += 1
        if restored:
            try:
                self.undo_break_boundary("clean_import_recovered", "클린본 pending 복구")
            except Exception:
                pass
            try:
                self.has_unsaved_changes = True
                self.update_window_title()
            except Exception:
                pass
            try:
                self.log(f"🧯 클린본 pending 복구 적용: {restored}페이지")
            except Exception:
                pass
        return restored

    def mark_page_data_dirty_explicit(self, page_idx, kind="data"):
        """현재 화면 페이지가 아니어도 특정 page_idx를 dirty로 표시한다."""
        try:
            page_idx = int(page_idx)
        except Exception:
            page_idx = int(getattr(self, "idx", 0) or 0)
        try:
            if hasattr(self, "project_engine") and self.project_engine is not None:
                self.project_engine.mark_page_dirty(page_idx, str(kind or "data"))
        except Exception:
            pass
        try:
            if hasattr(self, "page_engine") and self.page_engine is not None:
                self.page_engine.mark_dirty(page_idx, str(kind or "data"))
        except Exception:
            pass
        try:
            self.has_unsaved_changes = True
            self.update_window_title()
        except Exception:
            pass

    def release_clean_background_payload_for_replace(self, page_idx, curr=None):
        """클린본 교체 전 기존 큰 이미지 참조를 먼저 끊는다.

        새 클린본을 읽고 PNG bytes로 인코딩한 뒤 기존 bg_clean에 덮어쓰면,
        교체 순간에 기존 클린본 + 새 디코딩 배열 + 새 인코딩 bytes가 같이 살아 메모리 피크가 커진다.
        그래서 교체 모드에서는 새 이미지를 읽기 전에 기존 클린본/최종 페인트 계열을 먼저 비운다.
        """
        try:
            page_idx = int(page_idx)
        except Exception:
            page_idx = int(getattr(self, "idx", 0) or 0)
        if curr is None:
            curr = (getattr(self, "data", {}) or {}).get(page_idx)
        if not isinstance(curr, dict):
            return False
        had_existing = False
        for key in ("bg_clean", "final_paint", "final_paint_above", "working_source"):
            try:
                if curr.get(key) is not None:
                    had_existing = True
                curr[key] = None
            except Exception:
                pass
        try:
            self._page_image_cache_order.pop(page_idx, None)
        except Exception:
            pass
        try:
            if page_idx == int(getattr(self, "idx", -1) or -1) and hasattr(self, "view") and hasattr(self.view, "clear_final_paint_layers"):
                self.view.clear_final_paint_layers()
        except Exception:
            pass
        if had_existing:
            try:
                QPixmapCache.clear()
            except Exception:
                pass
        return had_existing

    def apply_clean_image_to_page(self, page_idx, path, *, replace_mode=False):
        curr = self.data.get(page_idx)
        if curr is None:
            try:
                curr = self.make_page_data_for_image(self.paths[page_idx])
                self.data[page_idx] = curr
            except Exception:
                return "failed", "페이지 데이터 생성 실패"

        # 기존 클린본이 있는 교체 상황에서는 새 파일을 읽기 전에 먼저 기존 payload를 끊는다.
        # 실패 시 기존 클린본은 이미 비워질 수 있지만, 대량 교체 안정성과 메모리 피크 감소를 우선한다.
        had_existing = False
        try:
            had_existing = bool(curr.get('bg_clean') is not None or curr.get('final_paint') is not None or curr.get('final_paint_above') is not None)
        except Exception:
            had_existing = False
        if replace_mode or had_existing:
            self.release_clean_background_payload_for_replace(page_idx, curr)
            try:
                __import__("gc").collect()
            except Exception:
                pass

        img = self.read_clean_image_file(path, page_idx)
        if img is None:
            self.mark_page_data_dirty_explicit(page_idx, "clean_background")
            return "failed", "이미지 읽기 실패"
        encoded = None
        try:
            encoded = self.encode_np_image_to_png_bytes(img)
            curr['bg_clean'] = encoded if encoded is not None else img
            curr['final_paint'] = None
            curr['final_paint_above'] = None
            curr['working_source'] = None
            self.mark_page_data_dirty_explicit(page_idx, "clean_background")
        finally:
            # img는 원본 디코딩 배열이라 대량 클린본 불러오기에서 바로 끊어주는 게 안전하다.
            # encoded는 curr['bg_clean']에 들어간 bytes 참조만 남기고 지역 참조는 제거한다.
            try:
                if encoded is not None:
                    img = None
            except Exception:
                pass
        try:
            if page_idx == int(getattr(self, "idx", -1) or -1) and hasattr(self.view, "clear_final_paint_layers"):
                self.view.clear_final_paint_layers()
        except Exception:
            pass
        try:
            # 클린본 자체는 bg_clean bytes로 들고 있으므로 원본 ori 캐시를 이 페이지에 유지할 필요가 없다.
            # keep_indices=[]로 두어 이미지 대량 교체 중 ori 캐시가 같이 쌓이지 않게 한다.
            self.trim_page_image_cache(keep_indices=[])
        except Exception:
            pass
        return "done", os.path.basename(str(path))

    def match_clean_image_paths_to_pages(self, paths):
        by_stem = {}
        exact_items = []
        for path in paths or []:
            try:
                stem = safe_page_file_stem(Path(str(path)).stem, fallback="")
                key = str(stem or "").casefold()
                if key:
                    exact_items.append((path, stem))
                    if key not in by_stem:
                        by_stem[key] = path
            except Exception:
                pass

        # 정확한 파일명 매칭을 먼저 등록한 뒤, 별칭 매칭은 빈 키에만 채운다.
        # 이렇게 해야 title.png와 clean_title.png가 동시에 있을 때 title.png가 우선된다.
        for path, stem in exact_items:
            for alias in self.filename_match_aliases(stem):
                key = str(alias or "").casefold()
                if key and key not in by_stem:
                    by_stem[key] = path

        matched = {}
        for page_idx in range(len(getattr(self, "paths", []) or [])):
            for cand in self.clean_image_name_candidates(page_idx):
                key = str(cand or "").casefold()
                if key in by_stem:
                    matched[page_idx] = by_stem[key]
                    break
        return matched

    def import_clean_background(self):
        """클린본 이미지를 최종결과 배경(bg_clean)으로 불러온다.

        1개 선택: 현재 페이지에 적용.
        여러 개 선택: 파일명과 페이지명을 매칭해 각 페이지에 적용.
        """
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(self, self.tr_ui("일괄 작업 중"), self.tr_msg("이미 일괄 작업이 진행 중입니다.\n현재 작업이 끝난 뒤 다시 실행해 주세요."))
            return
        if not self.paths or self.idx not in self.data:
            return
        start_dir = self.ensure_subdir("clean")
        files, _ = self.get_open_file_names_logged(
            "import_clean_background",
            self,
            self.tr_ui("클린본 이미지 불러오기"),
            start_dir,
            self.tr_ui("이미지 파일") + " (*.png *.jpg *.jpeg *.webp *.bmp);;" + self.tr_ui("모든 파일") + " (*.*)",
        )
        if not files:
            return
        try:
            self.commit_current_page_ui_to_data()
        except Exception:
            pass

        # 클린본 불러오기는 이미지-heavy 작업이다.
        # 최종결과 탭(mode 4)에서 원본 탭으로 강제 이동하면 mode_chg()/ref_tab() 재렌더가 무겁게 걸릴 수 있다.
        # 따라서 실제 탭 전환은 하지 않고, 작업 중/완료 후 화면 갱신만 생략한다.
        try:
            current_mode_before_clean = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else -1
        except Exception:
            current_mode_before_clean = -1
        clean_started_from_final_mode = (current_mode_before_clean == 4)
        if clean_started_from_final_mode:
            try:
                self.log("🧼 클린본 불러오기: 최종결과 탭 전환 없이 데이터만 적용합니다.")
            except Exception:
                pass

        title = "클린본 불러오기"
        if len(files) == 1:
            target_map = {int(getattr(self, "idx", 0) or 0): files[0]}
            selected_label = self.tr_ui("현재 페이지")
        else:
            target_map = self.match_clean_image_paths_to_pages(files)
            selected_label = self.tr_ui("파일명 매칭")
            if not target_map:
                QMessageBox.warning(self, self.tr_ui("클린본 불러오기"), self.tr_ui("선택한 클린본 파일명과 일치하는 페이지를 찾지 못했습니다."))
                return

        selected_indices = list(target_map.keys())
        replace_indices = []
        for page_idx in selected_indices:
            try:
                curr = (getattr(self, "data", {}) or {}).get(int(page_idx))
                if isinstance(curr, dict) and (
                    curr.get('bg_clean') is not None
                    or curr.get('final_paint') is not None
                    or curr.get('final_paint_above') is not None
                ):
                    replace_indices.append(int(page_idx))
            except Exception:
                pass
        replace_mode = bool(replace_indices)
        if replace_mode:
            try:
                self.log(f"🧼 클린본 교체 모드: 기존 클린본 {len(replace_indices)}페이지를 먼저 해제하며 적용합니다.")
            except Exception:
                pass

        # 클린본은 이미지 대량 교체 작업이라 Undo에 올리지 않는다.
        # Undo 스냅샷 자체가 기존/신규 클린본 이미지를 모두 물고 메모리를 크게 잡아먹기 때문이다.
        changed = False

        def process_page(page_idx):
            nonlocal changed
            path = target_map.get(page_idx)
            if not path:
                return "skipped", "매칭 파일 없음"
            status, message = self.apply_clean_image_to_page(page_idx, path, replace_mode=replace_mode)
            if str(status).lower() == "done":
                changed = True
                # 무거운 ProjectStore 저장 대신, 복구에 필요한 최소 파일/맵만 즉시 기록한다.
                self.record_pending_clean_import_page(page_idx, path)
            return status, message

        result = self.run_page_queue_batch(
            title,
            "import_clean_background",
            selected_indices,
            selected_label,
            process_page,
            visual=False,
            cancellable=True,
            restore_page=False,
            save_work_cache=False,
        )
        if changed:
            try:
                self.undo_break_boundary("clean_import", "클린본 불러오기")
            except Exception:
                try:
                    self.undo_clear_all_pages("clean import")
                    self.undo_clear_project("project stack reset")
                except Exception:
                    pass
            try:
                __import__("gc").collect()
            except Exception:
                pass
        try:
            self.has_unsaved_changes = True
            self.update_window_title()
        except Exception:
            pass
        try:
            current_idx = int(getattr(self, "idx", 0) or 0)
            current_mode = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else -1
            # 대량 클린본 불러오기 직후에는 load()/ref_tab()/mode_chg() 전체 재구성을 하지 않는다.
            # 최종결과 탭에서 시작한 경우도 실제 탭 전환/자동 새로고침 없이 데이터만 바꾼다.
            if clean_started_from_final_mode:
                self.log("ℹ️ 클린본 불러오기 완료: 최종결과 탭 자동 새로고침은 생략했습니다. 확인이 필요하면 탭/페이지를 다시 열어 주세요.")
            elif current_idx in selected_indices and len(selected_indices) == 1 and current_mode == 4:
                # 안전상 mode_chg(4) 직접 호출은 하지 않는다. 단일 적용도 다음 표시 시 반영한다.
                self.log("ℹ️ 클린본 불러오기 완료: 최종결과 탭 즉시 새로고침은 생략했습니다. 탭/페이지를 다시 열면 반영됩니다.")
            elif current_idx in selected_indices:
                self.log("ℹ️ 클린본 불러오기 완료: 대량 작업 후 화면 전체 갱신은 생략했습니다. 탭/페이지를 다시 열면 반영됩니다.")
        except Exception:
            pass
        # 클린본 불러오기는 pending_clean_import 캐시를 별도로 남긴다.
        # 여기서 일반 작업 캐시 자동 저장을 예약하면 대량 이미지 저장이 다시 걸릴 수 있으므로 하지 않는다.

    def import_translation_current(self):
        """TXT 번역문을 불러온다.

        1개 선택: 현재 페이지에 적용.
        여러 개 선택: 파일명과 페이지명을 매칭해 각 페이지에 적용.
        """
        if not self.paths:
            return
        if self.idx not in self.data:
            return

        start_path = os.path.join(self.ensure_subdir("txt"), f"{self.get_page_stem(self.idx)}.txt")
        legacy_txt = os.path.join(self.get_output_root(), "Txt", f"{self.get_page_stem(self.idx)}.txt")
        if (not os.path.exists(start_path)) and os.path.exists(legacy_txt):
            start_path = legacy_txt

        files, _ = self.get_open_file_names_logged(
            "import_translation_txt",
            self,
            self.tr_ui("번역문 TXT 불러오기"),
            start_path,
            self.tr_ui("TXT 파일") + " (*.txt);;" + self.tr_ui("모든 파일") + " (*.*)",
        )
        if not files:
            return

        try:
            self.commit_current_page_ui_to_data()
        except Exception:
            pass

        title = "번역문 불러오기"
        if len(files) == 1:
            target_map = {int(getattr(self, "idx", 0) or 0): files[0]}
            selected_label = self.tr_ui("현재 페이지")
        else:
            target_map = self.match_translation_txt_paths_to_pages(files)
            selected_label = self.tr_ui("파일명 매칭")
            if not target_map:
                QMessageBox.warning(self, self.tr_ui("번역문 불러오기"), self.tr_ui("선택한 번역문 파일명과 일치하는 페이지를 찾지 못했습니다."))
                return

        selected_indices = list(target_map.keys())
        undo_rec = self.make_batch_page_data_undo_record(title, selected_indices)
        changed = False
        total_count = 0

        def process_page(page_idx):
            nonlocal changed, total_count
            curr = self.data.get(page_idx)
            if not curr or not curr.get('data'):
                return "skipped", "텍스트 데이터 없음"
            path = target_map.get(page_idx)
            if not path:
                return "skipped", "매칭 파일 없음"
            valid_ids = [str(x.get('id', n + 1)) for n, x in enumerate(curr.get('data', []))]
            if not valid_ids:
                return "skipped", "불러올 텍스트 번호 없음"
            trans_map = self.parse_translation_txt(path, valid_ids)
            if not trans_map:
                return "skipped", "맞는 텍스트 번호 없음"
            count = self.apply_translation_map_to_page(page_idx, trans_map)
            if count <= 0:
                return "skipped", "변경된 번역문 없음"
            changed = True
            total_count += count
            return "done", f"{count}개 적용"

        result = self.run_page_queue_batch(title, "import_translation", selected_indices, selected_label, process_page, visual=False, cancellable=True)

        if changed:
            try:
                self.undo_push_project(undo_rec)
            except Exception:
                pass
        try:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        except Exception:
            pass
        try:
            self.schedule_deferred_auto_save_project(200)
        except Exception:
            self.auto_save_project()
        self.log(f"📥 번역문 불러오기 완료: {total_count}개")

    def import_translation_batch(self):
        """구버전 호환용 래퍼.

        별도 '일괄 번역문 불러오기' 메뉴는 제거되었고,
        이제 '번역문 불러오기'의 다중 파일 선택으로 같은 작업을 처리한다.
        """
        return self.import_translation_current()


    def clear_translation_current(self):
        """현재 페이지의 번역문 칸을 모두 비운다."""
        if not self.paths or self.idx not in self.data:
            return

        self.commit_current_page_ui_to_data()
        curr = self.data.get(self.idx)
        if not curr or not curr.get('data'):
            self.log("⚠️ 지울 번역문이 없습니다.")
            return

        undo_rec = self.make_project_undo_record("번역문 내용 지우기")
        count = 0
        for item in curr.get('data', []):
            if str(item.get('translated_text', '') or ''):
                item['translated_text'] = ''
                try:
                    self.shrink_text_rect_to_content(item)
                except Exception:
                    pass
                count += 1

        if count:
            self.undo_push_project(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🧹 번역문 내용 지우기 완료: {count}개")

    def clear_translation_batch(self):
        """선택한 페이지의 번역문 칸을 모두 비운다."""
        if not self.paths:
            return

        title = "일괄 번역문 내용 지우기"
        selected_indices, selected_label = self.choose_batch_page_indices_for_context(title, "clear_translation")
        if selected_indices is None:
            self.log("↩️ 일괄 번역문 내용 지우기 취소")
            return

        self.commit_current_page_ui_to_data()

        def process_page(page_idx):
            curr = self.data.get(page_idx)
            if not curr or not curr.get('data'):
                return "skipped", "텍스트 데이터 없음"
            page_count = 0
            for item in curr.get('data', []):
                if str(item.get('translated_text', '') or ''):
                    item['translated_text'] = ''
                    try:
                        self.shrink_text_rect_to_content(item)
                    except Exception:
                        pass
                    page_count += 1
            if page_count <= 0:
                return "skipped", "지울 번역문 없음"
            return "done", f"{page_count}개 삭제"

        result = self.run_page_queue_batch(title, "clear_translation", selected_indices, selected_label, process_page, visual=False, cancellable=True)
        try:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        except Exception:
            pass



    def clear_masks_for_removed_items(self, curr, removed_items):
        if not curr or not removed_items:
            return
        mask_keys = ['mask_merge', 'mask_inpaint', 'mask_merge_off', 'mask_inpaint_off']
        for item in removed_items:
            try:
                x, y, w, h = [int(v) for v in item.get('rect', [0, 0, 0, 0])]
            except Exception:
                continue
            for key in mask_keys:
                m = curr.get(key)
                if not isinstance(m, np.ndarray):
                    continue
                yy1 = max(0, y)
                yy2 = min(m.shape[0], y + h)
                xx1 = max(0, x)
                xx2 = min(m.shape[1], x + w)
                if yy2 > yy1 and xx2 > xx1:
                    m[yy1:yy2, xx1:xx2] = 0

    def clean_text_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr or 'data' not in curr:
            return 0
        old_items = list(curr.get('data', []))
        removed = [x for x in old_items if not x.get('use_inpaint', True)]
        kept = [x for x in old_items if x.get('use_inpaint', True)]
        if not removed:
            return 0

        self.clear_masks_for_removed_items(curr, removed)
        for n, item in enumerate(kept, 1):
            item['id'] = n
        curr['data'] = kept
        return len(removed)

    def clean_text_current(self):
        if not self.paths or self.idx not in self.data:
            return
        self.commit_current_page_ui_to_data()
        removed_count = sum(1 for x in self.data[self.idx].get('data', []) if not x.get('use_inpaint', True))
        if removed_count <= 0:
            self.log("🧹 There are no unchecked items to delete." if self.ui_language == LANG_EN else "🧹 삭제할 체크 해제 항목이 없습니다.")
            return
        if self.ui_language == LANG_EN:
            msg = f"Delete {removed_count} unchecked text item(s) and reorder IDs?\nThe masks for those text areas will also be cleared."
        else:
            msg = f"체크 해제된 텍스트 {removed_count}개를 삭제하고 번호를 재정렬할까요?\n해당 텍스트 영역의 마스크도 함께 지워집니다."
        ans = QMessageBox.question(
            self,
            self.tr_ui("텍스트 정리"),
            msg,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        undo_rec = self.make_project_undo_record("텍스트 정리")
        removed = self.clean_text_for_page(self.idx)
        if removed:
            self.undo_push_project(undo_rec)
        self.ref_tab()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log((f"🧹 Clean text complete: {removed} items deleted / IDs reordered" if self.ui_language == LANG_EN else f"🧹 텍스트 정리 완료: {removed}개 삭제 / 번호 재정렬"))
        self.auto_save_project()

    def clean_text_batch(self):
        if not self.paths:
            return
        title = "일괄 텍스트 정리"
        selected_indices, selected_label = self.choose_batch_page_indices_for_context(title, "clean_text")
        if selected_indices is None:
            self.log("↩️ 일괄 텍스트 정리 취소")
            return
        self.commit_current_page_ui_to_data()
        total_candidates = 0
        for i in selected_indices:
            curr = self.data.get(i)
            if curr:
                total_candidates += sum(1 for x in curr.get('data', []) if not x.get('use_inpaint', True))
        if total_candidates <= 0:
            self.log("🧹 There are no unchecked items to clean in selected pages." if self.ui_language == LANG_EN else "🧹 선택한 페이지에 일괄 정리할 체크 해제 항목이 없습니다.")
            return
        if self.ui_language == LANG_EN:
            msg = f"Delete {total_candidates} unchecked text item(s) in selected pages and reorder IDs?\nThe masks for those text areas will also be cleared."
        else:
            msg = f"선택한 페이지에서 체크 해제된 텍스트 {total_candidates}개를 삭제하고 번호를 재정렬할까요?\n해당 텍스트 영역의 마스크도 함께 지워집니다."
        ans = QMessageBox.question(self, self.tr_ui(title), msg)
        if ans != QMessageBox.StandardButton.Yes:
            return

        def process_page(i):
            removed = self.clean_text_for_page(i)
            if removed <= 0:
                return "skipped", "삭제할 체크 해제 항목 없음"
            return "done", f"{removed}개 삭제"

        result = self.run_page_queue_batch(title, "clean_text", selected_indices, selected_label, process_page, visual=False, cancellable=True)
        try:
            self.ref_tab()
            self.mode_chg(self.cb_mode.currentIndex())
        except Exception:
            pass



    def bg_clean_to_np_image(self, bg):
        """bg_clean 값을 화면/마스크 작업용 OpenCV 이미지(BGR np.ndarray)로 변환한다."""
        if bg is None:
            return None

        try:
            if isinstance(bg, np.ndarray):
                return bg.copy()

            if isinstance(bg, (bytes, bytearray)):
                arr = np.frombuffer(bg, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return img.copy() if img is not None else None

            if isinstance(bg, str) and os.path.exists(bg):
                arr = np.fromfile(bg, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return img.copy() if img is not None else None
        except Exception:
            return None

        return None

    def get_real_original_image(self, page_idx):
        """프로젝트 images 폴더에 있는 실제 원본 파일을 다시 읽는다."""
        if page_idx < 0 or page_idx >= len(self.paths):
            return None
        try:
            return cv2.imdecode(np.fromfile(self.paths[page_idx], np.uint8), 1)
        except Exception:
            return None

    def normalize_image_to_original_size(self, page_idx, img):
        """
        인페인팅 결과 이미지를 프로젝트 원본 해상도에 맞춘다.

        일부 인페인팅 API는 결과 해상도를 바꿔서 반환할 수 있다.
        이 상태로 다시 인페인팅하면 기존 마스크/텍스트 좌표와 크기가 어긋날 수 있으므로
        툴 내부 기준 이미지는 항상 원본 해상도에 맞춘다.
        """
        if img is None:
            return None

        ref = self.get_real_original_image(page_idx)
        if ref is None:
            return img

        rh, rw = ref.shape[:2]
        h, w = img.shape[:2]
        if (h, w) == (rh, rw):
            return img

        try:
            resized = cv2.resize(img, (rw, rh), interpolation=cv2.INTER_CUBIC)
            self.log(f"↔️ 인페인팅 결과 해상도 보정: {w}x{h} → {rw}x{rh}")
            return resized
        except Exception:
            return img

    def encode_np_image_to_png_bytes(self, img):
        if img is None:
            return None
        try:
            ok, buf = cv2.imencode(".png", img)
            if ok:
                return buf.tobytes()
        except Exception:
            pass
        return None

    def set_working_source_image(self, curr, img, page_idx=None):
        """인페인팅/최종 브러시/클린본 반영 후 '원본 탭 기준 이미지'로 쓸 작업중 소스를 저장한다."""
        if curr is None or img is None:
            return
        encoded = self.encode_np_image_to_png_bytes(img)
        curr['working_source'] = encoded if encoded is not None else img
        curr['use_inpainted_as_source'] = True
        curr['ori'] = img.copy() if isinstance(img, np.ndarray) else img
        try:
            if page_idx is None:
                page_idx = self.idx if hasattr(self, 'idx') else None
            if page_idx is not None:
                self.touch_page_image_cache(int(page_idx))
                self.trim_page_image_cache(keep_indices=[int(page_idx)])
        except Exception:
            pass

    def write_np_image_as_inpaint_source(self, page_idx, img):
        """현재 기준 이미지를 인페인팅 입력 파일로 저장한다. Windows 한글 경로 안전 처리."""
        if img is None:
            return None

        clean_dir = self.ensure_subdir("clean")
        out_path = os.path.join(clean_dir, f"inpaint_source_{page_idx + 1:04d}.png")

        try:
            ok, buf = cv2.imencode(".png", img)
            if not ok:
                self.log("⚠️ 인페인팅 기준 이미지 인코딩 실패")
                return None

            # cv2.imwrite는 Windows 한글 경로에서 실패할 수 있어 np.tofile로 저장한다.
            buf.tofile(out_path)

            if not os.path.exists(out_path) or os.path.getsize(out_path) <= 0:
                self.log("⚠️ 인페인팅 기준 이미지 파일 저장 실패")
                return None

            return out_path
        except Exception as e:
            self.log(f"⚠️ 인페인팅 기준 이미지 저장 오류: {e}")
            return None

    def normalize_inpaint_mask_to_input_image(self, input_path, mask):
        """인페인팅 입력 이미지와 마스크 크기가 다르면 마스크를 입력 이미지 크기에 맞춘다."""
        if mask is None:
            return None

        try:
            img = cv2.imdecode(np.fromfile(input_path, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return mask

            ih, iw = img.shape[:2]
            mh, mw = mask.shape[:2]
            if (mh, mw) == (ih, iw):
                return mask

            fixed = cv2.resize(mask, (iw, ih), interpolation=cv2.INTER_NEAREST)
            self.log((f"↔️ Inpaint mask size normalized: {mw}x{mh} → {iw}x{ih}" if self.ui_language == LANG_EN else f"↔️ 인페인팅 마스크 해상도 보정: {mw}x{mh} → {iw}x{ih}"))
            return fixed
        except Exception:
            return mask

    def get_source_display_image(self, page_idx):
        """
        원본/분석/마스크 탭에서 실제로 보여줄 기준 이미지.

        use_inpainted_as_source=True면 프로젝트 내부의 작업중 원본(working_source)을 우선 사용한다.
        working_source는 "인페인팅을 원본으로"와 "최종 브러시를 원본으로"가 공유하는 최신 기준 파일이다.
        """
        curr = self.data.get(page_idx, {})

        if curr.get('use_inpainted_as_source'):
            if curr.get('working_source') is None and (curr.get('working_source_path') or curr.get('clean_path')):
                try:
                    self.ensure_page_runtime_loaded(page_idx, include_ori=False, include_heavy=True, include_masks=False)
                except Exception:
                    pass
            img = self.bg_clean_to_np_image(curr.get('working_source'))
            if img is not None:
                img = self.normalize_image_to_original_size(page_idx, img)
                curr['ori'] = img.copy()
                try:
                    self.touch_page_image_cache(page_idx)
                    self.trim_page_image_cache(keep_indices=[page_idx])
                except Exception:
                    pass
                return curr['ori']

            img = self.bg_clean_to_np_image(curr.get('bg_clean'))
            if img is not None:
                img = self.normalize_image_to_original_size(page_idx, img)
                self.set_working_source_image(curr, img, page_idx=page_idx)
                try:
                    self.touch_page_image_cache(page_idx)
                    self.trim_page_image_cache(keep_indices=[page_idx])
                except Exception:
                    pass
                return curr['ori']

        img = curr.get('ori')
        if img is None:
            img = self.get_real_original_image(page_idx)
            if img is not None:
                curr['ori'] = img
                try:
                    self.touch_page_image_cache(page_idx)
                    self.trim_page_image_cache(keep_indices=[page_idx])
                except Exception:
                    pass
        return img

    def get_inpainting_input_path(self, page_idx):
        curr = self.data.get(page_idx, {})
        if curr.get('use_inpainted_as_source'):
            # 덧칠 모드에서는 현재 원본 탭에 표시되는 이미지(curr['ori'])를 그대로 입력으로 쓴다.
            # bg_clean을 다시 직접 쓰면, 최신 결과와 표시 기준이 엇갈릴 수 있다.
            img = self.get_source_display_image(page_idx)
            src = self.write_np_image_as_inpaint_source(page_idx, img)
            if src:
                return src
            self.log("⚠️ Failed to save the inpaint source image. Using the real original image instead." if self.ui_language == LANG_EN else "⚠️ 인페인팅 기준 이미지 저장 실패. 실제 원본 이미지로 진행합니다.")
        return self.paths[page_idx]

    def use_inpainted_as_source(self):
        """구버전 메뉴/단축키 호환: 인페인팅 결과뿐 아니라 현재 최종결과 배경을 작업용 원본으로 쓴다."""
        if hasattr(self, "use_final_background_as_source"):
            return self.use_final_background_as_source()

        curr = self.data.get(self.idx)
        if not curr:
            return
        if not curr.get('bg_clean'):
            QMessageBox.warning(self, self.tr_ui("인페인팅 결과 없음"), self.tr_ui("먼저 인페인팅된 이미지가 있어야 원본으로 가져올 수 있습니다."))
            return

        img = self.bg_clean_to_np_image(curr.get('bg_clean'))
        if img is None:
            QMessageBox.warning(self, self.tr_ui("이미지 변환 실패"), self.tr_ui("인페인팅 결과 이미지를 원본 탭에 표시할 수 없습니다."))
            return

        # 실제 원본 파일은 건드리지 않고, 프로젝트 내부 작업중 원본(working_source)에 저장한다.
        img = self.normalize_image_to_original_size(self.idx, img)
        self.set_working_source_image(curr, img, page_idx=self.idx)
        self.log("🔁 Inpaint result has been imported as the working source image for the Original tab." if self.ui_language == LANG_EN else "🔁 인페인팅 결과를 원본 탭의 작업중 기준 이미지로 가져왔습니다.")
        self.auto_save_project()
        self.mode_chg(self.cb_mode.currentIndex())

    def restore_original_source_to_page(self, page_idx):
        """한 페이지의 작업용 원본을 실제 원본 이미지로 되돌린다."""
        curr = self.data.get(page_idx)
        if not curr:
            return "skipped", "페이지 데이터 없음"
        if not curr.get('use_inpainted_as_source') and curr.get('working_source') is None:
            return "skipped", "이미 실제 원본 상태"
        curr['use_inpainted_as_source'] = False
        curr['working_source'] = None
        real_ori = self.get_real_original_image(page_idx)
        if real_ori is not None:
            curr['ori'] = real_ori
            try:
                self.touch_page_image_cache(page_idx)
                self.trim_page_image_cache(keep_indices=[page_idx])
            except Exception:
                pass
        try:
            self.mark_page_data_dirty_explicit(page_idx, "restore_original_source")
        except Exception:
            pass
        return "done", "실제 원본으로 복구"

    def restore_original_source(self):
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(self, self.tr_ui("일괄 작업 중"), self.tr_msg("이미 일괄 작업이 진행 중입니다.\n현재 작업이 끝난 뒤 다시 실행해 주세요."))
            return
        if not getattr(self, "paths", None):
            return

        title = "원본으로 돌아가기"
        selected_indices, selected_label = self.choose_batch_page_indices_for_context(title, "restore_original_source")
        if selected_indices is None:
            self.log("↩️ " + self.tr_ui("원본으로 돌아가기") + " " + self.tr_ui("취소"))
            return

        try:
            self.commit_current_page_ui_to_data()
        except Exception:
            pass

        current_idx = int(getattr(self, "idx", 0) or 0)
        try:
            current_mode = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else -1
        except Exception:
            current_mode = -1
        single_current = len(selected_indices or []) == 1 and int(selected_indices[0]) == current_idx

        # 이미지/원본 기준 대량 변경은 Undo 스냅샷과 작업 캐시 저장을 끊어 메모리 폭증을 막는다.
        undo_rec = self.make_batch_page_data_undo_record(title, selected_indices) if single_current else None
        changed = False

        def process_page(page_idx):
            nonlocal changed
            status, message = self.restore_original_source_to_page(page_idx)
            if str(status).lower() == "done":
                changed = True
            return status, message

        result = self.run_page_queue_batch(
            title,
            "restore_original_source",
            selected_indices,
            selected_label,
            process_page,
            visual=False,
            cancellable=True,
            restore_page=False,
            save_work_cache=bool(single_current),
        )

        if changed:
            if single_current and undo_rec is not None:
                try:
                    self.undo_push_project(undo_rec)
                except Exception:
                    pass
            else:
                try:
                    self.undo_apply_boundary("restore_original_source", title, selected_page_indices=selected_indices)
                except Exception:
                    pass
            try:
                self.has_unsaved_changes = True
                self.update_window_title()
            except Exception:
                pass
            try:
                __import__("gc").collect()
            except Exception:
                pass
        # 다중/전체 이미지 작업은 여기서 일반 작업 캐시 저장을 예약하지 않는다.
        # 정식 반영은 사용자가 [프로젝트 저장]을 눌렀을 때 처리한다.
        try:
            if single_current:
                self.mode_chg(current_mode if current_mode >= 0 else self.cb_mode.currentIndex())
            elif current_idx in set(int(i) for i in (selected_indices or [])):
                self.log("ℹ️ 원본으로 돌아가기 완료: 대량 이미지 작업 후 화면 전체 갱신은 생략했습니다. 탭/페이지를 다시 열면 반영됩니다.")
        except Exception:
            pass
        self.log("↩️ " + ("The Original tab base image has been restored to the real original image." if self.ui_language == LANG_EN else "원본 탭의 기준 이미지를 실제 원본으로 되돌렸습니다."))

    def restart_engine(self, show_error=True):
        apply_settings_to_config(self.api_settings)

        try:
            self.engine = MangaProcessEngine()
            if show_error and hasattr(self, "log_w"):
                self.log("🔧 Engine restarted" if self.ui_language == LANG_EN else "🔧 엔진 재시동 완료")
            return True
        except Exception as e:
            self.engine = None
            print(f"Engine Init Error: {e}")
            if show_error:
                QMessageBox.warning(
                    self,
                    self.tr_ui("엔진 초기화 실패"),
                    self.tr_msg("API 설정이 비어 있거나 잘못되어 엔진을 시작하지 못했습니다.\n"
                    "[옵션 > API 관리]에서 키를 저장한 뒤 다시 시도해주세요.\n\n") + f"{self.tr_ui('오류')}: {e}"
                )
            return False

    def ensure_engine_ready(self):
        if self.engine is not None:
            return True

        QMessageBox.warning(
            self,
            self.tr_ui("API 설정 필요"),
            self.tr_msg("엔진이 아직 준비되지 않았습니다.\n[옵션 > API 관리]에서 키를 저장해주세요.")
        )
        return False

    def bring_to_front(self):
        """두 번째 실행 요청이 들어왔을 때 현재 창을 앞으로 가져온다."""
        self.force_app_focus(reason="single-instance")

    def force_app_focus(self, reason="external-open", log_once=False):
        """
        .ysbt 더블클릭 / 드래그 앤 드롭 / 외부 열기 후 창 포커스를 YSB로 되돌린다.
        Windows는 다른 프로세스가 만든 포커스 변경을 막는 경우가 있어 Qt 포커스와 Win32 포커스를 여러 번 같이 시도한다.
        """
        delays = (0, 80, 220, 450)
        for delay in delays:
            QTimer.singleShot(delay, lambda r=reason: self._force_app_focus_once(r))
        if log_once:
            try:
                if self.ui_language == LANG_EN:
                    self.log(f"🪟 Focus requested: {reason}")
                else:
                    self.log(f"🪟 창 포커스 요청: {reason}")
            except Exception:
                pass

    def _force_app_focus_once(self, reason="external-open"):
        try:
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()

            try:
                self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
            except Exception:
                pass

            # Qt 기본 포커스 요청
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

            # Windows에서는 파일 더블클릭/두 번째 프로세스 전달 뒤 포커스가 탐색기나 cmd에 남는 경우가 있다.
            if sys.platform.startswith("win"):
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    hwnd = int(self.winId())
                    SW_RESTORE = 9
                    HWND_TOPMOST = -1
                    HWND_NOTOPMOST = -2
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    SWP_SHOWWINDOW = 0x0040
                    ASFW_ANY = -1
                    try:
                        user32.AllowSetForegroundWindow(ASFW_ANY)
                    except Exception:
                        pass
                    try:
                        user32.ShowWindow(hwnd, SW_RESTORE)
                    except Exception:
                        pass
                    # 포커스 제한이 걸린 환경에서도 앞으로 나오도록 topmost를 아주 짧게 토글한다.
                    try:
                        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                    except Exception:
                        pass
                    try:
                        user32.BringWindowToTop(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.SetFocus(hwnd)
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    def has_open_project(self):
        return bool(self.project_dir or self.paths)


    def ensure_task_progress_overlay(self):
        try:
            overlay = getattr(self, "_task_progress_overlay", None)
            if overlay is None:
                overlay = CenterTaskProgressOverlay(self)
                overlay.cancelRequested.connect(self.request_current_long_task_cancel)
                self._task_progress_overlay = overlay
            return overlay
        except Exception:
            return None

    def ensure_task_alert_overlay(self):
        try:
            overlay = getattr(self, "_task_alert_overlay", None)
            if overlay is None:
                overlay = CenterTaskAlertOverlay(self)
                self._task_alert_overlay = overlay
            return overlay
        except Exception:
            return None

    def pause_task_progress_overlay_for_alert(self, detail=None):
        try:
            overlay = getattr(self, "_task_progress_overlay", None)
            if overlay is not None and overlay.isVisible():
                overlay.set_paused(True, detail=detail)
        except Exception:
            pass

    def show_task_alert_overlay(self, title="작업 알림", detail=""):
        try:
            self.pause_task_progress_overlay_for_alert(detail=detail)
            overlay = self.ensure_task_alert_overlay()
            if overlay is not None:
                overlay.show_alert(title, detail)
        except Exception:
            pass

    def _is_long_task_alert_message(self, message):
        text = str(message or "")
        if not text.strip():
            return False
        markers = ("❌", "⚠️", "오류", "에러", "실패", "Error", "ERROR", "Exception", "Traceback")
        return any(m in text for m in markers)

    def handle_long_task_message(self, message, *, current=None, total=None):
        text = str(message or "")
        try:
            self.log(text)
        except Exception:
            pass
        # 일괄 작업 중 worker 로그/진행 메시지가 들어와도 진행창 자체를 새 문구 크기로
        # 갈아엎지 않는다. 선택 페이지 큐 형식의 고정 레이아웃을 유지하고, 상세 줄만 갱신한다.
        try:
            if bool(getattr(self, "is_batch_running", False)) and hasattr(self, "batch_progress_detail"):
                cur = int(current if current is not None else (getattr(self, "_batch_progress_done", 0) or 0))
                tot = int(total if total is not None else (getattr(self, "_batch_total", 0) or 0))
                page_idx = getattr(self, "_batch_current_page_idx", None)
                if tot > 0:
                    detail = self.batch_progress_detail(getattr(self, "current_batch_mode", None), cur, tot, page_idx, text)
                    self.update_task_progress_overlay(current=cur, total=tot, detail=detail)
                    if self._is_long_task_alert_message(text):
                        self.show_task_alert_overlay("작업 알림", text)
                    return
        except Exception:
            pass
        if self._is_long_task_alert_message(text):
            self.update_task_progress_overlay(current=current, total=total, detail=text)
            self.show_task_alert_overlay("작업 알림", text)
            return
        self.update_task_progress_overlay(current=current, total=total, detail=text)

    def prepare_task_progress_overlay(self, title, detail="", total=0, cancellable=True):
        """Prepare the center progress overlay without showing it yet.

        The overlay should not appear while pre-flight validation dialogs are still
        possible.  It is displayed lazily on the first worker progress/log signal,
        which means a missing key / confirmation / early alert does not leave a
        fake progress panel on screen.
        """
        try:
            self._pending_task_progress_overlay = {
                "title": str(title or "작업 중"),
                "detail": str(detail or ""),
                "total": int(total or 0) if str(total or "").strip() else 0,
                "cancellable": bool(cancellable),
            }
            self.ensure_task_progress_overlay()
        except Exception:
            self._pending_task_progress_overlay = None

    def show_task_progress_overlay(self, title, detail="", total=0, cancellable=True):
        try:
            self._pending_task_progress_overlay = None
            overlay = self.ensure_task_progress_overlay()
            if overlay is None:
                return
            # 진행 중인 창이 이미 있으면 새로 show/reset하지 않고 같은 창에서 내용만 바꾼다.
            if overlay.isVisible():
                overlay.update_task(current=None, total=total, detail=detail)
                try:
                    overlay.title_label.setText(str(title or "작업 중"))
                    overlay.cancel_btn.setVisible(bool(cancellable))
                    overlay.note_label.setVisible(bool(cancellable))
                except Exception:
                    pass
            else:
                overlay.show_task(title, detail, total=total, cancellable=cancellable)
        except Exception:
            pass

    def update_task_progress_overlay(self, current=None, total=None, detail=None):
        try:
            overlay = getattr(self, "_task_progress_overlay", None)
            pending = getattr(self, "_pending_task_progress_overlay", None)
            if (overlay is None or not overlay.isVisible()) and pending:
                overlay = self.ensure_task_progress_overlay()
                if overlay is not None:
                    show_detail = str(detail if detail is not None else pending.get("detail", ""))
                    show_total = total if total is not None else pending.get("total", 0)
                    overlay.show_task(
                        pending.get("title", "작업 중"),
                        show_detail,
                        total=show_total,
                        cancellable=pending.get("cancellable", True),
                    )
                    self._pending_task_progress_overlay = None
            if overlay is not None and overlay.isVisible():
                overlay.update_task(current=current, total=total, detail=detail)
        except Exception:
            pass

    def hide_task_progress_overlay(self):
        try:
            self._pending_task_progress_overlay = None
            overlay = getattr(self, "_task_progress_overlay", None)
            if overlay is not None:
                overlay.hide()
            alert = getattr(self, "_task_alert_overlay", None)
            if alert is not None:
                alert.hide()
        except Exception:
            pass

    def request_current_long_task_cancel(self):
        """Cancel button handler for the center progress overlay.

        Long OCR/API/local-model calls cannot always be interrupted in the middle of
        the current request.  Workers stop before the next page/chunk/step.
        """
        self._long_task_cancel_requested = True
        worker = None
        for name in ("translation_worker", "bw", "iw", "w"):
            try:
                candidate = getattr(self, name, None)
            except Exception:
                candidate = None
            if candidate is not None and hasattr(candidate, "stop"):
                worker = candidate
                try:
                    candidate.stop()
                except Exception:
                    pass
        try:
            if getattr(self, "_active_long_task_kind", "") == "save":
                detail = "취소 요청됨. 현재 저장 항목이 끝난 뒤 중단됩니다."
                log_text = "⏹️ 저장 취소 요청됨: 현재 저장 항목이 끝난 뒤 중단됩니다."
            elif getattr(self, "_active_long_task_kind", "") == "open_extract":
                detail = "취소 요청됨. 현재 압축 해제 항목이 끝난 뒤 중단됩니다."
                log_text = "⏹️ YSBT 열기 취소 요청됨: 현재 압축 해제 항목이 끝난 뒤 중단됩니다."
            else:
                detail = "취소 요청됨. 현재 페이지 작업이 끝난 뒤 중단됩니다."
                log_text = "⏹️ 취소 요청됨. 현재 페이지 작업이 끝난 뒤 중단됩니다."
        except Exception:
            detail = "취소 요청됨. 현재 페이지 작업이 끝난 뒤 중단됩니다."
            log_text = "⏹️ 취소 요청됨: 현재 페이지 작업이 끝난 뒤 중단됩니다."
        self.update_task_progress_overlay(detail=detail)
        try:
            self.log(log_text)
        except Exception:
            pass

    def busy_reason_text(self, reason=""):
        reason = str(reason or "").strip()
        if reason:
            return reason
        return "Working..." if getattr(self, "ui_language", LANG_KO) == LANG_EN else "작업 중"

    def begin_busy_state(self, reason="작업 중"):
        """긴 내부 작업 중에는 Wait Cursor와 UI 잠금을 걸어 중복 클릭을 막는다."""
        try:
            if not hasattr(self, "_busy_counter"):
                self._busy_counter = 0
            if not hasattr(self, "_busy_reason_stack"):
                self._busy_reason_stack = []
            self._busy_counter += 1
            self._busy_reason_stack.append(self.busy_reason_text(reason))
            if self._busy_counter > 1:
                QApplication.processEvents()
                return

            try:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            except Exception:
                pass

            widgets = []
            try:
                cw = self.centralWidget()
                if cw is not None:
                    widgets.append(cw)
            except Exception:
                pass
            try:
                mb = self.menuBar()
                if mb is not None:
                    widgets.append(mb)
            except Exception:
                pass
            try:
                for tb in self.findChildren(QToolBar):
                    widgets.append(tb)
            except Exception:
                pass

            self._busy_widgets = []
            for w in widgets:
                try:
                    self._busy_widgets.append((w, bool(w.isEnabled())))
                    w.setEnabled(False)
                except Exception:
                    pass

            try:
                self.setCursor(Qt.CursorShape.WaitCursor)
            except Exception:
                pass

            text = self._busy_reason_stack[-1] if self._busy_reason_stack else self.busy_reason_text(reason)
            self.log(
                f"⏳ Busy: {text} / UI locked"
                if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                f"⏳ 작업 중: {text} / UI 잠금"
            )
            QApplication.processEvents()
        except Exception:
            pass

    def end_busy_state(self, reason=""):
        """begin_busy_state()로 잠근 UI와 커서를 복구한다."""
        try:
            if not hasattr(self, "_busy_counter"):
                self._busy_counter = 0
            if self._busy_counter <= 0:
                self._busy_counter = 0
                return

            self._busy_counter -= 1
            try:
                if getattr(self, "_busy_reason_stack", None):
                    self._busy_reason_stack.pop()
            except Exception:
                pass

            if self._busy_counter > 0:
                QApplication.processEvents()
                return

            for w, enabled in reversed(getattr(self, "_busy_widgets", []) or []):
                try:
                    w.setEnabled(enabled)
                except Exception:
                    pass
            self._busy_widgets = []

            try:
                self.unsetCursor()
            except Exception:
                pass
            try:
                while QApplication.overrideCursor() is not None:
                    QApplication.restoreOverrideCursor()
            except Exception:
                pass

            text = self.busy_reason_text(reason)
            self.hide_task_progress_overlay()
            self.log(
                f"✅ Busy finished: {text} / UI unlocked"
                if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                f"✅ 작업 완료: {text} / UI 잠금 해제"
            )
            QApplication.processEvents()
        except Exception:
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass

    def guard_project_action(self, action_name="프로젝트 작업"):
        """일괄 작업 중에는 프로젝트 열기/저장/위치 변경 같은 구조 변경 동작을 막는다."""
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(
                self,
                self.tr_ui("일괄 작업 중"),
                self.tr_msg(f"현재 일괄 작업이 진행 중입니다.\n{action_name}은(는) 일괄 작업이 끝난 뒤 다시 시도해 주세요."),
            )
            self.log(f"⛔ 일괄 작업 중 차단됨: {action_name}")
            return False
        return True

    def set_project_action_interlock(self, locked):
        """일괄 작업 중 사용하면 위험한 프로젝트 관련 메뉴를 비활성화한다."""
        for key in (
            "project_new",
            "project_open",
            "project_open_json",
            "project_save",
            "project_save_as",
            "option_workspace_location",
            "option_workspace_reset_default",
        ):
            action = self.actions.get(key) if hasattr(self, "actions") else None
            if action is not None:
                action.setEnabled(not locked)

    def close_current_project_state_for_switch(self):
        """새 프로젝트를 열기 전 현재 프로젝트의 임시 상태를 정리한다."""
        try:
            self.cleanup_work_cache()
        except Exception:
            pass
        try:
            self.delete_temp_project_if_needed()
        except Exception:
            pass
        self.has_unsaved_changes = False

    def confirm_close_current_project_for_open(self, source_text=""):
        """외부 .ysbt 열기 요청이 들어왔을 때 현재 프로젝트를 닫을지 확인한다."""
        if not self.has_open_project():
            return True
        title = self.tr_ui("프로젝트 열기")
        message = self.tr_msg(
            "현재 열려있는 프로젝트를 닫고 새 프로젝트를 열까요?\n\n"
            "[예] 기존 프로젝트를 닫고 새 프로젝트를 엽니다.\n"
            "[아니오] 열기를 취소합니다."
        )
        if source_text:
            message += f"\n\n{self.tr_ui('열려고 하는 파일:')}\n{source_text}"
        ans = styled_question(
            self,
            title,
            message,
            default_yes=False,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 외부 프로젝트 열기 취소")
            return False

        # 저장하지 않은 작업이 있으면 기존 저장 확인 루틴을 한 번 더 거친다.
        # 사용자가 저장/저장 안 함/취소 중 선택할 수 있게 해서 데이터 손실을 막는다.
        if self.has_unsaved_changes:
            return self.confirm_unsaved_before_switch()

        self.close_current_project_state_for_switch()
        return True

    def setup_external_open_queue_monitor(self):
        """YSB Launcher가 기록한 .ysbt 열기 요청 큐를 감시한다."""
        try:
            self.write_external_open_runtime_info()
        except Exception:
            pass

        self._external_open_queue_timer = QTimer(self)
        self._external_open_queue_timer.setInterval(350)
        self._external_open_queue_timer.timeout.connect(self.process_external_open_queue)
        self._external_open_queue_timer.start()

        self._external_runtime_timer = QTimer(self)
        self._external_runtime_timer.setInterval(5000)
        self._external_runtime_timer.timeout.connect(self.write_external_open_runtime_info)
        self._external_runtime_timer.start()

        QTimer.singleShot(700, self.process_external_open_queue)

    def write_external_open_runtime_info(self):
        """경량 런처가 메인 앱 실행 여부를 빠르게 판단할 수 있게 pid 정보를 남긴다."""
        try:
            path = ysb_main_runtime_info_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "pid": os.getpid(),
                "exe": str(Path(sys.executable).resolve()),
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "queue": str(ysb_open_queue_path()),
            }
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def cleanup_external_open_runtime_info(self):
        """정상 종료 시 런처용 pid 정보를 정리한다. 실패해도 종료는 막지 않는다."""
        try:
            path = ysb_main_runtime_info_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if int(data.get("pid") or -1) != os.getpid():
                        return
                except Exception:
                    pass
                path.unlink()
        except Exception:
            pass

    def is_fresh_external_open_payload(self, payload, max_age_sec=600):
        """오래 전에 남은 열기 큐가 재실행 때 이전 프로젝트를 다시 여는 일을 막는다."""
        try:
            t = payload.get("time_epoch")
            if t is None:
                return False
            age = time.time() - float(t)
            return 0 <= age <= float(max_age_sec)
        except Exception:
            return False

    def process_external_open_queue(self):
        """open_queue.jsonl에 쌓인 .ysbt 열기 요청을 기존 창에서 처리한다."""
        queue_path = ysb_open_queue_path()
        if not queue_path.exists():
            return
        try:
            processing_path = queue_path.with_suffix(f".processing.{os.getpid()}.{int(time.time() * 1000)}")
            try:
                queue_path.replace(processing_path)
            except FileNotFoundError:
                return
            except Exception:
                # 다른 프로세스가 쓰는 순간이면 다음 타이머에서 다시 처리한다.
                return

            try:
                raw = processing_path.read_text(encoding="utf-8", errors="replace")
            finally:
                try:
                    processing_path.unlink()
                except Exception:
                    pass

            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                if not self.is_fresh_external_open_payload(payload):
                    try:
                        self.log("🧹 오래된 외부 열기 큐 무시")
                    except Exception:
                        pass
                    continue
                command = str(payload.get("command") or "activate")
                if command == "activate":
                    self.handle_single_instance_payload({"command": "activate", "source": "launcher-queue"})
                    continue
                if command != "open":
                    continue
                path = str(payload.get("path") or "")
                if not path:
                    continue
                if not (path.lower().endswith(YSB_EXTENSION) or os.path.basename(path).lower() == PROJECT_FILENAME):
                    continue
                self.handle_single_instance_payload({"command": "open", "path": path, "source": "launcher-queue"})
        except Exception as e:
            try:
                self.log(f"⚠️ 외부 열기 큐 처리 실패: {e}")
            except Exception:
                pass

    def handle_single_instance_payload(self, payload):
        """두 번째 실행 프로세스에서 넘어온 메시지를 현재 창에서 처리한다."""
        self.force_app_focus(reason="external request")
        payload = payload or {}
        command = str(payload.get("command", "activate") or "activate")
        if command != "open":
            return
        path = str(payload.get("path", "") or "")
        if not path:
            return
        if not self.guard_project_action("외부 YSBT 파일 열기"):
            return
        if not self.confirm_close_current_project_for_open(path):
            return
        self.open_project_path(path, external_request=True)
        self.force_app_focus(reason="external file open")

    def is_supported_image_path(self, path):
        try:
            return bool(path) and Path(str(path)).suffix.lower() in IMAGE_DROP_EXTS and os.path.isfile(str(path))
        except Exception:
            return False

    def normalize_image_drop_paths(self, paths):
        out = []
        seen = set()
        for path in paths or []:
            try:
                p = os.path.abspath(str(path))
            except Exception:
                continue
            if p.lower() in seen:
                continue
            if self.is_supported_image_path(p):
                out.append(p)
                seen.add(p.lower())
        return out

    def page_original_name(self, page_idx):
        try:
            curr = self.data.get(int(page_idx), {}) if isinstance(self.data, dict) else {}
            name = curr.get("original_name") if isinstance(curr, dict) else ""
            if name:
                return str(name)
            return os.path.basename(str(self.paths[int(page_idx)]))
        except Exception:
            return f"page{int(page_idx) + 1:03d}"

    def page_display_name(self, page_idx, mode=None, include_ext=False):
        mode = normalize_page_display_mode(mode or getattr(self, "page_tab_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        original = self.page_original_name(page_idx)
        stem = safe_page_file_stem(original, fallback=f"page{int(page_idx) + 1:03d}")
        ext = Path(str(original)).suffix if include_ext else ""
        if mode == PAGE_DISPLAY_MODE_ORIGINAL:
            return f"{stem}{ext}"
        if mode == PAGE_DISPLAY_MODE_PAGE_NUMBER:
            return f"page{int(page_idx) + 1:03d}{ext}"
        return f"{int(page_idx) + 1}p_{stem}{ext}"

    def output_display_stem(self, page_idx):
        return self.page_display_name(page_idx, mode=getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE), include_ext=False)

    def path_for_output_display(self, page_idx):
        """구버전 호환용 표시명 경로. 실제 출력은 output_display_stem을 별도로 넘긴다."""
        try:
            src = str(self.paths[int(page_idx)])
            ext = Path(src).suffix or ".png"
            return os.path.join(os.path.dirname(os.path.abspath(src)), self.output_display_stem(page_idx) + ext)
        except Exception:
            return os.path.join(self.get_output_root(), self.output_display_stem(page_idx) + ".png")

    def output_format_label_pairs(self):
        return [
            ("png", "PNG"),
            ("jpg", "JPG"),
            ("webp", "WebP"),
        ]

    def output_text_render_quality_label_pairs(self):
        return [
            ("normal", self.tr_ui("기본 렌더 (1x)")),
            ("2x", self.tr_ui("고품질 렌더 (2x)")),
            ("3x", self.tr_ui("최고품질 렌더 (3x)")),
            ("4x", self.tr_ui("실험적 렌더 (4x)")),
        ]

    def current_output_text_render_quality(self):
        return normalize_output_text_render_quality(getattr(self, "output_text_render_quality", DEFAULT_OUTPUT_TEXT_RENDER_QUALITY))

    def current_output_text_render_scale(self):
        return output_text_render_scale(self.current_output_text_render_quality())

    def current_output_image_format(self):
        return normalize_output_image_format(getattr(self, "output_image_format", DEFAULT_OUTPUT_IMAGE_FORMAT))

    def current_clean_image_format(self):
        return normalize_output_image_format(getattr(self, "clean_image_format", DEFAULT_OUTPUT_IMAGE_FORMAT))

    def current_output_image_quality(self):
        return normalize_output_image_quality(getattr(self, "output_image_quality", DEFAULT_OUTPUT_IMAGE_QUALITY))

    def current_clean_image_quality(self):
        return normalize_output_image_quality(getattr(self, "clean_image_quality", DEFAULT_OUTPUT_IMAGE_QUALITY))

    def output_result_file_path(self, output_stem):
        ext = output_image_extension(self.current_output_image_format())
        return os.path.join(self.get_output_root(), "result", f"Result_{safe_page_file_stem(output_stem, 'output')}{ext}")

    def output_clean_file_path(self, clean_stem):
        ext = output_image_extension(self.current_clean_image_format())
        return os.path.join(self.get_output_root(), "clean", f"{safe_page_file_stem(clean_stem, 'clean')}{ext}")

    def remove_output_format_variants(self, directory, stem, prefix=""):
        """출력 형식이 바뀌었을 때 같은 stem의 기존 PNG/JPG/WebP를 중복으로 남기지 않는다."""
        try:
            folder = Path(str(directory))
            if not folder.exists():
                return
            safe_stem = safe_page_file_stem(stem, "output")
            current_exts = {".png", ".jpg", ".jpeg", ".webp"}
            for ext in current_exts:
                for name in (f"{prefix}{safe_stem}{ext}",):
                    p = folder / name
                    try:
                        if p.exists() and p.is_file():
                            p.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    def ensure_page_source_path(self, page_idx):
        """원본 파일명 변경/저장 후 self.paths가 낡았을 때 images/original_name 기준으로 복구한다."""
        try:
            page_idx = int(page_idx)
        except Exception:
            return False
        if page_idx < 0 or page_idx >= len(getattr(self, "paths", []) or []):
            return False

        try:
            current = Path(str(self.paths[page_idx]))
            if current.exists():
                return True
        except Exception:
            current = None

        curr = self.data.get(page_idx, {}) if isinstance(self.data, dict) else {}
        original = curr.get("original_name") if isinstance(curr, dict) else ""
        images_dirs = []
        try:
            if self.project_dir:
                images_dirs.append(Path(str(self.project_dir)) / "images")
        except Exception:
            pass
        try:
            active = self.active_page_storage_dir()
            if active:
                images_dirs.append(Path(str(active)) / "images")
        except Exception:
            pass

        candidates = []
        if original:
            for d in images_dirs:
                candidates.append(d / str(original))

        original_stem = Path(str(original)).stem.lower() if original else ""
        for d in images_dirs:
            try:
                if not d.exists():
                    continue
                if original_stem:
                    for p in d.iterdir():
                        if p.is_file() and p.stem.lower() == original_stem:
                            candidates.append(p)
                if current is not None:
                    old_stem = current.stem.lower()
                    for p in d.iterdir():
                        if p.is_file() and p.stem.lower() == old_stem:
                            candidates.append(p)
            except Exception:
                pass

        for cand in candidates:
            try:
                if cand.exists() and cand.is_file():
                    self.paths[page_idx] = str(cand)
                    if isinstance(curr, dict):
                        curr["original_name"] = cand.name
                        self.data[page_idx] = curr
                    try:
                        self.save_project_store(self.project_store)
                    except Exception:
                        pass
                    return True
            except Exception:
                pass

        return False

    def collect_used_source_stems_for_rename(self, except_index=None):
        used = set()
        try:
            except_index = None if except_index is None else int(except_index)
        except Exception:
            except_index = None
        for i, p in enumerate(getattr(self, "paths", []) or []):
            if except_index is not None and i == except_index:
                continue
            try:
                used.add(Path(str(p)).stem.lower())
            except Exception:
                pass
            try:
                curr = self.data.get(i, {}) if isinstance(self.data, dict) else {}
                original = curr.get("original_name") if isinstance(curr, dict) else ""
                if original:
                    used.add(Path(str(original)).stem.lower())
            except Exception:
                pass
        return used

    def unique_source_rename_target(self, current_path, requested_stem, page_index):
        current = Path(str(current_path))
        folder = current.parent
        ext = current.suffix or ".png"
        base = safe_page_file_stem(requested_stem, fallback=current.stem or "image")
        used = self.collect_used_source_stems_for_rename(except_index=page_index)

        def candidate(n=None):
            stem = base if n is None else f"{base}({n})"
            return stem, folder / f"{stem}{ext}"

        stem, path = candidate(None)
        if stem.lower() not in used and (not path.exists() or str(path.resolve()).lower() == str(current.resolve()).lower()):
            return str(path), False

        for n in range(1, 10000):
            stem, path = candidate(n)
            if stem.lower() not in used and not path.exists():
                return str(path), True

        stem = f"{base}({uuid.uuid4().hex[:8]})"
        return str(folder / f"{stem}{ext}"), True

    def rename_page_source_from_tab(self, page_idx):
        return self.rename_page_source_file(page_idx)

    def rename_current_page_source_file(self):
        return self.rename_page_source_file(getattr(self, "idx", 0))

    def rename_page_source_file(self, page_idx):
        """프로젝트 내부 images 원본 파일명을 변경하고 관련 기준 이름을 갱신한다."""
        if not getattr(self, "paths", None):
            return False
        try:
            page_idx = int(page_idx)
        except Exception:
            page_idx = int(getattr(self, "idx", 0) or 0)
        if page_idx < 0 or page_idx >= len(self.paths):
            return False
        if not self.guard_project_action("페이지 탭 파일명 변경"):
            return False

        current_path = Path(str(self.paths[page_idx]))
        if not current_path.exists():
            QMessageBox.warning(
                self,
                self.tr_ui("파일 없음"),
                f"{self.tr_ui('현재 페이지의 원본 이미지 파일을 찾을 수 없습니다.')}\n{current_path}",
            )
            return False

        current_stem = current_path.stem
        while True:
            new_stem, ok = QInputDialog.getText(
                self,
                self.tr_ui("페이지 탭 파일명 변경"),
                self.tr_msg("새 원본 파일명을 입력하세요.\n확장자는 현재 파일의 확장자를 유지합니다."),
                QLineEdit.EchoMode.Normal,
                current_stem,
            )
            if not ok:
                return False
            new_stem = safe_page_file_stem(Path(str(new_stem or "")).stem, fallback=current_stem)
            if not new_stem:
                continue
            if new_stem == current_stem:
                return False

            target_path, has_conflict = self.unique_source_rename_target(current_path, new_stem, page_idx)
            if has_conflict:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle(self.tr_ui("파일명 중복"))
                msg.setText(self.tr_ui("같은 이름의 원본 이미지 파일명이 이미 있습니다."))
                msg.setInformativeText(
                    f"{self.tr_ui('입력한 이름')} : {new_stem}{current_path.suffix}\n"
                    f"{self.tr_ui('자동 이름')} : {os.path.basename(target_path)}"
                )
                btn_auto = msg.addButton(self.tr_ui("자동 이름 사용"), QMessageBox.ButtonRole.AcceptRole)
                btn_retry = msg.addButton(self.tr_ui("다시 입력"), QMessageBox.ButtonRole.ActionRole)
                btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
                for _btn in (btn_auto, btn_retry, btn_cancel):
                    try:
                        _btn.setMinimumWidth(128)
                    except Exception:
                        pass
                msg.setDefaultButton(btn_retry)
                msg.setEscapeButton(btn_cancel)
                try:
                    msg.setStyleSheet(
                        self.message_box_style()
                        + "\nQMessageBox QPushButton { min-width:128px; padding:6px 14px; }"
                    )
                except Exception:
                    pass
                force_message_box_front(msg)
                msg.exec()
                clicked = msg.clickedButton()
                if clicked is btn_cancel:
                    return False
                if clicked is btn_retry:
                    current_stem = new_stem
                    continue
                # 자동 이름 사용은 target_path 그대로 진행
            break

        try:
            self.commit_current_page_ui_to_data()
            self.remember_current_view_state()
        except Exception:
            pass

        undo_rec = None
        if not getattr(self, "_project_undo_restore_lock", False):
            try:
                from ysb.core.project_structure_undo import make_rename_record
                old_name = str((self.data.get(page_idx) or {}).get("original_name") or os.path.basename(str(current_path))) if isinstance(self.data, dict) else os.path.basename(str(current_path))
                undo_rec = make_rename_record(page_idx, str(current_path), old_name, reason="원본 파일명 변경")
            except Exception:
                undo_rec = None

        new_path = Path(target_path)
        try:
            if str(current_path.resolve()).lower() == str(new_path.resolve()).lower() and str(current_path) != str(new_path):
                temp_path = current_path.with_name(f".__ysb_rename_tmp_{uuid.uuid4().hex}{current_path.suffix}")
                os.rename(str(current_path), str(temp_path))
                os.rename(str(temp_path), str(new_path))
            else:
                os.rename(str(current_path), str(new_path))
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("파일명 변경 실패"),
                f"{self.tr_ui('원본 이미지 파일명을 변경하지 못했습니다.')}\n{e}",
            )
            return False

        self.paths[page_idx] = str(new_path)
        if not isinstance(self.data, dict):
            self.data = {}
        curr = self.data.get(page_idx) or {}
        curr["original_name"] = os.path.basename(str(new_path))
        self.data[page_idx] = curr

        if undo_rec is not None:
            try:
                undo_rec["file_rename_ops"] = [{
                    "page_idx": int(page_idx),
                    "from_path": str(new_path),
                    "to_path": str(current_path),
                    "reason": "원본 파일명 변경",
                }]
                self.undo_push_project(undo_rec)
            except Exception:
                pass

        try:
            if hasattr(self, "page_tab_bar"):
                self.page_tab_bar.setTabText(page_idx, self.page_display_name(page_idx))
                self.page_tab_bar.setTabToolTip(page_idx, "")
        except Exception:
            pass
        try:
            if page_idx == self.idx:
                self.btn_page.setText(f"{self.idx + 1} / {len(self.paths)}")
                self.sync_page_tab_current_only()
        except Exception:
            pass
        try:
            self.schedule_deferred_auto_save_project()
        except Exception:
            self.auto_save_project()
        self.log(f"✏️ 원본 파일명 변경: {current_path.name} → {new_path.name}")
        return True

    def apply_page_tab_style(self):
        if not hasattr(self, "page_tab_container") or not hasattr(self, "page_tab_bar"):
            return
        if self.is_light_theme():
            self.page_tab_container.setStyleSheet("background:#F1ECEF; border:1px solid #DED8DC; border-radius:0px;")
            self.page_tab_bar.setStyleSheet(
                "QTabBar::tab { background:#ffffff; color:#555056; padding:6px 28px 6px 10px; border:1px solid #D1C9CE; border-bottom:1px solid #D1C9CE; border-radius:0px; min-width:82px; }"
                "QTabBar::tab:selected { background:#F5E8EA; color:#111827; font-weight:700; border-color:#C78A90; }"
                "QTabBar::tab:hover { background:#FBF5F6; color:#111827; }"
                "QTabBar::scroller { width:0px; }"
                "QTabBar QToolButton { width:0px; height:0px; max-width:0px; max-height:0px; border:0px; padding:0px; margin:0px; background:transparent; color:transparent; }"
            )
            if hasattr(self, "btn_page_tab_menu"):
                self.btn_page_tab_menu.setStyleSheet(
                    "QToolButton { background:#ffffff; color:#28262B; border:1px solid #D1C9CE; border-radius:0px; font-size:16px; font-weight:700; }"
                    "QToolButton:hover { background:#FBF5F6; border-color:#C78A90; }"
                    "QToolButton:disabled { background:#F1ECEF; color:#A39BA1; border:1px solid #D3CCD1; }"
                )
            for _btn in (getattr(self, "btn_page_scroll_left", None), getattr(self, "btn_page_scroll_right", None)):
                if _btn is not None:
                    _btn.setStyleSheet(
                        "QToolButton { background:#ffffff; color:#111827; border:1px solid #D1C9CE; border-radius:0px; font-size:14px; font-weight:900; padding:0px; }"
                        "QToolButton:hover { background:#FBF5F6; border-color:#C78A90; }"
                        "QToolButton:disabled { background:#F1ECEF; color:#A39BA1; border:1px solid #D3CCD1; }"
                    )
            if hasattr(self, "btn_page_add"):
                self.btn_page_add.setStyleSheet(
                    "QToolButton { background:#ffffff; color:#28262B; border:1px solid #D1C9CE; border-radius:0px; font-size:17px; font-weight:700; }"
                    "QToolButton:hover { background:#FBF5F6; border-color:#C78A90; }"
                    "QToolButton:disabled { background:#F1ECEF; color:#A39BA1; border:1px solid #D3CCD1; }"
                )
            try:
                self.page_tab_bar.apply_theme(True)
            except Exception:
                pass
            self.update_page_tab_scroll_buttons()
        else:
            self.page_tab_container.setStyleSheet("background:#211F23; border:1px solid #3A363B; border-radius:0px;")
            self.page_tab_bar.setStyleSheet(
                "QTabBar::tab { background:#2B282D; color:#BDB6BB; padding:6px 28px 6px 10px; border:1px solid #3A363B; border-bottom:1px solid #3A363B; border-radius:0px; min-width:82px; }"
                "QTabBar::tab:selected { background:#5B3136; color:#ffffff; font-weight:700; border-color:#C78A90; }"
                "QTabBar::tab:hover { background:#3A343A; color:#ffffff; }"
                "QTabBar::scroller { width:0px; }"
                "QTabBar QToolButton { width:0px; height:0px; max-width:0px; max-height:0px; border:0px; padding:0px; margin:0px; background:transparent; color:transparent; }"
            )
            if hasattr(self, "btn_page_tab_menu"):
                self.btn_page_tab_menu.setStyleSheet(
                    "QToolButton { background:#2B282D; color:#ffffff; border:1px solid #3A363B; border-radius:0px; font-size:16px; font-weight:700; }"
                    "QToolButton:hover { background:#3A343A; border-color:#C78A90; }"
                    "QToolButton:disabled { background:#211F23; color:#736A71; border:1px solid #373136; }"
                )
            for _btn in (getattr(self, "btn_page_scroll_left", None), getattr(self, "btn_page_scroll_right", None)):
                if _btn is not None:
                    _btn.setStyleSheet(
                        "QToolButton { background:#2B282D; color:#ffffff; border:1px solid #3A363B; border-radius:0px; font-size:14px; font-weight:900; padding:0px; }"
                        "QToolButton:hover { background:#3A343A; border-color:#C78A90; }"
                        "QToolButton:disabled { background:#211F23; color:#736A71; border:1px solid #373136; }"
                    )
            if hasattr(self, "btn_page_add"):
                self.btn_page_add.setStyleSheet(
                    "QToolButton { background:#2B282D; color:#ffffff; border:1px solid #3A363B; border-radius:0px; font-size:17px; font-weight:700; }"
                    "QToolButton:hover { background:#3A343A; border-color:#C78A90; }"
                    "QToolButton:disabled { background:#211F23; color:#736A71; border:1px solid #373136; }"
                )
            try:
                self.page_tab_bar.apply_theme(False)
            except Exception:
                pass
            self.update_page_tab_scroll_buttons()

    def scroll_page_tabs_left(self):
        self.page_tab_scroll_generation = int(getattr(self, "page_tab_scroll_generation", 0) or 0) + 1
        bar = getattr(self, "page_tab_bar", None)
        if bar is not None and hasattr(bar, "scroll_step"):
            return bar.scroll_step(-1)
        return False

    def scroll_page_tabs_right(self):
        self.page_tab_scroll_generation = int(getattr(self, "page_tab_scroll_generation", 0) or 0) + 1
        bar = getattr(self, "page_tab_bar", None)
        if bar is not None and hasattr(bar, "scroll_step"):
            return bar.scroll_step(+1)
        return False

    def update_page_tab_scroll_buttons(self):
        """커스텀 탭바에서는 내부 스크롤 버튼 보정이 필요 없다."""
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is not None and hasattr(bar, "apply_theme"):
                bar.apply_theme(self.is_light_theme())
        except Exception:
            pass

    def schedule_current_page_tab_visible(self, center=False):
        scheduled_generation = int(getattr(self, "page_tab_scroll_generation", 0) or 0)
        def _run():
            if scheduled_generation != int(getattr(self, "page_tab_scroll_generation", 0) or 0):
                return
            self.ensure_current_page_tab_visible(center=center)
        QTimer.singleShot(0, _run)

    def ensure_current_page_tab_visible(self, center=False):
        """현재 페이지 탭이 페이지탭 박스 안에 완전히 보이도록 스크롤한다."""
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is None or not hasattr(bar, "scroll") or not hasattr(bar, "_tabs"):
                return False
            idx = int(getattr(self, "idx", 0) or 0)
            if idx < 0 or idx >= len(bar._tabs):
                return False

            sb = bar.scroll.horizontalScrollBar()
            viewport_w = bar.scroll.viewport().width()
            tab = bar._tabs[idx]
            left = int(tab.x())
            right = int(tab.x() + tab.width())
            cur = int(sb.value())
            view_left = cur
            view_right = cur + max(1, viewport_w)

            if center:
                target = left - max(0, (viewport_w - tab.width()) // 2)
            elif left < view_left:
                target = left
            elif right > view_right:
                target = right - viewport_w
            else:
                return True

            target = max(sb.minimum(), min(sb.maximum(), int(target)))
            sb.setValue(target)
            return True
        except Exception:
            return False

    def show_current_page_full_name(self):
        """Alt+V: 현재 페이지 탭 전체 이름을 누르고 있는 동안만 보여준다."""
        if not getattr(self, "paths", None):
            self.log("⚠️ 표시할 페이지가 없습니다.")
            return False
        try:
            page_idx = max(0, min(int(self.idx), len(self.paths) - 1))
        except Exception:
            page_idx = 0
        text = self.page_display_name(page_idx, include_ext=True)
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is not None and 0 <= page_idx < bar.count():
                rect = bar.tabRect(page_idx)
                anchor = bar.mapToGlobal(rect.bottomLeft()) + QPoint(0, 8)
            else:
                anchor = QCursor.pos() + QPoint(12, 12)

            html = self.native_tooltip_html("현재 페이지 이름", "Alt+V", text)
            popup = getattr(self, "_page_full_name_popup", None)
            if popup is None:
                popup = QLabel(self)
                popup.setObjectName("pageFullNameOverlay")
                popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                popup.setTextFormat(Qt.TextFormat.RichText)
                popup.hide()
                self._page_full_name_popup = popup
            popup.setText(html)
            if self.is_light_theme():
                popup.setStyleSheet("QLabel#pageFullNameOverlay { background:#ffffff; color:#111827; border:1px solid #D1C9CE; border-radius:0px; padding:5px; }")
            else:
                popup.setStyleSheet("QLabel#pageFullNameOverlay { background:#242329; color:#ffffff; border:1px solid #555056; border-radius:0px; padding:5px; }")
            popup.adjustSize()
            local = self.mapFromGlobal(anchor)
            x = max(4, min(local.x(), max(4, self.width() - popup.width() - 4)))
            y = max(4, min(local.y(), max(4, self.height() - popup.height() - 4)))
            popup.move(x, y)
            popup.show()
            popup.raise_()
            try:
                self.audit_top_level_widgets("page_full_name_popup", throttle_ms=1000)
            except Exception:
                pass
            self._page_full_name_popup_hold_by_shortcut = True
        except Exception:
            try:
                QMessageBox.information(self, self.tr_ui("현재 페이지 이름"), text)
            except Exception:
                pass
        self.log(f"📄 현재 페이지 이름: {text}")
        return True

    def hide_current_page_full_name(self):
        try:
            QToolTip.hideText()
        except Exception:
            pass
        try:
            popup = getattr(self, "_page_full_name_popup", None)
            if popup is not None:
                popup.hide()
        except Exception:
            pass
        self._page_full_name_popup_hold_by_shortcut = False

    def hide_page_tab_menu(self):
        try:
            old_popup = getattr(self, "_page_list_popup", None)
            if old_popup is not None and old_popup.isVisible():
                old_popup.close()
        except Exception:
            pass
        self._page_list_popup = None
        self._page_list_popup_hold_by_shortcut = False

    def show_page_tab_menu(self, hold_by_shortcut=False):
        """좌측 3선 버튼/단축키에서 현재 프로젝트의 페이지 목록을 포커스 가능한 세로 목록으로 보여준다."""
        try:
            old_popup = getattr(self, "_page_list_popup", None)
            if old_popup is not None and old_popup.isVisible():
                if hold_by_shortcut:
                    self._page_list_popup_hold_by_shortcut = True
                    return
                old_popup.close()
                return
        except Exception:
            pass
        self._page_list_popup_hold_by_shortcut = bool(hold_by_shortcut)

        btn = getattr(self, "btn_page_tab_menu", None)
        anchor = btn if btn is not None else self

        popup = QFrame(self, Qt.WindowType.Popup)
        self._page_list_popup = popup
        popup.setObjectName("PageListPopup")
        popup.setMinimumWidth(260)
        try:
            if self.is_light_theme():
                popup.setStyleSheet(
                    "QFrame#PageListPopup { background:#ffffff; color:#111827; border:1px solid #D1C9CE; }"
                    "QLabel { color:#111827; font-weight:700; padding:6px 8px 2px 8px; }"
                    "QListWidget { background:#ffffff; color:#111827; border:0px; outline:0px; }"
                    "QListWidget::item { padding:6px 10px; min-height:22px; }"
                    "QListWidget::item:selected { background:#F5E8EA; color:#111827; }"
                    "QListWidget::item:hover { background:#FBF5F6; }"
                )
            else:
                popup.setStyleSheet(
                    "QFrame#PageListPopup { background:#252328; color:#ffffff; border:1px solid #3A363B; }"
                    "QLabel { color:#ffffff; font-weight:700; padding:6px 8px 2px 8px; }"
                    "QListWidget { background:#252328; color:#ffffff; border:0px; outline:0px; }"
                    "QListWidget::item { padding:6px 10px; min-height:22px; }"
                    "QListWidget::item:selected { background:#5B3136; color:#ffffff; }"
                    "QListWidget::item:hover { background:#3A343A; }"
                )
        except Exception:
            pass

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title = QLabel(self.tr_ui("페이지 목록"), popup)
        layout.addWidget(title)

        page_list = QListWidget(popup)
        page_list.setUniformItemSizes(True)
        page_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        page_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        page_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        popup.page_list_widget = page_list
        layout.addWidget(page_list)

        current_page_item = None
        if not self.paths:
            item = QListWidgetItem(self.tr_ui("페이지 없음"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            page_list.addItem(item)
        else:
            for i in range(len(self.paths)):
                label = self.page_display_name(i, include_ext=False)
                is_current = (i == self.idx)
                prefix = "▶ " if is_current else "   "
                item = QListWidgetItem(prefix + label)
                item.setData(Qt.ItemDataRole.UserRole, i)
                item.setData(Qt.ItemDataRole.UserRole + 1, is_current)
                try:
                    item.setToolTip(self.page_display_name(i, include_ext=True))
                except Exception:
                    pass
                if is_current:
                    current_page_item = item
                    try:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        if self.is_light_theme():
                            item.setBackground(QBrush(QColor("#fff7ed")))
                            item.setForeground(QBrush(QColor("#111827")))
                        else:
                            item.setBackground(QBrush(QColor("#303846")))
                            item.setForeground(QBrush(QColor("#ffffff")))
                    except Exception:
                        pass
                page_list.addItem(item)
            if 0 <= self.idx < page_list.count():
                page_list.setCurrentRow(self.idx)
                try:
                    page_list.setCurrentItem(page_list.item(self.idx), QItemSelectionModel.SelectionFlag.ClearAndSelect)
                except Exception:
                    pass
            elif page_list.count() > 0:
                page_list.setCurrentRow(0)

        def _activate_item(item=None):
            try:
                item = item or page_list.currentItem()
                if item is None:
                    return
                page = item.data(Qt.ItemDataRole.UserRole)
                if page is None:
                    return
                popup.close()
                self.jump_to_page_from_menu(int(page))
            except Exception:
                pass

        page_list.itemActivated.connect(_activate_item)
        page_list.itemClicked.connect(_activate_item)

        row_height = 30
        try:
            max_popup_height = max(180, self.height() // 2)
        except Exception:
            max_popup_height = 300
        visible_rows = max(1, min(page_list.count() or 1, max(1, (max_popup_height - 34) // row_height)))
        popup_height = min(max_popup_height, 34 + max(1, page_list.count()) * row_height)
        try:
            popup_width = max(360, min(760, self.width() // 2))
        except Exception:
            popup_width = 520
        popup.resize(popup_width, popup_height)
        page_list.setMinimumHeight(min(visible_rows * row_height, max_popup_height - 34))
        page_list.setMaximumHeight(max_popup_height - 34)

        try:
            pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        except Exception:
            pos = self.mapToGlobal(QPoint(40, 80))
        popup.move(pos)
        popup.show()
        popup.raise_()
        popup.activateWindow()
        try:
            if current_page_item is not None:
                page_list.scrollToItem(current_page_item, QAbstractItemView.ScrollHint.PositionAtCenter)
                page_list.setCurrentItem(current_page_item, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            elif page_list.currentItem() is not None:
                page_list.scrollToItem(page_list.currentItem(), QAbstractItemView.ScrollHint.PositionAtCenter)
        except Exception:
            pass
        page_list.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def jump_to_page_from_menu(self, page_idx):
        try:
            page_idx = int(page_idx)
        except Exception:
            return
        if page_idx < 0 or page_idx >= len(self.paths):
            return
        if hasattr(self, "page_tab_bar"):
            try:
                self.page_tab_bar.setCurrentIndex(page_idx)
                return
            except Exception:
                pass
        self.on_page_tab_changed(page_idx)

    def refresh_page_tabs(self):
        if not hasattr(self, "page_tab_bar"):
            return
        bar = self.page_tab_bar
        has_pages = bool(self.paths)
        try:
            if hasattr(self, "btn_page_tab_menu"):
                self.btn_page_tab_menu.setEnabled(has_pages)
        except Exception:
            pass
        try:
            bar.setEnabled(has_pages)
        except Exception:
            pass
        self._refreshing_page_tabs = True
        try:
            bar.blockSignals(True)
            if not self.paths:
                while bar.count() > 0:
                    bar.removeTab(0)
                bar.setTabsClosable(False)
                bar.setMovable(False)
                return

            bar.setTabsClosable(True)
            bar.setMovable(True)

            desired_count = len(self.paths)
            need_rebuild = (bar.count() != desired_count)
            if need_rebuild:
                while bar.count() > 0:
                    bar.removeTab(0)
                for i in range(desired_count):
                    label = self.page_display_name(i)
                    bar.addTab(label)
                    try:
                        bar.setTabToolTip(i, "")
                    except Exception:
                        pass
            else:
                for i in range(desired_count):
                    try:
                        label = self.page_display_name(i)
                        tooltip = ""
                        if bar.tabText(i) != label:
                            bar.setTabText(i, label)
                        try:
                            old_tip = bar.tabToolTip(i)
                        except Exception:
                            old_tip = None
                        if old_tip != tooltip:
                            try:
                                bar.setTabToolTip(i, "")
                            except Exception:
                                pass
                    except Exception:
                        pass

            if self.idx < 0:
                self.idx = 0
            if self.idx >= len(self.paths):
                self.idx = len(self.paths) - 1
            if bar.currentIndex() != self.idx:
                bar.setCurrentIndex(self.idx)
        finally:
            try:
                bar.blockSignals(False)
            except Exception:
                pass
            self._refreshing_page_tabs = False
            try:
                self.update_page_tab_scroll_buttons()
            except Exception:
                pass

    def sync_page_tab_current_only(self):
        """페이지 이동 때 탭바 전체를 다시 만들지 않고 현재 선택만 맞춘다.

        대용량 프로젝트에서는 load()가 호출될 때마다 모든 페이지 탭 이름/툴팁을
        재계산하는 것만으로도 렉이 난다. 페이지 수나 구조가 바뀐 경우만
        refresh_page_tabs()를 쓰고, 단순 페이지 이동은 이 경량 동기화만 사용한다.
        """
        bar = getattr(self, "page_tab_bar", None)
        if bar is None:
            return False
        try:
            if not self.paths:
                return False
            if bar.count() != len(self.paths):
                return False
            idx = max(0, min(int(getattr(self, "idx", 0) or 0), len(self.paths) - 1))
            if bar.currentIndex() != idx:
                old = getattr(self, "_refreshing_page_tabs", False)
                self._refreshing_page_tabs = True
                try:
                    bar.blockSignals(True)
                    bar.setCurrentIndex(idx)
                finally:
                    try:
                        bar.blockSignals(False)
                    except Exception:
                        pass
                    self._refreshing_page_tabs = old
            try:
                self.update_page_tab_scroll_buttons()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def remap_indexed_dict_by_order(self, src, order):
        out = {}
        src = src or {}
        for new_idx, old_idx in enumerate(order or []):
            if old_idx in src:
                out[new_idx] = src.get(old_idx)
        return out

    def remap_view_states_by_order(self, order):
        states = getattr(self, "project_ui_view_states", {}) or {}
        if not isinstance(states, dict) or not order:
            self.project_ui_view_states = {} if not order else states
            return
        old_to_new = {int(old): int(new) for new, old in enumerate(order)}
        new_states = {}
        for key, state in states.items():
            try:
                page_s, mode_s = str(key).split(":", 1)
                old_page = int(page_s)
                if old_page in old_to_new:
                    new_states[f"{old_to_new[old_page]}:{int(mode_s)}"] = copy.deepcopy(state)
            except Exception:
                pass
        self.project_ui_view_states = new_states

    def on_page_tab_changed(self, index):
        if getattr(self, "_refreshing_page_tabs", False):
            return
        if index < 0 or index >= len(self.paths):
            return
        if index == self.idx:
            return

        preserve_scroll = None
        target_was_visible = False
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is not None and hasattr(bar, "scroll") and hasattr(bar, "_tabs"):
                sb = bar.scroll.horizontalScrollBar()
                preserve_scroll = int(sb.value())
                if 0 <= int(index) < len(bar._tabs):
                    tab = bar._tabs[int(index)]
                    left = int(tab.x())
                    right = int(tab.x() + tab.width())
                    view_left = preserve_scroll
                    view_right = preserve_scroll + max(1, int(bar.scroll.viewport().width()))
                    target_was_visible = (left >= view_left and right <= view_right)
        except Exception:
            preserve_scroll = None
            target_was_visible = False

        # 페이지 전환은 현재 페이지 작업실의 Undo 경계다.
        # 다른 페이지로 넘어가면 이전 페이지 내부 Ctrl+Z 흐름은 끊는다.
        # 단, 페이지를 닫기 전에 현재 화면 변경분과 view_state는 현재 idx 기준으로 먼저 고정한다.
        try:
            self.prepare_current_page_boundary("page change")
        except Exception:
            try:
                self.undo_clear_current_page("page change")
            except Exception:
                pass
            self.commit_current_page_ui_to_data()
            self.remember_current_view_state()
        # 페이지 전환은 구조 변경이 아니라 탐색 동작이다.
        # 이미 보이는 탭을 클릭했다면 탭바 시점은 보존하고,
        # 보이지 않거나 절반만 보일 때만 현재 순간 기준으로 한 번 보정한다.
        self.idx = int(index)
        self.load()
        self.restore_current_view_state_later()

        scheduled_generation = int(getattr(self, "page_tab_scroll_generation", 0) or 0)

        def _restore_or_ensure_tab_position():
            # 예약 후 사용자가 좌우 화살표로 탭바를 수동 이동했다면,
            # 오래된 자동 보정은 실행하지 않는다.
            if scheduled_generation != int(getattr(self, "page_tab_scroll_generation", 0) or 0):
                return
            try:
                bar = getattr(self, "page_tab_bar", None)
                if target_was_visible and preserve_scroll is not None and bar is not None and hasattr(bar, "scroll"):
                    sb = bar.scroll.horizontalScrollBar()
                    sb.setValue(max(sb.minimum(), min(sb.maximum(), int(preserve_scroll))))
                    return
            except Exception:
                pass
            self.ensure_current_page_tab_visible()

        QTimer.singleShot(0, _restore_or_ensure_tab_position)

    def selected_page_tab_indices(self):
        """페이지 탭바에서 Ctrl/Shift로 선택된 페이지 인덱스를 가져온다."""
        bar = getattr(self, "page_tab_bar", None)
        if bar is not None and hasattr(bar, "selectedIndices"):
            try:
                selected = [int(i) for i in bar.selectedIndices()]
                return [i for i in selected if 0 <= i < len(self.paths)]
            except Exception:
                pass
        try:
            return [int(self.idx)] if self.paths else []
        except Exception:
            return []

    def confirm_and_delete_pages(self, indices, title="일괄 페이지탭 삭제"):
        clean = []
        seen = set()
        for raw in indices or []:
            try:
                i = int(raw)
            except Exception:
                continue
            if 0 <= i < len(self.paths) and i not in seen:
                clean.append(i)
                seen.add(i)
        if not clean:
            self.log("⚠️ 삭제할 이미지탭이 없습니다.")
            return False

        names = [self.page_display_name(i, include_ext=True) for i in clean[:8]]
        info = "\n".join(str(x) for x in names)
        if len(clean) > 8:
            info += f"\n... 외 {len(clean) - 8}개"
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui(title))
        msg.setText(self.tr_ui(f"선택한 {len(clean)}개의 페이지탭을 삭제할까요?"))
        msg.setInformativeText(info)
        btn_delete = msg.addButton(self.tr_ui("삭제"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_cancel)
        try:
            msg.setStyleSheet(self.message_box_style())
        except Exception:
            pass
        force_message_box_front(msg)
        msg.exec()
        if msg.clickedButton() is not btn_delete:
            self.log("↩️ 페이지탭 삭제 취소")
            return False
        return self.delete_pages_at(clean, reason=title)

    def close_page_from_tab(self, index):
        if index < 0 or index >= len(self.paths):
            return
        selected = self.selected_page_tab_indices()
        if len(selected) > 1 and index in selected:
            self.confirm_and_delete_pages(selected, title="일괄 페이지탭 삭제")
            return
        self.confirm_and_delete_pages([index], title="페이지 삭제")


    def delete_pages_at(self, indices, reason="페이지 삭제"):
        clean = []
        seen = set()
        for raw in indices or []:
            try:
                i = int(raw)
            except Exception:
                continue
            if 0 <= i < len(self.paths) and i not in seen:
                clean.append(i)
                seen.add(i)
        if not clean:
            return False

        remove_set = set(clean)
        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        before_structure_state = self._snapshot_project_structure_state(reason)
        old_count = len(self.paths)
        old_idx = int(getattr(self, "idx", 0) or 0)
        order = [i for i in range(old_count) if i not in remove_set]
        removed_names = [self.page_display_name(i, include_ext=True) for i in clean]

        self.paths = [self.paths[i] for i in order]
        self.data = self.remap_indexed_dict_by_order(self.data, order)
        self.remap_view_states_by_order(order)

        if self.paths:
            removed_before = sum(1 for i in remove_set if i < old_idx)
            if old_idx in remove_set:
                self.idx = min(max(0, old_idx - removed_before), len(self.paths) - 1)
            else:
                self.idx = min(max(0, old_idx - removed_before), len(self.paths) - 1)
        else:
            self.idx = 0
            self.project_ui_view_states = {}

        after_structure_state = self._snapshot_project_structure_state(reason)
        self.undo_clear_all_pages("page delete")
        self.push_project_structure_command(before_structure_state, after_structure_state, reason=reason, action="page_delete")
        self.load()
        try:
            bar = getattr(self, "page_tab_bar", None)
            if bar is not None and hasattr(bar, "setSelectedIndices") and self.paths:
                bar.setSelectedIndices([self.idx])
        except Exception:
            pass
        self.auto_save_project()
        if len(clean) == 1:
            self.log(f"🗑️ 페이지 삭제: {removed_names[0]}")
        else:
            self.log(f"🗑️ {reason}: {len(clean)}개")
        return True

    def delete_page_at(self, index):
        return self.delete_pages_at([index], reason="페이지 삭제")


    def delete_current_page_shortcut(self):
        """Ctrl+Q: 현재 열려 있거나 탭바에서 선택된 이미지 탭을 삭제한다."""
        if not getattr(self, "paths", None):
            self.log("⚠️ 삭제할 이미지탭이 없습니다.")
            return False
        selected = self.selected_page_tab_indices()
        if len(selected) > 1:
            return self.confirm_and_delete_pages(selected, title="일괄 페이지탭 삭제")
        try:
            index = max(0, min(int(self.idx), len(self.paths) - 1))
        except Exception:
            index = 0
        self.close_page_from_tab(index)
        return True


    def delete_all_pages_shortcut(self):
        """Ctrl+Shift+Q: 선택한 범위의 페이지탭을 일괄 삭제한다."""
        if not getattr(self, "paths", None):
            self.log("⚠️ 삭제할 이미지탭이 없습니다.")
            return False

        selected = self.selected_page_tab_indices()
        if len(selected) <= 1:
            selected, label = self.choose_batch_page_indices("일괄 페이지탭 삭제", "delete_pages")
            if selected is None:
                self.log("↩️ 일괄 페이지탭 삭제 취소")
                return False
        else:
            label = f"선택 {len(selected)}개"

        result = self.confirm_and_delete_pages(selected, title="일괄 페이지탭 삭제")
        if result:
            self.log(f"🗑️ 일괄 페이지탭 삭제 완료: {len(selected)}개 ({label})")
        return result


    def on_page_tab_moved(self, from_index, to_index):
        if getattr(self, "_refreshing_page_tabs", False):
            return
        if from_index == to_index:
            return
        try:
            self.undo_clear_all_pages()
        except Exception:
            pass
        if from_index < 0 or to_index < 0 or from_index >= len(self.paths) or to_index >= len(self.paths):
            self.refresh_page_tabs()
            return

        bar = getattr(self, "page_tab_bar", None)
        try:
            visible_index = int(bar.currentIndex()) if bar is not None else int(self.idx)
        except Exception:
            visible_index = int(self.idx) if self.paths else 0
        try:
            tab_scroll_value = int(bar.scroll.horizontalScrollBar().value()) if bar is not None and hasattr(bar, "scroll") else None
        except Exception:
            tab_scroll_value = None

        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        before_structure_state = self._snapshot_project_structure_state("페이지 순서 변경")

        n = len(self.paths)
        order = list(range(n))
        moved_old = order.pop(from_index)
        order.insert(to_index, moved_old)

        old_paths = list(self.paths)
        self.paths = [old_paths[old_i] for old_i in order]
        self.data = self.remap_indexed_dict_by_order(self.data, order)
        self.remap_view_states_by_order(order)

        # QTabBar가 이미 화면상으로 탭을 이동시켰으므로, 여기서 전체 탭을 다시 만들지 않는다.
        # 다시 만들면 드래그 직후 잡고 있던 탭/선택 위치가 한 번 더 튀어 보일 수 있다.
        self.idx = max(0, min(visible_index, len(self.paths) - 1)) if self.paths else 0
        after_structure_state = self._snapshot_project_structure_state("페이지 순서 변경")
        self.undo_clear_all_pages("page reorder")
        self.push_project_structure_command(before_structure_state, after_structure_state, reason="페이지 순서 변경", action="page_reorder")

        try:
            if bar is not None:
                bar.blockSignals(True)
                try:
                    for i in range(min(bar.count(), len(self.paths))):
                        bar.setTabText(i, self.page_display_name(i))
                        bar.setTabToolTip(i, "")
                    # 커스텀 탭바는 드래그 시 이미 시각적 이동을 끝낸 상태다.
                    # 여기서 currentIndex를 다시 강제로 바꾸면 탭 위치가 또 확인되는 느낌이 생기므로,
                    # 내부 idx와 표시 상태만 조용히 맞춘다.
                    try:
                        bar._current = self.idx
                        bar.apply_theme(self.is_light_theme())
                    except Exception:
                        pass
                finally:
                    bar.blockSignals(False)
        except Exception:
            pass

        # 순서 변경은 프로젝트 구조 작업이지만, 화면 전체를 즉시 다시 조립할 필요는 없다.
        # 현재 보이는 페이지는 그대로 두고 탭/목록 메타만 동기화한다. 실제 저장은 지연 저장으로 보낸다.
        try:
            self.sync_page_tab_current_only()
        except Exception:
            pass
        try:
            if tab_scroll_value is not None and bar is not None and hasattr(bar, "scroll"):
                QTimer.singleShot(0, lambda v=tab_scroll_value, b=bar: b.scroll.horizontalScrollBar().setValue(
                    max(b.scroll.horizontalScrollBar().minimum(), min(b.scroll.horizontalScrollBar().maximum(), int(v)))
                ))
        except Exception:
            pass
        self.update_page_tab_scroll_buttons()
        try:
            self.schedule_deferred_auto_save_project(800)
        except Exception:
            self.auto_save_project()
        self.log(f"↔️ 페이지 순서 변경: {from_index + 1} → {to_index + 1}")

    def active_page_storage_dir(self):
        """새로 삽입하는 이미지는 항상 현재 workspace/images에 바로 넣는다.

        예전 work_sessions 캐시 구조에서는 자동저장 OFF일 때 별도 작업 캐시에 먼저 넣었지만,
        지금은 workspaces 폴더 자체가 작업대이자 복구본이다. 따라서 이미지 추가는 즉시
        project_dir/images로 복사되어야 하고, work_sessions full copy를 만들면 안 된다.
        """
        return str(self.project_dir or "")

    def workspace_page_entry_light(self, page_idx, old_page=None):
        """큰 이미지 payload를 건드리지 않고 project.json page entry만 만든다.

        이미지 추가/구조 변경 직후에는 이미 workspace/images에 파일이 복사되어 있다.
        여기서는 파일 재저장/재인코딩 없이 경로와 텍스트 JSON만 갱신한다.
        """
        try:
            page_idx = int(page_idx)
        except Exception:
            page_idx = 0
        curr = (getattr(self, "data", {}) or {}).get(page_idx)
        if not isinstance(curr, dict):
            curr = {}
        page = copy.deepcopy(old_page) if isinstance(old_page, dict) else {}
        try:
            image_path = str((getattr(self, "paths", []) or [])[page_idx])
        except Exception:
            image_path = ""
        if image_path:
            try:
                page["image"] = relpath(image_path, self.project_dir)
            except Exception:
                page["image"] = image_path.replace("\\", "/")
        page["original_name"] = str(curr.get("original_name") or os.path.basename(str(image_path)) or f"page{page_idx + 1:03d}.png")
        page["data"] = json_safe(curr.get("data", []))
        page["ocr_analysis_regions"] = json_safe(curr.get("ocr_analysis_regions", []))
        page["mask_toggle_enabled"] = bool(curr.get("mask_toggle_enabled", False))
        page["use_inpainted_as_source"] = bool(curr.get("use_inpainted_as_source", False))

        path_fields = {
            "clean": "clean_path",
            "working_source": "working_source_path",
            "final_paint": "final_paint_path",
            "final_paint_above": "final_paint_above_path",
            "mask_merge": "mask_merge_path",
            "mask_inpaint": "mask_inpaint_path",
            "mask_merge_off": "mask_merge_off_path",
            "mask_inpaint_off": "mask_inpaint_off_path",
        }
        for json_key, data_key in path_fields.items():
            p = curr.get(data_key)
            if p and os.path.exists(str(p)):
                try:
                    page[json_key] = relpath(str(p), self.project_dir)
                except Exception:
                    page[json_key] = str(p).replace("\\", "/")
            elif json_key in page:
                # 기존 페이지에 남은 경로가 아직 workspace 안에 존재하면 보존한다.
                try:
                    old_abs = os.path.join(str(self.project_dir), str(page.get(json_key)).replace("/", os.sep))
                    if not page.get(json_key) or not os.path.exists(old_abs):
                        page.pop(json_key, None)
                except Exception:
                    pass
        return page

    def save_workspace_project_json_light(self, *, reason="structure_light"):
        """workspace/project.json만 가볍게 갱신한다.

        ProjectStore.save(force_full=True)는 전체 페이지를 순회하며 이미지/클린본/마스크 저장 루트를
        확인하므로 이미지 추가 직후 10초 이상 UI를 막을 수 있다. 구조 변경 직후에는 이미 파일이
        workspace/images에 있으므로 project.json만 갱신하면 된다.
        """
        if not getattr(self, "project_dir", None) or not getattr(self, "paths", None):
            return False
        project_file = os.path.join(str(self.project_dir), PROJECT_FILENAME)
        old_payload = {}
        try:
            if os.path.exists(project_file):
                with open(project_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    old_payload = loaded
        except Exception:
            old_payload = {}
        old_pages = old_payload.get("pages", []) if isinstance(old_payload.get("pages"), list) else []
        pages = []
        for i in range(len(self.paths)):
            old_page = old_pages[i] if i < len(old_pages) and isinstance(old_pages[i], dict) else {}
            pages.append(self.workspace_page_entry_light(i, old_page=old_page))
        ui_state = {}
        try:
            ui_state = self.current_project_ui_state()
        except Exception:
            ui_state = old_payload.get("ui_state", {}) if isinstance(old_payload.get("ui_state"), dict) else {}
        payload = {
            "version": old_payload.get("version", 1) if isinstance(old_payload, dict) else 1,
            "current_index": int(getattr(self, "idx", 0) or 0),
            "pages": pages,
            "ui_state": json_safe(ui_state if isinstance(ui_state, dict) else {}),
        }
        try:
            if getattr(self, "project_store", None) is not None:
                self.project_store.write_manifest()
        except Exception:
            pass
        tmp = project_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, project_file)
        return True

    def flush_workspace_structure_after_image_insert(self, *, reason="image_insert"):
        """페이지 삽입/삭제/순서 변경처럼 구조가 바뀐 작업을 workspace project.json에 즉시 반영한다."""
        if not getattr(self, "project_dir", None) or not getattr(self, "project_store", None):
            return False
        try:
            if hasattr(self, "mark_project_structure_dirty"):
                self.mark_project_structure_dirty(str(reason or "image_insert"))
        except Exception:
            pass
        try:
            self.audit_boundary_event("WORKSPACE_STRUCTURE_LIGHT_SAVE_ENTER", reason=str(reason or "image_insert"), stack=True)
        except Exception:
            pass
        ok = False
        try:
            ok = bool(self.save_workspace_project_json_light(reason=reason))
        except Exception as e:
            try:
                self.log(f"⚠️ 이미지 추가 workspace 구조 저장 실패: {e}")
            except Exception:
                pass
            ok = False
        try:
            self.record_recovery_project_dir(self.project_dir)
        except Exception:
            pass
        try:
            self.audit_boundary_event("WORKSPACE_STRUCTURE_LIGHT_SAVE_DONE", reason=str(reason or "image_insert"), ok=bool(ok))
        except Exception:
            pass
        try:
            self.has_unsaved_changes = True
            self.update_window_title()
        except Exception:
            pass
        return ok

    def unique_insert_image_path(self, src_path):
        storage_root = self.active_page_storage_dir() or str(self.project_dir)
        images_dir = os.path.join(storage_root, "images")
        os.makedirs(images_dir, exist_ok=True)
        src = Path(src_path)
        ext = src.suffix.lower() if src.suffix.lower() in IMAGE_DROP_EXTS else ".png"
        base = safe_page_file_stem(src.stem, fallback="inserted")

        # 원본 파일명을 최대한 보존하되, 확장자가 달라도 표시 stem이 겹치면 회피한다.
        # 예: 0007.jpg가 있으면 0007.png는 0007(1).png로 저장.
        existing_stems = set()
        try:
            for p in Path(images_dir).iterdir():
                if p.is_file():
                    existing_stems.add(p.stem.lower())
        except Exception:
            pass

        candidate_stem = base
        candidate = os.path.join(images_dir, f"{candidate_stem}{ext}")
        if candidate_stem.lower() not in existing_stems and not os.path.exists(candidate):
            return candidate

        for n in range(1, 10000):
            candidate_stem = f"{base}({n})"
            candidate = os.path.join(images_dir, f"{candidate_stem}{ext}")
            if candidate_stem.lower() not in existing_stems and not os.path.exists(candidate):
                return candidate

        return os.path.join(images_dir, f"{base}({uuid.uuid4().hex[:8]}){ext}")

    def unique_initial_image_target_path(self, src_path, images_dir, used_stems=None, current_path=None):
        """새 프로젝트 생성 직후 원본 파일명 보존용 대상 경로를 만든다.

        ProjectStore 경로가 0001/0002 같은 번호명을 만들었더라도 여기서 최종적으로
        원본명 기반 파일명으로 다시 정리한다.
        """
        used_stems = used_stems if used_stems is not None else set()
        src = Path(str(src_path))
        ext = src.suffix.lower() if src.suffix.lower() in IMAGE_DROP_EXTS else ".png"
        base = safe_page_file_stem(src.stem, fallback="image")
        current_resolved = ""
        try:
            current_resolved = str(Path(str(current_path)).resolve()).lower() if current_path else ""
        except Exception:
            current_resolved = ""

        existing_stems = set(used_stems)
        try:
            for p in Path(images_dir).iterdir():
                if not p.is_file():
                    continue
                try:
                    if current_resolved and str(p.resolve()).lower() == current_resolved:
                        continue
                except Exception:
                    pass
                existing_stems.add(p.stem.lower())
        except Exception:
            pass

        def make_candidate(n=None):
            stem = base if n is None else f"{base}({n})"
            return stem, Path(images_dir) / f"{stem}{ext}"

        stem, target = make_candidate(None)
        if stem.lower() not in existing_stems and (not target.exists() or str(target.resolve()).lower() == current_resolved):
            used_stems.add(stem.lower())
            return str(target)

        for n in range(1, 10000):
            stem, target = make_candidate(n)
            if stem.lower() not in existing_stems and not target.exists():
                used_stems.add(stem.lower())
                return str(target)

        stem = f"{base}({uuid.uuid4().hex[:8]})"
        used_stems.add(stem.lower())
        return str(Path(images_dir) / f"{stem}{ext}")

    def enforce_initial_project_image_names(self, source_paths):
        """새 프로젝트 생성 후 images 폴더의 실제 파일명을 원본명 기반으로 정리한다."""
        if not getattr(self, "project_dir", None) or not getattr(self, "paths", None):
            return False
        images_dir = os.path.join(str(self.project_dir), "images")
        os.makedirs(images_dir, exist_ok=True)
        changed = False
        used_stems = set()
        limit = min(len(self.paths), len(source_paths or []))
        for i in range(limit):
            try:
                src = source_paths[i]
                old_path = Path(str(self.paths[i]))
                if not old_path.exists():
                    continue
                target_path = Path(self.unique_initial_image_target_path(src, images_dir, used_stems, current_path=old_path))
                if str(old_path.resolve()).lower() != str(target_path.resolve()).lower():
                    if str(old_path.resolve()).lower() == str(target_path.resolve()).lower() and str(old_path) != str(target_path):
                        tmp = old_path.with_name(f".__ysb_init_rename_{uuid.uuid4().hex}{old_path.suffix}")
                        os.rename(str(old_path), str(tmp))
                        os.rename(str(tmp), str(target_path))
                    else:
                        os.rename(str(old_path), str(target_path))
                    self.paths[i] = str(target_path)
                    changed = True
                else:
                    self.paths[i] = str(target_path)
                if not isinstance(self.data, dict):
                    self.data = {}
                curr = self.data.get(i) or {}
                curr["original_name"] = os.path.basename(str(target_path))
                self.data[i] = curr
            except Exception as e:
                try:
                    self.log(f"⚠️ 원본 파일명 보존 실패({i + 1}p): {e}")
                except Exception:
                    pass
        if changed:
            try:
                self.save_project_store(self.project_store)
            except Exception:
                try:
                    self.project_store.save(self.paths, self.data, current_index=getattr(self, "idx", 0))
                except Exception:
                    pass
        return changed

    def _ensure_page_payload_cache_state(self):
        if not hasattr(self, "_page_payload_cache_order") or self._page_payload_cache_order is None:
            self._page_payload_cache_order = OrderedDict()
        try:
            limit = int(getattr(self, "page_payload_cache_limit", 3) or 3)
        except Exception:
            limit = 3
        self.page_payload_cache_limit = max(1, limit)

    def touch_page_payload_cache(self, page_idx):
        self._ensure_page_payload_cache_state()
        try:
            page_idx = int(page_idx)
        except Exception:
            return
        self._page_payload_cache_order.pop(page_idx, None)
        self._page_payload_cache_order[page_idx] = True

    def trim_page_payload_cache(self, keep_indices=None):
        self._ensure_page_payload_cache_state()
        keep = set()
        try:
            keep.add(int(getattr(self, "idx", -1)))
        except Exception:
            pass
        for raw in list(keep_indices or []):
            try:
                keep.add(int(raw))
            except Exception:
                pass
        payload_keys = ("bg_clean", "working_source", "final_paint", "final_paint_above")
        loaded = []
        for page_idx, curr in list((getattr(self, "data", {}) or {}).items()):
            if isinstance(curr, dict) and any(curr.get(k) is not None for k in payload_keys):
                loaded.append(int(page_idx))
                if page_idx not in self._page_payload_cache_order:
                    self._page_payload_cache_order[page_idx] = True
        while len(loaded) > self.page_payload_cache_limit:
            victim = None
            for candidate in list(self._page_payload_cache_order.keys()):
                if candidate in keep:
                    continue
                curr = (getattr(self, "data", {}) or {}).get(candidate)
                if isinstance(curr, dict) and any(curr.get(k) is not None for k in payload_keys):
                    victim = candidate
                    break
                self._page_payload_cache_order.pop(candidate, None)
            if victim is None:
                break
            curr = self.data.get(victim)
            if isinstance(curr, dict):
                for key in payload_keys:
                    curr[key] = None
            self._page_payload_cache_order.pop(victim, None)
            loaded = [idx for idx in loaded if idx != victim]

    def _read_binary_asset_bytes(self, path_value):
        path = self.resolve_project_asset_path(path_value) if hasattr(self, "resolve_project_asset_path") else path_value
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception:
            return None

    def note_ui_interaction_activity(self, pause_ms=900):
        """사용자 드래그/줌/편집 직후에는 백그라운드 페이지 로더를 잠깐 쉬게 한다."""
        try:
            now = __import__("time").time()
            until = now + max(0.1, float(pause_ms or 900) / 1000.0)
            old_until = float(getattr(self, "_progressive_page_load_pause_until", 0.0) or 0.0)
            self._progressive_page_load_pause_until = max(old_until, until)
        except Exception:
            pass

    def mark_current_page_for_recovery_checkpoint(self, kind="checkpoint_text"):
        """YSBT 저장용 dirty와 workspace checkpoint용 dirty를 분리한다.

        project_engine/page_engine dirty는 명시 저장 전까지 유지되어야 하고,
        checkpoint dirty는 journal 저장이 끝나면 바로 비워져야 한다.
        """
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            page_idx = 0
        kind_s = str(kind or "checkpoint_text")
        try:
            if hasattr(self, "project_engine") and self.project_engine is not None:
                self.project_engine.mark_page_dirty(page_idx, kind_s)
        except Exception:
            pass
        try:
            if hasattr(self, "page_engine") and self.page_engine is not None:
                self.page_engine.mark_dirty(page_idx, kind_s)
        except Exception:
            pass
        try:
            pages = getattr(self, "_checkpoint_dirty_pages", None)
            if pages is None:
                pages = set()
                self._checkpoint_dirty_pages = pages
            pages.add(int(page_idx))
            kinds = getattr(self, "_checkpoint_dirty_kinds", None)
            if kinds is None:
                kinds = {}
                self._checkpoint_dirty_kinds = kinds
            kinds.setdefault(int(page_idx), set()).add(kind_s)
        except Exception:
            pass
        try:
            self.has_unsaved_changes = True
            self.update_window_title()
        except Exception:
            pass

    def schedule_workspace_checkpoint(self, delay_ms=1600, reason=""):
        """YSBT는 건드리지 않고, 현재 workspace/project.json에 page delta만 지연 반영한다."""
        if (
            getattr(self, "_suppress_work_cache_dirty", False)
            or getattr(self, "is_loading_project", False)
            or getattr(self, "is_autosaving", False)
            or not getattr(self, "project_dir", None)
            or not getattr(self, "paths", None)
        ):
            return
        try:
            self.note_ui_interaction_activity(int(delay_ms or 800) + 300)
        except Exception:
            pass
        try:
            self._last_workspace_checkpoint_reason = str(reason or "workspace_checkpoint")
        except Exception:
            pass
        try:
            timer = getattr(self, "_deferred_work_cache_save_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._run_deferred_workspace_checkpoint)
                self._deferred_work_cache_save_timer = timer
            timer.stop()
            timer.start(max(1200, int(delay_ms or 1600)))
        except Exception:
            try:
                self.auto_save_project()
            except Exception:
                pass

    def _run_deferred_workspace_checkpoint(self):
        if getattr(self, "_text_item_drag_active", False) or getattr(self, "_text_scene_mutation_lock", False):
            try:
                self.audit_boundary_event(
                    "WORK_CACHE_SAVE_DEFERRED_DURING_TEXT_DRAG",
                    text_drag=bool(getattr(self, "_text_item_drag_active", False)),
                    scene_mutation=bool(getattr(self, "_text_scene_mutation_lock", False)),
                    throttle_ms=120,
                )
            except Exception:
                pass
            try:
                timer = getattr(self, "_deferred_work_cache_save_timer", None)
                if timer is not None:
                    timer.start(650)
                    return
            except Exception:
                pass
        try:
            self.auto_save_project()
        except Exception:
            pass

    def ensure_page_runtime_loaded(self, page_idx, *, include_ori=True, include_heavy=False, include_masks=False):
        try:
            page_idx = int(page_idx)
        except Exception:
            return
        if page_idx < 0 or page_idx >= len(getattr(self, "paths", []) or []):
            return
        curr = (getattr(self, "data", {}) or {}).get(page_idx)
        if not isinstance(curr, dict):
            return
        if include_ori and curr.get('ori') is None and not curr.get('use_inpainted_as_source'):
            try:
                curr['ori'] = cv2.imdecode(np.fromfile(self.paths[page_idx], np.uint8), 1)
            except Exception:
                curr['ori'] = None
            try:
                self.touch_page_image_cache(page_idx)
                self.trim_page_image_cache(keep_indices=[page_idx])
            except Exception:
                pass
        if include_heavy:
            loaded_any = False
            for field, path_key in (
                ('working_source', 'working_source_path'),
                ('bg_clean', 'clean_path'),
                ('final_paint', 'final_paint_path'),
                ('final_paint_above', 'final_paint_above_path'),
            ):
                if curr.get(field) is None and curr.get(path_key):
                    payload = self._read_binary_asset_bytes(curr.get(path_key))
                    if payload is not None:
                        curr[field] = payload
                        loaded_any = True
            if loaded_any:
                try:
                    self.touch_page_payload_cache(page_idx)
                    self.trim_page_payload_cache(keep_indices=[page_idx])
                except Exception:
                    pass
        if include_masks:
            try:
                self.ensure_page_masks_loaded(page_idx)
                self.touch_page_mask_cache(page_idx)
                self.trim_page_mask_cache(keep_indices=[page_idx])
            except Exception:
                pass

    def page_runtime_fully_loaded(self, page_idx):
        try:
            page_idx = int(page_idx)
        except Exception:
            return False
        curr = (getattr(self, "data", {}) or {}).get(page_idx) if getattr(self, "data", None) else None
        if not isinstance(curr, dict):
            return False
        # 백그라운드 순차 로더는 UI 렉 방지를 위해 원본 디코딩 정도만 선로딩한다.
        # clean/final_paint/working_source 같은 heavy payload는 실제로 해당 페이지를 열 때만 읽는다.
        if curr.get('ori') is None and not curr.get('use_inpainted_as_source'):
            return False
        return True

    def _ensure_progressive_page_loader(self):
        if not hasattr(self, '_progressive_page_load_queue') or self._progressive_page_load_queue is None:
            self._progressive_page_load_queue = []
        if not hasattr(self, '_progressive_page_load_timer') or self._progressive_page_load_timer is None:
            timer = QTimer(self)
            timer.setSingleShot(False)
            timer.setInterval(120)
            timer.timeout.connect(self._progressive_page_load_tick)
            self._progressive_page_load_timer = timer

    def stop_progressive_page_loader(self):
        try:
            timer = getattr(self, '_progressive_page_load_timer', None)
            if timer is not None:
                timer.stop()
        except Exception:
            pass
        self._progressive_page_load_queue = []

    def schedule_progressive_page_load(self, priority_index=None):
        self._ensure_progressive_page_loader()
        total = len(getattr(self, 'paths', []) or [])
        if total <= 1:
            return
        try:
            priority = int(self.idx if priority_index is None else priority_index)
        except Exception:
            priority = int(getattr(self, 'idx', 0) or 0)
        priority = max(0, min(priority, total - 1))
        ordered = list(range(priority, total)) + list(range(0, priority))
        queue = []
        seen = set()
        for i in ordered:
            if i == priority or i in seen:
                continue
            seen.add(i)
            if not self.page_runtime_fully_loaded(i):
                queue.append(i)
        self._progressive_page_load_queue = queue
        try:
            timer = getattr(self, '_progressive_page_load_timer', None)
            if timer is not None and queue:
                timer.start()
            elif timer is not None:
                timer.stop()
        except Exception:
            pass

    def _progressive_page_load_tick(self):
        if getattr(self, '_app_is_closing', False) or getattr(self, 'is_loading_project', False):
            return
        try:
            pause_until = float(getattr(self, "_progressive_page_load_pause_until", 0.0) or 0.0)
            if pause_until > __import__("time").time():
                return
        except Exception:
            pass
        queue = list(getattr(self, '_progressive_page_load_queue', []) or [])
        if not queue:
            try:
                timer = getattr(self, '_progressive_page_load_timer', None)
                if timer is not None:
                    timer.stop()
            except Exception:
                pass
            return
        page_idx = queue.pop(0)
        self._progressive_page_load_queue = queue
        try:
            self.ensure_page_runtime_loaded(page_idx, include_ori=True, include_heavy=False, include_masks=False)
        except Exception:
            pass
        if not self._progressive_page_load_queue:
            try:
                timer = getattr(self, '_progressive_page_load_timer', None)
                if timer is not None:
                    timer.stop()
            except Exception:
                pass

    def _ensure_page_image_cache_state(self):
        if not hasattr(self, "_page_image_cache_order") or self._page_image_cache_order is None:
            self._page_image_cache_order = OrderedDict()
        try:
            limit = int(getattr(self, "page_image_cache_limit", 3) or 3)
        except Exception:
            limit = 3
        self.page_image_cache_limit = max(1, limit)

    def touch_page_image_cache(self, page_idx):
        self._ensure_page_image_cache_state()
        try:
            page_idx = int(page_idx)
        except Exception:
            return
        self._page_image_cache_order.pop(page_idx, None)
        self._page_image_cache_order[page_idx] = True

    def trim_page_image_cache(self, keep_indices=None):
        self._ensure_page_image_cache_state()
        keep = set()
        try:
            keep.add(int(getattr(self, "idx", -1)))
        except Exception:
            pass
        for raw in list(keep_indices or []):
            try:
                keep.add(int(raw))
            except Exception:
                pass

        # 현재 메모리에 원본 이미지를 들고 있는 페이지들만 대상으로 LRU 정리
        loaded = []
        for page_idx, curr in list((getattr(self, "data", {}) or {}).items()):
            if isinstance(curr, dict) and isinstance(curr.get('ori'), np.ndarray):
                loaded.append(int(page_idx))
                if page_idx not in self._page_image_cache_order:
                    self._page_image_cache_order[page_idx] = True

        while len(loaded) > self.page_image_cache_limit:
            victim = None
            for candidate in list(self._page_image_cache_order.keys()):
                if candidate in keep:
                    continue
                curr = (getattr(self, "data", {}) or {}).get(candidate)
                if isinstance(curr, dict) and isinstance(curr.get('ori'), np.ndarray):
                    victim = candidate
                    break
                self._page_image_cache_order.pop(candidate, None)
            if victim is None:
                break
            curr = self.data.get(victim)
            if isinstance(curr, dict):
                curr['ori'] = None
            self._page_image_cache_order.pop(victim, None)
            loaded = [idx for idx in loaded if idx != victim]

    def _ensure_page_mask_cache_state(self):
        if not hasattr(self, "_page_mask_cache_order") or self._page_mask_cache_order is None:
            self._page_mask_cache_order = OrderedDict()
        try:
            limit = int(getattr(self, "page_mask_cache_limit", 3) or 3)
        except Exception:
            limit = 3
        self.page_mask_cache_limit = max(1, limit)

    def touch_page_mask_cache(self, page_idx):
        self._ensure_page_mask_cache_state()
        try:
            page_idx = int(page_idx)
        except Exception:
            return
        self._page_mask_cache_order.pop(page_idx, None)
        self._page_mask_cache_order[page_idx] = True

    def resolve_project_asset_path(self, path_value):
        if not path_value:
            return None
        try:
            p = str(path_value)
            if os.path.isabs(p):
                return p
            root = str(getattr(self, "project_dir", "") or "")
            if root:
                return os.path.join(root, p.replace("/", os.sep))
        except Exception:
            return None
        return None

    def load_mask_array_from_path(self, path_value):
        path = self.resolve_project_asset_path(path_value)
        if not path or not os.path.exists(path):
            return None
        try:
            return np.load(path).copy()
        except Exception as e:
            try:
                self.log(f"⚠️ 마스크 지연 로딩 실패: {e}")
            except Exception:
                pass
            return None

    def ensure_page_masks_loaded(self, page_idx, keys=None):
        if page_idx < 0 or page_idx >= len(getattr(self, "paths", []) or []):
            return
        curr = (getattr(self, "data", {}) or {}).get(page_idx)
        if not isinstance(curr, dict):
            return
        keys = keys or ("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off")
        loaded = []
        if hasattr(self, "mask_engine") and self.mask_engine is not None:
            try:
                loaded = self.mask_engine.load_missing_masks(curr, keys=keys, loader=self.load_mask_array_from_path)
            except Exception:
                loaded = []
        if not loaded:
            loaded_any = False
            for key in keys:
                if curr.get(key) is not None:
                    continue
                path_key = f"{key}_path"
                mask = self.load_mask_array_from_path(curr.get(path_key))
                if mask is not None:
                    curr[key] = mask
                    loaded_any = True
            if loaded_any:
                loaded = list(keys)
        if loaded:
            self.touch_page_mask_cache(page_idx)

    def trim_page_mask_cache(self, keep_indices=None):
        self._ensure_page_mask_cache_state()
        keep = set()
        try:
            keep.add(int(getattr(self, "idx", -1)))
        except Exception:
            pass
        for raw in list(keep_indices or []):
            try:
                keep.add(int(raw))
            except Exception:
                pass

        mask_keys = ("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off")
        loaded = []
        for page_idx, curr in list((getattr(self, "data", {}) or {}).items()):
            if isinstance(curr, dict) and any(isinstance(curr.get(k), np.ndarray) for k in mask_keys):
                loaded.append(int(page_idx))
                if page_idx not in self._page_mask_cache_order:
                    self._page_mask_cache_order[page_idx] = True

        while len(loaded) > self.page_mask_cache_limit:
            victim = None
            for candidate in list(self._page_mask_cache_order.keys()):
                if candidate in keep:
                    continue
                curr = (getattr(self, "data", {}) or {}).get(candidate)
                if isinstance(curr, dict) and any(isinstance(curr.get(k), np.ndarray) for k in mask_keys):
                    victim = candidate
                    break
                self._page_mask_cache_order.pop(candidate, None)
            if victim is None:
                break
            curr = self.data.get(victim)
            if isinstance(curr, dict):
                if hasattr(self, "mask_engine") and self.mask_engine is not None:
                    try:
                        self.mask_engine.unload_saved_masks(curr, keys=mask_keys)
                    except Exception:
                        pass
                else:
                    for k in mask_keys:
                        # path가 있는 저장된 마스크만 메모리에서 내린다.
                        if curr.get(f"{k}_path") and not curr.get(f"{k}_dirty"):
                            curr[k] = None
            self._page_mask_cache_order.pop(victim, None)
            loaded = [idx for idx in loaded if idx != victim]

    def write_page_mask_to_disk(self, page_idx, key, mask):
        if mask is None or not getattr(self, "project_dir", None):
            return None
        subdirs = {
            "mask_merge": ("masks", "text_mask", f"mask_merge_{page_idx + 1:04d}.npy"),
            "mask_inpaint": ("masks", "paint_mask", f"mask_inpaint_{page_idx + 1:04d}.npy"),
            "mask_merge_off": ("masks", "text_mask_off", f"mask_merge_off_{page_idx + 1:04d}.npy"),
            "mask_inpaint_off": ("masks", "paint_mask_off", f"mask_inpaint_off_{page_idx + 1:04d}.npy"),
        }
        parts = subdirs.get(key)
        if not parts:
            return None
        try:
            out_dir = os.path.join(str(self.project_dir), *parts[:-1])
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, parts[-1])
            np.save(out_path, np.array(mask, dtype=np.uint8).copy())
            return out_path
        except Exception as e:
            try:
                self.log(f"⚠️ 마스크 디스크 저장 실패({page_idx + 1}p/{key}): {e}")
            except Exception:
                pass
            return None

    def spill_payload_masks_to_disk(self, page_idx, curr, payload):
        if not isinstance(curr, dict) or not isinstance(payload, dict):
            return
        for key in ("mask_merge", "mask_inpaint"):
            value = payload.get(key)
            if not isinstance(value, np.ndarray):
                continue
            out_path = self.write_page_mask_to_disk(page_idx, key, value)
            if out_path:
                curr[f"{key}_path"] = out_path
                curr[f"{key}_dirty"] = False
                payload[f"{key}_path"] = out_path
                payload[key] = None

    def make_page_data_for_image(self, image_path, original_name=None):
        return {
            'ori': None,
            'data': [],
            'mask_merge': None,
            'mask_inpaint': None,
            'mask_merge_off': None,
            'mask_inpaint_off': None,
            'mask_merge_path': None,
            'mask_inpaint_path': None,
            'mask_merge_off_path': None,
            'mask_inpaint_off_path': None,
            'mask_toggle_enabled': False,
            'use_inpainted_as_source': False,
            'bg_clean': None,
            'working_source': None,
            'final_paint': None,
            'final_paint_above': None,
            'ocr_analysis_regions': [],
            'original_name': original_name or os.path.basename(image_path),
        }

    def insert_images_at_position(self, source_paths, insert_at=0, source_label="이미지 삽입"):
        source_paths = self.normalize_image_drop_paths(source_paths)
        if not source_paths:
            return False
        if not self.project_dir:
            return self.create_new_project_from_image_paths(source_paths, source_label=source_label)
        if not self.guard_project_action("이미지 삽입"):
            return False
        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        before_structure_state = self._snapshot_project_structure_state("이미지 삽입")
        insert_at = max(0, min(int(insert_at), len(self.paths)))
        copied_paths = []
        copied_data = []
        for src in source_paths:
            dst = self.unique_insert_image_path(src)
            shutil.copy2(src, dst)
            copied_paths.append(dst)
            copied_data.append(self.make_page_data_for_image(dst, original_name=os.path.basename(dst)))

        old_paths = list(self.paths)
        old_data = dict(self.data or {})
        self.paths = old_paths[:insert_at] + copied_paths + old_paths[insert_at:]
        new_data = {}
        for new_i in range(len(self.paths)):
            if new_i < insert_at:
                if new_i in old_data:
                    new_data[new_i] = old_data[new_i]
            elif new_i < insert_at + len(copied_data):
                new_data[new_i] = copied_data[new_i - insert_at]
            else:
                old_i = new_i - len(copied_data)
                if old_i in old_data:
                    new_data[new_i] = old_data[old_i]
        self.data = new_data

        states = getattr(self, "project_ui_view_states", {}) or {}
        shifted_states = {}
        for key, state in states.items():
            try:
                page_s, mode_s = str(key).split(":", 1)
                old_page = int(page_s)
                new_page = old_page + len(copied_data) if old_page >= insert_at else old_page
                shifted_states[f"{new_page}:{int(mode_s)}"] = copy.deepcopy(state)
            except Exception:
                pass
        self.project_ui_view_states = shifted_states
        self.idx = insert_at
        after_structure_state = self._snapshot_project_structure_state("이미지 삽입")
        self.undo_clear_all_pages("image insert")
        self.push_project_structure_command(before_structure_state, after_structure_state, reason="이미지 삽입", action="page_insert")
        # 이미지 추가는 구조 변경이다. 원본 파일은 이미 workspace/images에 복사되어 있으므로,
        # project.json도 즉시 저장해 JSON 열기/복구가 바로 같은 페이지 목록을 보게 한다.
        self.flush_workspace_structure_after_image_insert(reason="image_insert")
        self.load()
        self.log(f"🖼️ 이미지 {len(copied_paths)}장 삽입: {insert_at + 1}페이지부터")
        return True

    def insert_images_after_current(self, source_paths):
        insert_at = (self.idx + 1) if self.paths else 0
        return self.insert_images_at_position(source_paths, insert_at=insert_at, source_label="드래그 앤 드롭")

    def import_images_at_end_action(self):
        # 이전 버전 호환용: + 탭도 일반 이미지 불러오기와 같은 동작을 사용한다.
        return self.import_images_action()

    def _dragged_local_files(self, event):
        try:
            mime = event.mimeData()
            if not mime or not mime.hasUrls():
                return []
            out = []
            for url in mime.urls():
                path = url.toLocalFile()
                if path:
                    out.append(os.path.abspath(path))
            return out
        except Exception:
            return []

    def _dragged_image_paths(self, event):
        return self.normalize_image_drop_paths(self._dragged_local_files(event))

    def _dragged_supported_files(self, event):
        files = self._dragged_local_files(event)
        images = self.normalize_image_drop_paths(files)
        ysb = ""
        for path in files:
            if path and str(path).lower().endswith(YSB_EXTENSION):
                ysb = os.path.abspath(path)
                break
        return images, ysb

    def handle_supported_file_drop(self, event):
        images, ysb_path = self._dragged_supported_files(event)
        if images:
            if self.project_dir:
                return self.insert_images_after_current(images)
            return self.create_new_project_from_image_paths(images, source_label="드래그 앤 드롭")
        if ysb_path:
            if not self.guard_project_action("YSBT 파일 드래그 열기"):
                return False
            if not self.confirm_close_current_project_for_open(ysb_path):
                return False
            self.open_project_path(ysb_path, external_request=True)
            self.force_app_focus(reason="drag and drop open")
            return True
        return False

    def _dragged_ysbt_path(self, event):
        _images, ysb = self._dragged_supported_files(event)
        return ysb

    def dragEnterEvent(self, event):
        images, ysb = self._dragged_supported_files(event)
        if images or ysb:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        images, ysb = self._dragged_supported_files(event)
        if images or ysb:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        images, ysb = self._dragged_supported_files(event)
        if not images and not ysb:
            event.ignore()
            return
        event.acceptProposedAction()
        self.handle_supported_file_drop(event)

    def change_workspace_location(self):
        """옵션 메뉴에서 작업 폴더 설정 창을 다시 연다.

        첫 실행 설정창과 같은 UI를 쓰되, 닫기를 눌러도 프로그램은 종료하지 않는다.
        위치가 바뀐 경우에는 다음 실행 시 이동되도록 예약한다.
        """
        if not self.guard_project_action("작업 폴더 위치 변경"):
            return
        dlg = WorkspaceSetupDialog(self, first_run=False)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.workspace_root = str(get_workspace_root())
            self.log("📁 작업 폴더 설정 확인")
        else:
            self.log("📁 작업 폴더 설정 변경 취소")

    def reset_workspace_location_to_default(self, parent=None):
        """작업 폴더 위치를 Windows 실제 문서 폴더 기준 기본값으로 되돌린 뒤 재기동한다."""
        if not self.guard_project_action("작업 폴더 위치 기본값으로 변경"):
            return
        parent = parent or self
        target = default_workspace_root()
        try:
            current = Path(load_workspace_config().get("workspace_root") or get_workspace_root()).resolve()
            target_resolved = target.resolve()
        except Exception:
            current = Path(str(get_workspace_root()))
            target_resolved = target

        if current == target_resolved:
            set_workspace_root(target)
            QMessageBox.information(
                parent,
                self.tr_ui("설정 완료"),
                f"{self.tr_ui('작업 폴더 위치가 이미 기본값입니다.')}\n\n{target}",
            )
            self.log(f"📁 작업 폴더 기본값 확인: {target}")
            return

        if not workspace_restart_confirmation(parent, current, target, self.ui_language):
            self.log("📁 작업 폴더 기본값 변경 취소")
            return

        try:
            schedule_workspace_root_change(target)
            self.log(f"📁 작업 폴더 기본값 변경 예약 및 재기동: {target}")
            restart_application_detached()
        except Exception as e:
            QMessageBox.critical(
                parent,
                self.tr_ui("저장 실패"),
                f"{self.tr_ui('작업 폴더 위치를 기본값으로 변경하지 못했습니다.')}\n{e}",
            )

    def register_ysb_file_association(self):
        if not is_windows():
            QMessageBox.information(self, self.tr_ui("지원 안내"), self.tr_msg(".ysbt 확장자 연결 등록은 Windows에서만 지원합니다."))
            return
        if is_ysbt_file_association_registered():
            QMessageBox.information(self, self.tr_ui("이미 등록됨"), self.tr_msg(".ysbt 확장자가 현재 실행 중인 역식붕이 툴에 이미 연결되어 있습니다."))
            return

        if is_ysbt_file_association_registered_to_other_ysb():
            registered = get_registered_ysbt_file_association_command() or "알 수 없음"
            message = (
                ".ysbt 확장자가 다른 위치의 역식붕이 툴에 연결되어 있습니다.\n"
                "현재 실행 중인 프로그램으로 연결을 갱신할까요?\n\n"
                f"현재 등록된 실행 명령:\n{registered}\n\n"
                "이 작업은 Windows의 확장자 연결 정보만 현재 프로그램으로 덮어씁니다. 기존 .ysbt 프로젝트 파일은 변경되지 않습니다."
            )
        else:
            message = (
                "현재 사용자 계정에 .ysbt 확장자 연결을 등록합니다.\n"
                "등록 후 .ysbt 파일을 더블클릭하면 역식붕이 툴로 열립니다. 계속할까요?"
            )

        ans = QMessageBox.question(
            self,
            self.tr_ui(".ysbt 확장자 연결 등록"),
            self.tr_msg(message),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            register_ysbt_file_association_raw()
            QMessageBox.information(self, self.tr_ui("등록 완료"), self.tr_ui(".ysbt 확장자 연결을 현재 실행 중인 역식붕이 툴로 등록했습니다.\n아이콘 표시는 Windows 아이콘 캐시 때문에 조금 늦게 갱신될 수 있습니다."))
            self.log("🔗 .ysbt 확장자 연결 등록/갱신 완료")
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("등록 실패"), f"{self.tr_ui('.ysbt 확장자 연결 등록에 실패했습니다.')}\n{e}")

    def unregister_ysbt_file_association(self):
        """현재 사용자 계정에 등록된 .ysbt 연결을 제거한다.

        이전 테스트 버전에서 이 프로그램이 등록한 .ysb 연결도 함께 정리한다.
        단, 다른 프로그램에 연결된 .ysb는 변경하지 않는다.
        """
        if not is_windows():
            QMessageBox.information(self, self.tr_ui("지원 안내"), self.tr_ui("확장자 연결 해제는 Windows에서만 지원합니다."))
            return
        ans = QMessageBox.question(
            self,
            self.tr_ui("확장자 연결 해제"),
            self.tr_ui("현재 사용자 계정의 .ysbt 연결을 해제합니다.\n이전 테스트 버전에서 이 프로그램이 등록한 .ysb 연결도 함께 정리합니다.\n다른 프로그램에 연결된 .ysb는 변경하지 않습니다.\n\n계속할까요?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = unregister_ysbt_file_association_raw(include_legacy=True)
            msg = self.tr_ui("확장자 연결 해제를 완료했습니다.")
            if removed:
                msg += "\n\n" + self.tr_ui("제거 항목") + ":\n- " + "\n- ".join(removed)
            else:
                msg += "\n\n" + self.tr_ui("제거할 연결 항목이 없었습니다.")
            QMessageBox.information(self, self.tr_ui("해제 완료"), msg)
            self.log("🔗 확장자 연결 해제 완료: " + (", ".join(removed) if removed else "제거 항목 없음"))
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("해제 실패"), f"{self.tr_ui('확장자 연결 해제에 실패했습니다.')}\n{e}")

    def workspace_temp_project_dir(self, project_name="unsaved_project"):
        """새 프로젝트용 임시 작업 폴더를 만든다.

        v1.8 런처 이후에는 사용자가 작업 폴더를 문서/YSB_Translator로 잡아두었는지
        바로 확인할 수 있어야 하므로, 새 프로젝트의 임시 작업도 workspaces 아래에 만든다.
        아직 .ysbt로 저장되지 않은 상태라는 의미는 is_temp_project 플래그로 관리한다.
        """
        safe = safe_project_name(project_name)
        return unique_dir(workspaces_dir(), f"unsaved_{safe}_{uuid.uuid4().hex[:8]}")

    def workspace_project_dir(self, project_name="ysb_project", code=None, *, append_code=True):
        safe = clean_workspace_name(project_name)
        return unique_dir_with_code_suffix(workspaces_dir(), safe, code, append_code=append_code)

    def normalize_ysb_path(self, path):
        if not path:
            return path
        return path if path.lower().endswith(YSB_EXTENSION) else path + YSB_EXTENSION

    def current_package_default_path(self):
        base = getattr(self, "suggested_project_name", None) or (Path(self.project_dir).name if self.project_dir else "ysb_project")
        base = clean_workspace_name(base)
        try:
            package_dir = Path(getattr(self, "suggested_package_dir", None) or default_package_dir())
        except Exception:
            package_dir = default_package_dir()
        return str(package_dir / f"{safe_project_name(base)}{YSB_EXTENSION}")

    def delete_temp_project_if_needed(self):
        """저장되지 않은 임시 프로젝트 폴더를 안전하게 삭제한다.

        예전에는 임시 프로젝트가 temp 아래에만 있었지만, v1.8 런처 이후 새 프로젝트는
        사용자가 지정한 작업 폴더의 workspaces 아래에 unsaved_* 형태로 보이게 만든다.
        따라서 is_temp_project=True이고 아직 .ysbt 패키지에 연결되지 않은 경우에는
        temp/workspaces 내부의 unsaved_* 폴더를 정리한다.
        """
        if self.is_temp_project and self.project_dir and os.path.exists(self.project_dir):
            try:
                proj = os.path.abspath(self.project_dir)
                roots = [os.path.abspath(str(temp_dir()))]
                name = os.path.basename(proj)
                can_delete = (not getattr(self, "ysbt_package_path", None)) and name.startswith("unsaved_")
                if can_delete and any(proj.startswith(root) for root in roots):
                    shutil.rmtree(self.project_dir, ignore_errors=True)
                    self.log(f"🧹 임시 프로젝트 삭제: {self.project_dir}")
                elif can_delete:
                    self.log(f"🧷 workspaces 임시 프로젝트 자동 삭제 생략: {self.project_dir}")
            except Exception:
                pass
        self.is_temp_project = False

    def promote_temp_project_to_workspace(self, project_name=None):
        if not self.is_temp_project:
            return True
        if not self.project_dir or not os.path.exists(self.project_dir):
            return False

        name = clean_workspace_name(project_name or Path(self.project_dir).name)
        dst = self.workspace_project_dir(name)
        old_dir = self.project_dir
        try:
            # 현재 temp 프로젝트 저장 후, 새 폴더를 만들지 않고 temp 폴더 자체를 정식 작업 폴더로 승격한다.
            self.save_project_store(self.project_store)
            if os.path.abspath(old_dir) != os.path.abspath(dst):
                shutil.move(old_dir, dst)
            self.project_dir = dst
            self.project_store = ProjectStore(dst)
            # UUID는 manifest 내부에 유지하고, 폴더명/프로젝트명은 깔끔한 이름으로 갱신한다.
            self.project_store.write_manifest(project_name=name)
            self.is_temp_project = False

            # 혹시 이전 버전에서 workspaces 안에 unsaved_* 찌꺼기가 생겼다면,
            # 현재 승격한 폴더와 다른 빈/동일 임시 폴더만 안전하게 제거한다.
            try:
                ws_root = os.path.abspath(str(workspaces_dir()))
                old_abs = os.path.abspath(old_dir)
                dst_abs = os.path.abspath(dst)
                if old_abs.startswith(ws_root) and os.path.basename(old_abs).startswith("unsaved_") and old_abs != dst_abs and os.path.exists(old_abs):
                    # workspaces는 복구 기준 작업 공간이므로 자동 삭제하지 않는다.
                    pass
            except Exception:
                pass

            self.reload_saved_project_from_disk(refresh_view=False)
            self.log(f"📦 임시 프로젝트를 작업 폴더로 승격: {dst}")
            return True
        except Exception as e:
            msg_text = self.tr_ui("임시 프로젝트를 작업 폴더로 옮기지 못했습니다.")
            QMessageBox.critical(self, self.tr_ui("프로젝트 이동 실패"), f"{msg_text}\n{e}")
            return False

    def workspace_state_path_for_project_dir(self, project_dir):
        try:
            project_dir = os.path.abspath(str(project_dir or ""))
            if not project_dir:
                return None
            return os.path.join(project_dir, WORKSPACE_STATE_FILENAME)
        except Exception:
            return None

    def write_workspace_state_for_project(self, project_dir, *, is_dirty=True):
        """복구용 별도 캐시를 만들지 않고, workspace 자체에 작은 상태표만 붙인다."""
        try:
            if not project_dir:
                return
            project_dir = os.path.abspath(str(project_dir))
            if not os.path.exists(os.path.join(project_dir, PROJECT_FILENAME)):
                return

            dirty_pages = []
            dirty_summary = {}
            dirty_by_kind = {}
            try:
                if hasattr(self, "project_engine") and self.project_engine is not None:
                    dirty_pages = sorted(int(x) for x in self.project_engine.dirty_page_indices())
                    try:
                        dirty_summary = self.project_engine.dirty_summary()
                    except Exception:
                        dirty_summary = {}
            except Exception:
                dirty_pages = []
                dirty_summary = {}
            try:
                raw_dirty = dirty_summary.get("dirty_pages", {}) if isinstance(dirty_summary, dict) else {}
                if isinstance(raw_dirty, dict):
                    for page_key, kinds in raw_dirty.items():
                        try:
                            page_i = int(page_key)
                        except Exception:
                            continue
                        for kind in list(kinds or []):
                            kind_s = str(kind or "data")
                            dirty_by_kind.setdefault(kind_s, []).append(page_i)
                    dirty_by_kind = {k: sorted(set(v)) for k, v in dirty_by_kind.items()}
            except Exception:
                dirty_by_kind = {}

            write_workspace_state(
                project_dir,
                source_ysbt_path=str(getattr(self, "ysbt_package_path", "") or ""),
                project_name=str(getattr(self, "suggested_project_name", "") or Path(project_dir).name),
                is_dirty=bool(is_dirty),
                is_recovery=bool(is_dirty),
                dirty_pages=dirty_pages,
                dirty_by_kind=dirty_by_kind,
                text_dirty_pages=sorted(set(dirty_by_kind.get("text", []) + dirty_by_kind.get("checkpoint_text", []) + dirty_by_kind.get("checkpoint_fallback", []))),
                clean_dirty_pages=sorted(set(dirty_by_kind.get("clean_background", []) + dirty_by_kind.get("clean_import", []) + dirty_by_kind.get("final_paint", []))),
                mask_dirty_pages=sorted(set(dirty_by_kind.get("mask", []) + dirty_by_kind.get("mask_merge", []) + dirty_by_kind.get("mask_inpaint", []))),
                last_page_index=int(getattr(self, "idx", 0) or 0),
                last_mode=int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else 0,
            )
        except Exception:
            pass

    def mark_workspace_state_saved(self, project_dir):
        try:
            if not project_dir:
                return
            self.write_workspace_state_for_project(project_dir, is_dirty=False)
        except Exception:
            pass

    def is_path_under_root(self, path, root):
        try:
            p = Path(str(path)).resolve()
            r = Path(str(root)).resolve()
            return str(p).lower() == str(r).lower() or str(p).lower().startswith(str(r).lower() + os.sep)
        except Exception:
            return False

    def is_workspace_project_dir_path(self, path):
        try:
            if not path:
                return False
            p = Path(str(path)).resolve()
            return self.is_path_under_root(p, workspaces_dir()) and (p / PROJECT_FILENAME).exists()
        except Exception:
            return False

    def record_recovery_project_dir(self, project_dir):
        """마지막 작업 폴더를 기록한다. 복구 데이터 본체는 이 workspace 자체다."""
        try:
            if not project_dir:
                return
            project_dir = os.path.abspath(str(project_dir))
            if not os.path.exists(os.path.join(project_dir, PROJECT_FILENAME)):
                return
            self.app_options["last_recovery_project_dir"] = project_dir
            save_app_options(self.app_options)
            self.write_workspace_state_for_project(project_dir, is_dirty=True)
        except Exception:
            pass

    def recovery_candidate_roots(self):
        # 새 구조에서는 workspaces가 실제 작업대이자 복구본이다.
        # workspaces는 위의 상태표 스캔에서 dirty/(복구) 폴더만 골라 보고,
        # 여기서는 temp와 구버전 work_sessions 호환 후보만 전체 검색한다.
        return [temp_dir(), self.project_cache_root()]

    def find_recovery_candidates(self):
        """work_sessions/temp 안에서 project.json 또는 pending 클린본 복구 후보를 최신순으로 찾는다."""
        candidates = []
        seen = set()

        def candidate_key(project_dir, pending_dir=None):
            try:
                return (str(Path(str(project_dir)).resolve()), str(Path(str(pending_dir)).resolve()) if pending_dir else "")
            except Exception:
                return (str(project_dir), str(pending_dir or ""))

        def add_candidate(path, pending_dir=None, mtime_hint=None):
            try:
                p = Path(path)
                project_file = p / PROJECT_FILENAME
                if not project_file.exists():
                    return
                key = candidate_key(str(p), pending_dir)
                if key in seen:
                    return
                seen.add(key)
                try:
                    mtime = max(project_file.stat().st_mtime, p.stat().st_mtime)
                except Exception:
                    mtime = p.stat().st_mtime if p.exists() else 0
                if mtime_hint:
                    try:
                        mtime = max(float(mtime), float(mtime_hint))
                    except Exception:
                        pass
                # 4번째 값은 pending 클린본 복구 폴더다. 구 후보는 None.
                candidates.append((mtime, str(p), str(project_file), str(pending_dir) if pending_dir else None))
            except Exception:
                pass

        def add_pending_candidate(pending_base):
            """pending_clean_import_map.json만 있는 후보도 원본 프로젝트와 엮어 복구 후보로 등록한다."""
            try:
                if not pending_base:
                    return
                pending_base = os.path.abspath(str(pending_base))
                manifest_path = self.pending_clean_import_manifest_path(pending_base)
                if not manifest_path or not os.path.exists(manifest_path):
                    return
                manifest = self.load_pending_clean_import_manifest(pending_base)
                pages = manifest.get("pages") if isinstance(manifest, dict) else None
                if not isinstance(pages, dict) or not pages:
                    return
                mtime_hint = None
                try:
                    mtime_hint = os.path.getmtime(manifest_path)
                except Exception:
                    pass

                # 가장 안전한 순서:
                # 1) pending_base 자체에 project.json이 있으면 그 폴더를 복구
                # 2) manifest에 기록된 원래 project_dir/work_project_dir의 project.json을 복구
                roots = [pending_base]
                for key in ("project_dir", "work_project_dir"):
                    value = str(manifest.get(key) or "").strip()
                    if value:
                        roots.append(value)
                for root in roots:
                    try:
                        root = os.path.abspath(str(root))
                    except Exception:
                        continue
                    if os.path.exists(os.path.join(root, PROJECT_FILENAME)):
                        add_candidate(root, pending_dir=pending_base, mtime_hint=mtime_hint)
                        return
            except Exception:
                pass

        # 1순위: 마지막 작업 캐시로 명시 기록한 폴더
        last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "").strip()
        if last_dir:
            add_candidate(last_dir)
            add_pending_candidate(last_dir)

        # 1.5순위: 클린본 pending 복구 후보로 명시 기록한 폴더
        last_pending_dir = str((self.app_options or {}).get("last_pending_clean_import_dir") or "").strip()
        if last_pending_dir:
            add_pending_candidate(last_pending_dir)

        # 2순위: workspaces의 상태표 검색
        try:
            ws_root = Path(workspaces_dir())
            if ws_root.exists():
                for child in ws_root.iterdir():
                    if not child.is_dir():
                        continue
                    state_path = child / WORKSPACE_STATE_FILENAME
                    state = {}
                    try:
                        if state_path.exists():
                            with open(state_path, "r", encoding="utf-8") as f:
                                loaded = json.load(f)
                            state = loaded if isinstance(loaded, dict) else {}
                    except Exception:
                        state = {}
                    is_dirty = bool(state.get("is_dirty", False)) or "(복구)" in child.name
                    if is_dirty:
                        mtime_hint = None
                        try:
                            mtime_hint = max(state_path.stat().st_mtime, child.stat().st_mtime) if state_path.exists() else child.stat().st_mtime
                        except Exception:
                            pass
                        add_candidate(child, mtime_hint=mtime_hint)
        except Exception:
            pass

        # 2.5순위: 구버전 work_sessions marker 호환 검색
        try:
            marker_root = self.project_cache_root()
            for marker in marker_root.glob("recovery_marker_*.json"):
                try:
                    with open(marker, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    project_dir = str(payload.get("project_dir") or "").strip()
                    if project_dir:
                        add_candidate(project_dir, mtime_hint=os.path.getmtime(marker))
                except Exception:
                    pass
        except Exception:
            pass

        # 3순위: workspaces / temp / 구 work cache 폴더 전체 검색
        for root in self.recovery_candidate_roots():
            try:
                root = Path(root)
                if not root.exists():
                    continue
                for child in root.iterdir():
                    if child.is_dir():
                        add_candidate(child)
                        add_pending_candidate(child)
            except Exception:
                pass

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates

    def recover_last_work_project(self):
        """마지막 작업 캐시/임시 프로젝트를 열어 복구한다."""
        if not self.guard_project_action("마지막 작업 복구"):
            return
        candidates = self.find_recovery_candidates()
        if not candidates:
            QMessageBox.information(
                self,
                self.tr_ui("복구할 작업 없음"),
                self.tr_ui("복구할 수 있는 임시 작업 파일을 찾지 못했습니다."),
            )
            self.log("⚠️ 복구할 임시 작업 파일 없음")
            return

        first = candidates[0]
        if len(first) >= 4:
            _mtime, project_dir, project_file, pending_clean_dir = first[:4]
        else:
            _mtime, project_dir, project_file = first[:3]
            pending_clean_dir = None
        msg = (
            f"{self.tr_ui('마지막 작업 폴더를 복구할까요?')}\n\n"
            f"{project_dir}\n\n"
            f"{self.tr_ui('복구한 작업은 아직 정식 YSBT 파일이 아닐 수 있습니다. 필요한 경우 [프로젝트 저장]으로 다시 저장해 주세요.')}"
        )
        ans = QMessageBox.question(
            self,
            self.tr_ui("마지막 작업 복구"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 마지막 작업 복구 취소")
            return

        if not self.confirm_unsaved_before_switch():
            return

        shown_overlay = False
        old_load_progress = getattr(self, "_project_load_progress_callback", None)
        old_loading_recovery = bool(getattr(self, "_loading_recovery_project", False))
        self._long_task_cancel_requested = False
        self._active_long_task_kind = "recover"

        def _recover_progress(current=0, total=100, detail="복구 준비 중..."):
            try:
                show_total = max(1, int(total or 100))
                show_current = max(0, min(show_total, int(current or 0)))
                folder_name = os.path.basename(str(project_dir))
                formatted = (
                    f"{self.tr_ui('복구 폴더')}: {folder_name}\n"
                    f"{str(detail or '')}"
                )
                self.update_task_progress_overlay(current=show_current, total=show_total, detail=formatted)
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            except Exception:
                pass

        try:
            self.begin_busy_state("마지막 작업 복구")
            self.show_task_progress_overlay(
                "마지막 작업 복구",
                f"{self.tr_ui('복구 폴더')}: {os.path.basename(str(project_dir))}\n복구 준비 중...",
                total=100,
                cancellable=False,
            )
            shown_overlay = True
            try:
                overlay = getattr(self, "_task_progress_overlay", None)
                if overlay is not None:
                    overlay.note_label.setText("복구 중에는 프로젝트 데이터를 읽고 화면을 다시 구성합니다.")
            except Exception:
                pass
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

            self._loading_recovery_project = True
            self._project_load_progress_callback = _recover_progress

            _recover_progress(8, 100, "복구 프로젝트 파일을 읽는 중...")
            # 복구는 별도 캐시를 여는 것이 아니라, 남아 있는 workspace 작업대를 직접 여는 것이다.
            # 상태표에 원본 .ysbt가 있으면 그대로 연결해 [프로젝트 저장]으로 확정할 수 있게 한다.
            workspace_state = {}
            try:
                workspace_state = read_workspace_state(project_dir)
            except Exception:
                workspace_state = {}
            source_package = str(workspace_state.get("source_ysbt_path") or workspace_state.get("package_path") or "").strip() if isinstance(workspace_state, dict) else ""
            if source_package and not os.path.exists(source_package):
                source_package = ""
            self.load_project_json(project_file, package_path=source_package or None, temp_project=False)

            if pending_clean_dir:
                try:
                    _recover_progress(86, 100, "pending 클린본 복구를 적용하는 중...")
                    restored = self.apply_pending_clean_import_if_available(pending_clean_dir)
                    if restored:
                        self.log(f"🧯 pending 클린본 복구 추가 적용: {restored}페이지")
                except Exception as e:
                    self.log(f"⚠️ pending 클린본 복구 추가 적용 실패: {e}")

            _recover_progress(94, 100, "복구 상태를 정리하는 중...")
            if source_package:
                self.ysbt_package_path = source_package
                self.is_temp_project = False
            else:
                self.is_temp_project = True
            self.has_unsaved_changes = True
            self.record_recovery_project_dir(project_dir)
            try:
                if pending_clean_dir:
                    self.app_options["last_pending_clean_import_dir"] = str(pending_clean_dir)
                    save_app_options(self.app_options)
            except Exception:
                pass
            self.update_window_title()
            self.log(f"🧯 마지막 작업 복구 완료: {project_dir}")
            self.log("💾 복구한 작업은 [프로젝트 저장] 또는 [다른 이름으로 저장]으로 YSBT 파일에 확정하세요.")
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("복구 실패"),
                f"{self.tr_ui('마지막 작업을 복구하지 못했습니다.')}\n{project_dir}\n\n{e}",
            )
            self.log(f"❌ 마지막 작업 복구 실패: {e}")
        finally:
            try:
                self._project_load_progress_callback = old_load_progress
            except Exception:
                pass
            try:
                self._loading_recovery_project = old_loading_recovery
            except Exception:
                pass
            try:
                self._active_long_task_kind = ""
                self._long_task_cancel_requested = False
            except Exception:
                pass
            try:
                if shown_overlay:
                    self.hide_task_progress_overlay()
            except Exception:
                pass
            try:
                self.end_busy_state()
            except Exception:
                pass

    def temp_path_created_timestamp(self, path):
        """폴더 생성 시각을 우선 사용하고, 불가능하면 수정 시각을 사용한다."""
        try:
            return Path(path).stat().st_ctime
        except Exception:
            try:
                return Path(path).stat().st_mtime
            except Exception:
                return 0

    def temp_cleanup_category_roots(self):
        return [
            ("temp", self.tr_ui("임시 프로젝트"), temp_dir()),
            ("work_sessions", self.tr_ui("작업 캐시"), self.project_cache_root()),
        ]

    def empty_temp_cleanup_summary(self):
        return {
            "temp": {"label": self.tr_ui("임시 프로젝트"), "count": 0, "size": 0},
            "work_sessions": {"label": self.tr_ui("작업 캐시"), "count": 0, "size": 0},
        }

    def format_size_mb(self, size_bytes):
        try:
            return f"{float(size_bytes or 0) / (1024 * 1024):.1f} MB"
        except Exception:
            return "0.0 MB"

    def collect_temp_cleanup_targets(self, *, older_than_days=None, skip_current=True, exclude_recovery=False):
        """temp/work_sessions에서 삭제 가능한 임시 작업 폴더를 분류별로 모은다."""
        skip_dirs = set()
        if skip_current:
            for p in (getattr(self, "project_dir", None), getattr(self, "work_project_dir", None)):
                if p:
                    try:
                        skip_dirs.add(str(Path(p).resolve()))
                    except Exception:
                        pass

        if exclude_recovery:
            try:
                last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "").strip()
                if last_dir:
                    skip_dirs.add(str(Path(last_dir).resolve()))
            except Exception:
                pass

        now_ts = time.time()
        max_age_seconds = None
        if older_than_days is not None:
            try:
                max_age_seconds = max(0, int(older_than_days)) * 24 * 60 * 60
            except Exception:
                max_age_seconds = None

        targets = []
        total_size = 0
        summary = self.empty_temp_cleanup_summary()

        for key, label, root in self.temp_cleanup_category_roots():
            try:
                root = Path(root)
                if not root.exists():
                    continue
                for child in root.iterdir():
                    if not child.is_dir():
                        continue
                    try:
                        resolved = str(child.resolve())
                    except Exception:
                        resolved = str(child)
                    if resolved in skip_dirs:
                        continue

                    if max_age_seconds is not None:
                        created_ts = self.temp_path_created_timestamp(child)
                        if created_ts and (now_ts - created_ts) < max_age_seconds:
                            continue

                    folder_size = 0
                    try:
                        for file in child.rglob("*"):
                            if file.is_file():
                                folder_size += file.stat().st_size
                    except Exception:
                        pass

                    targets.append(child)
                    total_size += folder_size
                    summary.setdefault(key, {"label": label, "count": 0, "size": 0})
                    summary[key]["label"] = label
                    summary[key]["count"] += 1
                    summary[key]["size"] += folder_size
            except Exception:
                pass

        return targets, total_size, summary

    def temp_cleanup_summary_text(self, summary, total_count=None, total_size=None):
        summary = summary or self.empty_temp_cleanup_summary()
        temp_info = summary.get("temp", {})
        work_info = summary.get("work_sessions", {})
        if total_count is None:
            total_count = int(temp_info.get("count", 0) or 0) + int(work_info.get("count", 0) or 0)
        if total_size is None:
            total_size = int(temp_info.get("size", 0) or 0) + int(work_info.get("size", 0) or 0)
        return (
            f"{self.tr_ui('임시 프로젝트')}: {int(temp_info.get('count', 0) or 0)} / {self.format_size_mb(temp_info.get('size', 0))}\n"
            f"{self.tr_ui('작업 캐시')}: {int(work_info.get('count', 0) or 0)} / {self.format_size_mb(work_info.get('size', 0))}\n"
            f"{self.tr_ui('총합')}: {int(total_count or 0)} / {self.format_size_mb(total_size)}"
        )

    def temp_cleanup_period_options(self):
        return [
            (7, "일주일"),
            (30, "한달"),
            (90, "3개월"),
            (180, "6개월"),
            (365, "12개월"),
        ]

    def get_temp_auto_cleanup_days(self):
        try:
            days = int((self.app_options or {}).get("temp_auto_cleanup_days", 7) or 7)
        except Exception:
            days = 7
        if days not in (7, 30, 90, 180, 365):
            days = 7
        return days

    def is_temp_auto_cleanup_enabled(self):
        return bool((self.app_options or {}).get("temp_auto_cleanup_enabled", True))

    def set_temp_cleanup_options(self, enabled=None, days=None):
        try:
            if enabled is not None:
                self.app_options["temp_auto_cleanup_enabled"] = bool(enabled)
            if days is not None:
                days = int(days)
                if days not in (7, 30, 90, 180, 365):
                    days = 7
                self.app_options["temp_auto_cleanup_days"] = days
            save_app_options(self.app_options)
        except Exception:
            pass

    def auto_cleanup_temp_files_if_needed(self):
        """설정된 주기마다, 설정된 기간 이상 지난 임시 작업 폴더를 자동 삭제한다."""
        try:
            if not self.is_temp_auto_cleanup_enabled():
                self.log(
                    "🧹 Auto temp cleanup is disabled."
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    "🧹 자동 임시 파일 정리: 꺼짐"
                )
                return

            period_days = self.get_temp_auto_cleanup_days()
            max_age_days = period_days
            now_ts = time.time()
            last_ts = float((self.app_options or {}).get("last_temp_auto_cleanup_at", 0) or 0)
            if last_ts and (now_ts - last_ts) < period_days * 24 * 60 * 60:
                return

            # 자동 정리는 AppData 실행 캐시 + 오래된 임시 작업/복구 캐시를 대상으로 한다.
            # 최근 프로젝트/설정/개인정보와 실제 작업 폴더(workspaces)는 절대 자동 삭제하지 않는다.
            targets, total_size, summary = self.collect_auto_cache_cleanup_targets(older_than_days=max_age_days)
            temp_targets, temp_size, temp_summary = self.collect_temp_cleanup_targets(
                older_than_days=max_age_days,
                skip_current=True,
                exclude_recovery=False,
            )
            targets.extend(temp_targets)
            total_size += int(temp_size or 0)
            for key, info in (temp_summary or {}).items():
                if int((info or {}).get("count", 0) or 0) <= 0 and int((info or {}).get("size", 0) or 0) <= 0:
                    continue
                dst = summary.setdefault(key, {"label": (info or {}).get("label") or key, "count": 0, "size": 0})
                dst["label"] = (info or {}).get("label") or dst.get("label") or key
                dst["count"] += int((info or {}).get("count", 0) or 0)
                dst["size"] += int((info or {}).get("size", 0) or 0)

            deleted, failed = self.cleanup_delete_paths(targets)

            try:
                last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "")
                if last_dir and not os.path.exists(last_dir):
                    self.app_options.pop("last_recovery_project_dir", None)
            except Exception:
                pass

            self.app_options["last_temp_auto_cleanup_at"] = now_ts
            self.app_options["temp_auto_cleanup_enabled"] = True
            self.app_options["temp_auto_cleanup_days"] = period_days
            save_app_options(self.app_options)

            if deleted or failed:
                size_mb = total_size / (1024 * 1024)
                self.log(
                    f"🧹 Auto cache cleanup: deleted {deleted}, failed {failed}, approx. {size_mb:.1f} MB / period {period_days} days"
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    f"🧹 자동 캐시 정리: 삭제 {deleted}개 / 실패 {failed}개 / 약 {size_mb:.1f} MB / 주기 {period_days}일"
                )
            else:
                self.log(
                    "🧹 Auto cache cleanup: no old cache files."
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    "🧹 자동 캐시 정리: 오래된 캐시 없음"
                )
        except Exception as e:
            try:
                self.log(
                    f"⚠️ Auto temp cleanup failed: {e}"
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    f"⚠️ 자동 임시 파일 정리 실패: {e}"
                )
                _save_ui_diag("MESSAGEBOX_DONE_CLOSED")
            except Exception as e:
                _save_ui_diag("MESSAGEBOX_DONE_EXCEPTION", error=repr(e))
                pass

    def delete_temp_files_now(self, parent=None):
        """현재 작업과 연결되지 않은 temp/work_sessions 임시 파일을 즉시 삭제한다."""
        targets, total_size, summary = self.collect_temp_cleanup_targets(
            older_than_days=None,
            skip_current=True,
            exclude_recovery=False,
        )

        if not targets:
            QMessageBox.information(
                parent or self,
                self.tr_ui("삭제할 임시 파일 없음"),
                self.tr_ui("삭제할 수 있는 임시 작업 파일이 없습니다."),
            )
            self.log("🧹 삭제할 임시 작업 파일 없음")
            return False

        msg = (
            f"{self.tr_ui('현재 열려 있는 작업을 제외한 임시 작업 폴더를 삭제합니다.')}\n\n"
            f"{self.temp_cleanup_summary_text(summary, len(targets), total_size)}\n\n"
            f"{self.tr_ui('삭제 후에는 해당 임시 작업을 복구할 수 없습니다. 계속할까요?')}"
        )
        ans = QMessageBox.question(
            parent or self,
            self.tr_ui("임시 파일 삭제"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 임시 파일 삭제 취소")
            return False

        deleted = 0
        failed = 0
        for path in targets:
            try:
                shutil.rmtree(path, ignore_errors=False)
                deleted += 1
            except Exception:
                failed += 1

        # 삭제한 폴더가 마지막 복구 기록이면 기록도 비운다.
        try:
            last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "")
            if last_dir and not os.path.exists(last_dir):
                self.app_options.pop("last_recovery_project_dir", None)
                save_app_options(self.app_options)
        except Exception:
            pass

        self.log(f"🧹 임시 파일 삭제 완료: {deleted}개 삭제 / {failed}개 실패")
        QMessageBox.information(
            parent or self,
            self.tr_ui("임시 파일 삭제 완료"),
            self.tr_ui(f"임시 파일 삭제가 완료되었습니다.\n삭제: {deleted}개\n실패: {failed}개"),
        )
        return True

    def cleanup_entry_size(self, path):
        """삭제 후보 1개의 파일/폴더 수와 용량을 계산한다."""
        try:
            path = Path(path)
        except Exception:
            return 0, 0, 0
        if not path.exists():
            return 0, 0, 0
        file_count = 0
        dir_count = 0
        total_size = 0
        try:
            if path.is_file():
                return 1, 0, int(path.stat().st_size)
            if path.is_dir():
                dir_count += 1
                for child in path.rglob("*"):
                    try:
                        if child.is_file():
                            file_count += 1
                            total_size += int(child.stat().st_size)
                        elif child.is_dir():
                            dir_count += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return file_count, dir_count, total_size

    def cleanup_open_folder(self, path):
        """사용자 데이터/캐시 폴더를 OS 파일 탐색기로 연다."""
        try:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            QMessageBox.warning(self, self.tr_ui("폴더 열기 실패"), f"{self.tr_ui('폴더를 열지 못했습니다.')}\n{path}\n\n{e}")

    def cleanup_delete_path(self, path):
        try:
            path = Path(path)
            if not path.exists():
                return True
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=False)
            else:
                path.unlink()
            return True
        except Exception:
            return False

    def collect_user_data_cleanup_entries(self):
        """사용자에게 보여줄 정리 항목을 대분류로만 만든다.

        내부 파일 종류를 그대로 노출하지 않는다.
        temp/work_sessions 임시 작업 캐시는 용량이 커질 수 있으므로 이 창에서 먼저 보여준다.
        실제 작업 폴더(workspaces)는 별도의 [작업 폴더 용량 관리] 창에서 확인 후 삭제한다.
        """
        entries = []
        try:
            app_root = Path(app_config_dir())
        except Exception:
            app_root = Path.home() / ".YSB_Translator"
        try:
            workspace_root = Path(get_workspace_root())
        except Exception:
            workspace_root = Path(getattr(self, "workspace_root", "") or default_workspace_root())
        cache_root = workspace_root / "cache"

        def temp_work_session_cleanup_paths():
            try:
                targets, _total_size, _summary = self.collect_temp_cleanup_targets(
                    older_than_days=None,
                    skip_current=True,
                    exclude_recovery=False,
                )
                return list(targets or [])
            except Exception:
                return []

        def existing_paths(paths):
            out = []
            for item in paths or []:
                try:
                    pp = Path(item)
                    if pp.exists():
                        out.append(pp)
                except Exception:
                    pass
            return out

        def entry_size(paths):
            file_count = 0
            dir_count = 0
            total_size = 0
            for pp in existing_paths(paths):
                fc, dc, sz = self.cleanup_entry_size(pp)
                file_count += fc
                dir_count += dc
                total_size += sz
            return file_count, dir_count, total_size

        def add_group(key, label, desc, paths, *, manual_only=False, sensitive=False, open_path=None):
            paths = existing_paths(paths)
            files, dirs, size = entry_size(paths)
            entries.append({
                "key": key,
                "label": self.tr_ui(label),
                "desc": self.tr_ui(desc),
                "paths": paths,
                "files": files,
                "dirs": dirs,
                "size": size,
                "manual_only": bool(manual_only),
                "sensitive": bool(sensitive),
                "open_path": Path(open_path) if open_path else None,
            })

        # 1. 임시 작업/복구 캐시: temp + cache/work_sessions. 실제로 용량을 가장 많이 먹을 수 있으므로 최상단에 보여준다.
        add_group(
            "temp_work_sessions",
            "임시 작업/복구 캐시 삭제",
            "자동 정리 대상이지만 용량이 클 수 있어 직접 삭제할 수도 있습니다. 현재 열려 있는 작업은 제외됩니다.",
            temp_work_session_cleanup_paths(),
            manual_only=False,
            open_path=app_root,
        )

        # 2. AppData 캐시: PC별 런처/로그/런타임 상태. 작업 폴더 위치 설정은 설정 정보로 분리한다.
        add_group(
            "appdata_cache",
            "AppData 캐시 삭제",
            "실행 로그, 런처 상태, 앱 실행 중 생긴 임시 데이터입니다.",
            [
                app_root / "runtime",
                app_root / "logs",
                app_root / "restart_logs",
                app_root / "ysb_launcher.log",
                app_root / "open_queue.jsonl",
                app_root / "launcher_launch_stats.json",
                app_root / "association_preflight.json",
            ],
            manual_only=False,
            open_path=app_root,
        )

        # 3. 최근 프로젝트 정보: 자동 삭제 금지. 사용자가 직접 누를 때만 삭제한다.
        add_group(
            "recent_projects",
            "최근 프로젝트 정보 삭제",
            "최근 열었던 프로젝트 목록과 홈 화면 썸네일 정보입니다. 프로젝트 파일 자체는 삭제하지 않습니다.",
            [
                cache_root / "recent_projects.json",
                cache_root / "recent_thumbnails",
            ],
            manual_only=True,
        )

        # 4. 설정 정보: 자동 삭제 금지. 초기화 성격이므로 수동 삭제 전용.
        add_group(
            "settings_info",
            "설정 정보 삭제",
            "언어, 테마, 단축키, 프리셋, 작업 폴더 위치 같은 사용자 설정입니다.",
            [
                app_root / "workspace_config.json",
                cache_root / "app_options.json",
                cache_root / "shortcut_cache.json",
                cache_root / "text_preset",
                cache_root / "item_text_preset",
                cache_root / "macro_settings.json",
            ],
            manual_only=True,
        )

        # 5. 개인정보: API/클라우드 토큰. 자동 삭제 금지.
        add_group(
            "privacy_info",
            "개인정보 삭제",
            "API 키, 클라우드 로그인 토큰, 클라우드 백업 설정 같은 민감 정보입니다.",
            [
                cache_root / "api_cache.json",
                cache_root / "cloud" / "google_drive_token.json",
                cache_root / "cloud" / "google_oauth_client_secret.json",
                cache_root / "cloud" / "cloud_config.json",
            ],
            manual_only=True,
            sensitive=True,
        )

        return entries, app_root, workspace_root

    def collect_auto_cache_cleanup_targets(self, older_than_days=None):
        """자동 정리 대상 중 AppData 실행 캐시를 모은다.

        temp/work_sessions 임시 작업/복구 캐시는 auto_cleanup_temp_files_if_needed()에서
        별도로 collect_temp_cleanup_targets()를 통해 함께 정리한다.
        workspaces 아래의 실제 작업 폴더는 실사용 데이터이므로 자동 삭제 대상에 넣지 않는다.
        """
        entries, _app_root, _workspace_root = self.collect_user_data_cleanup_entries()
        auto_entries = [e for e in entries if e.get("key") in ("appdata_cache",)]
        now_ts = time.time()
        max_age_seconds = None
        if older_than_days is not None:
            try:
                max_age_seconds = max(0, int(older_than_days)) * 24 * 60 * 60
            except Exception:
                max_age_seconds = None

        targets = []
        total_size = 0
        summary = {}

        def add_target(path, group_key, label):
            nonlocal total_size
            try:
                pp = Path(path)
            except Exception:
                return
            if not pp.exists():
                return
            if max_age_seconds is not None:
                try:
                    ts = self.temp_path_created_timestamp(pp)
                    if ts and (now_ts - ts) < max_age_seconds:
                        return
                except Exception:
                    pass
            fc, dc, sz = self.cleanup_entry_size(pp)
            targets.append(pp)
            total_size += int(sz or 0)
            info = summary.setdefault(group_key, {"label": label, "count": 0, "size": 0})
            info["count"] += 1
            info["size"] += int(sz or 0)

        for e in auto_entries:
            label = e.get("label") or e.get("key")
            key = e.get("key") or label
            for pp in e.get("paths") or []:
                add_target(pp, key, label)
        return targets, total_size, summary

    def cleanup_delete_paths(self, paths):
        deleted = 0
        failed = 0
        for pp in paths or []:
            if self.cleanup_delete_path(pp):
                deleted += 1
            else:
                failed += 1
        try:
            changed_options = False
            last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "")
            if last_dir and not os.path.exists(last_dir):
                self.app_options.pop("last_recovery_project_dir", None)
                changed_options = True
            last_pending = str((self.app_options or {}).get("last_pending_clean_import_dir") or "")
            if last_pending and not os.path.exists(last_pending):
                self.app_options.pop("last_pending_clean_import_dir", None)
                changed_options = True
            if changed_options:
                save_app_options(self.app_options)
        except Exception:
            pass
        return deleted, failed


    def collect_workspace_folder_entries(self):
        """workspaces 아래의 실제 작업 폴더들을 날짜순으로 수집한다."""
        try:
            root = Path(workspaces_dir())
        except Exception:
            root = Path(get_workspace_root()) / "workspaces"
        entries = []
        current_project_dir = None
        current_work_dir = None
        try:
            current_project_dir = Path(str(getattr(self, "project_dir", "") or "")).resolve()
        except Exception:
            current_project_dir = None
        try:
            current_work_dir = Path(str(getattr(self, "work_project_dir", "") or "")).resolve()
        except Exception:
            current_work_dir = None

        if not root.exists():
            return entries, root
        try:
            children = [p for p in root.iterdir() if p.is_dir()]
        except Exception:
            children = []

        for folder in children:
            try:
                resolved = folder.resolve()
            except Exception:
                resolved = folder
            is_current = False
            for cur in (current_project_dir, current_work_dir):
                if cur is None:
                    continue
                try:
                    if resolved == cur or cur.is_relative_to(resolved) or resolved.is_relative_to(cur):
                        is_current = True
                        break
                except Exception:
                    try:
                        if os.path.abspath(str(resolved)) == os.path.abspath(str(cur)):
                            is_current = True
                            break
                    except Exception:
                        pass
            fc, dc, size = self.cleanup_entry_size(folder)
            try:
                mtime = folder.stat().st_mtime
            except Exception:
                mtime = 0
            project_json = folder / PROJECT_FILENAME
            status = "현재 열림" if is_current else ("프로젝트 폴더" if project_json.exists() else "작업 폴더")
            display_name = folder.name
            try:
                if project_json.exists():
                    with open(project_json, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    display_name = str(meta.get("project_name") or meta.get("name") or display_name)
            except Exception:
                pass
            entries.append({
                "path": folder,
                "name": display_name,
                "folder_name": folder.name,
                "mtime": mtime,
                "size": int(size or 0),
                "files": fc,
                "dirs": dc,
                "current": is_current,
                "status": status,
            })
        entries.sort(key=lambda e: (float(e.get("mtime") or 0), str(e.get("folder_name") or "")), reverse=True)
        return entries, root

    def open_workspace_folder_size_manager_dialog(self):
        """작업 폴더별 용량을 보고 사용자가 직접 삭제하는 관리창."""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("작업 폴더 용량 관리"))
        dlg.setModal(True)
        dlg.resize(980, 660)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root_layout = QVBoxLayout(dlg)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(12)

        title = QLabel(self.tr_ui("작업 폴더 용량 관리"), dlg)
        title.setObjectName("SettingsTitle")
        root_layout.addWidget(title)

        desc = QLabel(self.tr_ui("작업 폴더는 .ysbt 파일을 열어 작업할 때 생성되는 작업 공간입니다. 삭제해도 .ysbt 파일 자체는 삭제되지 않지만, 저장되지 않은 작업 내용은 사라질 수 있습니다. 현재 열려 있는 작업 폴더는 삭제할 수 없습니다."), dlg)
        desc.setObjectName("SettingsDescription")
        desc.setWordWrap(True)
        root_layout.addWidget(desc)

        path_box = QFrame(dlg)
        path_box.setObjectName("SettingsBlock")
        path_layout = QHBoxLayout(path_box)
        path_layout.setContentsMargins(12, 10, 12, 10)
        path_layout.setSpacing(10)
        path_title = QLabel(self.tr_ui("작업 폴더 위치"), path_box)
        path_title.setObjectName("SettingsItemTitle")
        path_label = QLabel("", path_box)
        path_label.setObjectName("SettingsPath")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setWordWrap(True)
        btn_open_root = QPushButton(self.tr_ui("전체 폴더 열기"), path_box)
        path_layout.addWidget(path_title)
        path_layout.addWidget(path_label, 1)
        path_layout.addWidget(btn_open_root)
        root_layout.addWidget(path_box)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        rows_widget = QWidget(scroll)
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(8)
        scroll.setWidget(rows_widget)
        root_layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_rescan = QPushButton(self.tr_ui("다시 스캔"), dlg)
        total_label = QLabel("", dlg)
        total_label.setObjectName("SettingsDescription")
        btn_close = QPushButton(self.tr_ui("닫기"), dlg)
        btn_row.addWidget(btn_rescan)
        btn_row.addWidget(total_label, 1)
        btn_row.addWidget(btn_close)
        root_layout.addLayout(btn_row)

        state = {"root": None, "entries": []}

        def clear_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                child_layout = item.layout()
                if w is not None:
                    w.deleteLater()
                elif child_layout is not None:
                    clear_layout(child_layout)

        def format_mtime(ts):
            try:
                if not ts:
                    return "-"
                return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                return "-"

        def delete_entry(entry):
            if not entry:
                return
            if entry.get("current"):
                QMessageBox.information(dlg, self.tr_ui("삭제할 수 없음"), self.tr_ui("현재 열려 있는 작업 폴더는 삭제할 수 없습니다."))
                return
            path = Path(entry.get("path"))
            msg = (
                f"{self.tr_ui('이 작업 폴더를 삭제합니다. 이 작업은 되돌릴 수 없습니다.')}\n\n"
                f"{entry.get('name') or path.name}\n"
                f"{path}\n"
                f"{self.tr_ui('용량')}: {self.format_size_mb(entry.get('size', 0))}\n\n"
                f"{self.tr_ui('계속할까요?')}"
            )
            ans = QMessageBox.question(
                dlg,
                self.tr_ui("작업 폴더 삭제 확인"),
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            ok = self.cleanup_delete_path(path)
            if ok:
                self.log(f"🧹 작업 폴더 삭제: {path}")
            else:
                QMessageBox.warning(dlg, self.tr_ui("삭제 실패"), f"{self.tr_ui('작업 폴더를 삭제하지 못했습니다.')}\n{path}")
            refresh()

        def make_row(entry):
            row = QFrame(rows_widget)
            row.setObjectName("SettingsItem")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(12, 10, 12, 10)
            lay.setSpacing(12)

            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)
            name = QLabel(str(entry.get("name") or entry.get("folder_name") or ""), row)
            name.setObjectName("SettingsItemTitle")
            detail = QLabel(
                f"{entry.get('folder_name') or ''}  ·  {self.tr_ui('수정')}: {format_mtime(entry.get('mtime'))}  ·  {entry.get('status') or ''}",
                row,
            )
            detail.setObjectName("SettingsDescription")
            detail.setWordWrap(True)
            text_box.addWidget(name)
            text_box.addWidget(detail)
            lay.addLayout(text_box, 1)

            size_label = QLabel(self.format_size_mb(entry.get("size", 0)), row)
            size_label.setMinimumWidth(100)
            size_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(size_label)

            btn_open = QPushButton(self.tr_ui("폴더 열기"), row)
            btn_open.setMinimumWidth(88)
            btn_open.clicked.connect(lambda _=False, p=entry.get("path"): self.cleanup_open_folder(p))
            lay.addWidget(btn_open)

            btn_delete = QPushButton(self.tr_ui("삭제"), row)
            btn_delete.setMinimumWidth(88)
            btn_delete.setEnabled(not bool(entry.get("current")))
            btn_delete.clicked.connect(lambda _=False, e=entry: delete_entry(e))
            lay.addWidget(btn_delete)
            return row

        def refresh():
            entries, root = self.collect_workspace_folder_entries()
            state["entries"] = entries
            state["root"] = root
            path_label.setText(str(root))
            clear_layout(rows_layout)
            total = sum(int(e.get("size") or 0) for e in entries)
            total_label.setText(f"{self.tr_ui('총')} {len(entries)}{self.tr_ui('개')} / {self.tr_ui('용량')}: {self.format_size_mb(total)}")
            if not entries:
                empty = QLabel(self.tr_ui("표시할 작업 폴더가 없습니다."), rows_widget)
                empty.setObjectName("SettingsDescription")
                rows_layout.addWidget(empty)
            for entry in entries:
                rows_layout.addWidget(make_row(entry))
            rows_layout.addStretch(1)

        btn_open_root.clicked.connect(lambda: self.cleanup_open_folder(state.get("root") or workspaces_dir()))
        btn_rescan.clicked.connect(refresh)
        btn_close.clicked.connect(dlg.reject)
        refresh()
        dlg.exec()

    def cleanup_temp_files_dialog(self):
        """5개 대분류만 보여주는 사용자 데이터/임시파일 정리 창."""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("사용자 데이터 및 임시파일 정리"))
        dlg.setModal(True)
        dlg.resize(860, 560)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("사용자 데이터 및 임시파일 정리"), dlg)
        title.setObjectName("SettingsTitle")
        root.addWidget(title)

        desc = QLabel(self.tr_ui("임시 작업/복구 캐시는 자동 정리되지만 용량이 크게 커질 수 있어 최상단에 표시합니다. 현재 열려 있는 작업은 삭제 대상에서 제외됩니다. 실제 작업 폴더 용량은 별도의 작업 폴더 용량 관리에서 확인합니다."), dlg)
        desc.setObjectName("SettingsDescription")
        desc.setWordWrap(True)
        root.addWidget(desc)

        path_box = QFrame(dlg)
        path_box.setObjectName("SettingsBlock")
        path_layout = QGridLayout(path_box)
        path_layout.setContentsMargins(12, 12, 12, 12)
        path_layout.setHorizontalSpacing(10)
        path_layout.setVerticalSpacing(8)
        app_path_label = QLabel("", path_box)
        app_path_label.setObjectName("SettingsPath")
        app_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        app_path_label.setWordWrap(True)
        btn_open_app = QPushButton(self.tr_ui("AppData 폴더 열기"), path_box)
        path_layout.addWidget(QLabel(self.tr_ui("AppData"), path_box), 0, 0)
        path_layout.addWidget(app_path_label, 0, 1)
        path_layout.addWidget(btn_open_app, 0, 2)
        root.addWidget(path_box)

        auto_box = QFrame(dlg)
        auto_box.setObjectName("SettingsItem")
        auto_layout = QHBoxLayout(auto_box)
        auto_layout.setContentsMargins(12, 10, 12, 10)
        auto_layout.setSpacing(10)
        auto_text = QVBoxLayout()
        auto_title = QLabel(self.tr_ui("오래된 캐시 자동 정리"), auto_box)
        auto_title.setObjectName("SettingsItemTitle")
        auto_desc = QLabel(self.tr_ui("자동 정리 대상은 AppData 실행 캐시와 오래된 임시 작업/복구 캐시입니다. 실제 작업 폴더는 사용자가 직접 확인하고 삭제합니다."), auto_box)
        auto_desc.setObjectName("SettingsDescription")
        auto_desc.setWordWrap(True)
        auto_text.addWidget(auto_title)
        auto_text.addWidget(auto_desc)
        cb_auto = QCheckBox(self.tr_ui("자동정리"), auto_box)
        combo_days = QComboBox(auto_box)
        current_days = self.get_temp_auto_cleanup_days()
        for days, label in self.temp_cleanup_period_options():
            combo_days.addItem(self.tr_ui(label), days)
            if days == current_days:
                combo_days.setCurrentIndex(combo_days.count() - 1)
        cb_auto.setChecked(self.is_temp_auto_cleanup_enabled())
        combo_days.setEnabled(cb_auto.isChecked())
        auto_layout.addLayout(auto_text, 1)
        auto_layout.addWidget(cb_auto)
        auto_layout.addWidget(combo_days)
        root.addWidget(auto_box)

        rows_area = QScrollArea(dlg)
        rows_area.setWidgetResizable(True)
        rows_area.setFrameShape(QFrame.Shape.NoFrame)
        rows_widget = QWidget(rows_area)
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(8)
        rows_area.setWidget(rows_widget)
        root.addWidget(rows_area, 1)

        btn_row = QHBoxLayout()
        btn_rescan = QPushButton(self.tr_ui("다시 스캔"), dlg)
        btn_close = QPushButton(self.tr_ui("닫기"), dlg)
        btn_row.addWidget(btn_rescan)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        state = {"entries": [], "app_root": None, "workspace_root": None}

        def save_options():
            days = combo_days.currentData()
            self.set_temp_cleanup_options(cb_auto.isChecked(), days)
            combo_days.setEnabled(cb_auto.isChecked())
            self.log(f"🧹 캐시 자동 정리 설정: {'ON' if cb_auto.isChecked() else 'OFF'} / {int(days)}일")

        def confirm_and_delete(entry):
            if not entry or not entry.get("paths"):
                QMessageBox.information(dlg, self.tr_ui("삭제할 항목 없음"), self.tr_ui("삭제할 수 있는 항목이 없습니다."))
                return
            label = entry.get("label") or ""
            size = self.format_size_mb(entry.get("size", 0))
            warning = self.tr_ui("이 항목을 삭제합니다. 이 작업은 되돌릴 수 없습니다.")
            if entry.get("manual_only"):
                warning += "\n" + self.tr_ui("이 항목은 자동 정리 대상이 아니며, 사용자가 직접 누를 때만 삭제됩니다.")
            if entry.get("key") == "temp_work_sessions":
                warning += "\n" + self.tr_ui("현재 열려 있는 작업은 제외되지만, 다른 저장되지 않은 복구 작업은 사라질 수 있습니다.")
            if entry.get("sensitive"):
                warning += "\n" + self.tr_ui("삭제 후 API 키나 클라우드 로그인을 다시 설정해야 할 수 있습니다.")
            msg = f"{warning}\n\n{label}\n{self.tr_ui('용량')}: {size}\n\n{self.tr_ui('계속할까요?')}"
            ans = QMessageBox.question(
                dlg,
                self.tr_ui("삭제 확인"),
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                self.log(f"↩️ {label} 삭제 취소")
                return
            deleted, failed = self.cleanup_delete_paths(entry.get("paths") or [])
            self.log(f"🧹 {label}: 삭제 {deleted}개 / 실패 {failed}개")
            QMessageBox.information(
                dlg,
                self.tr_ui("삭제 완료"),
                f"{label}\n{self.tr_ui('삭제')}: {deleted}{self.tr_ui('개')}\n{self.tr_ui('실패')}: {failed}{self.tr_ui('개')}",
            )
            refresh_rows()

        def clear_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                child_layout = item.layout()
                if w is not None:
                    w.deleteLater()
                elif child_layout is not None:
                    clear_layout(child_layout)

        def make_row(entry):
            row = QFrame(rows_widget)
            row.setObjectName("SettingsItem")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(12, 10, 12, 10)
            lay.setSpacing(12)

            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)
            name = QLabel(str(entry.get("label") or ""), row)
            name.setObjectName("SettingsItemTitle")
            desc_label = QLabel(str(entry.get("desc") or ""), row)
            desc_label.setObjectName("SettingsDescription")
            desc_label.setWordWrap(True)
            text_box.addWidget(name)
            text_box.addWidget(desc_label)
            lay.addLayout(text_box, 1)

            size_label = QLabel(self.format_size_mb(entry.get("size", 0)), row)
            size_label.setMinimumWidth(90)
            size_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(size_label)

            open_path = entry.get("open_path")
            if open_path:
                btn_open = QPushButton(self.tr_ui("폴더 열기"), row)
                btn_open.setMinimumWidth(88)
                btn_open.clicked.connect(lambda _=False, p=open_path: self.cleanup_open_folder(p))
                lay.addWidget(btn_open)
            else:
                spacer = QWidget(row)
                spacer.setFixedWidth(88)
                lay.addWidget(spacer)

            btn_delete = QPushButton(self.tr_ui("삭제"), row)
            btn_delete.setMinimumWidth(88)
            btn_delete.setEnabled(bool(entry.get("paths")))
            btn_delete.clicked.connect(lambda _=False, e=entry: confirm_and_delete(e))
            lay.addWidget(btn_delete)
            return row

        def refresh_rows():
            entries, app_root, workspace_root = self.collect_user_data_cleanup_entries()
            state["entries"] = entries
            state["app_root"] = app_root
            state["workspace_root"] = workspace_root
            app_path_label.setText(str(app_root))
            clear_layout(rows_layout)
            for entry in entries:
                rows_layout.addWidget(make_row(entry))
            rows_layout.addStretch(1)

        cb_auto.toggled.connect(lambda _checked: save_options())
        combo_days.currentIndexChanged.connect(lambda _idx: save_options())
        btn_rescan.clicked.connect(refresh_rows)
        btn_close.clicked.connect(dlg.reject)
        btn_open_app.clicked.connect(lambda: self.cleanup_open_folder(state.get("app_root") or app_config_dir()))

        refresh_rows()
        dlg.exec()

    def open_project_path(self, path, external_request=False):
        """파일 연결/명령행 인자로 받은 .ysbt 또는 project.json을 연다."""
        if not path:
            return
        self._file_dialog_log("FILE_DIALOG_GUARD_ENTER", reason="open_project_ysbt")
        if not self.guard_project_action("프로젝트 열기"):
            self._file_dialog_log("FILE_DIALOG_GUARD_BLOCKED", reason="open_project_ysbt")
            return
        self._file_dialog_log("FILE_DIALOG_GUARD_DONE", reason="open_project_ysbt")
        path = os.path.abspath(path)

        if path.lower().endswith(YSB_EXTENSION):
            self.open_ysbt_from_home(path, external_request=external_request)
            return

        if not external_request:
            if self.has_open_project():
                if not self.confirm_unsaved_before_switch():
                    return
            else:
                # 런처 화면에는 열린 프로젝트가 없으므로 남은 dirty 플래그/타이머는 이전 세션 찌꺼기다.
                try:
                    self.clear_pending_work_cache_save_state("open_project_without_project")
                except Exception:
                    pass
                self.has_unsaved_changes = False
        if os.path.isdir(path):
            project_file = os.path.join(path, PROJECT_FILENAME)
        else:
            project_file = path
        if os.path.basename(project_file) != PROJECT_FILENAME or not os.path.exists(project_file):
            msg_text = self.tr_ui("열 수 있는 프로젝트 파일이 아닙니다.")
            QMessageBox.warning(self, self.tr_ui("프로젝트 없음"), f"{msg_text}\n{path}")
            return
        self.load_project_json(project_file)
        if external_request:
            self.force_app_focus(reason="external project open")

    def open_ysbt_from_home(self, path, external_request=False):
        """YSBT 열기는 항상 홈화면 위에서 진행창을 띄운 뒤 시작한다."""
        path = os.path.abspath(str(path))
        if not os.path.exists(path):
            QMessageBox.warning(self, self.tr_ui("파일을 찾을 수 없음"), f"{self.tr_ui('파일을 찾을 수 없습니다.')}\n{path}")
            return False

        if self.has_open_project():
            if not external_request:
                if not self.confirm_unsaved_before_switch():
                    return False
            elif getattr(self, "has_unsaved_changes", False):
                # 외부 열기 루트는 보통 handle_single_instance_payload()에서 이미 확인을 거치지만,
                # 직접 호출되는 예외 상황을 방어한다.
                if not self.confirm_unsaved_before_switch():
                    return False
            self.clear_current_project_runtime_state()
        else:
            try:
                self.clear_pending_work_cache_save_state("open_ysbt_from_home_without_project")
            except Exception:
                pass
            self.has_unsaved_changes = False

        try:
            self._show_launcher_screen_only()
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        except Exception:
            pass

        def _start_open():
            try:
                self.open_ysb_package(path)
                if external_request:
                    self.force_app_focus(reason="external project open")
            except Exception as e:
                QMessageBox.critical(self, self.tr_ui("YSBT 열기 실패"), f"{self.tr_ui('YSBT 프로젝트를 열지 못했습니다.')}\n{path}\n\n{e}")

        # 홈화면 전환/갱신이 먼저 보인 뒤 그 위에 압축 해제 진행창이 뜨도록 한 박자 늦춘다.
        QTimer.singleShot(50, _start_open)
        return True

    def load_project_json(self, project_file, package_path=None, temp_project=False):
        self.is_loading_project = True
        load_progress = getattr(self, "_project_load_progress_callback", None)

        def _emit_load_progress(current, total, detail):
            if callable(load_progress):
                try:
                    load_progress(current, total, detail)
                except Exception:
                    pass

        try:
            _emit_load_progress(12, 100, "현재 화면 상태를 정리하는 중...")
            self.commit_current_page_ui_to_data()
            _emit_load_progress(22, 100, "프로젝트 데이터를 읽는 중...")
            self.project_store = ProjectStore()
            self.paths, self.data, self.idx = self.project_store.load(project_file, lazy_assets=True)
            _emit_load_progress(35, 100, "Undo/화면 상태를 초기화하는 중...")
            self.undo_clear_all_pages("project load")
            self.undo_clear_project("project stack reset")
            self.undo_boundary = None
            self.update_undo_redo_buttons()
            ui_state = getattr(self.project_store, "ui_state", {}) or {}
            self.project_ui_view_states = copy.deepcopy(ui_state.get("view_states") or {})
            self.restore_project_ui_state(ui_state, refresh=False)
            self.project_dir = self.project_store.project_dir
            self.ysbt_package_path = package_path
            self.suggested_project_name = self.split_uuid_suffix_from_name(Path(package_path).stem)[0] if package_path else None
            self.is_temp_project = bool(temp_project)
            self.update_window_title()
            self.mark_saved_state()
            self.log(f"📂 프로젝트 열림: {self.project_dir}")
            if package_path:
                self.log(f"📦 연결된 YSBT 파일: {package_path}")

            # 새 프로젝트/복구 프로젝트는 원본 탭으로 시작한다.
            # 특히 복구 직후 mode 4(최종결과)를 바로 복원하면 대량 클린본/이미지 상태에서 첫 렌더가 매우 무거워질 수 있다.
            if temp_project or bool(getattr(self, "_loading_recovery_project", False)):
                mode_to_load = 0
            else:
                mode_to_load = int(ui_state.get("current_mode", 0) or 0)
            _emit_load_progress(45, 100, "첫 페이지 화면을 구성하는 중...\n이미지가 많은 프로젝트는 이 단계에서 시간이 걸릴 수 있습니다.")
            self.set_work_mode_without_undo(mode_to_load)
            self.show_editor()
            self.load()
            try:
                self.schedule_progressive_page_load(self.idx)
            except Exception:
                pass
            _emit_load_progress(75, 100, "첫 페이지 화면 구성 완료")
            self.record_current_project_recent()
            state = self.project_ui_view_states.get(self.view_state_key(self.idx, mode_to_load))
            if state:
                self.apply_view_state(state)
                QTimer.singleShot(0, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                QTimer.singleShot(30, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                QTimer.singleShot(80, lambda st=copy.deepcopy(state): self.apply_view_state(st))

            pending_clean_restored = 0
            try:
                pending_clean_restored = self.apply_pending_clean_import_if_available(self.project_dir)
            except Exception as e:
                pending_clean_restored = 0
                try:
                    self.log(f"⚠️ 클린본 pending 복구 실패: {e}")
                except Exception:
                    pass

            # 열기 직후에는 작업 캐시 full snapshot을 만들지 않는다.
            # YSBT를 풀어 둔 project_dir 자체를 현재 작업 기준 폴더로 사용하고,
            # 실제 변경이 생긴 페이지부터 save_pages_delta()로만 반영한다.
            try:
                self.work_project_dir = self.project_dir
                self.work_project_store = self.project_store
                if pending_clean_restored:
                    self.record_recovery_project_dir(self.project_dir)
                    self.has_unsaved_changes = True
            except Exception:
                pass
            _emit_load_progress(100, 100, "프로젝트 로드 완료")
        finally:
            self.is_loading_project = False

    def open_ysb_package(self, package_path):
        self._long_task_cancel_requested = False
        self._active_long_task_kind = "open_extract"
        shown_overlay = False

        def _open_progress(current=None, total=None, detail=None):
            try:
                show_total = int(total or 0)
                show_current = int(current or 0)
                raw_detail = str(detail or "압축 해제 중...")
                file_name = os.path.basename(str(package_path))
                formatted = (
                    f"{self.tr_ui('파일')}: {file_name}\n"
                    f"{raw_detail}"
                )
                self.update_task_progress_overlay(current=show_current, total=show_total, detail=formatted)
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            except Exception:
                pass

        def _open_cancel_requested():
            return bool(getattr(self, "_long_task_cancel_requested", False))

        try:
            self.begin_busy_state("YSBT 열기")
            self.show_task_progress_overlay(
                "YSBT 열기",
                f"{self.tr_ui('파일')}: {os.path.basename(str(package_path))}\n압축 해제 준비 중...",
                total=0,
                cancellable=True,
            )
            shown_overlay = True
            try:
                overlay = getattr(self, "_task_progress_overlay", None)
                if overlay is not None:
                    overlay.note_label.setText("취소 시 압축 해제를 중단하고 부분 작업 폴더를 삭제합니다.")
                    overlay.cancel_btn.setVisible(True)
                    overlay.cancel_btn.setEnabled(True)
            except Exception:
                pass
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

            # .ysbt는 항상 본체다.
            # 기존 workspaces 해제본은 옛 작업 공간이므로 재사용하지 않고,
            # 같은 이름/uuid 작업 폴더를 비운 뒤 현재 .ysbt를 다시 압축 해제해서 연다.
            target_dir, manifest, reused = extract_ysb_package(
                package_path,
                workspaces_dir(),
                reuse_existing=False,
                progress_callback=_open_progress,
                cancel_checker=_open_cancel_requested,
            )

            self.update_task_progress_overlay(
                current=1,
                total=1,
                detail=f"{self.tr_ui('파일')}: {os.path.basename(str(package_path))}\n프로젝트 데이터를 불러오는 중..."
            )
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            self.load_project_json(os.path.join(target_dir, PROJECT_FILENAME), package_path=package_path, temp_project=False)
        except PackageProjectCancelled:
            try:
                self.log("⏹️ YSBT 열기 취소됨")
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("YSBT 열기 실패"), f"{self.tr_ui('YSBT 프로젝트를 열지 못했습니다.')}\n{package_path}\n\n{e}")
        finally:
            try:
                self._active_long_task_kind = ""
            except Exception:
                pass
            try:
                self._long_task_cancel_requested = False
            except Exception:
                pass
            try:
                if shown_overlay:
                    self.hide_task_progress_overlay()
            except Exception:
                pass
            try:
                self.end_busy_state()
            except Exception:
                pass

    def project_cache_root(self):
        root = get_cache_dir() / "work_sessions"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def clear_pending_work_cache_save_state(self, reason=""):
        """저장/닫기/프로젝트 전환 뒤에 남은 지연 커밋 예약을 정리한다.

        v2.4 QA20:
        복구용 작업 캐시 저장 QTimer는 제거되었다. 여기서는 최종 페인트/마스크
        뷰 레이어 지연 커밋만 끊어, 화면 전환 뒤 이전 프로젝트의 예약 작업이
        새 프로젝트 상태를 건드리지 못하게 한다.
        """
        for attr in ("_deferred_view_layer_commit_timer", "_deferred_work_cache_save_timer"):
            try:
                timer = getattr(self, attr, None)
                if timer is not None:
                    timer.stop()
            except Exception:
                pass
        try:
            self._pending_view_layer_commit_kinds = set()
        except Exception:
            pass

    def forget_recovery_project_dir(self, project_dir=None):
        """저장 완료 등으로 복구 후보가 더 필요 없을 때 마지막 복구 기록만 지운다."""
        try:
            target = os.path.abspath(str(project_dir or getattr(self, "work_project_dir", "") or ""))
            if not target:
                return
            changed = False
            last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "")
            try:
                if last_dir and os.path.abspath(last_dir).lower() == target.lower():
                    self.app_options.pop("last_recovery_project_dir", None)
                    changed = True
            except Exception:
                pass
            last_pending = str((self.app_options or {}).get("last_pending_clean_import_dir") or "")
            try:
                if last_pending and os.path.abspath(last_pending).lower().startswith(target.lower()):
                    self.app_options.pop("last_pending_clean_import_dir", None)
                    changed = True
            except Exception:
                pass
            try:
                self.mark_workspace_state_saved(target)
            except Exception:
                pass
            # 구버전 work_sessions recovery_marker 파일은 best-effort로 정리한다.
            try:
                marker = self.project_cache_root() / f"recovery_marker_{Path(target).name}_{uuid.uuid5(uuid.NAMESPACE_URL, target).hex[:12]}.json"
                if marker.exists():
                    marker.unlink()
            except Exception:
                pass
            if changed:
                save_app_options(self.app_options)
        except Exception:
            pass

    def cleanup_work_cache(self):
        try:
            self.clear_pending_work_cache_save_state("cleanup_work_cache")
        except Exception:
            pass
        old_cache = self.work_project_dir
        try:
            self.forget_recovery_project_dir(old_cache)
        except Exception:
            pass
        if old_cache and os.path.exists(old_cache):
            try:
                old_abs = os.path.abspath(str(old_cache))
                project_abs = os.path.abspath(str(getattr(self, "project_dir", "") or ""))
                if old_abs == project_abs or self.is_workspace_project_dir_path(old_abs):
                    # workspaces는 실제 작업 공간이자 복구 기준이므로 자동 삭제하지 않는다.
                    try:
                        self.log(f"🧷 작업 폴더 자동 삭제 생략: {old_cache}")
                    except Exception:
                        pass
                else:
                    shutil.rmtree(old_cache, ignore_errors=True)
            except Exception:
                pass
        self.work_project_dir = None
        self.work_project_store = None
        self.page_tab_scroll_generation = 0

    def make_work_cache_dir(self):
        if self.project_dir:
            base = Path(self.project_dir).name
        else:
            base = "unsaved_project"
        safe_base = "".join(c if c.isalnum() or c in ("_", "-", ".") else "_" for c in base)
        return str(self.project_cache_root() / f"{safe_base}_{uuid.uuid4().hex[:10]}")

    def start_work_cache_from_current(self, mark_dirty=False):
        """현재 메모리 상태를 기준으로 새 작업 캐시를 만든다."""
        if not self.project_dir:
            return
        old_cache = self.work_project_dir
        cache_dir = self.make_work_cache_dir()

        store = ProjectStore(cache_dir)
        old_suppress = bool(getattr(self, "_suppress_work_cache_dirty", False))
        self._suppress_work_cache_dirty = True
        try:
            self.save_project_store(store, force_full=True)
        finally:
            self._suppress_work_cache_dirty = old_suppress

        # store.save()가 paths를 cache 내부 이미지 경로로 고정할 수 있으므로 이후 작업은 캐시 기준으로 돌아간다.
        self.work_project_store = store
        self.work_project_dir = cache_dir
        self.record_recovery_project_dir(cache_dir)
        self.has_unsaved_changes = bool(mark_dirty)

        if old_cache and old_cache != cache_dir and os.path.exists(old_cache):
            try:
                if self.is_workspace_project_dir_path(old_cache):
                    self.log(f"🧷 기존 workspaces 작업 폴더 자동 삭제 생략: {old_cache}")
                else:
                    shutil.rmtree(old_cache, ignore_errors=True)
            except Exception:
                pass

        self.log(f"🧪 작업 캐시 시작: {cache_dir}")

    def flush_workspace_image_pages(self, page_indices, *, reason="image_heavy", release_non_current=True):
        """이미지-heavy 페이지를 즉시 workspace delta로 저장한다.

        인페인팅/클린본/배경 교체처럼 큰 이미지 payload가 생기는 작업은
        page journal이 아니라 save_pages_delta()로 바로 파일 flush 해야 한다.
        일괄 작업에서는 페이지 하나를 저장한 뒤 메모리 payload를 끊어 다음
        페이지로 넘어가도록 이 helper를 쓴다.
        """
        if (
            getattr(self, "_suppress_work_cache_dirty", False)
            or getattr(self, "is_loading_project", False)
            or not getattr(self, "project_dir", None)
            or not getattr(self, "paths", None)
        ):
            return False
        indices = []
        seen = set()
        for raw in list(page_indices or []):
            try:
                i = int(raw)
            except Exception:
                continue
            if 0 <= i < len(getattr(self, 'paths', []) or []) and i not in seen:
                indices.append(i)
                seen.add(i)
        if not indices:
            return False
        if self.work_project_store is None or not self.work_project_dir:
            self.work_project_store = getattr(self, 'project_store', None)
            self.work_project_dir = getattr(self, 'project_dir', None)
        if self.work_project_store is None or not self.work_project_dir:
            return False
        try:
            self.work_project_store.ui_state = self.current_project_ui_state()
        except Exception:
            self.work_project_store.ui_state = getattr(self.work_project_store, 'ui_state', {}) or {}
        self.work_project_store.clean_image_format = self.current_clean_image_format() if hasattr(self, 'current_clean_image_format') else getattr(self, 'clean_image_format', 'png')
        self.work_project_store.clean_image_quality = self.current_clean_image_quality() if hasattr(self, 'current_clean_image_quality') else getattr(self, 'clean_image_quality', 95)
        try:
            self.audit_boundary_event(
                'WORK_CACHE_IMAGE_DELTA_SAVE_ENTER',
                dirty_pages=sorted(int(x) for x in indices),
                reason=str(reason or 'image_heavy'),
                stack=True,
            )
        except Exception:
            pass
        self.work_project_store.save_pages_delta(self.paths, self.data, set(indices), current_index=getattr(self, 'idx', 0))
        try:
            self.record_recovery_project_dir(self.work_project_dir)
        except Exception:
            pass
        try:
            self.audit_boundary_event(
                'WORK_CACHE_IMAGE_DELTA_SAVE_DONE',
                dirty_pages=sorted(int(x) for x in indices),
                reason=str(reason or 'image_heavy'),
            )
        except Exception:
            pass
        if release_non_current:
            try:
                current_idx = int(getattr(self, 'idx', -1) or -1)
            except Exception:
                current_idx = -1
            for i in indices:
                if i == current_idx:
                    continue
                try:
                    curr = (getattr(self, 'data', {}) or {}).get(int(i))
                    if not isinstance(curr, dict):
                        continue
                    if curr.get('clean_path'):
                        curr['bg_clean'] = None
                    if curr.get('working_source_path'):
                        curr['working_source'] = None
                    if curr.get('final_paint_path'):
                        curr['final_paint'] = None
                    if curr.get('final_paint_above_path'):
                        curr['final_paint_above'] = None
                    curr['ori'] = None
                except Exception:
                    pass
            try:
                if hasattr(self, 'trim_page_image_cache'):
                    keep = [current_idx] if current_idx >= 0 else []
                    self.trim_page_image_cache(keep_indices=keep)
            except Exception:
                pass
            try:
                if hasattr(self, 'trim_page_mask_cache'):
                    keep = [current_idx] if current_idx >= 0 else []
                    self.trim_page_mask_cache(keep_indices=keep)
            except Exception:
                pass
            try:
                __import__('gc').collect()
            except Exception:
                pass
        return True

    def save_to_work_cache(self):
        if (
            getattr(self, "_suppress_work_cache_dirty", False)
            or getattr(self, "is_loading_project", False)
            or not self.project_dir
            or not getattr(self, "paths", None)
        ):
            return
        if self.work_project_store is None or not self.work_project_dir:
            # 더 이상 첫 변경 시 별도 work_sessions full copy를 만들지 않는다.
            # 현재 열려 있는 project_dir에 dirty page만 delta 저장한다.
            self.work_project_store = getattr(self, "project_store", None)
            self.work_project_dir = getattr(self, "project_dir", None)
        if self.work_project_store is None or not self.work_project_dir:
            return
        checkpoint_pages = set()
        try:
            checkpoint_pages = {int(x) for x in (getattr(self, "_checkpoint_dirty_pages", set()) or set())}
        except Exception:
            checkpoint_pages = set()

        dirty_pages = set()
        try:
            if hasattr(self, "storage_engine") and self.storage_engine is not None:
                plan = self.storage_engine.make_plan(force_full=False, reason="work_cache_page_delta")
                dirty_pages = set(getattr(plan, "dirty_pages", set()) or set())
        except Exception:
            dirty_pages = set()
        try:
            if not dirty_pages and hasattr(self, "project_engine") and self.project_engine is not None:
                dirty_pages = set(self.project_engine.dirty_page_indices())
        except Exception:
            pass
        try:
            if not dirty_pages and hasattr(self, "page_engine") and self.page_engine is not None:
                dirty_pages = set(self.page_engine.dirty_pages())
        except Exception:
            pass

        dirty_kinds_by_page = {}
        try:
            pe = getattr(self, "project_engine", None)
            summary = pe.dirty_summary() if pe is not None and hasattr(pe, "dirty_summary") else {}
            raw_dirty = summary.get("dirty_pages", {}) if isinstance(summary, dict) else {}
            if isinstance(raw_dirty, dict):
                for k, v in raw_dirty.items():
                    try:
                        dirty_kinds_by_page[int(k)] = {str(x or "data") for x in list(v or [])}
                    except Exception:
                        pass
        except Exception:
            dirty_kinds_by_page = {}

        text_json_only_kinds = {"text", "checkpoint_text", "checkpoint_fallback", "data", "translation", "translated_text", "text_effect_preview"}

        checkpoint_kinds = {}
        try:
            checkpoint_kinds = getattr(self, "_checkpoint_dirty_kinds", {}) or {}
        except Exception:
            checkpoint_kinds = {}
        checkpoint_text_only = bool(checkpoint_pages)
        if checkpoint_text_only:
            try:
                for pidx in checkpoint_pages:
                    # checkpoint kind와 project/page dirty kind를 합쳐서 판단한다.
                    # 이전에는 checkpoint_text만 남아 있고 실제 dirty에는 paint가 있어도 journal로 빠졌다.
                    kinds = {str(x or "") for x in list(checkpoint_kinds.get(int(pidx), set()) or set())}
                    kinds |= {str(x or "") for x in list(dirty_kinds_by_page.get(int(pidx), set()) or set())}
                    if not kinds or not set(kinds).issubset(text_json_only_kinds):
                        checkpoint_text_only = False
                        break
            except Exception:
                checkpoint_text_only = False

        if checkpoint_pages and checkpoint_text_only and hasattr(self.work_project_store, "save_page_data_delta"):
            journal_pages = set(checkpoint_pages)
            try:
                self.work_project_store.ui_state = self.current_project_ui_state()
            except Exception:
                self.work_project_store.ui_state = getattr(self.work_project_store, "ui_state", {}) or {}
            try:
                self.audit_boundary_event(
                    "WORK_CACHE_PAGE_JOURNAL_SAVE_ENTER",
                    dirty_pages=sorted(int(x) for x in journal_pages),
                    stack=True,
                )
            except Exception:
                pass
            self.work_project_store.save_page_data_delta(self.data, journal_pages, current_index=getattr(self, "idx", 0))
            try:
                self.audit_boundary_event(
                    "WORK_CACHE_PAGE_JOURNAL_SAVE_DONE",
                    dirty_pages=sorted(int(x) for x in journal_pages),
                )
            except Exception:
                pass
            try:
                self._checkpoint_dirty_pages.difference_update(journal_pages)
                for pidx in list(journal_pages):
                    try:
                        self._checkpoint_dirty_kinds.pop(int(pidx), None)
                    except Exception:
                        pass
            except Exception:
                pass
            dirty_pages = journal_pages

        elif checkpoint_pages and hasattr(self.work_project_store, "save_pages_delta"):
            image_pages = set(checkpoint_pages)
            try:
                self.audit_boundary_event(
                    "WORK_CACHE_PAGE_CHECKPOINT_IMAGE_DELTA_ENTER",
                    dirty_pages=sorted(int(x) for x in image_pages),
                    kinds={int(k): sorted(list(v)) for k, v in (checkpoint_kinds or {}).items() if int(k) in image_pages},
                    stack=True,
                )
            except Exception:
                pass
            try:
                self.flush_workspace_image_pages(image_pages, reason="checkpoint_image_dirty", release_non_current=True)
            except Exception:
                try:
                    self.work_project_store.save_pages_delta(self.paths, self.data, image_pages, current_index=getattr(self, "idx", 0))
                except Exception:
                    pass
            try:
                self._checkpoint_dirty_pages.difference_update(image_pages)
                for pidx in list(image_pages):
                    try:
                        self._checkpoint_dirty_kinds.pop(int(pidx), None)
                    except Exception:
                        pass
            except Exception:
                pass
            dirty_pages = image_pages

        elif not dirty_pages:
            # view/UI 상태만 바뀐 상황에서 work cache 전체 저장으로 빠지면 다시 프로젝트 단위 저장이 된다.
            # 개별 페이지 dirty가 없으면 복구 후보 기록만 갱신하고 끝낸다.
            try:
                self.audit_boundary_event("WORK_CACHE_PAGE_DELTA_SKIP_NO_DIRTY_PAGE")
            except Exception:
                pass

        else:
            text_only_project_dirty = bool(dirty_pages) and bool(dirty_kinds_by_page)
            if text_only_project_dirty:
                try:
                    for page_i in dirty_pages:
                        kinds = dirty_kinds_by_page.get(int(page_i), set())
                        if not kinds or not set(kinds).issubset(text_json_only_kinds):
                            text_only_project_dirty = False
                            break
                except Exception:
                    text_only_project_dirty = False

            if text_only_project_dirty:
                # 이미 journal에 반영된 텍스트 dirty는 YSBT 저장용 dirty로만 남긴다.
                # checkpoint_dirty가 없는데 project_dirty 전체를 다시 journal로 쓰면 매번 [1,2,...]가 반복 저장된다.
                try:
                    self.audit_boundary_event(
                        "WORK_CACHE_PAGE_JOURNAL_SKIP_NO_CHECKPOINT_DIRTY",
                        dirty_pages=sorted(int(x) for x in dirty_pages),
                        throttle_ms=1200,
                    )
                except Exception:
                    pass

            elif hasattr(self.work_project_store, "save_pages_delta"):
                try:
                    self.work_project_store.ui_state = self.current_project_ui_state()
                except Exception:
                    self.work_project_store.ui_state = getattr(self.work_project_store, "ui_state", {}) or {}
                self.work_project_store.clean_image_format = self.current_clean_image_format() if hasattr(self, "current_clean_image_format") else getattr(self, "clean_image_format", "png")
                self.work_project_store.clean_image_quality = self.current_clean_image_quality() if hasattr(self, "current_clean_image_quality") else getattr(self, "clean_image_quality", 95)
                try:
                    self.audit_boundary_event(
                        "WORK_CACHE_PAGE_DELTA_SAVE_ENTER",
                        dirty_pages=sorted(int(x) for x in dirty_pages),
                        stack=True,
                    )
                except Exception:
                    pass
                self.work_project_store.save_pages_delta(self.paths, self.data, dirty_pages, current_index=getattr(self, "idx", 0))
                try:
                    self.audit_boundary_event(
                        "WORK_CACHE_PAGE_DELTA_SAVE_DONE",
                        dirty_pages=sorted(int(x) for x in dirty_pages),
                    )
                except Exception:
                    pass
            else:
                # 구버전 객체 호환용 최후 폴백. 새 ProjectStore에는 save_pages_delta가 있어야 한다.
                try:
                    self.audit_boundary_event("WORK_CACHE_PAGE_DELTA_FALLBACK_FULL_STORE", dirty_pages=sorted(int(x) for x in dirty_pages), stack=True)
                except Exception:
                    pass
                self.save_project_store(self.work_project_store, force_full=False)
        self.record_recovery_project_dir(self.work_project_dir)
        if dirty_pages:
            self.has_unsaved_changes = True

    def mark_saved_state(self):
        try:
            self.clear_pending_work_cache_save_state("mark_saved_state")
        except Exception:
            pass
        self.has_unsaved_changes = False
        try:
            if hasattr(self, "project_engine") and self.project_engine is not None:
                self.project_engine.mark_saved()
            if hasattr(self, "page_engine") and self.page_engine is not None:
                self.page_engine.clear_dirty()
        except Exception:
            pass

    def save_app_options_cache(self):
        # v2.4 QA6: 실시간 자동저장은 폐지. 예전 캐시가 남아도 항상 OFF로 저장한다.
        self.auto_save_enabled = False
        self.app_options["auto_save_enabled"] = False
        self.app_options[UI_THEME_KEY] = str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK)
        self.app_options[UI_LANGUAGE_KEY] = normalize_ui_language(getattr(self, "ui_language", LANG_KO))
        self.app_options["analysis_number_box_width"] = int(getattr(self, "analysis_number_box_width", 40))
        try:
            self.app_options["brush_size"] = max(1, min(500, int(getattr(getattr(self, "view", None), "brush_size", 25) or 25)))
        except Exception:
            self.app_options["brush_size"] = int(self.app_options.get("brush_size", 25) or 25)
        self.app_options[PAGE_TAB_DISPLAY_MODE_KEY] = normalize_page_display_mode(getattr(self, "page_tab_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        self.app_options[OUTPUT_DISPLAY_MODE_KEY] = normalize_page_display_mode(getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        self.app_options[OUTPUT_IMAGE_FORMAT_KEY] = normalize_output_image_format(getattr(self, "output_image_format", DEFAULT_OUTPUT_IMAGE_FORMAT))
        self.app_options[CLEAN_IMAGE_FORMAT_KEY] = normalize_output_image_format(getattr(self, "clean_image_format", DEFAULT_OUTPUT_IMAGE_FORMAT))
        self.app_options[OUTPUT_IMAGE_QUALITY_KEY] = normalize_output_image_quality(getattr(self, "output_image_quality", DEFAULT_OUTPUT_IMAGE_QUALITY))
        self.app_options[CLEAN_IMAGE_QUALITY_KEY] = normalize_output_image_quality(getattr(self, "clean_image_quality", DEFAULT_OUTPUT_IMAGE_QUALITY))
        self.app_options[OUTPUT_TEXT_RENDER_QUALITY_KEY] = normalize_output_text_render_quality(getattr(self, "output_text_render_quality", DEFAULT_OUTPUT_TEXT_RENDER_QUALITY))
        self.app_options[LOG_PANEL_COLLAPSED_KEY] = bool(getattr(self, "log_panel_collapsed", DEFAULT_LOG_PANEL_COLLAPSED))
        self.app_options[SHOW_PATHS_IN_LOG_KEY] = bool(getattr(self, "show_paths_in_log", False))
        self.app_options[SHOW_CACHE_PATHS_IN_SETTINGS_KEY] = bool(getattr(self, "show_cache_paths_in_settings", False))
        self.app_options["interface_tooltips_enabled"] = bool(getattr(self, "interface_tooltips_enabled", True))
        self.app_options["use_light_file_dialog"] = bool(getattr(self, "use_light_file_dialog", True))
        self.app_options["temp_auto_cleanup_enabled"] = bool(self.app_options.get("temp_auto_cleanup_enabled", True))
        cleanup_days = int(self.app_options.get("temp_auto_cleanup_days", 7) or 7)
        if cleanup_days not in (7, 30, 90, 180, 365):
            cleanup_days = 7
        self.app_options["temp_auto_cleanup_days"] = cleanup_days
        self.app_options[ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY] = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY, getattr(Config, "MERGE_RATIO", DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO)),
            DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO,
        )
        self.app_options[ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY] = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY, getattr(Config, "INPAINT_RATIO", DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO)),
            DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO,
        )
        self.app_options[ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY] = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY, getattr(Config, "MERGE_MIN_STROKE_PX", DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX)),
            DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX,
        )
        self.app_options[ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY] = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY, getattr(Config, "MIN_STROKE_PX", DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX)),
            DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX,
        )
        self.sync_analysis_mask_options_to_config()
        self.app_options.setdefault(TRANSLATION_PROMPT_KEY, "")
        self.app_options.setdefault(TRANSLATION_GLOSSARY_TEXT_KEY, "")
        self.app_options.setdefault(TRANSLATION_GLOSSARY_PATH_KEY, "")
        save_app_options(self.app_options)

    def page_name_mode_label_pairs(self):
        return [
            (PAGE_DISPLAY_MODE_ORIGINAL, "원본 파일명"),
            (PAGE_DISPLAY_MODE_PAGE_ORIGINAL, "1p_원본 파일명"),
            (PAGE_DISPLAY_MODE_PAGE_NUMBER, "page001"),
        ]

    def ask_page_name_mode(self, title, current_mode):
        pairs = self.page_name_mode_label_pairs()
        current_mode = normalize_page_display_mode(current_mode)
        labels = [label for _mode, label in pairs]
        current_index = 0
        for i, (mode, _label) in enumerate(pairs):
            if mode == current_mode:
                current_index = i
                break
        value, ok = QInputDialog.getItem(
            self,
            self.tr_ui(title),
            self.tr_ui("표시명 형식:"),
            [self.tr_ui(label) for label in labels],
            current_index,
            False,
        )
        if not ok:
            return None
        try:
            selected_index = [self.tr_ui(label) for label in labels].index(value)
        except ValueError:
            selected_index = current_index
        return pairs[selected_index][0]

    def open_page_tab_display_name_dialog(self):
        old_mode = normalize_page_display_mode(getattr(self, "page_tab_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        new_mode = self.ask_page_name_mode("페이지 탭 표시명 설정", old_mode)
        if not new_mode or new_mode == old_mode:
            return False
        self.page_tab_display_name_mode = normalize_page_display_mode(new_mode)
        self.save_app_options_cache()
        self.refresh_page_tabs()
        self.log(f"📑 페이지 탭 표시명 설정: {self.page_tab_display_name_mode}")
        return True

    def open_output_display_name_dialog(self):
        old_mode = normalize_page_display_mode(getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        new_mode = self.ask_page_name_mode("출력 표시명 설정", old_mode)
        if not new_mode or new_mode == old_mode:
            return False
        self.output_display_name_mode = normalize_page_display_mode(new_mode)
        self.save_app_options_cache()
        self.log(f"📤 출력 표시명 설정: {self.output_display_name_mode}")
        return True

    def sync_translation_option_cache_to_config(self):
        """옵션 캐시에 저장된 번역 프롬프트/단어장을 번역 엔진 Config에 반영한다."""
        try:
            Config.TRANSLATION_PROMPT = str(self.app_options.get(TRANSLATION_PROMPT_KEY, "") or "")
            Config.TRANSLATION_GLOSSARY_TEXT = str(self.app_options.get(TRANSLATION_GLOSSARY_TEXT_KEY, "") or "")
        except Exception:
            pass

    def sync_analysis_mask_options_to_config(self):
        """옵션 캐시의 분석 마스크 확장 설정을 엔진 Config에 반영한다."""
        try:
            text_ratio = clamp_analysis_mask_ratio(
                self.app_options.get(ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO),
                DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO,
            )
            paint_ratio = clamp_analysis_mask_ratio(
                self.app_options.get(ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO),
                DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO,
            )
            text_min_px = clamp_analysis_mask_min_px(
                self.app_options.get(ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX),
                DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX,
            )
            paint_min_px = clamp_analysis_mask_min_px(
                self.app_options.get(ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX),
                DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX,
            )
            self.app_options[ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY] = text_ratio
            self.app_options[ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY] = paint_ratio
            self.app_options[ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY] = text_min_px
            self.app_options[ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY] = paint_min_px
            Config.MERGE_RATIO = text_ratio
            Config.INPAINT_RATIO = paint_ratio
            Config.MERGE_MIN_STROKE_PX = text_min_px
            Config.MIN_STROKE_PX = paint_min_px
        except Exception:
            pass

    def reload_saved_project_from_disk(self, refresh_view=True):
        """실제 프로젝트 저장본을 다시 로드해서 paths를 프로젝트 폴더 기준으로 되돌린다."""
        if not self.project_dir:
            return False
        project_file = os.path.join(self.project_dir, PROJECT_FILENAME)
        if not os.path.exists(project_file):
            return False

        self.is_loading_project = True
        try:
            store = ProjectStore()
            self.paths, self.data, self.idx = store.load(project_file)
            self.project_store = store
            self.project_dir = store.project_dir
            ui_state = getattr(store, "ui_state", {}) or {}
            self.project_ui_view_states = copy.deepcopy(ui_state.get("view_states") or getattr(self, "project_ui_view_states", {}) or {})
            self.restore_project_ui_state(ui_state, refresh=False)
            if refresh_view:
                mode_to_load = int(ui_state.get("current_mode", self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0) or 0)
                self.set_work_mode_without_undo(mode_to_load)
                self.load()
                state = self.project_ui_view_states.get(self.view_state_key(self.idx, mode_to_load))
                if state:
                    self.apply_view_state(state)
                    QTimer.singleShot(0, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                    QTimer.singleShot(30, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                    QTimer.singleShot(80, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            return True
        finally:
            self.is_loading_project = False

    def commit_to_real_project_only(self):
        """작업 캐시 상태를 실제 프로젝트에 저장하되, 새 작업 캐시는 만들지 않는다."""
        if not self.project_dir:
            return False
        self.commit_current_page_ui_to_data()
        self.save_project_store(self.project_store)
        self.mark_saved_state()
        try:
            self.clear_pending_clean_import_cache(getattr(self, "work_project_dir", None))
            self.clear_pending_clean_import_cache(getattr(self, "project_dir", None))
        except Exception:
            pass
        return True

    def toggle_auto_save_mode(self, checked=False):
        """Deprecated: 실시간 자동저장 모드는 YSBT 패키지 구조 이후 폐지되었다.

        일반 편집 변경분은 복구용 작업 캐시에 저장되고, 실제 .ysbt 반영은
        [프로젝트 저장]/[다른 이름으로 저장]에서만 확정한다.
        """
        self.auto_save_enabled = False
        try:
            self.app_options["auto_save_enabled"] = False
            self.save_app_options_cache()
        except Exception:
            pass
        try:
            action = getattr(self, "act_auto_save_mode", None)
            if action is not None:
                action.blockSignals(True)
                action.setChecked(False)
                action.setEnabled(False)
                action.setVisible(False)
                action.blockSignals(False)
        except Exception:
            pass
        try:
            self.log("🧪 자동저장 모드는 폐지되었습니다. 변경 사항은 작업 캐시에 보관되고, 프로젝트 저장 시 YSBT에 확정됩니다.")
        except Exception:
            pass

    def confirm_unsaved_before_switch(self):
        if not self.has_open_project():
            try:
                self.clear_pending_work_cache_save_state("confirm_without_project")
            except Exception:
                pass
            self.has_unsaved_changes = False
            return True
        if not self.has_unsaved_changes:
            return True

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("저장하지 않은 작업"))
        msg.setText(self.tr_ui("저장하지 않은 작업이 있습니다."))
        msg.setInformativeText(self.tr_ui("현재 프로젝트를 닫기 전에 저장할까요?"))
        btn_save = msg.addButton(self.tr_ui("저장"), QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton(self.tr_ui("저장 안 함"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_save:
            self.save_project()
            return not self.has_unsaved_changes
        if clicked == btn_discard:
            self.cleanup_work_cache()
            self.delete_temp_project_if_needed()
            self.has_unsaved_changes = False
            return True
        return False

    def closeEvent(self, event):
        """프로그램 종료 처리.

        최종화면의 인라인 텍스트 편집/QGraphics 상태가 열린 채로 종료 확인창이 뜨면
        focusOutEvent와 closeEvent가 겹쳐 예외가 날 수 있다. 종료 전에 현재 편집 상태를
        먼저 안전하게 확정하고, 종료 처리 중 예외가 나도 프로그램이 바로 튕기지 않게 막는다.
        """
        try:
            if getattr(self, "is_batch_running", False):
                _save_ui_diag("MESSAGEBOX_DONE_BEGIN")
                QMessageBox.information(
                    self,
                    self.tr_ui("일괄 작업 중"),
                    self.tr_ui("일괄 작업 중에는 프로그램을 종료할 수 없습니다.\n작업이 끝난 뒤 다시 종료해 주세요."),
                )
                event.ignore()
                return

            if getattr(self, "_closing_confirmed", False):
                self.cleanup_external_open_runtime_info()
                event.accept()
                return

            self._app_is_closing = True

            # 핵심 보정: 최종화면 인라인 텍스트 편집 중 종료하면 QMessageBox 포커스 이동으로
            # finish_inline_text_edit()가 closeEvent 도중 재진입할 수 있다. 먼저 확정해서 안정화한다.
            if getattr(self, "inline_text_editor", None) is not None:
                try:
                    self.finish_inline_text_edit(commit=True, refresh=False)
                except Exception as e:
                    self.log(f"⚠️ 종료 전 텍스트 편집 확정 실패: {e}")

            # 최종화면/표의 현재 UI 상태를 가능한 한 data에 반영한다. 실패해도 종료 확인창은 유지한다.
            try:
                if getattr(self, "project_dir", None) and getattr(self, "paths", None):
                    self.commit_current_page_ui_to_data()
                    if getattr(self, "auto_save_enabled", False):
                        self.auto_save_project()
            except Exception as e:
                self.log(f"⚠️ 종료 전 현재 화면 상태 반영 실패: {e}")

            if self.has_unsaved_changes:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle(self.tr_ui("저장하지 않은 작업"))
                msg.setText(self.tr_ui("저장하지 않은 작업이 있습니다."))
                msg.setInformativeText(self.tr_ui("종료하기 전에 프로젝트를 저장할까요?"))
                btn_save = msg.addButton(self.tr_ui("저장"), QMessageBox.ButtonRole.AcceptRole)
                btn_discard = msg.addButton(self.tr_ui("저장 안 함"), QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
                msg.setDefaultButton(btn_save)
                msg.exec()

                clicked = msg.clickedButton()
                if clicked == btn_cancel:
                    self._app_is_closing = False
                    event.ignore()
                    return
                if clicked == btn_save:
                    self.save_project()
                    if self.has_unsaved_changes:
                        self._app_is_closing = False
                        event.ignore()
                        return
                    # 저장에 성공했고 곧 종료할 것이므로 복구용 작업 캐시는 남기지 않는다.
                    try:
                        self.cleanup_work_cache()
                    except Exception as e:
                        self.log(f"⚠️ 작업 캐시 정리 실패: {e}")
                elif clicked == btn_discard:
                    try:
                        self.cleanup_work_cache()
                    except Exception as e:
                        self.log(f"⚠️ 작업 캐시 정리 실패: {e}")
                    try:
                        self.delete_temp_project_if_needed()
                    except Exception as e:
                        self.log(f"⚠️ 임시 프로젝트 삭제 실패: {e}")
                    self.has_unsaved_changes = False
            else:
                # 정상 종료 시 남은 작업 캐시는 삭제한다. 실패해도 종료 자체를 튕기게 만들지 않는다.
                try:
                    self.cleanup_work_cache()
                except Exception as e:
                    self.log(f"⚠️ 작업 캐시 정리 실패: {e}")

            self.cleanup_external_open_runtime_info()
            self._closing_confirmed = True
            event.accept()
        except Exception as e:
            self._app_is_closing = False
            try:
                import traceback
                detail = traceback.format_exc()
                self.log(f"❌ 종료 처리 중 오류: {e}")
                QMessageBox.critical(
                    self,
                    self.tr_ui("종료 오류"),
                    self.tr_ui("프로그램 종료 처리 중 오류가 발생했습니다.\n작업 보호를 위해 종료를 취소합니다.") + f"\n\n{detail}",
                )
            except Exception:
                pass
            event.ignore()

    def default_empty_project_name(self):
        """빈 프로젝트 생성 기본 이름을 만든다."""
        try:
            return self.tr_ui("새 프로젝트")
        except Exception:
            return "새 프로젝트"

    def project_creation_preview_path(self, parent_dir, project_name):
        """새 빈 프로젝트가 생성될 YSBT 경로를 미리 보여준다."""
        try:
            parent = Path(str(parent_dir or workspaces_dir())).expanduser()
        except Exception:
            parent = workspaces_dir()
        name = clean_workspace_name(project_name or self.default_empty_project_name())
        return str(parent / f"{safe_project_name(name)}{YSB_EXTENSION}")

    def remember_last_project_create_dir(self, directory):
        try:
            directory = str(directory or "").strip()
            if not directory:
                return
            self.app_options[LAST_PROJECT_CREATE_DIR_KEY] = directory
            save_app_options(self.app_options)
        except Exception:
            pass

    def resolve_initial_project_create_dir(self):
        fallback = str(workspaces_dir())
        saved = str((self.app_options or {}).get(LAST_PROJECT_CREATE_DIR_KEY, "") or "").strip()
        if saved and os.path.isdir(saved):
            return saved
        if saved and not os.path.isdir(saved):
            QMessageBox.warning(
                self,
                self.tr_ui("프로젝트 생성 위치 확인"),
                self.tr_ui("마지막 프로젝트 생성 위치를 찾지 못했습니다.\n새 위치를 선택해 주세요."),
            )
            chosen = QFileDialog.getExistingDirectory(self, self.tr_ui("프로젝트 생성 위치 선택"), fallback)
            if chosen:
                self.remember_last_project_create_dir(chosen)
                return chosen
        return fallback

    def build_create_project_ysbt_path(self, parent_dir, project_name):
        """새 프로젝트 만들기에서 사용자가 입력한 이름 그대로의 YSBT 경로를 만든다.

        중복 이름은 자동 suffix를 붙이지 않고, 생성창에서 사용자에게
        이름 변경/덮어쓰기/취소를 물어본다.
        """
        parent = Path(str(parent_dir or workspaces_dir())).expanduser()
        parent.mkdir(parents=True, exist_ok=True)
        safe_name = safe_project_name(clean_workspace_name(project_name or self.default_empty_project_name()))
        return str(parent / f"{safe_name}{YSB_EXTENSION}")

    def build_unique_create_project_ysbt_path(self, parent_dir, project_name):
        return self.build_create_project_ysbt_path(parent_dir, project_name)

    def new_empty_project_action(self):
        """이미지 없이 빈 프로젝트를 먼저 생성한다."""
        if not self.guard_project_action("새 프로젝트 만들기"):
            return False

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("새 프로젝트 만들기"))
        dlg.setModal(True)
        dlg.resize(560, 220)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        name_label = QLabel(self.tr_ui("프로젝트 이름"), dlg)
        name_edit = QLineEdit(dlg)
        name_edit.setText(self.default_empty_project_name())
        name_edit.selectAll()
        layout.addWidget(name_label)
        layout.addWidget(name_edit)

        location_label = QLabel(self.tr_ui("생성 위치"), dlg)
        location_row = QHBoxLayout()
        location_edit = QLineEdit(dlg)
        try:
            location_edit.setText(self.resolve_initial_project_create_dir())
        except Exception:
            location_edit.setText(str(workspaces_dir()))
        browse_btn = QToolButton(dlg)
        browse_btn.setText("⋯")
        browse_btn.setFixedWidth(34)
        location_row.addWidget(location_edit, 1)
        location_row.addWidget(browse_btn, 0)
        layout.addWidget(location_label)
        layout.addLayout(location_row)

        preview_label = QLabel(dlg)
        preview_label.setWordWrap(True)
        preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_label.setObjectName("ProjectCreatePathPreview")
        try:
            preview_label.setStyleSheet("QLabel#ProjectCreatePathPreview { color:#9fb7d8; padding:6px 0px; }")
        except Exception:
            pass
        layout.addWidget(preview_label)

        info_label = QLabel(self.tr_ui("프로젝트 이름과 생성 위치를 먼저 확정하고, 빈 프로젝트(.ysbt)를 만든 뒤 나중에 이미지 불러오기로 페이지를 추가합니다."), dlg)
        info_label.setWordWrap(True)
        try:
            info_label.setStyleSheet("color:#A39BA1;")
        except Exception:
            pass
        layout.addWidget(info_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        try:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("만들기"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("취소"))
        except Exception:
            pass
        layout.addWidget(buttons)

        def update_preview():
            try:
                preview = self.project_creation_preview_path(location_edit.text(), name_edit.text())
                preview_label.setText(f"{self.tr_ui('생성 경로')}: {preview}")
            except Exception:
                pass

        def browse_location():
            start = location_edit.text().strip() or str(workspaces_dir())
            folder = QFileDialog.getExistingDirectory(dlg, self.tr_ui("프로젝트 생성 위치 선택"), start)
            if folder:
                location_edit.setText(folder)
                update_preview()

        overwrite_choice = {"value": False}

        def accept_with_duplicate_check():
            project_name_now = clean_workspace_name(name_edit.text() or self.default_empty_project_name())
            parent_dir_now = location_edit.text().strip() or str(workspaces_dir())
            try:
                candidate_path = self.build_create_project_ysbt_path(parent_dir_now, project_name_now)
            except Exception:
                candidate_path = self.project_creation_preview_path(parent_dir_now, project_name_now)

            if candidate_path and os.path.exists(candidate_path):
                msg = QMessageBox(dlg)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle(self.tr_ui("이름 중복"))
                msg.setText(self.tr_ui("같은 이름의 YSBT 프로젝트가 이미 있습니다."))
                msg.setInformativeText(str(candidate_path))
                btn_rename = msg.addButton(self.tr_ui("이름 바꾸기"), QMessageBox.ButtonRole.AcceptRole)
                btn_overwrite = msg.addButton(self.tr_ui("덮어쓰기"), QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
                msg.setDefaultButton(btn_rename)
                msg.setEscapeButton(btn_cancel)
                try:
                    msg.setStyleSheet(self.message_box_style())
                except Exception:
                    pass
                force_message_box_front(msg)
                msg.exec()
                clicked = msg.clickedButton()

                if clicked is btn_rename:
                    overwrite_choice["value"] = False
                    name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
                    name_edit.selectAll()
                    return
                if clicked is btn_overwrite:
                    overwrite_choice["value"] = True
                    dlg.accept()
                    return
                return

            overwrite_choice["value"] = False
            dlg.accept()

        browse_btn.clicked.connect(browse_location)
        name_edit.textChanged.connect(update_preview)
        location_edit.textChanged.connect(update_preview)
        buttons.accepted.connect(accept_with_duplicate_check)
        buttons.rejected.connect(dlg.reject)
        update_preview()

        name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False

        project_name = clean_workspace_name(name_edit.text() or self.default_empty_project_name())
        parent_dir = location_edit.text().strip() or str(workspaces_dir())
        return self.create_empty_project(project_name=project_name, parent_dir=parent_dir, overwrite_existing=bool(overwrite_choice.get("value")))

    def create_empty_project(self, project_name="새 프로젝트", parent_dir=None, overwrite_existing=False):
        """이미지 없는 빈 프로젝트를 만들고, 즉시 YSBT까지 생성한 뒤 에디터로 진입한다."""
        if not self.guard_project_action("새 프로젝트 만들기"):
            return False
        if not self.confirm_unsaved_before_switch():
            return False

        project_name = clean_workspace_name(project_name or self.default_empty_project_name())
        try:
            parent = Path(str(parent_dir or workspaces_dir())).expanduser()
            parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("프로젝트 생성 실패"),
                f"{self.tr_ui('프로젝트 생성 위치를 만들 수 없습니다.')}\n{parent_dir}\n\n{e}",
            )
            return False

        try:
            self.commit_current_page_ui_to_data()
        except Exception:
            pass

        package_seed = self.build_create_project_ysbt_path(parent, project_name)
        package_path, display_project_name, project_uuid = self.make_ysbt_path_with_uuid_suffix(package_seed)
        if os.path.exists(package_path) and not overwrite_existing:
            QMessageBox.warning(
                self,
                self.tr_ui("이름 중복"),
                f"{self.tr_ui('같은 이름의 YSBT 프로젝트가 이미 있습니다.')}\n{package_path}",
            )
            return False
        project_dir = self.workspace_project_dir(display_project_name, code=project_uuid[:8], append_code=True)
        try:
            store = ProjectStore(project_dir)
            store.init_dirs()
            store.ui_state = {"current_mode": 0, "view_states": {}, "show_final_text": True}
            store.save([], {}, current_index=0)
            store.write_manifest(package_source=package_path, project_name=display_project_name, project_uuid=project_uuid)
            if overwrite_existing and os.path.exists(package_path):
                try:
                    os.remove(package_path)
                except Exception:
                    pass
            package_project(project_dir, package_path, project_name=display_project_name, project_uuid=project_uuid)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("프로젝트 생성 실패"),
                f"{self.tr_ui('빈 프로젝트를 만들지 못했습니다.')}\n{package_path}\n\n{e}",
            )
            return False

        self.close_current_project_state_for_switch()
        self.project_store = store
        self.project_dir = project_dir
        self.paths = []
        self.data = {}
        self.idx = 0
        self.undo_clear_all_pages("project reset")
        self.undo_clear_project("project reset")
        self.undo_boundary = None
        self.project_ui_view_states = {}
        self.ysbt_package_path = package_path
        self.is_temp_project = False
        self.suggested_project_name = display_project_name
        self.suggested_package_dir = str(parent)
        self.work_project_dir = None
        self.work_project_store = None
        self.is_loading_project = False
        self.record_recovery_project_dir(project_dir)
        self.remember_last_project_create_dir(parent)
        self.mark_saved_state()
        self.update_window_title()
        self.update_undo_redo_buttons()
        self.reset_mode_to_original()
        self.show_editor()
        self.load()
        self.record_current_project_recent()
        self.log(f"📁 빈 프로젝트 생성: {project_dir}")
        self.log(f"💾 YSBT가 저장되었습니다: {package_path}")
        self.log("🖼️ 아직 이미지가 없습니다. [이미지 불러오기] 또는 페이지 탭의 [+]로 페이지를 추가하세요.")
        if not self.auto_save_enabled:
            self.start_work_cache_from_current(mark_dirty=False)
        return True

    def create_new_project_from_image_paths(self, source_paths, source_label="이미지 드롭"):
        source_paths = self.normalize_image_drop_paths(source_paths)
        if not source_paths:
            self.log("⚠️ 불러올 이미지 파일이 없습니다.")
            return False
        if not self.guard_project_action("새 프로젝트 만들기"):
            return False
        if not self.confirm_unsaved_before_switch():
            return False

        # 프로젝트 이름은 첫 생성 때 묻지 않는다.
        # 실제 이름은 .ysbt로 저장할 때 파일명 기준으로 확정된다.
        self.suggested_project_name = safe_project_name(Path(source_paths[0]).stem + "_project")
        self.suggested_package_dir = None
        project_dir = self.workspace_temp_project_dir(self.suggested_project_name)

        self.commit_current_page_ui_to_data()

        self.project_store = ProjectStore(project_dir)
        self.paths, self.data = self.project_store.create_from_images(project_dir, source_paths)
        self.undo_clear_all_pages("project reset")
        self.undo_clear_project("project reset")
        self.undo_boundary = None
        self.update_undo_redo_buttons()
        self.project_ui_view_states = {}
        self.project_store.write_manifest(project_name="unsaved_project")
        self.project_dir = project_dir
        self.enforce_initial_project_image_names(source_paths)
        self.record_recovery_project_dir(project_dir)
        self.ysbt_package_path = None
        self.is_temp_project = True
        self.update_window_title()
        self.idx = 0
        self.is_loading_project = False
        self.log(f"📁 새 임시 프로젝트 작업 폴더 생성: {project_dir}")
        self.log("💾 아직 YSBT 파일로 저장되지 않았습니다. [프로젝트 저장] 또는 [다른 이름으로 저장]을 눌러 .ysbt로 저장하세요.")
        self.log(f"🖼️ 이미지 {len(source_paths)}장으로 새 프로젝트 생성: {source_label}")
        self.has_unsaved_changes = True
        if not self.auto_save_enabled:
            self.start_work_cache_from_current(mark_dirty=True)
            self.enforce_initial_project_image_names(source_paths)
        self.reset_mode_to_original()
        self.show_editor()
        self.load()
        return True

    def import_images_action(self):
        """이미지를 불러온다. 작업 중이면 현재 페이지 뒤에 삽입하고, 홈에서는 새 프로젝트로 시작한다."""
        try:
            self._file_dialog_log("FILE_DIALOG_ACTION_TRIGGER", reason="import_images_action", has_open_project=bool(self.has_open_project()), stack_widget=str(type(self.main_stack.currentWidget()).__name__) if hasattr(self, "main_stack") else "")
        except Exception:
            pass
        source_paths, _ = self.get_open_file_names_logged(
            "import_images_action",
            self,
            self.tr_ui("불러올 이미지 선택"),
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
        )
        if not source_paths:
            return
        try:
            in_editor = (
                hasattr(self, "main_stack")
                and hasattr(self, "editor_widget")
                and self.main_stack.currentWidget() is self.editor_widget
            )
        except Exception:
            in_editor = False
        if in_editor and self.has_open_project():
            return self.insert_images_after_current(source_paths)
        return self.create_new_project_from_image_paths(source_paths, source_label="이미지 불러오기")

    def new_project_from_images(self):
        try:
            self._file_dialog_log("FILE_DIALOG_ACTION_TRIGGER", reason="new_project_from_images")
        except Exception:
            pass
        source_paths, _ = self.get_open_file_names_logged(
            "new_project_from_images",
            self,
            self.tr_ui("프로젝트에 넣을 이미지 선택"),
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
        )
        if not source_paths:
            return
        self.create_new_project_from_image_paths(source_paths, source_label="파일 선택")

    def open_project(self):
        try:
            self._file_dialog_log("FILE_DIALOG_ACTION_TRIGGER", reason="open_project_ysbt")
        except Exception:
            pass
        """YSBT 전용 프로젝트 열기.

        v1.6부터 기본 프로젝트 열기는 .ysbt 패키지만 지원한다.
        구버전 폴더/project.json 열기 흐름은 아래에 주석으로 남겨두고,
        별도 메뉴인 [JSON으로 열기]에서만 project.json을 열 수 있게 분리한다.
        """
        if not self.guard_project_action("프로젝트 열기"):
            return

        path, _ = self.get_open_file_name_logged(
            "open_project_ysbt",
            self,
            self.tr_ui("YSBT 프로젝트 열기"),
            str(default_package_dir()),
            ("YSBT Project (*.ysbt);;All Files (*.*)" if str(getattr(self, "ui_language", LANG_KO)).lower().startswith("en") else "YSBT 프로젝트 (*.ysbt);;모든 파일 (*.*)")
        )
        if not path:
            return

        self.open_project_path(path)

    def open_project_json(self):
        """구버전/디버그용 project.json 직접 열기. 기본 열기와 분리한다."""
        try:
            self._file_dialog_log("FILE_DIALOG_ACTION_TRIGGER", reason="open_project_json")
        except Exception:
            pass
        self._file_dialog_log("FILE_DIALOG_GUARD_ENTER", reason="open_project_json")
        if not self.guard_project_action("JSON으로 열기"):
            self._file_dialog_log("FILE_DIALOG_GUARD_BLOCKED", reason="open_project_json")
            return
        self._file_dialog_log("FILE_DIALOG_GUARD_DONE", reason="open_project_json")

        path, _ = self.get_open_file_name_logged(
            "open_project_json",
            self,
            self.tr_ui("프로젝트 JSON 열기"),
            str(workspaces_dir()),
            "Project JSON (project.json);;JSON (*.json);;All Files (*.*)"
        )
        if not path:
            return

        self.open_project_path(path)

    def save_project(self):
        def _save_ui_diag(event: str, **fields):
            try:
                root = os.environ.get("LOCALAPPDATA")
                if not root:
                    root = os.path.join(str(Path.home()), "AppData", "Local")
                log_dir = os.path.join(root, "YSBTranslator", "logs")
                os.makedirs(log_dir, exist_ok=True)
                path = os.path.join(log_dir, "save_package_diag.log")
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                parts = [f"[{ts}]", f"UI_{event}"]
                for k, v in fields.items():
                    try:
                        sv = repr(v)
                    except Exception:
                        sv = "<unrepr>"
                    parts.append(f"{k}={sv}")
                with open(path, "a", encoding="utf-8") as f:
                    f.write(" | ".join(parts) + "\n")
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except Exception:
                        pass
            except Exception:
                pass

        _save_ui_diag("SAVE_PROJECT_ENTER", page_idx=getattr(self, "idx", None), ysbt=getattr(self, "ysbt_package_path", None), project_dir=getattr(self, "project_dir", None))
        try:
            self.audit_boundary_event("SAVE_PROJECT_ENTER", stack=True)
        except Exception:
            pass
        if not self.guard_project_action("프로젝트 저장"):
            return
        if not self.project_dir:
            self.log("⚠️ 프로젝트가 없습니다. 새 프로젝트를 먼저 만들어주세요.")
            return
        if not self.ysbt_package_path:
            # 새 프로젝트/구버전 폴더 프로젝트는 첫 저장 때 .ysbt 위치를 정한다.
            self.save_project_as()
            return

        total_pages = len(getattr(self, "paths", []) or [])
        self._long_task_cancel_requested = False
        self._active_long_task_kind = "save"
        save_cancelled = False
        dirty_count = 0
        structure_dirty = True
        save_mode_text = "YSBT 저장"

        self.begin_busy_state("프로젝트 저장")
        try:
            self.show_task_progress_overlay(
                "프로젝트 저장",
                f"""전체 페이지: {total_pages}개
변경 페이지: 계산 중
저장 진행: 0/{total_pages}
잠시 후 저장을 시작합니다.""",
                total=total_pages,
                cancellable=True,
            )
            try:
                overlay = getattr(self, "_task_progress_overlay", None)
                if overlay is not None:
                    overlay.note_label.setText("취소 시 현재 저장 항목이 끝난 뒤 중단됩니다.")
            except Exception:
                pass
            try:
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
                QThread.msleep(300)
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            except Exception:
                pass
            if bool(getattr(self, "_long_task_cancel_requested", False)):
                raise PackageProjectCancelled("저장 시작 전 취소되었습니다.")

            try:
                if hasattr(self, "project_engine") and self.project_engine is not None:
                    self.project_engine.begin_explicit_save()
            except Exception:
                pass
            try:
                self.flush_pending_view_layer_commit(save_after=False)
            except Exception:
                pass
            self.update_task_progress_overlay(current=0, total=total_pages, detail=f"""전체 페이지: {total_pages}개
변경 페이지: 계산 중
저장 진행: 0/{total_pages}
현재 작업: 현재 화면 상태를 저장 데이터에 반영하는 중입니다...""")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            _save_ui_diag("COMMIT_CURRENT_PAGE_UI_BEGIN", total_pages=total_pages)
            self.commit_current_page_ui_to_data()
            _save_ui_diag("COMMIT_CURRENT_PAGE_UI_DONE", total_pages=total_pages)
            try:
                # 리팩토링 중 일부 구형 편집 경로가 dirty flag를 못 찍는 경우를 방어한다.
                pe = getattr(self, "project_engine", None)
                if bool(getattr(self, "has_unsaved_changes", False)) and pe is not None and not pe.has_dirty():
                    page_idx = int(getattr(self, "idx", 0) or 0)
                    pe.mark_page_dirty(page_idx, "save_fallback")
                    if hasattr(self, "page_engine") and self.page_engine is not None:
                        self.page_engine.mark_dirty(page_idx, "save_fallback")
            except Exception:
                pass

            try:
                pe = getattr(self, "project_engine", None)
                page_dirty = False
                try:
                    page_dirty = bool(getattr(self, "page_engine", None) and self.page_engine.dirty_pages())
                except Exception:
                    page_dirty = False
                project_dirty = bool(pe.has_dirty()) if pe is not None else False
                if (
                    not bool(getattr(self, "has_unsaved_changes", False))
                    and not project_dirty
                    and not page_dirty
                    and not bool(getattr(self, "is_temp_project", False))
                ):
                    _save_ui_diag("SAVE_SKIPPED_NO_CHANGES")
                    try:
                        self.audit_boundary_event("SAVE_PROJECT_SKIPPED_NO_CHANGES")
                    except Exception:
                        pass
                    try:
                        self.log("💾 저장할 변경 사항이 없습니다.")
                    except Exception:
                        pass
                    self.mark_saved_state()
                    try:
                        self.mark_workspace_state_saved(getattr(self, "project_dir", None))
                    except Exception:
                        pass
                    self.record_current_project_recent()
                    self.hide_task_progress_overlay()
                    return
            except Exception:
                pass

            self.update_task_progress_overlay(current=0, total=total_pages, detail=f"""전체 페이지: {total_pages}개
변경 페이지: 계산 중
저장 진행: 0/{total_pages}
현재 작업: 변경된 페이지를 확인하는 중입니다...""")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            _save_ui_diag("SAVE_PROJECT_STORE_BEGIN")
            self.save_project_store(self.project_store)
            _save_ui_diag("SAVE_PROJECT_STORE_DONE")
            if bool(getattr(self, "_long_task_cancel_requested", False)):
                raise PackageProjectCancelled("YSBT 반영 전 저장이 취소되었습니다.")

            try:
                plan = getattr(getattr(self, "storage_engine", None), "last_plan", None)
                dirty_pages = set(getattr(plan, "dirty_pages", set()) or set()) if plan is not None else set()
                dirty_count = len(dirty_pages)
                structure_dirty = bool(plan.needs_full_save()) if plan is not None else True
                force_full_package = bool(getattr(self, "is_temp_project", False))
                if force_full_package:
                    structure_dirty = True
                    save_mode_text = "전체 YSBT 재패키징"
                    self.log("💾 [Save] 임시/복구 프로젝트 저장: 전체 YSBT 재패키징")
                elif structure_dirty:
                    save_mode_text = "전체 YSBT 재패키징"
                    self.log("💾 [Save] 프로젝트 구조 변경 감지: 전체 YSBT 재패키징")
                else:
                    save_mode_text = "증분 YSBT 저장"
                    self.log(f"💾 [Save] 변경 페이지 {dirty_count} / 전체 {total_pages}: 증분 YSBT 저장")
                self.update_task_progress_overlay(current=0, total=total_pages, detail=f"""전체 페이지: {total_pages}개
변경 페이지: {dirty_count}개
저장 진행: 0/{total_pages}
현재 작업: YSBT 반영을 준비하는 중입니다...""")
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

                def _save_progress(current=None, total=None, detail=None):
                    try:
                        show_total = int(total or total_pages or 0)
                        show_current = int(current or 0)
                        raw_detail = str(detail or "저장 중...")
                        if "최종 반영" in raw_detail:
                            overlay = getattr(self, "_task_progress_overlay", None)
                            if overlay is not None:
                                try:
                                    overlay.cancel_btn.setEnabled(False)
                                    overlay.note_label.setText("최종 반영 중입니다. 이 짧은 단계에서는 취소할 수 없습니다.")
                                except Exception:
                                    pass
                        formatted_detail = (
                            f"전체 페이지: {total_pages}개\n"
                            f"변경 페이지: {dirty_count}개\n"
                            f"저장 진행: {show_current}/{show_total}\n"
                            f"현재 작업: {raw_detail}"
                        )
                        self.update_task_progress_overlay(current=show_current, total=show_total, detail=formatted_detail)
                        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
                    except Exception:
                        pass

                def _save_cancel_requested():
                    return bool(getattr(self, "_long_task_cancel_requested", False))

                text_json_only_kinds = {"text", "checkpoint_text", "checkpoint_fallback", "data", "translation", "translated_text", "text_effect_preview"}
                json_fast_save = False
                dirty_kinds_for_save = {}
                try:
                    pe = getattr(self, "project_engine", None)
                    summary = pe.dirty_summary() if pe is not None and hasattr(pe, "dirty_summary") else {}
                    raw_dirty = summary.get("dirty_pages", {}) if isinstance(summary, dict) else {}
                    if isinstance(raw_dirty, dict):
                        for k, v in raw_dirty.items():
                            try:
                                dirty_kinds_for_save[int(k)] = {str(x or "data") for x in list(v or [])}
                            except Exception:
                                pass
                    if (
                        bool(dirty_pages)
                        and not bool(structure_dirty)
                        and not bool(getattr(self, "is_temp_project", False))
                        and os.path.exists(str(getattr(self, "ysbt_package_path", "") or ""))
                    ):
                        json_fast_save = True
                        for page_i in set(int(x) for x in dirty_pages):
                            kinds = dirty_kinds_for_save.get(int(page_i), set())
                            if not kinds or not set(kinds).issubset(text_json_only_kinds):
                                json_fast_save = False
                                break
                except Exception:
                    json_fast_save = False

                try:
                    plan_dirty_pages = sorted(int(x) for x in dirty_pages)
                except Exception:
                    plan_dirty_pages = []
                try:
                    all_dirty_kinds = sorted({str(kind) for kinds in dirty_kinds_for_save.values() for kind in (kinds or set())})
                except Exception:
                    all_dirty_kinds = []
                try:
                    json_fast_reject_reason = ""
                    if not json_fast_save:
                        if bool(structure_dirty):
                            json_fast_reject_reason = "structure_dirty"
                        elif not bool(dirty_pages):
                            json_fast_reject_reason = "no_dirty_pages"
                        elif bool(getattr(self, "is_temp_project", False)):
                            json_fast_reject_reason = "temp_project"
                        elif not os.path.exists(str(getattr(self, "ysbt_package_path", "") or "")):
                            json_fast_reject_reason = "missing_ysbt"
                        else:
                            json_fast_reject_reason = "non_text_dirty_kind_or_missing_kind"
                except Exception:
                    json_fast_reject_reason = "diagnostic_error"
                _save_ui_diag(
                    "PACKAGE_PROJECT_BEGIN",
                    save_mode=save_mode_text,
                    dirty_count=dirty_count,
                    structure_dirty=structure_dirty,
                    json_fast_save=json_fast_save,
                    dirty_pages=plan_dirty_pages,
                    dirty_kind_names=all_dirty_kinds,
                    json_fast_reject_reason=json_fast_reject_reason,
                    dirty_kinds=dirty_kinds_for_save,
                )
                try:
                    self.audit_boundary_event(
                        "SAVE_DIRTY_DIAG",
                        save_mode=save_mode_text,
                        dirty_count=dirty_count,
                        structure_dirty=structure_dirty,
                        json_fast_save=json_fast_save,
                        dirty_pages=plan_dirty_pages,
                        dirty_kind_names=all_dirty_kinds,
                        json_fast_reject_reason=json_fast_reject_reason,
                        throttle_ms=100,
                    )
                except Exception:
                    pass
                if json_fast_save:
                    try:
                        self.log(f"💾 [Save] 텍스트/번역 JSON 변경 {dirty_count}페이지: YSBT 빠른 저장")
                    except Exception:
                        pass
                    try:
                        append_project_json_to_package(
                            self.project_dir,
                            self.ysbt_package_path,
                            progress_callback=_save_progress,
                            cancel_checker=_save_cancel_requested,
                        )
                    except PackageProjectCancelled:
                        raise
                    except Exception as fast_e:
                        _save_ui_diag("JSON_FAST_SAVE_FALLBACK_PACKAGE", error=repr(fast_e))
                        try:
                            self.log(f"💾 [Save] 빠른 저장 불가 → 일반 증분 저장으로 전환: {fast_e}")
                        except Exception:
                            pass
                        package_project(
                            self.project_dir,
                            self.ysbt_package_path,
                            dirty_pages=dirty_pages,
                            structure_dirty=structure_dirty,
                            incremental=not structure_dirty,
                            progress_callback=_save_progress,
                            cancel_checker=_save_cancel_requested,
                        )
                else:
                    package_project(
                        self.project_dir,
                        self.ysbt_package_path,
                        dirty_pages=dirty_pages,
                        structure_dirty=structure_dirty,
                        incremental=not structure_dirty,
                        progress_callback=_save_progress,
                        cancel_checker=_save_cancel_requested,
                    )
                _save_ui_diag("PACKAGE_PROJECT_DONE", save_mode=save_mode_text, json_fast_save=json_fast_save)
            except PackageProjectCancelled:
                _save_ui_diag("PACKAGE_PROJECT_CANCELLED")
                save_cancelled = True
                self.has_unsaved_changes = True
                try:
                    self.log("⏹️ [Save] 프로젝트 저장 취소됨: 원본 YSBT는 변경되지 않았습니다.")
                except Exception:
                    pass
                self.hide_task_progress_overlay()
                QMessageBox.warning(
                    self,
                    self.tr_ui("프로젝트 저장 취소"),
                    """프로젝트 저장이 취소되었습니다.

원본 YSBT 파일은 변경되지 않았습니다.
현재 작업 내용은 프로그램과 복구용 작업 캐시에 남아 있습니다.
다시 저장하면 YSBT에 반영할 수 있습니다.""",
                )
                return
            except Exception as e:
                _save_ui_diag("PACKAGE_PROJECT_EXCEPTION", error=repr(e))
                msg_text = self.tr_ui("프로젝트는 작업 폴더에 저장했지만, YSBT 파일 저장에 실패했습니다.")
                self.hide_task_progress_overlay()
                QMessageBox.critical(self, self.tr_ui("YSBT 저장 실패"), f"""{msg_text}

{e}""")
                self.has_unsaved_changes = True
                return

            _save_ui_diag("MARK_SAVED_BEGIN")
            self.mark_saved_state()
            try:
                self.clear_pending_clean_import_cache(getattr(self, "work_project_dir", None))
                self.clear_pending_clean_import_cache(getattr(self, "project_dir", None))
            except Exception:
                pass
            _save_ui_diag("MARK_SAVED_DONE")
            self.update_window_title()
            self.log(f"💾 프로젝트 저장 완료: {self.ysbt_package_path}")
            self.record_current_project_recent()
            _save_ui_diag("HIDE_OVERLAY_BEGIN")
            self.hide_task_progress_overlay()
            _save_ui_diag("HIDE_OVERLAY_DONE")
            try:
                QMessageBox.information(
                    self,
                    self.tr_ui("프로젝트 저장 완료"),
                    f"""프로젝트 저장이 완료되었습니다.

전체 페이지: {total_pages}개
변경 페이지: {dirty_count}개""",
                )
            except Exception:
                pass

            # 저장 완료 후에는 화면을 다시 로드하지 않고, 작업 캐시도 다시 만들지 않는다.
            # 저장된 시점의 본체는 YSBT 파일이므로 복구용 work cache를 매번 full save로 재생성할 필요가 없다.
            # 닫기 중 저장이면 어차피 나갈 것이므로 기존 작업 캐시를 삭제하고,
            # 일반 저장이면 마지막 복구 후보 기록만 지워 저장 직후 "복구할 작업"으로 보이지 않게 한다.
            if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
                try:
                    _save_ui_diag("CLEANUP_WORK_CACHE_AFTER_SAVE_BEGIN", reason="closing")
                    self.cleanup_work_cache()
                    _save_ui_diag("CLEANUP_WORK_CACHE_AFTER_SAVE_DONE", reason="closing")
                except Exception as e:
                    _save_ui_diag("CLEANUP_WORK_CACHE_AFTER_SAVE_FAILED", reason="closing", error=repr(e))
            else:
                try:
                    _save_ui_diag("SKIP_WORK_CACHE_REBUILD_AFTER_SAVE")
                    self.forget_recovery_project_dir(getattr(self, "work_project_dir", None))
                except Exception:
                    pass
        except PackageProjectCancelled:
            self.has_unsaved_changes = True
            self.hide_task_progress_overlay()
            try:
                self.log("⏹️ [Save] 프로젝트 저장 취소됨: 원본 YSBT는 변경되지 않았습니다.")
            except Exception:
                pass
            QMessageBox.warning(
                self,
                self.tr_ui("프로젝트 저장 취소"),
                """프로젝트 저장이 취소되었습니다.

원본 YSBT 파일은 변경되지 않았습니다.
현재 작업 내용은 프로그램과 복구용 작업 캐시에 남아 있습니다.""",
            )
            return
        finally:
            _save_ui_diag("SAVE_PROJECT_FINALLY_BEGIN", save_cancelled=save_cancelled)
            try:
                if hasattr(self, "project_engine") and self.project_engine is not None:
                    self.project_engine.end_explicit_save()
            except Exception:
                pass
            try:
                self._active_long_task_kind = ""
            except Exception:
                pass
            if not save_cancelled:
                try:
                    # 정상 완료/실패 모두에서 남은 진행창을 정리한다. 취소 분기는 위에서 이미 정리한다.
                    if getattr(self, "_task_progress_overlay", None) is not None and self._task_progress_overlay.isVisible():
                        self.hide_task_progress_overlay()
                except Exception:
                    pass
            self.end_busy_state("프로젝트 저장")
            _save_ui_diag("SAVE_PROJECT_FINALLY_DONE")

    def ensure_save_as_output_parent(self, path_abs: str):
        """다른 이름으로 저장 대상 폴더가 없을 때 먼저 만든다."""
        parent = os.path.dirname(os.path.abspath(str(path_abs or "")))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

    def _write_image_for_save_as_fallback(self, img, dst_path: str) -> bool:
        """원본 이미지 경로가 사라진 경우 메모리 이미지/작업 이미지를 새 저장용 파일로 복구한다."""
        if img is None:
            return False
        try:
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            ext = Path(dst_path).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"):
                ext = ".png"
                dst_path = str(Path(dst_path).with_suffix(ext))

            if isinstance(img, (bytes, bytearray)):
                with open(dst_path, "wb") as f:
                    f.write(img)
                return os.path.exists(dst_path) and os.path.getsize(dst_path) > 0

            if isinstance(img, np.ndarray):
                encode_ext = ".jpg" if ext == ".jpeg" else ext
                ok, buf = cv2.imencode(encode_ext, img)
                if ok:
                    buf.tofile(dst_path)
                    return os.path.exists(dst_path) and os.path.getsize(dst_path) > 0
        except Exception:
            return False
        return False

    def prepare_save_as_paths_for_store(self, target_project_dir: str):
        """Save As용 이미지 경로 목록을 만든다.

        ProjectStore.save()는 원본 이미지 파일이 실제 디스크에 있어야 새 프로젝트 폴더로 복사할 수 있다.
        그런데 작업 폴더 이동/임시 캐시 정리/구버전 경로 문제로 self.paths의 일부가 사라진 경우
        다른 이름으로 저장이 [WinError 3]로 실패할 수 있다.

        이 함수는 저장 전에 각 이미지 경로를 확인하고,
        경로가 없으면 현재 프로젝트 images 폴더나 메모리의 ori/working_source로 복구한다.
        """
        prepared = list(self.paths or [])
        image_dir = os.path.join(str(target_project_dir), "images")
        os.makedirs(image_dir, exist_ok=True)

        project_images_dir = os.path.join(str(self.project_dir or ""), "images")
        known_exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")

        for i, src in enumerate(prepared):
            src_text = str(src or "")
            if src_text and os.path.exists(src_text):
                continue

            candidates = []
            if src_text:
                candidates.append(src_text)
                if self.project_dir and not os.path.isabs(src_text):
                    candidates.append(os.path.join(str(self.project_dir), src_text))
                if self.project_dir:
                    candidates.append(os.path.join(str(self.project_dir), "images", os.path.basename(src_text)))

            if os.path.isdir(project_images_dir):
                try:
                    for ext in known_exts:
                        candidates.append(os.path.join(project_images_dir, f"{i + 1:04d}{ext}"))
                except Exception:
                    pass

            found = None
            for cand in candidates:
                try:
                    if cand and os.path.exists(cand):
                        found = os.path.abspath(cand)
                        break
                except Exception:
                    pass

            if found:
                prepared[i] = found
                continue

            curr = self.data.get(i, {}) if isinstance(self.data, dict) else {}
            ext = Path(src_text).suffix.lower() if src_text else ".png"
            if ext not in known_exts:
                ext = ".png"
            original_hint = curr.get("original_name") if isinstance(curr, dict) else ""
            base = safe_page_file_stem(Path(str(original_hint or src_text or f"page{i + 1:03d}")).stem, fallback=f"page{i + 1:03d}")
            candidate = os.path.join(image_dir, f"{base}{ext}")
            if os.path.exists(candidate):
                for n in range(1, 10000):
                    candidate = os.path.join(image_dir, f"{base}({n}){ext}")
                    if not os.path.exists(candidate):
                        break
            dst = candidate

            recovered = False
            img = curr.get("ori") if isinstance(curr, dict) else None
            if img is not None:
                recovered = self._write_image_for_save_as_fallback(img, dst)

            if not recovered and isinstance(curr, dict):
                working_source = curr.get("working_source")
                if working_source is not None:
                    recovered = self._write_image_for_save_as_fallback(working_source, dst)

            if not recovered:
                raise FileNotFoundError(
                    "다른 이름으로 저장할 원본 이미지 경로를 찾지 못했습니다.\n"
                    f"페이지: {i + 1}\n"
                    f"기존 경로: {src_text or '(비어 있음)'}"
                )

            prepared[i] = dst

        return prepared

    def save_project_as(self):
        if not self.guard_project_action("다른 이름으로 저장"):
            return
        if not self.project_dir and not self.paths:
            self.log("⚠️ 저장할 이미지/프로젝트가 없습니다.")
            return

        default_path = self.ysbt_package_path or self.current_package_default_path()
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr_ui("다른 이름으로 YSBT 저장"),
            default_path,
            "YSBT Project (*.ysbt)"
        )
        if not path:
            return
        old_package_path = os.path.abspath(self.ysbt_package_path) if self.ysbt_package_path else None
        old_is_temp_project = bool(getattr(self, "is_temp_project", False))
        old_has_unsaved_changes = bool(getattr(self, "has_unsaved_changes", False))
        path_abs, display_project_name, new_uuid = self.make_ysbt_path_with_uuid_suffix(path)
        path_abs = os.path.abspath(path_abs)

        # 같은 .ysbt 파일을 고른 경우에는 일반 저장과 동일하게 처리한다.
        if old_package_path and os.path.abspath(path_abs).lower() == old_package_path.lower():
            self.save_project()
            return

        total_pages = len(getattr(self, "paths", []) or [])
        self._long_task_cancel_requested = False
        self._active_long_task_kind = "save_as"
        save_as_paths = None
        new_store = None
        new_project_dir = None
        project_name = None

        self.begin_busy_state("다른 이름으로 저장")
        try:
            self.show_task_progress_overlay(
                "다른 이름으로 저장",
                f"""전체 페이지: {total_pages}개
저장 진행: 0/{total_pages}
현재 작업: 새 저장 위치를 준비하는 중입니다...""",
                total=total_pages,
                cancellable=True,
            )
            try:
                overlay = getattr(self, "_task_progress_overlay", None)
                if overlay is not None:
                    overlay.note_label.setText("취소 시 현재 저장 항목이 끝난 뒤 중단됩니다.")
            except Exception:
                pass
            try:
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
                QThread.msleep(120)
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            except Exception:
                pass
            if bool(getattr(self, "_long_task_cancel_requested", False)):
                raise PackageProjectCancelled("다른 이름으로 저장 시작 전 취소되었습니다.")

            self.update_task_progress_overlay(current=0, total=total_pages, detail=f"""전체 페이지: {total_pages}개
저장 진행: 0/{total_pages}
현재 작업: 현재 화면 상태를 저장 데이터에 반영하는 중입니다...""")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            self.commit_current_page_ui_to_data()
            if bool(getattr(self, "_long_task_cancel_requested", False)):
                raise PackageProjectCancelled("저장 데이터 반영 후 취소되었습니다.")

            # Save As는 새 .ysbt 패키지와 새 작업 폴더로 분기한다.
            # 기존 .ysbt 파일에는 현재까지의 미저장 변경분을 쓰지 않고,
            # 새 파일/새 작업 폴더가 현재 상태를 이어받는다.
            project_name = clean_workspace_name(display_project_name or Path(path_abs).stem)
            old_project_dir = self.project_dir
            old_work_cache = self.work_project_dir
            # .ysbt 파일명은 깔끔하게 유지하고, 실제 작업 폴더에만 uuid 짧은값을 붙인다.
            new_project_dir = self.workspace_project_dir(project_name, code=new_uuid[:8], append_code=True)

            self.update_task_progress_overlay(current=0, total=total_pages, detail=f"""전체 페이지: {total_pages}개
저장 진행: 0/{total_pages}
현재 작업: 새 작업 폴더를 준비하는 중입니다...""")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            self.ensure_save_as_output_parent(path_abs)
            new_store = ProjectStore(new_project_dir)

            self.update_task_progress_overlay(current=0, total=total_pages, detail=f"""전체 페이지: {total_pages}개
저장 진행: 0/{total_pages}
현재 작업: 원본 이미지 경로를 확인하는 중입니다...""")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            save_as_paths = self.prepare_save_as_paths_for_store(new_project_dir)
            if bool(getattr(self, "_long_task_cancel_requested", False)):
                raise PackageProjectCancelled("이미지 경로 준비 후 취소되었습니다.")

            self.update_task_progress_overlay(current=0, total=total_pages, detail=f"""전체 페이지: {total_pages}개
저장 진행: 0/{total_pages}
현재 작업: 새 작업 폴더에 프로젝트 데이터를 저장하는 중입니다...""")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            self.save_project_store(new_store, paths=save_as_paths)
            new_store.write_manifest(package_source=path_abs, project_name=project_name, project_uuid=new_uuid)
            if bool(getattr(self, "_long_task_cancel_requested", False)):
                raise PackageProjectCancelled("YSBT 패키징 전 저장이 취소되었습니다.")

            self.update_task_progress_overlay(current=0, total=total_pages, detail=f"""전체 페이지: {total_pages}개
저장 진행: 0/{total_pages}
현재 작업: 새 YSBT 파일을 만드는 중입니다...""")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

            def _save_as_progress(current=None, total=None, detail=None):
                try:
                    show_total = int(total or total_pages or 0)
                    show_current = int(current or 0)
                    raw_detail = str(detail or "다른 이름으로 저장 중...")
                    if "최종 반영" in raw_detail:
                        overlay = getattr(self, "_task_progress_overlay", None)
                        if overlay is not None:
                            try:
                                overlay.cancel_btn.setEnabled(False)
                                overlay.note_label.setText("최종 반영 중입니다. 이 짧은 단계에서는 취소할 수 없습니다.")
                            except Exception:
                                pass
                    formatted_detail = (
                        f"전체 페이지: {total_pages}개\n"
                        f"저장 진행: {show_current}/{show_total}\n"
                        f"현재 작업: {raw_detail}"
                    )
                    self.update_task_progress_overlay(current=show_current, total=show_total, detail=formatted_detail)
                    QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
                except Exception:
                    pass

            def _save_as_cancel_requested():
                return bool(getattr(self, "_long_task_cancel_requested", False))

            package_project(
                new_project_dir,
                path_abs,
                project_name=project_name,
                project_uuid=new_uuid,
                progress_callback=_save_as_progress,
                cancel_checker=_save_as_cancel_requested,
            )

            # 현재 작업은 새 파일/새 작업 폴더로 전환한다.
            self.paths = save_as_paths
            self.project_dir = new_project_dir
            self.project_store = new_store
            self.ysbt_package_path = path_abs
            self.suggested_project_name = display_project_name
            self.suggested_package_dir = os.path.dirname(path_abs)
            self.is_temp_project = False
            self.update_window_title()

            # 기존 임시 캐시/임시 프로젝트 정리.
            # workspaces 폴더는 복구 기준 작업 공간이므로 자동 삭제하지 않는다.
            if old_work_cache and old_work_cache != self.work_project_dir and os.path.exists(old_work_cache):
                try:
                    if self.is_workspace_project_dir_path(old_work_cache):
                        self.log(f"🧷 기존 workspaces 작업 폴더 자동 삭제 생략: {old_work_cache}")
                    else:
                        shutil.rmtree(old_work_cache, ignore_errors=True)
                except Exception:
                    pass
            if old_is_temp_project and old_project_dir and os.path.abspath(old_project_dir) != os.path.abspath(new_project_dir):
                try:
                    old_abs = os.path.abspath(old_project_dir)
                    roots = [os.path.abspath(str(temp_dir()))]
                    if os.path.basename(old_abs).startswith("unsaved_") and any(old_abs.startswith(root) for root in roots) and os.path.exists(old_abs):
                        shutil.rmtree(old_abs, ignore_errors=True)
                    elif os.path.basename(old_abs).startswith("unsaved_"):
                        self.log(f"🧷 workspaces 임시 프로젝트 자동 삭제 생략: {old_project_dir}")
                except Exception:
                    pass
            self.work_project_dir = self.project_dir
            self.work_project_store = self.project_store

            # Save As는 "A를 B로 복사해서 분기"하는 동작이다.
            # 기존 파일 A의 작업 폴더는 캐시라 하더라도 현재 세션/최근항목/패키지 참조가
            # 남아 있을 수 있으므로 여기서 삭제하거나 A.ysbt 기준으로 복구하지 않는다.
            # A 작업 폴더를 건드리면 새 B.ysbt 내부에 A 경로가 남은 경우 열기 안전검사에서 막히거나,
            # 사용자가 기대한 원본 A 작업 캐시가 비어 버리는 문제가 생긴다.
            self.update_task_progress_overlay(current=total_pages, total=total_pages, detail=f"""전체 페이지: {total_pages}개
저장 진행: {total_pages}/{total_pages}
현재 작업: 새 프로젝트로 전환하는 중입니다...""")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

            old_suppress = bool(getattr(self, "_suppress_work_cache_dirty", False))
            self._suppress_work_cache_dirty = True
            try:
                self.mark_saved_state()
                try:
                    self.clear_pending_clean_import_cache(old_work_cache)
                    self.clear_pending_clean_import_cache(old_project_dir)
                    self.clear_pending_clean_import_cache(new_project_dir)
                except Exception:
                    pass
                self.log(f"💾 다른 이름으로 저장 완료: {self.ysbt_package_path}")
                self.record_current_project_recent()
                # Save As 완료 후에도 별도 work_sessions full copy를 만들지 않는다.
                # 현재 새 workspaces 폴더가 복구 기준 작업 공간이다.
                self.work_project_dir = self.project_dir
                self.work_project_store = self.project_store
            finally:
                self._suppress_work_cache_dirty = old_suppress
            self.mark_saved_state()
        except PackageProjectCancelled:
            self.has_unsaved_changes = old_has_unsaved_changes
            try:
                if new_project_dir and os.path.exists(new_project_dir) and os.path.abspath(new_project_dir) != os.path.abspath(str(self.project_dir or "")):
                    if self.is_workspace_project_dir_path(new_project_dir):
                        self.log(f"🧷 취소된 Save As 작업 폴더 자동 삭제 생략: {new_project_dir}")
                    else:
                        shutil.rmtree(new_project_dir, ignore_errors=True)
            except Exception:
                pass
            self.hide_task_progress_overlay()
            try:
                self.log("⏹️ [Save As] 다른 이름으로 저장 취소됨: 현재 프로젝트는 변경되지 않았습니다.")
            except Exception:
                pass
            QMessageBox.warning(
                self,
                self.tr_ui("다른 이름으로 저장 취소"),
                """다른 이름으로 저장이 취소되었습니다.

현재 프로젝트와 기존 YSBT 파일은 변경되지 않았습니다.""",
            )
            return
        except Exception as e:
            self.has_unsaved_changes = True
            try:
                if new_project_dir and os.path.exists(new_project_dir) and os.path.abspath(new_project_dir) != os.path.abspath(str(self.project_dir or "")):
                    if self.is_workspace_project_dir_path(new_project_dir):
                        self.log(f"🧷 취소된 Save As 작업 폴더 자동 삭제 생략: {new_project_dir}")
                    else:
                        shutil.rmtree(new_project_dir, ignore_errors=True)
            except Exception:
                pass
            self.hide_task_progress_overlay()
            QMessageBox.critical(self, self.tr_ui("YSBT 저장 실패"), f"{self.tr_ui('YSBT 파일을 저장하지 못했습니다.')}\n{path_abs}\n\n{e}")
            return
        finally:
            self.hide_task_progress_overlay()
            self._active_long_task_kind = None
            self._long_task_cancel_requested = False
            self.end_busy_state("다른 이름으로 저장")

    def auto_save_project(self):
        """복구용 작업 캐시 저장 진입점.

        이름은 기존 호출부 호환을 위해 유지하지만, v2.4 QA6부터는 실제 프로젝트나
        .ysbt 패키지를 자동 갱신하지 않는다. 일반 편집 변경분은 작업 캐시에만 저장하고,
        실제 YSBT 반영은 명시적인 프로젝트 저장에서만 수행한다.
        """
        if getattr(self, "is_batch_running", False) and getattr(self, "current_batch_mode", None) in ("analyze", "reanalyze"):
            try:
                self.audit_boundary_event("AUTO_SAVE_SKIPPED_DURING_BATCH_MACRO", mode=getattr(self, "current_batch_mode", None))
            except Exception:
                pass
            self.has_unsaved_changes = True
            return
        try:
            checkpoint_pages = set(getattr(self, "_checkpoint_dirty_pages", set()) or set())
            if not checkpoint_pages:
                pe = getattr(self, "project_engine", None)
                summary = pe.dirty_summary() if pe is not None and hasattr(pe, "dirty_summary") else {}
                raw_dirty = summary.get("dirty_pages", {}) if isinstance(summary, dict) else {}
                text_only = bool(raw_dirty)
                for _p, _kinds in (raw_dirty or {}).items():
                    _set = {str(x or "") for x in list(_kinds or [])}
                    if not _set or not _set.issubset({"text", "checkpoint_text", "checkpoint_fallback", "data", "translation", "translated_text", "text_effect_preview"}):
                        text_only = False
                        break
                if text_only:
                    try:
                        self.audit_boundary_event("WORK_CACHE_SAVE_SKIPPED_NO_CHECKPOINT_DIRTY", throttle_ms=2000)
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        try:
            self.audit_boundary_event("WORK_CACHE_SAVE_ENTER", stack=True, throttle_ms=900)
        except Exception:
            pass
        try:
            self.note_ui_interaction_activity(600)
        except Exception:
            pass
        if (
            getattr(self, "_suppress_work_cache_dirty", False)
            or self.is_loading_project
            or self.is_autosaving
            or not self.project_dir
            or not getattr(self, "paths", None)
        ):
            return
        if getattr(self, "_text_transform_runtime_active", False):
            try:
                self.has_unsaved_changes = True
                self.update_window_title()
            except Exception:
                pass
            return
        self.auto_save_enabled = False
        self.is_autosaving = True
        try:
            try:
                self.flush_pending_view_layer_commit(save_after=False)
            except Exception:
                pass
            try:
                self.commit_current_page_ui_to_data(include_mask=False)
            except TypeError:
                self.commit_current_page_ui_to_data()
            try:
                pe = getattr(self, "project_engine", None)
                if bool(getattr(self, "has_unsaved_changes", False)) and pe is not None and not pe.has_dirty():
                    self.mark_current_page_for_recovery_checkpoint("checkpoint_fallback")
            except Exception:
                pass
            self.save_to_work_cache()
            self.update_window_title()
        finally:
            self.is_autosaving = False

    def flush_text_scene_geometry_to_data(self, data_items=None, *, mark_dirty=False, reason="scene geometry flush"):
        """현재 최종화면 텍스트 item 위치를 page data에 즉시 반영한다.

        텍스트를 드래그한 직후 변형/고급옵션/스타일 변경을 열면 data 기준으로
        레이어가 다시 만들어질 수 있다. 이때 이동 전 좌표를 쓰지 않도록
        진입 전에 scene -> data flush를 명시적으로 수행한다.
        """
        try:
            changed = bool(self.sync_final_text_scene_to_data())
        except Exception:
            changed = False

        # selected data_items가 scene item과 같은 dict가 아닐 가능성까지 보강한다.
        try:
            ids = {str(d.get('id')) for d in (data_items or []) if isinstance(d, dict) and d.get('id') is not None}
            if ids:
                curr = self.data.get(self.idx) or {}
                by_id = {str(d.get('id')): d for d in (curr.get('data', []) or []) if isinstance(d, dict) and d.get('id') is not None}
                for d in data_items or []:
                    if not isinstance(d, dict):
                        continue
                    sid = str(d.get('id'))
                    target = by_id.get(sid)
                    if target is not None and target is not d:
                        for k in ('rect', 'x_off', 'y_off', 'manual_text_rect', 'text_anchor_mode', 'rotation', 'char_width', 'char_height', 'skew_x', 'skew_y', 'trap_left', 'trap_right', 'trap_top', 'trap_bottom', 'arc_top', 'arc_bottom', 'arc_left', 'arc_right', 'arc_handles', 'arc_active_index'):
                            if k in target:
                                d[k] = copy.deepcopy(target.get(k))
        except Exception:
            pass

        if changed and mark_dirty:
            try:
                self.mark_active_page_dirty("text")
            except Exception:
                pass
            try:
                if hasattr(self, "text_engine") and self.text_engine is not None:
                    ids = [d.get('id') for d in (data_items or []) if isinstance(d, dict) and d.get('id') is not None]
                    self.text_engine.mark_dirty(int(getattr(self, "idx", 0) or 0), ids, ['rect', 'x_off', 'y_off'])
            except Exception:
                pass

        try:
            self.audit_boundary_event("TEXT_SCENE_GEOMETRY_FLUSH", reason=str(reason or ""), changed=bool(changed), mark_dirty=bool(mark_dirty), throttle_ms=120)
        except Exception:
            pass
        return changed

    def refresh_text_items_live_in_place(self, items=None, *, keep_selection=True):
        """선택 텍스트만 현재 data 기준으로 즉시 다시 그린다.

        전체 Final 텍스트 레이어 rebuild는 scene/data 개수가 어긋났을 때 안전하지만,
        스타일 수치를 휠로 바꿀 때마다 쓰면 렉이 커진다. 살아 있는 선택 item은
        item 내부 path/style만 재생성해서 가볍게 미리보기한다.
        """
        items = list(items or self.selected_text_items() or [])
        if not items:
            return False
        ok = False
        selected_ids = []
        for item in items:
            try:
                sid = getattr(item, 'data', {}).get('id')
                if sid is not None:
                    selected_ids.append(sid)
                if hasattr(item, 'rebuild_text_render_for_live_preview'):
                    item.rebuild_text_render_for_live_preview(force=True)
                else:
                    try:
                        item.prepareGeometryChange()
                    except Exception:
                        pass
                    item.update()
                ok = True
            except RuntimeError:
                continue
            except Exception:
                try:
                    item.update()
                    ok = True
                except Exception:
                    pass
        if ok:
            try:
                self.view.scene.update()
            except Exception:
                pass
            if keep_selection and selected_ids:
                try:
                    self.reselect_text_items(selected_ids)
                except Exception:
                    pass
            try:
                self.audit_boundary_event("TEXT_STYLE_REFRESH_IN_PLACE", selected_count=len(selected_ids), throttle_ms=120)
            except Exception:
                pass
        return bool(ok)

    def sync_final_text_scene_to_data(self):
        """최종화면의 실제 텍스트 아이템 위치를 현재 페이지 data에 동기화한다.

        일반 드래그/변형 드래그는 대부분 해당 이벤트에서 data를 갱신하지만,
        자동저장/페이지 이동/닫기처럼 이벤트 타이밍이 섞이는 경우를 위해
        저장 직전 화면에 남아 있는 TypesettingItem의 좌표를 한 번 더 확정한다.
        """
        if getattr(self, "_text_scene_sync_lock", False) or getattr(self, "_text_undo_restore_lock", False):
            return False
        scene = self._safe_graphics_scene()
        if scene is None:
            return False
        curr = self.data.get(self.idx)
        if not curr:
            return False

        self._text_scene_sync_lock = True
        changed = False
        try:
            data_list = curr.get('data', []) or []
            by_id = {str(d.get('id')): d for d in data_list if isinstance(d, dict)}
            try:
                scene_items = list(scene.items())
            except RuntimeError:
                return False
            except Exception:
                return False
            for item in scene_items:
                if not isinstance(item, TypesettingItem):
                    continue
                d = getattr(item, 'data', None)
                if not isinstance(d, dict):
                    continue
                if d.get('pending_new_text'):
                    continue
                item_id = str(d.get('id'))
                target = by_id.get(item_id)
                if target is None:
                    continue

                rect = list(target.get('rect') or [0, 0, 1, 1])
                while len(rect) < 4:
                    rect.append(1)
                try:
                    align = (target.get('align') or 'center').lower()
                    if align == 'left':
                        anchor_x = float(rect[0])
                    elif align == 'right':
                        anchor_x = float(rect[0]) + float(rect[2])
                    else:
                        anchor_x = float(rect[0]) + float(rect[2]) / 2.0

                    path_rect = getattr(item, '_text_path_rect', item.boundingRect())
                    item_pos = item.pos()
                    rect_x = float(rect[0])
                    rect_y = float(rect[1])
                    rect_w = max(1.0, float(rect[2]))
                    rect_h = max(1.0, float(rect[3]))
                    if bool(target.get('rasterized_text')) or bool(getattr(item, '_is_rasterized_text', False)):
                        # 객체화된 텍스트는 rect가 래스터 이미지의 좌상단 기준이다.
                        # 일반 텍스트처럼 center/align 보정을 넣으면 이동 후 저장 시 위치가 다시 밀린다.
                        new_x_off = int(round(float(item_pos.x()) - rect_x))
                        new_y_off = int(round(float(item_pos.y()) - rect_y))
                    elif align == 'left':
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.left()) - rect_x))
                        new_y_off = int(round(float(item_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
                    elif align == 'right':
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.right()) - (rect_x + rect_w)))
                        new_y_off = int(round(float(item_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
                    else:
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.center().x()) - (rect_x + rect_w / 2.0)))
                        new_y_off = int(round(float(item_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
                except Exception:
                    continue

                old_x_off = int(target.get('x_off', 0) or 0)
                old_y_off = int(target.get('y_off', 0) or 0)
                if new_x_off != old_x_off or new_y_off != old_y_off:
                    target['x_off'] = new_x_off
                    target['y_off'] = new_y_off
                    changed = True
            return changed
        finally:
            self._text_scene_sync_lock = False

    def commit_current_page_ui_to_data(self, include_mask=True):
        curr = self.data.get(self.idx)
        if not curr:
            return

        # 최종화면 탭에서는 화면 위 텍스트 아이템의 현재 위치를 저장 데이터에 먼저 고정한다.
        self.sync_final_text_scene_to_data()

        # 표 상태 반영
        for row in range(1, self.tab.rowCount()):
            data_index = row - 1
            if data_index < 0 or data_index >= len(curr.get('data', [])):
                continue

            data_item = curr['data'][data_index]
            data_item['use_inpaint'] = self.get_table_check_state(row)

            # 객체화된 텍스트는 우측 표에 [객체] 표시용 문자열을 보여주지만,
            # 그 문자열이 원본 translated_text에 다시 저장되면 [객체] 접두사가 누적된다.
            # 래스터 텍스트 객체는 이동/삭제/부분 지우기만 허용하고 내용 편집 값은 유지한다.
            if data_item.get('rasterized_text'):
                continue

            orig_item = self.tab.item(row, 2)
            if orig_item is not None:
                data_item['text'] = orig_item.text()

            trans_item = self.tab.item(row, 3)
            data_item['translated_text'] = trans_item.text() if trans_item else ""

        # 화면 마스크 자동 저장은 평상시 현재 페이지에서만 허용.
        # 페이지 로딩/일괄 작업 중에는 이전 화면의 마스크가 다른 페이지에 섞일 수 있으므로 차단한다.
        if (not include_mask) or self.is_page_loading or self.is_batch_running:
            return

        if self.cb_mode.currentIndex() in [2, 3]:
            m = self.view.get_mask_np()
            if m is not None:
                self.set_active_mask(curr, m, self.cb_mode.currentIndex())
                curr['mask_toggle_enabled'] = self.mask_toggle_enabled

