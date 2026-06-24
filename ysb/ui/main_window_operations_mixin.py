import gc
from ysb.ui.main_window_support import *
from ysb.utils.runtime_logger import append_log, memory_text, numpy_shape_text


class MainWindowOperationsMixin:

    def open_api_settings_dialog(self):
        dlg = ApiSettingsDialog(self.api_settings, self, show_cache_path=bool(getattr(self, "show_cache_paths_in_settings", False)))
        if not dlg.exec():
            return

        self.api_settings = dlg.get_settings()
        ApiSettingsStore.save(self.api_settings)
        apply_settings_to_config(self.api_settings)
        self.sync_translation_option_cache_to_config()
        self.trans_chunk_sizes = {
            "openai": int(getattr(self.api_settings, "openai_chunk_size", 20) or 20),
            "deepseek": int(getattr(self.api_settings, "deepseek_chunk_size", 8) or 8),
            "google": int(getattr(self.api_settings, "google_translate_chunk_size", 50) or 50),
            "gemini": int(getattr(self.api_settings, "gemini_chunk_size", 10) or 10),
            "custom": int(getattr(self.api_settings, "custom_translation_chunk_size", 20) or 20),
        }
        if hasattr(self, "cb_trans_provider"):
            self.cb_trans_provider.blockSignals(True)
            try:
                self.set_combo_current_data(self.cb_trans_provider, getattr(self.api_settings, "selected_translation_provider", "openai"))
                self.on_translation_provider_changed(save=False)
            finally:
                self.cb_trans_provider.blockSignals(False)
        if hasattr(self, "refresh_ocr_language_combo"):
            self.refresh_ocr_language_combo(save=False)
        self.restart_engine(show_error=True)
        self.log("🔑 API settings cache saved" if self.ui_language == LANG_EN else "🔑 API 설정 캐시 저장 완료")

    def open_translation_prompt_dialog(self):
        old_prompt = str(self.app_options.get(TRANSLATION_PROMPT_KEY, "") or "")
        dlg = TranslationPromptDialog(old_prompt, self)
        if not dlg.exec():
            self.log("↩️ 번역 프롬프트 저장 취소")
            return

        new_prompt = dlg.get_prompt_text()
        self.app_options[TRANSLATION_PROMPT_KEY] = new_prompt
        self.save_app_options_cache()
        self.sync_translation_option_cache_to_config()
        self.log(f"📝 번역 프롬프트 캐시 저장 완료 ({len(new_prompt):,}자)")

    def open_glossary_dialog(self):
        old_text = str(self.app_options.get(TRANSLATION_GLOSSARY_TEXT_KEY, "") or "")
        old_path = str(self.app_options.get(TRANSLATION_GLOSSARY_PATH_KEY, "") or "")
        dlg = GlossaryDialog(old_text, old_path, self)
        dlg.exec()

        new_text, new_path, changed = dlg.get_glossary_state()
        if not changed:
            return

        self.app_options[TRANSLATION_GLOSSARY_TEXT_KEY] = new_text
        self.app_options[TRANSLATION_GLOSSARY_PATH_KEY] = new_path
        self.save_app_options_cache()
        self.sync_translation_option_cache_to_config()

        if new_text:
            self.log(f"📚 단어장 캐시 저장 완료 ({len(new_text):,}자)")
        else:
            self.log("📚 단어장 캐시 초기화 완료")



    def capture_magic_wand_state(self):
        """요술봉 미리보기 상태를 Page-local MaskEngine에서 캡처한다."""
        try:
            active = bool(getattr(getattr(self, 'view', None), 'draw_mode', None) == 'magic_wand')
        except Exception:
            active = False
        page_idx = int(getattr(self, "idx", 0) or 0)
        if hasattr(self, "mask_engine") and self.mask_engine is not None:
            try:
                runtime = self.mask_engine.magic(page_idx)
                # Keep legacy attributes mirrored into the engine before capture.
                runtime.mask = self.magic_wand_mask.copy() if isinstance(getattr(self, 'magic_wand_mask', None), np.ndarray) else getattr(self, 'magic_wand_mask', None)
                runtime.seed = tuple(self.magic_wand_seed) if getattr(self, 'magic_wand_seed', None) else None
                runtime.seeds = [tuple(x) for x in (getattr(self, 'magic_wand_seeds', []) or [])]
                return self.mask_engine.capture_magic(page_idx, active=active)
            except Exception:
                pass
        return {
            "active": active,
            "mask": self.magic_wand_mask.copy() if isinstance(getattr(self, 'magic_wand_mask', None), np.ndarray) else None,
            "seed": tuple(self.magic_wand_seed) if getattr(self, 'magic_wand_seed', None) else None,
            "seeds": [tuple(x) for x in (getattr(self, 'magic_wand_seeds', []) or [])],
            "history": list(getattr(self, 'magic_wand_history', []) or []),
        }

    def restore_magic_wand_state(self, state):
        """Undo 복원 후 요술봉 선택/확장 상태를 화면에 다시 그린다."""
        page_idx = int(getattr(self, "idx", 0) or 0)
        if hasattr(self, "mask_engine") and self.mask_engine is not None:
            try:
                runtime = self.mask_engine.restore_magic(page_idx, state if isinstance(state, dict) else None)
                self.magic_wand_mask = runtime.mask.copy() if isinstance(runtime.mask, np.ndarray) else runtime.mask
                self.magic_wand_seeds = [tuple(x) for x in (runtime.seeds or [])]
                self.magic_wand_seed = tuple(runtime.seed) if runtime.seed else (self.magic_wand_seeds[-1] if self.magic_wand_seeds else None)
                self.magic_wand_history = runtime.history
            except Exception:
                self.magic_wand_mask = None
                self.magic_wand_seed = None
                self.magic_wand_seeds = []
        elif isinstance(state, dict):
            mask = state.get('mask')
            self.magic_wand_mask = mask.copy() if isinstance(mask, np.ndarray) else None
            self.magic_wand_seeds = [tuple(x) for x in (state.get('seeds') or [])]
            self.magic_wand_seed = tuple(state.get('seed')) if state.get('seed') else (self.magic_wand_seeds[-1] if self.magic_wand_seeds else None)
            self.magic_wand_history = list(state.get('history') or []) if isinstance(state, dict) else []
        else:
            self.clear_magic_wand_selection()
            return False
        active_state = bool(isinstance(state, dict) and state.get('active') and self.magic_wand_mask is not None)
        try:
            self._set_magic_wand_tool_restore_state(active_state)
        except Exception:
            pass
        if self.magic_wand_mask is not None:
            try:
                self.view.draw_magic_wand_preview(self.magic_wand_mask)
            except Exception:
                pass
        else:
            try:
                self.view.clear_magic_wand_preview()
            except Exception:
                pass
        return True

    def _copy_magic_state_light(self):
        """요술봉 현재 상태만 얕게 캡처한다. history 재귀 복사는 피한다."""
        try:
            return {
                "active": bool(getattr(getattr(self, "view", None), "draw_mode", None) == "magic_wand"),
                "mask": self.magic_wand_mask.copy() if isinstance(getattr(self, "magic_wand_mask", None), np.ndarray) else None,
                "seed": tuple(self.magic_wand_seed) if getattr(self, "magic_wand_seed", None) else None,
                "seeds": [tuple(x) for x in (getattr(self, "magic_wand_seeds", []) or [])],
            }
        except Exception:
            return {"active": False, "mask": None, "seed": None, "seeds": []}

    def _magic_wand_runtime(self):
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
            if hasattr(self, "mask_engine") and self.mask_engine is not None:
                return self.mask_engine.magic(page_idx)
        except Exception:
            pass
        return None

    def _sync_magic_wand_runtime_from_legacy(self):
        try:
            runtime = self._magic_wand_runtime()
            if runtime is not None:
                runtime.mask = self.magic_wand_mask.copy() if isinstance(getattr(self, 'magic_wand_mask', None), np.ndarray) else getattr(self, 'magic_wand_mask', None)
                runtime.seed = tuple(self.magic_wand_seed) if getattr(self, 'magic_wand_seed', None) else None
                runtime.seeds = [tuple(x) for x in (getattr(self, 'magic_wand_seeds', []) or [])]
                self.magic_wand_history = runtime.history
                return runtime
        except Exception:
            pass
        return None



    def _set_magic_wand_tool_restore_state(self, active):
        """Restore only the Magic Wand tool UI state without clearing command history."""
        try:
            active = bool(active)
            view = getattr(self, "view", None)
            if view is None:
                return False
            if active:
                mode = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else 2
                if mode in (2, 3, 4):
                    view.draw_mode = "magic_wand"
                    view.setDragMode(QGraphicsView.DragMode.NoDrag)
                    try:
                        self.update_left_tool_action_states("magic_wand")
                    except Exception:
                        pass
                    try:
                        self.update_final_paint_option_bar_visibility()
                    except Exception:
                        pass
                    try:
                        self.refresh_shared_option_bar()
                    except Exception:
                        pass
                    return True
            if getattr(view, "draw_mode", None) == "magic_wand":
                view.draw_mode = None
                view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                try:
                    self.update_left_tool_action_states(None)
                except Exception:
                    pass
                try:
                    self.update_final_paint_option_bar_visibility()
                except Exception:
                    pass
                try:
                    self.refresh_shared_option_bar()
                except Exception:
                    pass
                return True
        except Exception:
            return False
        return True

    def _push_runtime_command(self, component_type, target_id, field_name, before_value, after_value, *, reason="작업", meta=None):
        """Push a small runtime/UI command into the canonical single timeline."""
        if (
            getattr(self, "_text_undo_restore_lock", False)
            or getattr(self, "_project_undo_restore_lock", False)
            or getattr(self, "_command_undo_restore_lock", False)
        ):
            return False
        try:
            from ysb.core.command_undo import FieldChange, UndoCommand
        except Exception:
            return False
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            page_idx = 0
        try:
            changed = before_value != after_value
        except Exception:
            changed = True
        if not changed:
            return False
        change = FieldChange(
            target_id=str(target_id or f"{component_type}:{page_idx}"),
            field=str(field_name or "state"),
            before=copy.deepcopy(before_value),
            after=copy.deepcopy(after_value),
            component_type=str(component_type or "runtime_state"),
            page_idx=page_idx,
            meta=dict(meta or {}),
        )
        command = UndoCommand(
            reason=str(reason or "작업"),
            page_idx=page_idx,
            component_type=str(component_type or "runtime_state"),
            target_ids=[str(target_id or f"{component_type}:{page_idx}")],
            changes=[change],
            merge_key=f"{component_type}:{page_idx}:{reason}",
            meta=dict(meta or {}),
        )
        mgr = self.get_undo_manager() if hasattr(self, "get_undo_manager") else None
        if mgr is not None and hasattr(mgr, "push_command"):
            return bool(mgr.push_command(command, clear_redo=True, source=str(component_type or reason or "runtime_command")))
        return False

    def _begin_magic_wand_runtime_command(self):
        try:
            self._pending_magic_wand_runtime_before = self._copy_magic_state_light()
        except Exception:
            self._pending_magic_wand_runtime_before = None

    def _magic_state_equal(self, left, right):
        """Compare magic-wand runtime states without numpy truth-value errors."""
        try:
            if left is right:
                return True
            if not isinstance(left, dict) or not isinstance(right, dict):
                return False
            if set(left.keys()) != set(right.keys()):
                return False
            for key in left.keys():
                a = left.get(key)
                b = right.get(key)
                if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
                    if not (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)):
                        return False
                    if not np.array_equal(a, b):
                        return False
                else:
                    if a != b:
                        return False
            return True
        except Exception:
            return False

    def push_magic_wand_runtime_command(self, before_state=None, after_state=None, *, reason="요술봉 선택", extra_changes=None, meta=None):
        """Record one Magic Wand preview/fill step in the single Undo timeline."""
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            page_idx = 0
        try:
            from ysb.core.command_undo import FieldChange, UndoCommand
        except Exception:
            return False
        before_state = copy.deepcopy(before_state if isinstance(before_state, dict) else self._copy_magic_state_light())
        after_state = copy.deepcopy(after_state if isinstance(after_state, dict) else self._copy_magic_state_light())
        changes = []
        try:
            state_changed = not self._magic_state_equal(before_state, after_state)
        except Exception:
            state_changed = True
        if state_changed:
            changes.append(FieldChange(
                target_id=f"magic_wand:{page_idx}",
                field="state",
                before=before_state,
                after=after_state,
                component_type="magic_wand_runtime",
                page_idx=page_idx,
                meta=dict(meta or {}),
            ))
        for ch in list(extra_changes or []):
            try:
                changes.append(FieldChange.from_mapping(ch))
            except Exception:
                pass
        if not changes:
            return False
        command = UndoCommand(
            reason=str(reason or "요술봉 선택"),
            page_idx=page_idx,
            component_type="magic_wand_runtime",
            target_ids=[f"magic_wand:{page_idx}"],
            changes=changes,
            merge_key=f"magic_wand_runtime:{page_idx}:{reason}",
            meta=dict(meta or {}),
        )
        mgr = self.get_undo_manager() if hasattr(self, "get_undo_manager") else None
        if mgr is not None and hasattr(mgr, "push_command"):
            ok = bool(mgr.push_command(command, clear_redo=True, source="magic_wand_runtime"))
            try:
                self.audit_boundary_event(
                    "UNDO_MAGIC_WAND_COMMAND_PUSH",
                    page_idx=page_idx,
                    reason=str(reason or ""),
                    changes=len(changes),
                    before_active=bool(before_state.get("active")) if isinstance(before_state, dict) else False,
                    after_active=bool(after_state.get("active")) if isinstance(after_state, dict) else False,
                    before_has_mask=bool(isinstance(before_state.get("mask"), np.ndarray) and before_state.get("mask").size > 0) if isinstance(before_state, dict) else False,
                    after_has_mask=bool(isinstance(after_state.get("mask"), np.ndarray) and after_state.get("mask").size > 0) if isinstance(after_state, dict) else False,
                    throttle_ms=120,
                )
            except Exception:
                pass
            return ok
        return False

    def _finish_magic_wand_runtime_command(self, *, reason="요술봉 선택"):
        before = getattr(self, "_pending_magic_wand_runtime_before", None)
        self._pending_magic_wand_runtime_before = None
        if not isinstance(before, dict):
            return False
        try:
            after = self._copy_magic_state_light()
        except Exception:
            return False
        return self.push_magic_wand_runtime_command(before, after, reason=reason)

    def _apply_magic_wand_runtime_command(self, command, *, redo=False):
        changes = list(getattr(command, "changes", []) or [])
        if not changes:
            return False
        state_value = None
        mask_changes = []
        fail_reasons = []
        for change in changes:
            field_name = str(getattr(change, "field", "") or "")
            value = copy.deepcopy(getattr(change, "after", None) if redo else getattr(change, "before", None))
            if field_name == "state":
                state_value = value
            elif field_name in ("mask", "mask_state", "filled_mask"):
                mask_changes.append((change, value))
        ok = True
        # 실제 마스크 칠하기가 포함된 경우 먼저 픽셀 마스크를 되돌리고, 그 다음 preview/tool 상태를 복원한다.
        for change, value in mask_changes:
            try:
                meta = dict(getattr(change, "meta", {}) or {})
                mode = int(meta.get("mode", self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 2) or 2)
                mask_ok = bool(self._apply_magic_fill_mask_state(value, mode))
                if not mask_ok:
                    fail_reasons.append("mask_state_apply_failed")
                ok = mask_ok and ok
            except Exception as e:
                fail_reasons.append(f"mask_state_exception:{type(e).__name__}")
                ok = False
        if isinstance(state_value, dict):
            try:
                state_ok = bool(self._restore_magic_state_light(state_value))
                if not state_ok:
                    fail_reasons.append("state_restore_failed")
                ok = state_ok and ok
            except Exception as e:
                fail_reasons.append(f"state_exception:{type(e).__name__}")
                ok = False
        else:
            fail_reasons.append("missing_state")
            ok = False
        try:
            self.update_undo_redo_buttons()
            self.audit_boundary_event(
                "UNDO_MAGIC_WAND_COMMAND_APPLY",
                redo=bool(redo),
                ok=bool(ok),
                fail_reason=",".join(fail_reasons),
                has_state=isinstance(state_value, dict),
                has_mask_change=bool(mask_changes),
                state_active=bool(state_value.get("active")) if isinstance(state_value, dict) else False,
                state_has_mask=bool(isinstance(state_value, dict) and isinstance(state_value.get("mask"), np.ndarray) and state_value.get("mask").size > 0),
                draw_mode=str(getattr(getattr(self, "view", None), "draw_mode", None)),
                throttle_ms=120,
            )
        except Exception:
            pass
        return bool(ok)

    def push_magic_wand_history(self, action=None):
        # Paint/magic wand history uses the legacy lightweight runtime stack; do not push Command-Diff entries here.
        """요술봉 내부 작업 스택에 현재 상태 또는 특수 action을 넣는다.

        마스크 탭 요술봉은 픽셀 편집 전에 세심하게 선택/확장/칠하기를 반복하므로
        일반 page undo가 아니라 이 전용 runtime stack에서 한 단계씩 되돌린다.
        """
        page_idx = int(getattr(self, "idx", 0) or 0)
        try:
            # 새 요술봉 조작이 들어오면 redo 갈래는 끊는다.
            self.magic_wand_redo_history = []
        except Exception:
            pass

        runtime = self._sync_magic_wand_runtime_from_legacy()
        if runtime is not None:
            try:
                if isinstance(action, dict):
                    item = dict(action)
                    # numpy payload는 직접 copy해서 보존한다.
                    for key in ("before_mask", "after_mask"):
                        if isinstance(item.get(key), np.ndarray):
                            item[key] = item[key].copy()
                    runtime.history.append(item)
                else:
                    runtime.push_history(30)
                if len(runtime.history) > 30:
                    del runtime.history[0:len(runtime.history) - 30]
                self.magic_wand_history = runtime.history
                try:
                    self.audit_boundary_event("MAGIC_WAND_HISTORY_PUSH", action=str((action or {}).get("action") if isinstance(action, dict) else "state"), history_len=len(runtime.history), page_idx=page_idx, throttle_ms=100)
                except Exception:
                    pass
                return
            except Exception:
                pass

        if isinstance(action, dict):
            item = dict(action)
            for key in ("before_mask", "after_mask"):
                if isinstance(item.get(key), np.ndarray):
                    item[key] = item[key].copy()
            self.magic_wand_history.append(item)
        else:
            mask = self.magic_wand_mask.copy() if isinstance(self.magic_wand_mask, np.ndarray) else None
            seeds = list(getattr(self, "magic_wand_seeds", []) or [])
            self.magic_wand_history.append({"active": True, "mask": mask, "seed": self.magic_wand_seed, "seeds": seeds})
        if len(self.magic_wand_history) > 30:
            self.magic_wand_history.pop(0)

    def _apply_magic_fill_mask_state(self, mask, mode):
        """요술봉 fill_mask undo/redo용 마스크 적용."""
        if mask is None:
            return False
        try:
            mode = int(mode)
        except Exception:
            mode = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else 2
        try:
            applied = mask.copy() if isinstance(mask, np.ndarray) else mask
            color = QColor(0, 0, 255, 150) if mode == 3 else QColor(168, 93, 102, 140)
            self.view.set_user_mask_np(applied, color)
            curr = self.data.get(self.idx)
            if isinstance(curr, dict):
                self.set_active_mask(curr, applied, mode)
            try:
                self.on_view_mask_edited()
            except Exception:
                try:
                    self.schedule_deferred_view_layer_commit("mask", delay_ms=1200)
                except Exception:
                    pass
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 요술봉 마스크 상태 복원 실패: {e}")
            except Exception:
                pass
            return False

    def _restore_magic_state_light(self, state, *, preserve_history=None):
        if not isinstance(state, dict):
            state = {"active": False, "mask": None, "seed": None, "seeds": []}
        try:
            if isinstance(preserve_history, list):
                state = dict(state)
                state["history"] = preserve_history
            self.restore_magic_wand_state(state)
        except Exception:
            try:
                mask = state.get("mask")
                self.magic_wand_mask = mask.copy() if isinstance(mask, np.ndarray) else None
                self.magic_wand_seeds = [tuple(x) for x in (state.get("seeds") or [])]
                self.magic_wand_seed = tuple(state.get("seed")) if state.get("seed") else (self.magic_wand_seeds[-1] if self.magic_wand_seeds else None)
                if self.magic_wand_mask is not None:
                    self.view.draw_magic_wand_preview(self.magic_wand_mask)
                else:
                    self.view.clear_magic_wand_preview()
            except Exception:
                pass

    def undo_magic_wand_selection(self):
        page_idx = int(getattr(self, "idx", 0) or 0)
        runtime = self._magic_wand_runtime()
        history = runtime.history if runtime is not None else getattr(self, "magic_wand_history", [])
        if not history:
            self.log("⚠️ 되돌릴 요술봉 선택이 없습니다.")
            return False

        try:
            current_state = self._copy_magic_state_light()
            item = history.pop()
            redo_item = item
            if isinstance(item, dict) and item.get("action") == "fill_mask":
                before_mask = item.get("before_mask")
                mode = int(item.get("mode", self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 2) or 2)
                if not self._apply_magic_fill_mask_state(before_mask, mode):
                    history.append(item)
                    return False
                before_magic = item.get("before_magic_state") or {}
                self._restore_magic_state_light(before_magic, preserve_history=history)
                self.magic_wand_redo_history.append(redo_item)
                self.log("↩️ 요술봉 마스크 칠하기 되돌림")
            else:
                # 일반 선택/허용범위/확장 단계는 이전 preview 상태로 되돌린다.
                self.magic_wand_redo_history.append(current_state)
                self._restore_magic_state_light(item, preserve_history=history)
                self.log("↩️ 요술봉 선택 되돌림")

            try:
                if runtime is not None:
                    self.magic_wand_history = runtime.history
                self.update_undo_redo_buttons()
                self.audit_boundary_event("MAGIC_WAND_UNDO", action=str(item.get("action") if isinstance(item, dict) else "state"), history_len=len(getattr(self, "magic_wand_history", []) or []), redo_len=len(getattr(self, "magic_wand_redo_history", []) or []), page_idx=page_idx, throttle_ms=100)
            except Exception:
                pass
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 요술봉 되돌리기 실패: {e}")
            except Exception:
                pass
            return False

    def redo_magic_wand_selection(self):
        page_idx = int(getattr(self, "idx", 0) or 0)
        redo = getattr(self, "magic_wand_redo_history", []) or []
        if not redo:
            self.log("⚠️ 다시 실행할 요술봉 작업이 없습니다.")
            return False
        runtime = self._sync_magic_wand_runtime_from_legacy()
        history = runtime.history if runtime is not None else getattr(self, "magic_wand_history", [])
        try:
            item = redo.pop()
            if isinstance(item, dict) and item.get("action") == "fill_mask":
                after_mask = item.get("after_mask")
                mode = int(item.get("mode", self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 2) or 2)
                if not self._apply_magic_fill_mask_state(after_mask, mode):
                    redo.append(item)
                    return False
                # 다시 칠한 뒤에는 선택 preview가 사라진 상태를 유지하되, undo용 action은 history에 남긴다.
                self.clear_magic_wand_selection(clear_history=False)
                history.append(item)
                self.log("↷ 요술봉 마스크 칠하기 다시 실행")
            else:
                current_state = self._copy_magic_state_light()
                history.append(current_state)
                self._restore_magic_state_light(item, preserve_history=history)
                self.log("↷ 요술봉 선택 다시 실행")
            if len(history) > 30:
                del history[0:len(history) - 30]
            if runtime is not None:
                self.magic_wand_history = runtime.history
            else:
                self.magic_wand_history = history
            try:
                self.update_undo_redo_buttons()
                self.audit_boundary_event("MAGIC_WAND_REDO", action=str(item.get("action") if isinstance(item, dict) else "state"), history_len=len(getattr(self, "magic_wand_history", []) or []), redo_len=len(getattr(self, "magic_wand_redo_history", []) or []), page_idx=page_idx, throttle_ms=100)
            except Exception:
                pass
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 요술봉 다시 실행 실패: {e}")
            except Exception:
                pass
            return False

    def clear_magic_wand_selection(self, clear_history=True):
        page_idx = int(getattr(self, "idx", 0) or 0)
        if hasattr(self, "mask_engine") and self.mask_engine is not None:
            try:
                self.mask_engine.clear_magic(page_idx, clear_history=bool(clear_history))
            except Exception:
                pass
        self.magic_wand_mask = None
        self.magic_wand_seed = None
        self.magic_wand_seeds = []
        if clear_history:
            self.magic_wand_history = []
            self.magic_wand_redo_history = []
        else:
            try:
                runtime = self._magic_wand_runtime()
                self.magic_wand_history = runtime.history if runtime is not None else getattr(self, "magic_wand_history", [])
            except Exception:
                pass
        if hasattr(self, "view") and hasattr(self.view, "clear_magic_wand_preview"):
            self.view.clear_magic_wand_preview()

    def current_magic_source_image(self):
        # 최종결과 탭의 요술봉은 실제 최종 화면 기준으로 영역을 판정한다.
        try:
            if hasattr(self, "cb_mode") and self.cb_mode.currentIndex() == 4:
                rendered = self.render_final_scene_for_magic_wand()
                if rendered is not None:
                    return rendered
        except Exception:
            pass
        return self.get_source_display_image(self.idx)

    def render_final_scene_for_magic_wand(self):
        """현재 최종결과 scene을 요술봉 판정용 RGB 이미지로 렌더링한다."""
        try:
            scene = getattr(getattr(self, "view", None), "scene", None)
            if scene is None:
                return None
            rect = scene.sceneRect()
            w = max(1, int(round(rect.width())))
            h = max(1, int(round(rect.height())))
            qimg = QImage(w, h, QImage.Format.Format_ARGB32)
            qimg.fill(Qt.GlobalColor.transparent)
            painter = QPainter(qimg)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            # 미리보기 overlay가 있다면 판정에 섞이지 않도록 잠시 숨긴다.
            hidden = []
            try:
                for item in list(getattr(self.view, "magic_preview_items", []) or []):
                    if item is not None and item.isVisible():
                        item.setVisible(False)
                        hidden.append(item)
            except Exception:
                hidden = []
            try:
                scene.render(painter, QRectF(0, 0, w, h), rect)
            finally:
                painter.end()
                for item in hidden:
                    try:
                        item.setVisible(True)
                    except Exception:
                        pass
            qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
            ptr = qimg.bits()
            ptr.setsize(qimg.sizeInBytes())
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, qimg.bytesPerLine() // 4, 4))[:, :w, :4].copy()
            # 투명 영역은 흰 배경처럼 처리한다. 최종결과 배경이 깔린 경우엔 보통 alpha가 이미 255다.
            alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
            rgb = arr[:, :, :3].astype(np.float32)
            bg = np.full_like(rgb, 255.0)
            comp = (rgb * alpha + bg * (1.0 - alpha)).astype(np.uint8)
            return comp
        except Exception:
            return None

    def set_mask_wrap_shape(self, shape, silent=False):
        shape = "free" if str(shape) == "free" else "rect"
        try:
            self.view.mask_wrap_shape = shape
            self.view.clear_mask_wrap_preview()
        except Exception:
            pass
        for btn, active in ((getattr(self, "btn_mask_wrap_rect", None), shape == "rect"), (getattr(self, "btn_mask_wrap_free", None), shape == "free")):
            if btn is None:
                continue
            try:
                btn.blockSignals(True)
                btn.setChecked(active)
                btn.blockSignals(False)
                if active:
                    btn.setStyleSheet("font-weight:bold; background:#8A4A52; color:white;")
                else:
                    btn.setStyleSheet("opacity:0.7;")
            except Exception:
                pass
        if not silent:
            if shape == "rect":
                self.log("🩹 마스크 랩핑 모드: 사각형")
            else:
                self.log("🩹 마스크 랩핑 모드: 자유형")

    def set_mask_cut_shape(self, shape, silent=False):
        shape = "free" if str(shape) == "free" else "rect"
        try:
            self.view.mask_cut_shape = shape
            self.view.clear_mask_cut_preview()
        except Exception:
            pass
        for btn, active in ((getattr(self, "btn_mask_cut_rect", None), shape == "rect"), (getattr(self, "btn_mask_cut_free", None), shape == "free")):
            if btn is None:
                continue
            try:
                btn.blockSignals(True)
                btn.setChecked(active)
                btn.blockSignals(False)
                if active:
                    btn.setStyleSheet("font-weight:bold; background:#c2410c; color:white;")
                else:
                    btn.setStyleSheet("opacity:0.7;")
            except Exception:
                pass
        if not silent:
            if shape == "rect":
                self.log(self.tr_ui("🔪 마스크 커팅 모드: 사각형"))
            else:
                self.log(self.tr_ui("🔪 마스크 커팅 모드: 자유형"))

    def set_area_paint_shape(self, shape, silent=False):
        shape = "free" if str(shape) == "free" else "rect"
        try:
            self.view.area_paint_shape = shape
            self.view.clear_area_paint_preview()
        except Exception:
            pass
        for btn, active in ((getattr(self, "btn_area_paint_rect", None), shape == "rect"), (getattr(self, "btn_area_paint_free", None), shape == "free")):
            if btn is None:
                continue
            try:
                btn.blockSignals(True)
                btn.setChecked(active)
                btn.blockSignals(False)
                if active:
                    btn.setStyleSheet("font-weight:bold; background:#7c3aed; color:white;")
                else:
                    btn.setStyleSheet("opacity:0.7;")
            except Exception:
                pass
        if not silent:
            if shape == "rect":
                self.log(self.tr_ui("▦ 영역 페인팅 모드: 사각형"))
            else:
                self.log(self.tr_ui("▦ 영역 페인팅 모드: 자유형"))

    def apply_mask_wrapping(self, region_mask):
        """선택한 영역 안의 분리된 마스크 덩어리들을 하나의 채움 영역으로 감싸준다."""
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = -1
        if mode not in (2, 3):
            self.log("⚠️ 마스크 랩핑은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.")
            self.update_left_tool_action_states()
            return
        if region_mask is None:
            self.log("⚠️ 마스크 랩핑 영역이 비어 있습니다.")
            return
        before = self.view.get_mask_np()
        if before is None:
            self.log(self.tr_ui("⚠️ 현재 탭에 마스크 레이어가 없습니다."))
            return

        try:
            mask = (before > 0).astype(np.uint8) * 255
            region = (region_mask > 0).astype(np.uint8) * 255
            if mask.shape[:2] != region.shape[:2]:
                region = cv2.resize(region, (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_NEAREST)

            # 선택 영역 안에 실제로 들어온 마스크 조각만 대상으로 삼는다.
            inside = cv2.bitwise_and(mask, region)
            num, labels, stats, _ = cv2.connectedComponentsWithStats(inside, 8)
            comps = [i for i in range(1, num) if int(stats[i, cv2.CC_STAT_AREA]) > 0]
            if len(comps) < 2:
                self.log("⚠️ 선택한 영역 안에 랩핑할 마스크가 2개 이상 필요합니다.")
                return

            ys, xs = np.where(inside > 0)
            if len(xs) == 0 or len(ys) == 0:
                self.log("⚠️ 마스크 랩핑 영역 안에서 마스크를 찾지 못했습니다.")
                return

            try:
                self.commit_current_page_ui_to_data(include_mask=True)
                self.push_project_undo("마스크 랩핑")
            except Exception:
                pass

            x1, x2 = int(xs.min()), int(xs.max())
            y1, y2 = int(ys.min()), int(ys.max())
            fill = np.zeros_like(mask, dtype=np.uint8)
            cv2.rectangle(fill, (x1, y1), (x2, y2), 255, thickness=-1)
            # 사용자가 잡은 영역 밖은 절대 건드리지 않는다.
            fill = cv2.bitwise_and(fill, region)
            wrapped = cv2.bitwise_or(mask, fill)

            if np.array_equal(wrapped, mask):
                self.log("⚠️ 마스크 랩핑으로 추가될 영역이 없습니다.")
                return

            color = QColor(0, 0, 255, 150) if mode == 3 else QColor(168, 93, 102, 140)
            self.view.set_user_mask_np(wrapped, color)
            self.on_view_mask_edited()
            self.log(f"🩹 마스크 랩핑 완료: {len(comps)}개 마스크 덩어리를 1개 영역으로 감쌈")
        except Exception as e:
            self.log(f"⚠️ 마스크 랩핑 실패: {e}")

    def apply_mask_cutting(self, region_mask):
        """선택 영역 내부는 보존하고, 선택 영역 바깥 경계 주변의 마스크를 지정 px만큼 잘라낸다."""
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = -1
        if mode not in (2, 3):
            self.log(self.tr_ui("⚠️ 마스크 커팅은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요."))
            self.update_left_tool_action_states()
            return
        if region_mask is None:
            self.log(self.tr_ui("⚠️ 마스크 커팅 영역이 비어 있습니다."))
            return

        before = self.view.get_mask_np()
        if before is None:
            self.log(self.tr_ui("⚠️ 현재 탭에 마스크 레이어가 없습니다."))
            return

        try:
            cut_px = int(getattr(self, "sb_mask_cut_px", None).value()) if hasattr(self, "sb_mask_cut_px") else 8
        except Exception:
            cut_px = 8
        cut_px = max(1, min(200, int(cut_px)))

        try:
            mask = (before > 0).astype(np.uint8) * 255
            region = (region_mask > 0).astype(np.uint8) * 255
            if mask.shape[:2] != region.shape[:2]:
                region = cv2.resize(region, (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_NEAREST)

            kernel_size = cut_px * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            expanded = cv2.dilate(region, kernel, iterations=1)
            cut_band = cv2.bitwise_and(expanded, cv2.bitwise_not(region))

            if np.count_nonzero(cut_band) <= 0:
                self.log(self.tr_ui("⚠️ 마스크 커팅으로 제거할 외곽 영역이 없습니다."))
                return

            target_pixels = cv2.bitwise_and(mask, cut_band)
            removed = int(np.count_nonzero(target_pixels))
            if removed <= 0:
                self.log(self.tr_ui("⚠️ 지정한 커팅 영역에 제거할 마스크가 없습니다."))
                return

            try:
                self.commit_current_page_ui_to_data(include_mask=True)
                self.push_project_undo("마스크 커팅")
            except Exception:
                pass

            cut = mask.copy()
            cut[cut_band > 0] = 0

            if np.array_equal(cut, mask):
                self.log(self.tr_ui("⚠️ 마스크 커팅으로 변경된 영역이 없습니다."))
                return

            color = QColor(0, 0, 255, 150) if mode == 3 else QColor(168, 93, 102, 140)
            self.view.set_user_mask_np(cut, color)
            self.on_view_mask_edited()
            lang = normalize_ui_language(getattr(self, "ui_language", None) or current_ui_language())
            if lang == LANG_EN:
                self.log(f"🔪 Mask cutting complete: outer {cut_px}px / {removed} px removed")
            else:
                self.log(f"🔪 마스크 커팅 완료: 외곽 {cut_px}px / {removed} px 제거")
        except Exception as e:
            lang = normalize_ui_language(getattr(self, "ui_language", None) or current_ui_language())
            if lang == LANG_EN:
                self.log(f"⚠️ Mask cutting failed: {e}")
            else:
                self.log(f"⚠️ 마스크 커팅 실패: {e}")

    def magic_wand_pick(self, x, y):
        if self.cb_mode.currentIndex() not in [2, 3, 4]:
            self.log("⚠️ 요술봉은 마스크 탭 또는 최종결과 탭에서만 사용할 수 있습니다.")
            return

        img = self.current_magic_source_image()
        if img is None:
            self.log("⚠️ 요술봉 기준 이미지가 없습니다.")
            return

        h, w = img.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return

        tol = int(self.sb_magic_tolerance.value()) if hasattr(self, "sb_magic_tolerance") else 20
        # 요술봉 선택은 프로젝트 편집이 아니라 현재 페이지의 임시 선택 상태다.
        # ProjectUndo에 넣지 않고 MaskEngine의 magic-wand history로만 관리한다.
        self.push_magic_wand_history()
        self.magic_wand_seed = (int(x), int(y))
        if not hasattr(self, "magic_wand_seeds"):
            self.magic_wand_seeds = []
        self.magic_wand_seeds.append(self.magic_wand_seed)

        new_mask = self.build_magic_wand_mask(img, self.magic_wand_seed, tol)
        if self.magic_wand_mask is None:
            self.magic_wand_mask = new_mask
        else:
            self.magic_wand_mask = cv2.bitwise_or(self.magic_wand_mask.astype(np.uint8), new_mask.astype(np.uint8))

        try:
            if hasattr(self, "mask_engine") and self.mask_engine is not None:
                self.mask_engine.set_magic_mask(int(getattr(self, "idx", 0) or 0), self.magic_wand_mask, seeds=self.magic_wand_seeds, seed=self.magic_wand_seed)
        except Exception:
            pass
        self.view.draw_magic_wand_preview(self.magic_wand_mask)
        try:
            self._finish_magic_wand_runtime_command(reason="요술봉 선택 추가")
        except Exception:
            pass
        try:
            self.update_undo_redo_buttons()
        except Exception:
            pass
        self.log(f"요술봉 선택 추가: x={x}, y={y}, 허용범위={tol}, 누적={len(self.magic_wand_seeds)}")

    def build_magic_wand_mask(self, img, seed, tolerance):
        """
        Photoshop 요술봉에 가까운 기본 동작:
        클릭 픽셀과 RGB/BGR 값이 비슷하고, 서로 연결된 영역만 flood fill로 선택한다.
        """
        h, w = img.shape[:2]
        work_img = img.copy()
        flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        tol = max(0, min(255, int(tolerance)))
        diff = (tol, tol, tol)
        flags = 8 | cv2.FLOODFILL_FIXED_RANGE | (255 << 8)

        try:
            cv2.floodFill(work_img, flood_mask, tuple(seed), (0, 255, 255), diff, diff, flags)
        except Exception as e:
            self.log(f"⚠️ 요술봉 선택 실패: {e}")
            return np.zeros((h, w), dtype=np.uint8)

        raw = flood_mask[1:h + 1, 1:w + 1].copy()
        return self.fill_magic_wand_outer_region(raw)

    def fill_magic_wand_outer_region(self, mask):
        """요술봉 공통 후처리: 외부 외곽선을 기준으로 내부 구멍까지 채운다.

        도넛처럼 내부가 비어 있는 선택도 바깥 contour를 기준으로 하나의 면으로 칠한다.
        마스크 탭과 최종결과 탭이 같은 판정 결과를 공유한다.
        """
        try:
            if mask is None:
                return mask
            m = (mask.astype(np.uint8) > 0).astype(np.uint8) * 255
            contours, _hier = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return m
            out = np.zeros_like(m, dtype=np.uint8)
            cv2.drawContours(out, contours, -1, 255, thickness=-1)
            return out
        except Exception:
            try:
                return mask.astype(np.uint8)
            except Exception:
                return mask

    def on_magic_wand_tolerance_changed(self, value):
        # 허용범위를 바꾸면 누적 클릭 지점 전체를 기준으로 미리보기를 다시 계산한다.
        # 단, 영역확장 후 허용범위를 바꾸면 확장 상태는 재계산된다.
        if self.view.draw_mode != 'magic_wand':
            return
        seeds = list(getattr(self, "magic_wand_seeds", []) or [])
        if not seeds:
            return
        # 요술봉 허용범위 변경은 실제 프로젝트/마스크 편집이 아니라
        # 현재 요술봉 미리보기 안의 단계다. 전체 PageUndo가 아니라
        # MagicWandRuntime history에만 쌓아 Ctrl+Z가 순차적으로 되돌아가게 한다.
        self.push_magic_wand_history()
        img = self.current_magic_source_image()
        if img is None:
            return

        merged = None
        for seed in seeds:
            part = self.build_magic_wand_mask(img, seed, int(value))
            merged = part if merged is None else cv2.bitwise_or(merged.astype(np.uint8), part.astype(np.uint8))

        self.magic_wand_mask = merged
        try:
            if hasattr(self, "mask_engine") and self.mask_engine is not None:
                self.mask_engine.set_magic_mask(int(getattr(self, "idx", 0) or 0), self.magic_wand_mask, seeds=self.magic_wand_seeds, seed=self.magic_wand_seed)
        except Exception:
            pass
        self.view.draw_magic_wand_preview(self.magic_wand_mask)
        try:
            self._finish_magic_wand_runtime_command(reason="요술봉 허용범위 변경")
        except Exception:
            pass
        try:
            self.update_undo_redo_buttons()
        except Exception:
            pass

    def expand_magic_wand_selection(self):
        if self.magic_wand_mask is None:
            self.log("⚠️ 먼저 요술봉으로 영역을 선택하세요.")
            return

        amount = int(self.sb_magic_expand.value()) if hasattr(self, "sb_magic_expand") else 3
        if amount <= 0:
            self.view.draw_magic_wand_preview(self.magic_wand_mask)
            return

        # 영역 확장도 요술봉 내부 미리보기 단계다. Project/Page undo에 넣으면
        # Ctrl+Z 순서가 꼬여 선택 전체가 한 번에 사라질 수 있으므로
        # 요술봉 내부 history에만 직전 상태를 저장한다.
        self.push_magic_wand_history()
        kernel_size = amount * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        self.magic_wand_mask = cv2.dilate(self.magic_wand_mask, kernel, iterations=1)
        try:
            if hasattr(self, "mask_engine") and self.mask_engine is not None:
                self.mask_engine.set_magic_mask(int(getattr(self, "idx", 0) or 0), self.magic_wand_mask, seeds=self.magic_wand_seeds, seed=self.magic_wand_seed)
        except Exception:
            pass
        self.view.draw_magic_wand_preview(self.magic_wand_mask)
        try:
            self._finish_magic_wand_runtime_command(reason="요술봉 영역확장")
        except Exception:
            pass
        try:
            self.update_undo_redo_buttons()
        except Exception:
            pass
        self.log(f"요술봉 영역확장: {amount}px")

    def fill_magic_wand_mask(self):
        if self.magic_wand_mask is None:
            self.log("⚠️ 먼저 요술봉으로 영역을 선택하세요.")
            return

        mode = self.cb_mode.currentIndex()
        if mode == 4:
            return self.fill_magic_wand_final_paint()

        if mode not in [2, 3]:
            self.log("⚠️ 마스킹 칠하기는 마스크 탭에서만 가능합니다.")
            return

        if self.view.user_mask_item is None:
            self.log(self.tr_ui("⚠️ 현재 탭에 마스크 레이어가 없습니다."))
            return

        try:
            self.commit_current_page_ui_to_data(include_mask=True)
        except Exception:
            pass

        before = self.view.get_mask_np()
        if before is None:
            before = np.zeros_like(self.magic_wand_mask, dtype=np.uint8)
        before = before.copy() if isinstance(before, np.ndarray) else before
        before_magic_state = self.capture_magic_wand_state()

        mask = self.fill_magic_wand_outer_region(self.magic_wand_mask).astype(np.uint8)
        combined = cv2.bitwise_or(before.astype(np.uint8), mask)
        color = QColor(0, 0, 255, 150) if mode == 3 else QColor(168, 93, 102, 140)
        self.view.set_user_mask_np(combined, color)
        try:
            curr = self.data.get(self.idx)
            if isinstance(curr, dict):
                self.set_active_mask(curr, combined, mode)
        except Exception:
            pass

        self.push_magic_wand_history({
            "action": "fill_mask",
            "mode": int(mode),
            "before_mask": before.copy() if isinstance(before, np.ndarray) else before,
            "after_mask": combined.copy() if isinstance(combined, np.ndarray) else combined,
            "before_magic_state": before_magic_state,
        })
        # 칠한 뒤 preview는 지우되, 요술봉 내부 history는 유지한다.
        self.clear_magic_wand_selection(clear_history=False)
        self.on_view_mask_edited()
        self.log("요술봉 선택 영역을 현재 마스크에 칠했습니다.")

    def fill_magic_wand_final_paint(self):
        if self.magic_wand_mask is None:
            self.log("⚠️ 먼저 요술봉으로 영역을 선택하세요.")
            return False
        if self.cb_mode.currentIndex() != 4:
            return False
        if not hasattr(self, "view") or not hasattr(self.view, "apply_magic_wand_final_paint"):
            return False
        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass
        # 실제 Undo는 viewer.apply_magic_wand_final_paint()가 만든 QPixmap patch history로 처리한다.
        ok = False
        try:
            mask = self.fill_magic_wand_outer_region(self.magic_wand_mask).astype(np.uint8)
            ok = bool(self.view.apply_magic_wand_final_paint(mask))
        except Exception as e:
            self.log(f"⚠️ 요술봉 영역 칠하기 실패: {e}")
            ok = False
        if ok:
            self.clear_magic_wand_selection()
            try:
                if hasattr(self, "schedule_deferred_view_layer_commit"):
                    self.schedule_deferred_view_layer_commit("final_paint", delay_ms=1200)
                elif hasattr(self, "on_final_paint_edited"):
                    self.on_final_paint_edited()
            except Exception:
                pass
            self.log("요술봉 선택 영역을 현재 팔레트 색상으로 칠했습니다.")
        return ok


    def _sample_color_from_scene(self, scene, x, y):
        """Render a 1x1 scene pixel so eyedropper follows the visible result."""
        if scene is None:
            return None
        try:
            scene_rect = scene.sceneRect()
            if not scene_rect.contains(float(x), float(y)):
                return None
            qimg = QImage(1, 1, QImage.Format.Format_ARGB32)
            qimg.fill(Qt.GlobalColor.transparent)
            painter = QPainter(qimg)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            scene.render(painter, QRectF(0, 0, 1, 1), QRectF(float(x), float(y), 1, 1))
            painter.end()
            color = QColor(qimg.pixel(0, 0))
            if not color.isValid():
                return None
            return color
        except Exception:
            try:
                painter.end()
            except Exception:
                pass
            return None

    def _apply_final_paint_eyedropper_color(self, color, *, source_label="", global_pos=None):
        if color is None or not color.isValid():
            self.log(self.tr_ui("⚠️ 스포이드로 색상을 가져오지 못했습니다."))
            return False
        hex_color = color.name(QColor.NameFormat.HexRgb).upper()
        self.final_paint_color = hex_color
        try:
            QApplication.clipboard().setText(hex_color)
        except Exception:
            pass
        try:
            self.update_color_button_styles()
        except Exception:
            pass
        self._show_eyedropper_color_feedback(hex_color, source_label=source_label, global_pos=global_pos)
        self.log(f"🎯 {self.tr_ui('스포이드 색상 적용')}: {hex_color} ({self.tr_ui('클립보드에 복사됨')})")
        return True

    def pick_final_paint_color_from_scene(self, x, y, global_pos=None):
        color = self._sample_color_from_scene(getattr(getattr(self, "view", None), "scene", None), x, y)
        return self._apply_final_paint_eyedropper_color(color, source_label=self.tr_ui("최종화면"), global_pos=global_pos)

    def pick_final_paint_color_from_source_scene(self, x, y, global_pos=None):
        color = self._sample_color_from_scene(getattr(self, "source_compare_scene", None), x, y)
        return self._apply_final_paint_eyedropper_color(color, source_label=self.tr_ui("원본 비교창"), global_pos=global_pos)

    def _show_eyedropper_color_feedback(self, hex_color, *, source_label="", global_pos=None):
        try:
            QToolTip.hideText()
        except Exception:
            pass
        try:
            popup = getattr(self, "_eyedropper_color_popup", None)
            if popup is None:
                popup = QLabel(None)
                popup.setObjectName("ysbEyedropperColorPopup")
                popup.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
                popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                popup.setTextFormat(Qt.TextFormat.RichText)
                popup.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._eyedropper_color_popup = popup
            safe_hex = str(hex_color or "#000000").upper()
            c = QColor(safe_hex)
            text_fg = "#111111" if c.isValid() and c.lightness() > 170 else "#ffffff"
            popup.setText(
                "<div style='white-space:nowrap;'>"
                f"<span style='display:inline-block; width:30px; height:20px; "
                f"background:{safe_hex}; border:1px solid #111111; vertical-align:middle;'></span> "
                f"<b>{safe_hex}</b>"
                "</div>"
            )
            popup.setStyleSheet(
                "QLabel#ysbEyedropperColorPopup { "
                f"background:{safe_hex}; color:{text_fg}; border:1px solid #111111; "
                "border-radius:0px; padding:4px 7px; font-weight:700; }"
            )
            popup.adjustSize()
            pos = global_pos if global_pos is not None else QCursor.pos()
            try:
                pos = QPoint(pos)
            except Exception:
                pos = QCursor.pos()
            # 커서 위에 색상칩+HEX만 표시한다. 작업 지점은 가리지 않도록 살짝 띄운다.
            popup.move(pos + QPoint(10, -popup.height() - 12))
            popup.show()
            popup.raise_()
        except Exception:
            pass

    def _hide_eyedropper_color_feedback(self):
        try:
            QToolTip.hideText()
        except Exception:
            pass
        try:
            popup = getattr(self, "_eyedropper_color_popup", None)
            if popup is not None:
                popup.hide()
        except Exception:
            pass

    def adjust_magic_tolerance(self, delta):
        if not hasattr(self, "sb_magic_tolerance"):
            return
        self.sb_magic_tolerance.setValue(max(0, min(255, self.sb_magic_tolerance.value() + int(delta))))

    def adjust_magic_expand_range(self, delta):
        if not hasattr(self, "sb_magic_expand"):
            return
        self.sb_magic_expand.setValue(max(0, min(200, self.sb_magic_expand.value() + int(delta))))

    def _detach_source_compare_controls(self):
        try:
            controls = getattr(self, "source_compare_controls", None)
            if controls is None:
                return
            parent = controls.parentWidget()
            if parent is not None and parent.layout() is not None:
                try:
                    parent.layout().removeWidget(controls)
                except Exception:
                    pass
            try:
                controls.hide()
            except Exception:
                pass
            controls.setParent(None)
        except Exception:
            pass

    def _add_source_compare_controls_to_layout(self, layout):
        if layout is None or not hasattr(self, "source_compare_controls"):
            return False
        try:
            self._detach_source_compare_controls()
            # stretch 뒤에 붙여 같은 줄의 오른쪽 끝에 놓는다.
            layout.addWidget(self.source_compare_controls)
            self.source_compare_controls.show()
            return True
        except Exception:
            return False

    def place_source_compare_controls(self):
        """원본 비교 컨트롤은 공유 옵션바의 우측 고정 영역에만 배치한다."""
        try:
            right_layout = getattr(self, "shared_option_right_layout", None)
            controls = getattr(self, "source_compare_controls", None)
            effect_cb = getattr(self, "cb_text_effect_preview", None)
            if right_layout is None:
                return
            # 우측 고정 영역은 항상 [텍스트 이펙트 미리보기]를 맨 오른쪽 계열에 둔다.
            # 원본 비교창이 켜지면 체크박스 오른쪽에 비교창 컨트롤을 붙여 자연스럽게 왼쪽으로 밀린다.
            while right_layout.count():
                item = right_layout.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    try:
                        widget.hide()
                    except Exception:
                        pass
                    widget.setParent(None)
            if effect_cb is not None:
                try:
                    right_layout.addWidget(effect_cb)
                    effect_cb.show()
                except Exception:
                    pass
            visible = self.source_compare_is_visible() if hasattr(self, "source_compare_is_visible") else False
            if visible and controls is not None:
                right_layout.addWidget(controls)
                controls.show()
            elif controls is not None:
                controls.hide()
            if hasattr(self, "source_compare_bar"):
                self.source_compare_bar.hide()
            if hasattr(self, "shared_option_bar"):
                self.shared_option_bar.show()
        except Exception:
            pass

    def _hide_legacy_option_bars(self):
        for bar_name in (
            "area_paint_bar", "magic_wand_bar", "mask_wrap_bar", "mask_cut_bar",
            "ocr_region_bar", "final_paint_option_bar", "final_edit_bar",
            "source_compare_bar",
        ):
            try:
                bar = getattr(self, bar_name, None)
                if bar is not None:
                    bar.hide()
            except Exception:
                pass

    def _clear_shared_option_left(self):
        layout = getattr(self, "shared_option_left_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                # 출력/탭 전환 중 레이아웃에서 빠진 버튼이 부모 없는 독립 위젯으로
                # 좌상단에 떠버리는 것을 막기 위해 먼저 숨긴 뒤 분리한다.
                try:
                    widget.hide()
                except Exception:
                    pass
                widget.setParent(None)

    def _shared_add_label(self, text):
        try:
            label = QLabel(str(text))
            self.shared_option_left_layout.addWidget(label)
            return label
        except Exception:
            return None

    def refresh_shared_option_bar(self):
        """항상 보이는 한 줄 공유 옵션바의 왼쪽 도구 영역을 현재 상태에 맞게 재구성한다."""
        if getattr(self, "_export_rendering_guard", False):
            # 출력 렌더링은 사용자 조작이 아니므로 텍스트 선택용 옵션 위젯을
            # 새로 붙이지 않는다. 이미 붙어 있던 위젯도 숨겨 좌상단 탈출을 막는다.
            try:
                self._hide_legacy_option_bars()
                self._clear_shared_option_left()
                if hasattr(self, "shared_option_bar"):
                    self.shared_option_bar.show()
                if hasattr(self, "place_source_compare_controls"):
                    self.place_source_compare_controls()
            except Exception:
                pass
            return
        if getattr(self, "_suppress_shared_option_refresh", False):
            return
        if not hasattr(self, "shared_option_bar") or not hasattr(self, "shared_option_left_layout"):
            return
        self._hide_legacy_option_bars()
        self._clear_shared_option_left()
        try:
            self.shared_option_bar.show()
        except Exception:
            pass

        mode = self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0
        draw_mode = getattr(getattr(self, "view", None), "draw_mode", None)

        def add_widget(widget):
            try:
                if widget is not None:
                    self.shared_option_left_layout.addWidget(widget)
                    widget.show()
            except Exception:
                pass

        try:
            selected_text = self.selected_text_items() if hasattr(self, "selected_text_items") else []
        except Exception:
            selected_text = []

        populated = False
        try:
            if mode == 4 and draw_mode is None and selected_text:
                self._shared_add_label("불투명도")
                add_widget(getattr(self, "sb_text_opacity", None))
                add_widget(getattr(self, "btn_text_effect_gradient", None))
                add_widget(getattr(self, "btn_text_effect_transform", None))
                add_widget(getattr(self, "btn_text_effect_skew", None))
                add_widget(getattr(self, "btn_text_effect_trapezoid", None))
                add_widget(getattr(self, "btn_text_effect_arc", None))
                populated = True
            elif mode in (2, 3, 4) and draw_mode in ("draw", "erase"):
                self._shared_add_label(self.tr_ui("브러시"))
                self._shared_add_label(self.tr_ui("크기"))
                add_widget(getattr(self, "sb_brush_size", None))
                if mode == 4:
                    self._shared_add_label(self.tr_ui("불투명도"))
                    add_widget(getattr(self, "sb_final_paint_opacity", None))
                populated = True
            elif mode in (2, 3, 4) and draw_mode == "area_paint":
                self._shared_add_label(self.tr_ui("영역 마스킹") if mode in (2, 3) else self.tr_ui("영역 페인팅"))
                add_widget(getattr(self, "btn_area_paint_rect", None))
                add_widget(getattr(self, "btn_area_paint_free", None))
                self._shared_add_label(
                    self.tr_ui("선택한 영역을 현재 마스크에 채웁니다.")
                    if mode in (2, 3)
                    else self.tr_ui("선택한 영역을 현재 최종 페인팅 색상으로 채웁니다.")
                )
                populated = True
            elif mode in (2, 3, 4) and draw_mode == "magic_wand":
                self._shared_add_label("요술봉")
                self._shared_add_label("RGB 허용범위")
                add_widget(getattr(self, "sb_magic_tolerance", None))
                add_widget(getattr(self, "btn_magic_expand", None))
                self._shared_add_label("확장 범위")
                add_widget(getattr(self, "sb_magic_expand", None))
                try:
                    if getattr(self, "btn_magic_fill", None) is not None:
                        self.btn_magic_fill.setText(self.tr_ui("영역 칠하기") if mode == 4 else self.tr_ui("마스킹 칠하기"))
                except Exception:
                    pass
                add_widget(getattr(self, "btn_magic_fill", None))
                populated = True
            elif mode in (2, 3) and draw_mode == "mask_wrap":
                self._shared_add_label(self.tr_ui("마스크 랩핑"))
                add_widget(getattr(self, "btn_mask_wrap_rect", None))
                add_widget(getattr(self, "btn_mask_wrap_free", None))
                self._shared_add_label(self.tr_ui("선택한 영역 안의 떨어진 마스크들을 하나의 채움 영역으로 감싸줍니다."))
                populated = True
            elif mode in (2, 3) and draw_mode == "mask_cut":
                self._shared_add_label(self.tr_ui("마스크 커팅"))
                add_widget(getattr(self, "btn_mask_cut_rect", None))
                add_widget(getattr(self, "btn_mask_cut_free", None))
                self._shared_add_label(self.tr_ui("커팅 폭"))
                add_widget(getattr(self, "sb_mask_cut_px", None))
                populated = True
            elif draw_mode == "ocr_region_select":
                self._shared_add_label(self.tr_ui("OCR 분석 영역"))
                add_widget(getattr(self, "btn_ocr_region_rect", None))
                add_widget(getattr(self, "btn_ocr_region_free", None))
                self._shared_add_label(self.tr_ui("OCR이 읽을 범위를 드래그로 지정합니다."))
                add_widget(getattr(self, "btn_ocr_region_finish", None))
                populated = True
        except Exception:
            pass

        # 빈 상태여도 바 높이는 유지한다.
        try:
            self.shared_option_left_layout.addStretch(1)
        except Exception:
            pass
        try:
            self.place_source_compare_controls()
        except Exception:
            pass


    def _source_compare_sync_blocked(self):
        try:
            if getattr(self, "_text_scene_mutation_lock", False):
                return True
            if getattr(self, "_source_compare_splitter_adjusting", False):
                return True
            until = float(getattr(self, "_source_compare_sync_block_until", 0.0) or 0.0)
            if until and time.monotonic() < until:
                return True
        except Exception:
            pass
        return False

    def _block_source_compare_sync_temporarily(self, ms=180):
        try:
            self._source_compare_sync_block_until = max(
                float(getattr(self, "_source_compare_sync_block_until", 0.0) or 0.0),
                time.monotonic() + max(0, int(ms)) / 1000.0,
            )
            self._source_compare_sync_pending = False
            self._source_compare_reverse_sync_pending = False
        except Exception:
            pass

    def _source_compare_fast_path_log(self, event_name, **payload):
        try:
            if hasattr(self, "audit_boundary_event"):
                self.audit_boundary_event(event_name, **payload)
        except Exception:
            pass

    def _begin_source_compare_clone_fast_path(self, reason="sync", delay_ms=180):
        """Temporarily lower render cost for the source-compare clone view.

        The clone window mirrors the main view, so high-resolution pages can be
        repainted twice while zooming/panning.  During active synchronization we
        use a cheap render path for the clone, then restore the original render
        hints after movement stops.
        """
        try:
            if getattr(self, "_text_scene_mutation_lock", False) or getattr(self, "_text_item_drag_active", False):
                self._source_compare_fast_path_finish_pending = True
                self._source_compare_fast_path_log(
                    "TEXT_SCENE_MUTATION_TIMER_GUARD_BLOCKED_SOURCE_COMPARE",
                    action="begin",
                    reason=str(reason or "sync"),
                    text_drag=bool(getattr(self, "_text_item_drag_active", False)),
                    throttle_ms=100,
                )
                return
            view = getattr(self, "source_compare_view", None)
            if view is None or not view.isVisible():
                return
            try:
                delay_ms = int(delay_ms or 180)
            except Exception:
                delay_ms = 180
            delay_ms = max(80, min(delay_ms, 800))

            state = getattr(self, "_source_compare_fast_path_state", None)
            if not isinstance(state, dict):
                state = {"active": False}
                self._source_compare_fast_path_state = state

            if not state.get("active"):
                state.clear()
                state["active"] = True
                state["reason"] = str(reason or "sync")
                try:
                    state["hints"] = view.renderHints()
                except Exception:
                    state["hints"] = None
                try:
                    state["viewport_mode"] = view.viewportUpdateMode()
                except Exception:
                    state["viewport_mode"] = None
                try:
                    state["cache_mode"] = view.cacheMode()
                except Exception:
                    state["cache_mode"] = None
                try:
                    pix_item = getattr(self, "source_compare_pixmap_item", None)
                    if pix_item is not None:
                        state["pixmap_transform_mode"] = pix_item.transformationMode()
                        pix_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
                except Exception:
                    state["pixmap_transform_mode"] = None

                try:
                    view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                    view.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                    view.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
                except Exception:
                    pass
                try:
                    view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
                except Exception:
                    pass
                try:
                    view.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
                except Exception:
                    pass
                self._source_compare_fast_path_log(
                    "SOURCE_COMPARE_FAST_PATH_BEGIN",
                    reason=str(reason or "sync"),
                    delay_ms=delay_ms,
                    smooth_pixmap=False,
                    antialiasing=False,
                    viewport="BoundingRectViewportUpdate",
                    cache="CacheBackground",
                )
            else:
                state["reason"] = str(reason or state.get("reason") or "sync")

            timer = getattr(self, "_source_compare_fast_path_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._finish_source_compare_clone_fast_path)
                self._source_compare_fast_path_timer = timer
            timer.start(delay_ms)
        except Exception:
            pass

    def _finish_source_compare_clone_fast_path(self, force=False):
        try:
            state = getattr(self, "_source_compare_fast_path_state", None)
            if not isinstance(state, dict) or not state.get("active"):
                return
            if getattr(self, "_text_scene_mutation_lock", False) or getattr(self, "_text_item_drag_active", False):
                self._source_compare_fast_path_finish_pending = True
                try:
                    timer = getattr(self, "_source_compare_fast_path_timer", None)
                    if timer is not None and timer.isActive():
                        timer.stop()
                except Exception:
                    pass
                self._source_compare_fast_path_log(
                    "TEXT_SCENE_MUTATION_TIMER_GUARD_BLOCKED_SOURCE_COMPARE",
                    action="finish",
                    reason=str(state.get("reason") or "sync"),
                    throttle_ms=100,
                )
                return
            view = getattr(self, "source_compare_view", None)
            reason = str(state.get("reason") or "sync")
            if view is not None:
                try:
                    old_hints = state.get("hints")
                    if old_hints is not None:
                        view.setRenderHints(old_hints)
                    else:
                        view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                except Exception:
                    pass
                try:
                    old_mode = state.get("viewport_mode")
                    if old_mode is not None:
                        view.setViewportUpdateMode(old_mode)
                except Exception:
                    pass
                try:
                    old_cache = state.get("cache_mode")
                    if old_cache is not None:
                        view.setCacheMode(old_cache)
                    else:
                        view.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)
                except Exception:
                    pass
                try:
                    pix_item = getattr(self, "source_compare_pixmap_item", None)
                    old_transform = state.get("pixmap_transform_mode")
                    if pix_item is not None and old_transform is not None:
                        pix_item.setTransformationMode(old_transform)
                except Exception:
                    pass
                try:
                    view.viewport().update()
                except Exception:
                    pass
            self._source_compare_fast_path_state = {"active": False}
            self._source_compare_fast_path_finish_pending = False
            self._source_compare_fast_path_log("SOURCE_COMPARE_FAST_PATH_END", reason=reason)
        except Exception:
            try:
                self._source_compare_fast_path_state = {"active": False}
                self._source_compare_fast_path_finish_pending = False
            except Exception:
                pass

    def _capture_compare_view_state(self, view):
        try:
            if view is None:
                return None
            return {
                "transform": view.transform(),
                "h": view.horizontalScrollBar().value(),
                "v": view.verticalScrollBar().value(),
            }
        except Exception:
            return None

    def _restore_compare_view_state(self, view, state):
        try:
            if view is None or not state:
                return
            if state.get("transform") is not None:
                view.setTransform(state.get("transform"))
            if state.get("h") is not None:
                view.horizontalScrollBar().setValue(int(state.get("h")))
            if state.get("v") is not None:
                view.verticalScrollBar().setValue(int(state.get("v")))
            try:
                view.viewport().update()
            except Exception:
                pass
        except Exception:
            pass

    def _capture_source_compare_splitter_states(self):
        return {
            "main": self._capture_compare_view_state(getattr(self, "view", None)),
            "clone": self._capture_compare_view_state(getattr(self, "source_compare_view", None)),
        }

    def _restore_source_compare_splitter_states(self, states=None):
        try:
            if states is None:
                states = getattr(self, "_source_compare_splitter_view_states", None)
            if not states:
                return
            old_sync = getattr(self, "_source_compare_syncing", False)
            self._source_compare_syncing = True
            try:
                self._restore_compare_view_state(getattr(self, "view", None), states.get("main"))
                self._restore_compare_view_state(getattr(self, "source_compare_view", None), states.get("clone"))
            finally:
                self._source_compare_syncing = old_sync
        except Exception:
            pass

    def _capture_main_view_state_for_compare_splitter(self):
        try:
            states = self._capture_source_compare_splitter_states()
            return states.get("main")
        except Exception:
            return None

    def _restore_main_view_state_for_compare_splitter(self, state=None):
        try:
            if state is None:
                state = getattr(self, "_source_compare_splitter_main_view_state", None)
            old_sync = getattr(self, "_source_compare_syncing", False)
            self._source_compare_syncing = True
            try:
                self._restore_compare_view_state(getattr(self, "view", None), state)
            finally:
                self._source_compare_syncing = old_sync
        except Exception:
            pass

    def reset_source_compare_splitter_half(self):
        """원본 비교창과 작업창을 현재 사용 가능 너비 기준 정확히 반반으로 맞춘다."""
        try:
            keep_states = self._capture_source_compare_splitter_states()
            split = getattr(self, 'source_compare_splitter', None)
            if split is None or split.count() < 2:
                return
            total = max(0, int(split.width()) - max(0, (split.count() - 1) * int(split.handleWidth())))
            if total <= 0:
                total = sum(max(0, int(v)) for v in split.sizes())
            if total <= 0:
                return
            left = total // 2
            right = total - left
            self._source_compare_splitter_adjusting = True
            self._block_source_compare_sync_temporarily(260)
            try:
                split.setSizes([left, right])
                self._restore_source_compare_splitter_states(keep_states)
                QTimer.singleShot(0, lambda s=keep_states: self._restore_source_compare_splitter_states(s))
                QTimer.singleShot(80, lambda s=keep_states: self._restore_source_compare_splitter_states(s))
            finally:
                QTimer.singleShot(180, lambda: setattr(self, '_source_compare_splitter_adjusting', False))
            self.log('🖼️ 원본 비교창/작업창 너비를 1:1로 정렬했습니다.')
        except Exception as e:
            try:
                self.log(f'⚠️ 원본 비교창 정렬 실패: {e}')
            except Exception:
                pass

    def open_source_compare_view(self):
        """왼쪽에 현재 페이지의 원본 탭 이미지를 복제해 비교 보기로 띄운다.
        이미 열려 있으면 같은 버튼/단축키로 닫는다.
        """
        if not getattr(self, "paths", None):
            try:
                self.log(self.tr_ui("⚠️ 원본 비교창을 열 프로젝트가 없습니다."))
            except Exception:
                pass
            return
        try:
            if self.source_compare_is_visible():
                self.close_source_compare_view()
                return
            if hasattr(self, "source_compare_view"):
                self.source_compare_view.show()
            if hasattr(self, "source_compare_controls"):
                self.source_compare_controls.show()
            if hasattr(self, "source_compare_splitter"):
                sizes = self.source_compare_splitter.sizes()
                total = sum(sizes) if sizes else 0
                if total <= 0:
                    total = max(900, self.source_compare_splitter.width())
                left = max(40, int(total * 0.35))
                right = max(240, total - left)
                self.source_compare_splitter.setSizes([left, right])
            self.refresh_source_compare_view(fit=True)
            if hasattr(self, "sync_source_compare_from_main"):
                self.place_source_compare_controls()
                self.schedule_source_compare_sync(0)
                self.start_source_compare_sync_timer()
                QTimer.singleShot(60, lambda: self.schedule_source_compare_sync(0))
                QTimer.singleShot(160, lambda: self.schedule_source_compare_sync(0))
                QTimer.singleShot(300, lambda: self.schedule_source_compare_sync(0))
            self.log(self.tr_ui("🖼️ 원본 비교창을 열었습니다."))
        except Exception as e:
            try:
                self.log(self.tr_ui(f"⚠️ 원본 비교창 열기 실패: {e}"))
            except Exception:
                pass

    def close_source_compare_view(self):
        try:
            # Closing the clone view must not change the user's current work view.
            try:
                keep_transform = self.view.transform()
                keep_center = self.view.mapToScene(self.view.viewport().rect().center())
            except Exception:
                keep_transform = None
                keep_center = None

            self.stop_source_compare_sync_timer()
            if hasattr(self, "source_compare_view"):
                self.source_compare_view.hide()
            if hasattr(self, "source_compare_controls"):
                self.source_compare_controls.hide()
            if hasattr(self, "source_compare_bar"):
                self.source_compare_bar.hide()
            if hasattr(self, "source_compare_splitter"):
                self.source_compare_splitter.setSizes([0, max(400, self.source_compare_splitter.width())])

            def restore_main_view():
                try:
                    if keep_transform is not None:
                        self.view.setTransform(keep_transform)
                    if keep_center is not None:
                        self.view.centerOn(keep_center)
                except Exception:
                    pass
                try:
                    self.place_source_compare_controls()
                except Exception:
                    pass

            QTimer.singleShot(0, restore_main_view)
            QTimer.singleShot(80, restore_main_view)
            self.log(self.tr_ui("🖼️ 원본 비교창을 닫았습니다."))
        except Exception:
            pass

    def get_page_text_effect_preview_enabled(self, page_idx=None):
        """Return the page-local text effect preview setting.

        Heavy text effects are preview-only editor UI.  The setting is stored per
        page because a single project can contain both light pages and very heavy
        glow/shadow pages.  Missing value means ON.
        """
        try:
            pidx = int(page_idx if page_idx is not None else getattr(self, "idx", 0) or 0)
        except Exception:
            pidx = int(getattr(self, "idx", 0) or 0) if hasattr(self, "idx") else 0
        try:
            curr = (getattr(self, "data", {}) or {}).get(pidx)
            if isinstance(curr, dict) and "text_effect_preview_enabled" in curr:
                return bool(curr.get("text_effect_preview_enabled"))
        except Exception:
            pass
        return True

    def sync_text_effect_preview_checkbox_for_current_page(self):
        """Apply the current page-local effect-preview value to runtime/UI."""
        enabled = bool(self.get_page_text_effect_preview_enabled())
        try:
            self.text_effect_preview_enabled = enabled
        except Exception:
            pass
        cb = getattr(self, "cb_text_effect_preview", None)
        if cb is not None:
            try:
                old = cb.blockSignals(True)
                try:
                    cb.setChecked(enabled)
                finally:
                    cb.blockSignals(old)
            except Exception:
                try:
                    cb.setChecked(enabled)
                except Exception:
                    pass
        return enabled

    def on_text_effect_preview_toggled(self, checked):
        """Toggle heavy text effects for the current page editor preview only.

        This does not change export rendering.  It only skips expensive
        preview-only effects for the active page while editing/navigation is laggy.
        """
        enabled = bool(checked)
        changed = False
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            page_idx = 0
        try:
            curr = (getattr(self, "data", {}) or {}).get(page_idx)
            if isinstance(curr, dict):
                old = bool(curr.get("text_effect_preview_enabled", True))
                if old != enabled or "text_effect_preview_enabled" not in curr:
                    curr["text_effect_preview_enabled"] = enabled
                    changed = True
        except Exception:
            pass
        try:
            self.text_effect_preview_enabled = enabled
        except Exception:
            pass
        if changed:
            try:
                self.mark_current_page_for_recovery_checkpoint("text_effect_preview")
            except Exception:
                try:
                    self.mark_active_page_dirty("text_effect_preview")
                except Exception:
                    pass
            try:
                self.schedule_workspace_checkpoint(900, reason="text_effect_preview_toggle")
            except Exception:
                try:
                    self.schedule_deferred_auto_save_project(900)
                except Exception:
                    pass
        try:
            scene = getattr(getattr(self, "view", None), "scene", None)
            if scene is not None:
                for item in list(scene.items()):
                    if isinstance(item, TypesettingItem):
                        try:
                            item.update()
                        except Exception:
                            pass
        except Exception:
            pass
        try:
            view = getattr(self, "view", None)
            if view is not None and view.viewport() is not None:
                view.viewport().update()
        except Exception:
            pass
        try:
            msg = "텍스트 이펙트 미리보기 켜짐" if enabled else "텍스트 이펙트 미리보기 꺼짐 - 최종 출력에는 영향 없음"
            self.log(self.tr_ui(msg))
        except Exception:
            pass

    def on_source_compare_sync_toggled(self, checked):
        if checked:
            self.schedule_source_compare_sync(0)
            self.start_source_compare_sync_timer()
        else:
            self.stop_source_compare_sync_timer()
            try:
                self._source_compare_sync_pending = False
            except Exception:
                pass

    def source_compare_is_visible(self):
        try:
            return bool(hasattr(self, "source_compare_view") and self.source_compare_view.isVisible())
        except Exception:
            return False

    def ensure_source_compare_sync_timer(self):
        """Create a lightweight polling timer for clone sync."""
        try:
            timer = getattr(self, "_source_compare_sync_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setInterval(80)
                timer.timeout.connect(lambda: self.sync_source_compare_from_main())
                self._source_compare_sync_timer = timer
            return timer
        except Exception:
            return None

    def start_source_compare_sync_timer(self):
        try:
            if self._source_compare_sync_blocked():
                return
            if not self.source_compare_is_visible():
                return
            if hasattr(self, "cb_source_compare_sync") and not self.cb_source_compare_sync.isChecked():
                return
            timer = self.ensure_source_compare_sync_timer()
            if timer is not None and not timer.isActive():
                timer.start()
        except Exception:
            pass

    def stop_source_compare_sync_timer(self):
        try:
            timer = getattr(self, "_source_compare_sync_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
        except Exception:
            pass

    def schedule_source_compare_sync(self, delay=16):
        """Coalesce source-compare clone sync requests.

        Safe zoom-performance rule:
        - Do not change text item cache modes here. That made large text pages much slower.
        - During wheel/scroll fast path, postpone clone sync until the view settles.
        - Keep the existing one-shot/pending structure so this remains low-risk.
        """
        try:
            if getattr(self, "_text_scene_mutation_lock", False) or getattr(self, "_text_item_drag_active", False):
                self._source_compare_sync_resume_after_text_mutation = True
                self._source_compare_fast_path_log(
                    "TEXT_SCENE_MUTATION_TIMER_GUARD_BLOCKED_SOURCE_COMPARE",
                    action="schedule_sync",
                    text_drag=bool(getattr(self, "_text_item_drag_active", False)),
                    throttle_ms=100,
                )
                return
            if self._source_compare_sync_blocked() or getattr(self, "_source_compare_syncing", False) or getattr(self, "_source_compare_user_driving", False):
                return
            if not self.source_compare_is_visible():
                return
            if hasattr(self, "cb_source_compare_sync") and not self.cb_source_compare_sync.isChecked():
                return
            if getattr(self, "_source_compare_sync_pending", False):
                return
            self._source_compare_sync_pending = True
            def _run():
                try:
                    self._source_compare_sync_pending = False
                    if getattr(self, "_text_scene_mutation_lock", False) or getattr(self, "_text_item_drag_active", False):
                        self._source_compare_sync_resume_after_text_mutation = True
                        self._source_compare_fast_path_log(
                            "TEXT_SCENE_MUTATION_TIMER_GUARD_BLOCKED_SOURCE_COMPARE",
                            action="run_sync",
                            text_drag=bool(getattr(self, "_text_item_drag_active", False)),
                            throttle_ms=100,
                        )
                        return
                    view = getattr(self, "view", None)
                    if view is not None and getattr(view, "_view_interaction_fast_path_active", False):
                        # A wheel burst is still repainting the work view.  Syncing the
                        # clone now causes two views to repaint mid-gesture.  Push once.
                        self.schedule_source_compare_sync(180)
                        return
                    if self._source_compare_sync_blocked() or getattr(self, "_source_compare_user_driving", False):
                        return
                    self.sync_source_compare_from_main()
                except Exception:
                    self._source_compare_sync_pending = False
            try:
                effective_delay = max(16, int(delay or 0))
            except Exception:
                effective_delay = 16
            QTimer.singleShot(effective_delay, _run)
        except Exception:
            try:
                self._source_compare_sync_pending = False
            except Exception:
                pass

    def refresh_source_compare_view(self, fit=False):
        if not self.source_compare_is_visible():
            return
        try:
            # 원본 비교창은 작업용 원본(working_source)이 아니라, 처음 불러온 순수 원본을 유지한다.
            # Alt+P '배경을 원본으로 쓰기'는 분석/인페인팅 기준만 바꾸고 비교용 순수 원본은 건드리지 않는다.
            img = self.get_real_original_image(self.idx) if hasattr(self, "get_real_original_image") else None
            if img is None:
                img = self.get_source_display_image(self.idx)
            scene = self.source_compare_scene
            scene.clear()
            pix = self.qt_pixmap_from_image_source(img)
            if pix is None or pix.isNull():
                return
            item = scene.addPixmap(pix)
            self.source_compare_pixmap_item = item
            try:
                item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            except Exception:
                pass
            scene.setSceneRect(QRectF(pix.rect()))
            if fit and not (hasattr(self, "cb_source_compare_sync") and self.cb_source_compare_sync.isChecked()):
                self.source_compare_view.fitInView(scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            if hasattr(self, "cb_source_compare_sync") and self.cb_source_compare_sync.isChecked():
                self.schedule_source_compare_sync(0)
        except Exception as e:
            try:
                self.log(self.tr_ui(f"⚠️ 원본 비교창 갱신 실패: {e}"))
            except Exception:
                pass

    def sync_source_compare_from_main(self):
        if getattr(self, "_text_scene_mutation_lock", False) or getattr(self, "_text_item_drag_active", False):
            self._source_compare_sync_resume_after_text_mutation = True
            self._source_compare_fast_path_log(
                "TEXT_SCENE_MUTATION_TIMER_GUARD_BLOCKED_SOURCE_COMPARE",
                action="sync_from_main",
                text_drag=bool(getattr(self, "_text_item_drag_active", False)),
                throttle_ms=100,
            )
            return
        if self._source_compare_sync_blocked():
            return
        if getattr(self, "_source_compare_syncing", False) or getattr(self, "_source_compare_user_driving", False):
            return
        if not self.source_compare_is_visible():
            return
        if hasattr(self, "cb_source_compare_sync") and not self.cb_source_compare_sync.isChecked():
            return
        self._source_compare_syncing = True
        try:
            self._begin_source_compare_clone_fast_path("main_to_clone_sync", delay_ms=180)
            center = self.view.mapToScene(self.view.viewport().rect().center())
            self.source_compare_view.setTransform(self.view.transform())
            self.source_compare_view.centerOn(center)
            try:
                self.source_compare_view.viewport().update()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self._source_compare_syncing = False

    def schedule_main_sync_from_source_compare(self, delay=0):
        try:
            if getattr(self, "_text_scene_mutation_lock", False) or getattr(self, "_text_item_drag_active", False):
                self._source_compare_sync_resume_after_text_mutation = True
                self._source_compare_fast_path_log(
                    "TEXT_SCENE_MUTATION_TIMER_GUARD_BLOCKED_SOURCE_COMPARE",
                    action="schedule_reverse_sync",
                    text_drag=bool(getattr(self, "_text_item_drag_active", False)),
                    throttle_ms=100,
                )
                return
            if self._source_compare_sync_blocked() or getattr(self, "_source_compare_syncing", False):
                return
            if not self.source_compare_is_visible():
                return
            if hasattr(self, "cb_source_compare_sync") and not self.cb_source_compare_sync.isChecked():
                return
            if getattr(self, "_source_compare_reverse_sync_pending", False):
                return
            self._source_compare_reverse_sync_pending = True
            def _run():
                try:
                    self._source_compare_reverse_sync_pending = False
                    sc_view = getattr(self, "source_compare_view", None)
                    if sc_view is not None and getattr(sc_view, "_view_interaction_fast_path_active", False):
                        self.schedule_main_sync_from_source_compare(180)
                        return
                    if self._source_compare_sync_blocked():
                        return
                    self.sync_main_from_source_compare()
                except Exception:
                    self._source_compare_reverse_sync_pending = False
            try:
                effective_delay = max(16, int(delay or 0))
            except Exception:
                effective_delay = 16
            QTimer.singleShot(effective_delay, _run)
        except Exception:
            try:
                self._source_compare_reverse_sync_pending = False
            except Exception:
                pass

    def sync_main_from_source_compare(self):
        if self._source_compare_sync_blocked():
            return
        if getattr(self, "_source_compare_syncing", False):
            return
        if not self.source_compare_is_visible():
            return
        if hasattr(self, "cb_source_compare_sync") and not self.cb_source_compare_sync.isChecked():
            return
        self._source_compare_syncing = True
        try:
            self._begin_source_compare_clone_fast_path("clone_to_main_sync", delay_ms=180)
            try:
                if hasattr(self.view, "_begin_view_interaction_fast_path"):
                    self.view._begin_view_interaction_fast_path("source_compare_reverse_sync", delay_ms=180)
            except Exception:
                pass
            center = self.source_compare_view.mapToScene(self.source_compare_view.viewport().rect().center())
            self.view.setTransform(self.source_compare_view.transform())
            self.view.centerOn(center)
            try:
                self.view.viewport().update()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self._source_compare_syncing = False

    def _on_main_view_scroll_changed_for_source_compare(self, *_args):
        try:
            if self._source_compare_sync_blocked() or getattr(self, "_source_compare_syncing", False):
                return
            try:
                self._begin_source_compare_clone_fast_path("main_scroll_sync", delay_ms=180)
            except Exception:
                pass
            self.schedule_source_compare_sync(16)
        except Exception:
            pass

    def _on_source_compare_scroll_changed_for_main(self, *_args):
        try:
            if self._source_compare_sync_blocked() or getattr(self, "_source_compare_syncing", False):
                return
            sc_view = getattr(self, "source_compare_view", None)
            # Resize/layout changes also move scrollbars. Treat reverse sync as user intent
            # only when the clone view itself is being interacted with.
            user_driving = bool(getattr(self, "_source_compare_user_driving", False))
            try:
                user_driving = user_driving or bool(sc_view is not None and (sc_view.underMouse() or sc_view.viewport().underMouse()))
            except Exception:
                pass
            if not user_driving:
                return
            try:
                self._begin_source_compare_clone_fast_path("clone_scroll_reverse_sync", delay_ms=180)
            except Exception:
                pass
            self.schedule_main_sync_from_source_compare(16)
        except Exception:
            pass

    def update_left_tool_action_states(self, tool=None):
        """Reflect the active canvas tool on the left toolbar buttons.

        The source of truth is view.draw_mode.  This method is called both after
        mouse-click toolbar actions and after keyboard shortcuts, so the visual
        state is consistent regardless of how the tool was selected.
        """
        try:
            if tool is None and getattr(self, "view", None) is not None:
                tool = getattr(self.view, "draw_mode", None)
        except Exception:
            tool = None
        active_key = str(tool) if tool is not None else ""
        actions = getattr(self, "left_tool_actions", {}) or {}
        buttons = getattr(self, "left_tool_buttons", {}) or {}
        for key, action in list(actions.items()):
            active = str(key) == active_key
            if action is not None:
                try:
                    action.blockSignals(True)
                    action.setChecked(active)
                except Exception:
                    pass
                finally:
                    try:
                        action.blockSignals(False)
                    except Exception:
                        pass
            btn = buttons.get(key)
            if btn is None:
                try:
                    btn = self.tb.widgetForAction(action) if hasattr(self, "tb") and self.tb is not None and action is not None else None
                    if btn is not None:
                        buttons[key] = btn
                except Exception:
                    btn = None
            if btn is not None:
                try:
                    btn.setCheckable(True)
                    btn.blockSignals(True)
                    btn.setChecked(active)
                    btn.setProperty("ysb_active_tool", bool(active))
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                    btn.update()
                except Exception:
                    pass
                finally:
                    try:
                        btn.blockSignals(False)
                    except Exception:
                        pass
        try:
            self.left_tool_buttons = buttons
        except Exception:
            pass
        try:
            if hasattr(self, "tb") and self.tb is not None:
                self.tb.update()
        except Exception:
            pass

    def set_tool(self, m):
        mode = self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0

        if m == 'magic_wand' and mode not in [2, 3, 4]:
            self.log("⚠️ 요술봉은 마스크 탭 또는 최종결과 탭에서 사용하세요.")
            self.update_left_tool_action_states()
            return
        if m == 'mask_wrap' and mode not in [2, 3]:
            self.log("⚠️ 마스크 랩핑은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.")
            return
        if m == 'mask_cut' and mode not in [2, 3]:
            self.log(self.tr_ui("⚠️ 마스크 커팅은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요."))
            return
        if m == 'final_text' and mode != 4:
            self.log("⚠️ 텍스트 도구는 최종화면에서만 사용할 수 있습니다.")
            self.update_left_tool_action_states()
            return
        if m == 'area_paint' and mode not in [2, 3, 4]:
            self.log("⚠️ 영역 페인팅/마스킹은 마스크 탭 또는 최종화면에서만 사용할 수 있습니다.")
            self.update_left_tool_action_states()
            return
        if m == 'paste_text' and mode != 4:
            self.log("⚠️ 텍스트 붙여넣기는 최종화면에서만 사용할 수 있습니다.")
            self.update_left_tool_action_states()
            return
        if m == 'raster_erase' and mode != 4:
            self.log("⚠️ " + self.tr_ui("객체 일부 지우기는 최종화면에서만 사용할 수 있습니다."))
            self.update_left_tool_action_states()
            return
        if m in ('draw', 'erase') and mode not in [2, 3, 4]:
            self.log("⚠️ 브러시/지우개는 마스크 탭 또는 최종화면에서만 사용할 수 있습니다.")
            self.update_left_tool_action_states()
            return

        if m != 'paste_text':
            self.text_paste_pending = False
            try:
                self.view.clear_paste_preview()
            except Exception:
                pass

        self.view.draw_mode = m
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag if m else QGraphicsView.DragMode.ScrollHandDrag)
        self.update_left_tool_action_states(m)
        self._hide_legacy_option_bars()
        if m != 'magic_wand':
            self.clear_magic_wand_selection()
        if m != 'mask_wrap' and hasattr(self.view, "clear_mask_wrap_preview"):
            self.view.clear_mask_wrap_preview()
        if m != 'mask_cut' and hasattr(self.view, "clear_mask_cut_preview"):
            self.view.clear_mask_cut_preview()
        if m != 'ocr_region_select' and hasattr(self.view, "clear_ocr_region_preview"):
            self.view.clear_ocr_region_preview()
        if m != 'quick_ocr' and hasattr(self.view, "clear_quick_ocr_preview"):
            self.view.clear_quick_ocr_preview()
        if m != 'area_paint' and hasattr(self.view, "clear_area_paint_preview"):
            self.view.clear_area_paint_preview()
        if m != 'area_paint' and hasattr(self.view, "area_paint_points"):
            self.view.area_paint_points = []
        if m != 'raster_erase' and hasattr(self.view, "clear_raster_erase_preview"):
            self.view.clear_raster_erase_preview()

        self.update_final_paint_option_bar_visibility()
        try:
            self.refresh_shared_option_bar()
        except Exception:
            pass

        if m == 'final_text':
            self.log("🔤 도구: 텍스트")
        elif m == 'paste_text':
            self.log("📋 도구: 텍스트 붙여넣기 위치 지정")
        elif m == 'area_paint':
            if mode in (2, 3):
                self.log("▦ 도구: 영역 마스킹")
            else:
                self.log("▦ 도구: 영역 페인팅")
        elif m == 'raster_erase':
            self.log("🧽 " + self.tr_ui("도구: 텍스트 객체 일부 지우기"))
        elif m == 'draw':
            self.log("🖌️ 도구: 브러시")
        elif m == 'erase':
            self.log("🧼 도구: 지우개")
        elif m == 'mask_wrap':
            self.log("🩹 도구: 마스크 랩핑")
        elif m == 'mask_cut':
            self.log(self.tr_ui("🔪 도구: 마스크 커팅"))
        elif m == 'ocr_region_select':
            self.log("🔎 도구: OCR 분석 영역 지정")
        elif m == 'quick_ocr':
            self.log("🔎 도구: 빠른 OCR 영역 선택")
        elif m is None:
            self.log("✋ 도구: 이동")

    def _ocr_region_indices_label(self, indices):
        if not indices:
            return self.tr_ui("선택 페이지 없음")
        if len(indices) == len(getattr(self, "paths", []) or []):
            return self.tr_ui("전체 페이지")
        return ", ".join(str(i + 1) for i in indices[:12]) + ("..." if len(indices) > 12 else "")

    def ocr_analysis_regions_hidden(self):
        return bool((getattr(self, "app_options", {}) or {}).get("ocr_analysis_regions_hidden", False))

    def set_ocr_analysis_regions_hidden(self, hidden):
        self.app_options["ocr_analysis_regions_hidden"] = bool(hidden)
        self.save_app_options_cache()
        self.refresh_ocr_region_overlay()

    def current_ocr_regions_for_view(self):
        if self.ocr_analysis_regions_hidden():
            return []
        temp = getattr(self, "ocr_region_temp_by_page", None)
        if isinstance(temp, dict) and self.idx in temp:
            return copy.deepcopy(temp.get(self.idx) or [])
        curr = self.data.get(self.idx) if hasattr(self, "data") else None
        if not curr:
            return []
        return copy.deepcopy(curr.get('ocr_analysis_regions', []) or [])

    def refresh_ocr_region_overlay(self):
        try:
            if not hasattr(self, "view"):
                return
            if self.ocr_analysis_regions_hidden():
                self.view.clear_ocr_region_overlay()
                return
            mode = self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0
            if mode in (0, 1, 2, 3):
                self.view.draw_ocr_analysis_regions(self.current_ocr_regions_for_view())
            else:
                self.view.clear_ocr_region_overlay()
        except Exception:
            pass

    def set_ocr_region_shape(self, shape, silent=False):
        shape = "free" if str(shape) == "free" else "rect"
        try:
            self.view.ocr_region_shape = shape
            self.view.clear_ocr_region_preview()
        except Exception:
            pass
        for btn, active in ((getattr(self, "btn_ocr_region_rect", None), shape == "rect"), (getattr(self, "btn_ocr_region_free", None), shape == "free")):
            if btn is None:
                continue
            try:
                btn.blockSignals(True)
                btn.setChecked(active)
                btn.blockSignals(False)
                if active:
                    btn.setStyleSheet("font-weight:bold; background:#8A4A52; color:white;")
                else:
                    btn.setStyleSheet("opacity:0.7;")
            except Exception:
                pass
        if not silent:
            self.log("🔎 OCR 분석 영역: 사각형" if shape == "rect" else "🔎 OCR 분석 영역: 자유형")

    def open_ocr_analysis_region_dialog(self):
        if not getattr(self, "paths", None):
            QMessageBox.information(self, self.tr_ui("이미지 없음"), self.tr_ui("먼저 프로젝트에 이미지를 불러와 주세요."))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("OCR 분석 범위 지정"))
        dlg.setModal(True)
        dlg.resize(720, 430)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("OCR 분석 범위 지정"), dlg)
        title.setObjectName("SettingsTitle")
        root.addWidget(title)

        desc = QLabel(self.tr_ui("OCR이 읽을 영역을 페이지별로 제한합니다. 지정된 영역이 없으면 전체 화면을 분석합니다."), dlg)
        desc.setObjectName("SettingsDescription")
        desc.setWordWrap(True)
        root.addWidget(desc)

        form_box = QFrame(dlg)
        form_box.setObjectName("SettingsItem")
        form_layout = QVBoxLayout(form_box)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(12)

        def add_setting_row(title_text, description_text, button_text, handler):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)

            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)

            item_title = QLabel(self.tr_ui(title_text), dlg)
            item_title.setObjectName("SettingsItemTitle")
            item_desc = QLabel(self.tr_ui(description_text), dlg)
            item_desc.setObjectName("SettingsDescription")
            item_desc.setWordWrap(True)

            text_box.addWidget(item_title)
            text_box.addWidget(item_desc)
            row.addLayout(text_box, 1)

            btn = QPushButton(self.tr_ui(button_text), dlg)
            btn.setMinimumWidth(112)
            btn.clicked.connect(lambda checked=False, _h=handler: (dlg.accept(), _h()))
            row.addWidget(btn, 0)
            form_layout.addLayout(row)

        add_setting_row(
            "현재 페이지의 OCR 분석 범위 지정",
            "현재 보고 있는 페이지만 OCR 분석 영역을 지정합니다.",
            "지정하기",
            lambda: self.start_ocr_analysis_region_selection([self.idx], "현재 페이지"),
        )
        add_setting_row(
            "전체 페이지의 OCR 분석 범위 지정",
            "모든 페이지에 같은 OCR 분석 영역을 지정합니다.",
            "지정하기",
            lambda: self.start_ocr_analysis_region_selection(list(range(len(self.paths))), "전체 페이지"),
        )

        def selected_pages_handler():
            indices, label = self.choose_batch_page_indices(self.tr_ui("OCR 분석 범위 지정"), "analyze")
            if indices is None:
                self.log("↩️ OCR 분석 범위 지정 취소")
                return
            self.start_ocr_analysis_region_selection(indices, label)

        add_setting_row(
            "선택 페이지의 OCR 분석 범위 지정",
            "1-3, 1~3, 1,2,3 형식으로 지정한 페이지에 같은 영역을 적용합니다.",
            "지정하기",
            selected_pages_handler,
        )

        line = QFrame(dlg)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form_layout.addWidget(line)

        add_setting_row(
            "현재 페이지 범위지정 해제",
            "현재 보고 있는 페이지만 OCR 분석 영역을 지우고, 다른 페이지의 영역은 유지합니다.",
            "현재 페이지만 해제",
            self.clear_current_ocr_analysis_regions,
        )

        add_setting_row(
            "전체 범위지정 해제",
            "저장된 OCR 분석 영역을 모든 페이지에서 지우고, 다시 전체 화면 분석 상태로 되돌립니다.",
            "전체 해제",
            self.clear_all_ocr_analysis_regions,
        )

        hide_box = QFrame(dlg)
        hide_box.setObjectName("SettingsItem")
        hide_layout = QVBoxLayout(hide_box)
        hide_layout.setContentsMargins(12, 12, 12, 12)
        hide_layout.setSpacing(6)
        cb_hide_regions = QCheckBox(self.tr_ui("OCR 분석 영역 숨기기"), dlg)
        cb_hide_regions.setChecked(self.ocr_analysis_regions_hidden())
        cb_hide_desc = QLabel(self.tr_ui("체크하면 저장된 OCR 분석 영역은 유지하되, 모든 탭에서 영역 표시만 숨깁니다."), dlg)
        cb_hide_desc.setObjectName("SettingsDescription")
        cb_hide_desc.setWordWrap(True)
        hide_layout.addWidget(cb_hide_regions)
        hide_layout.addWidget(cb_hide_desc)
        cb_hide_regions.toggled.connect(lambda checked: self.set_ocr_analysis_regions_hidden(bool(checked)))

        root.addWidget(form_box)
        root.addWidget(hide_box)
        root.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(self.tr_ui("닫기"))
        buttons.rejected.connect(dlg.reject)
        root.addWidget(buttons)
        dlg.exec()


    def _copy_ocr_region_temp_state(self):
        try:
            temp = getattr(self, "ocr_region_temp_by_page", None)
            return {
                "temp_by_page": copy.deepcopy(temp) if isinstance(temp, dict) else None,
                "history": copy.deepcopy(getattr(self, "ocr_region_temp_history", []) or []),
                "target_indices": [int(x) for x in (getattr(self, "ocr_region_target_indices", []) or [])],
                "target_label": str(getattr(self, "ocr_region_target_label", "") or ""),
            }
        except Exception:
            return {"temp_by_page": None, "history": [], "target_indices": [], "target_label": ""}

    def push_ocr_region_temp_command(self, before_state=None, after_state=None, *, reason="OCR 분석 영역 임시 추가"):
        before_state = before_state if isinstance(before_state, dict) else self._copy_ocr_region_temp_state()
        after_state = after_state if isinstance(after_state, dict) else self._copy_ocr_region_temp_state()
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            page_idx = 0
        return self._push_runtime_command(
            "ocr_region_temp",
            f"ocr_region_temp:{page_idx}",
            "state",
            before_state,
            after_state,
            reason=reason,
            meta={"stage": "undo_exception_cleanup", "runtime_only": True},
        )

    def _apply_ocr_region_temp_command(self, command, *, redo=False):
        changes = list(getattr(command, "changes", []) or [])
        if not changes:
            return False
        value = None
        for change in changes:
            if str(getattr(change, "field", "") or "") == "state":
                value = copy.deepcopy(getattr(change, "after", None) if redo else getattr(change, "before", None))
                break
        if not isinstance(value, dict):
            return False
        try:
            temp = value.get("temp_by_page")
            self.ocr_region_temp_by_page = copy.deepcopy(temp) if isinstance(temp, dict) else temp
            self.ocr_region_temp_history = copy.deepcopy(value.get("history") or [])
            self.ocr_region_target_indices = [int(x) for x in (value.get("target_indices") or [])]
            self.ocr_region_target_label = str(value.get("target_label") or "")
            self.refresh_ocr_region_overlay()
            self.update_undo_redo_buttons()
            self.audit_boundary_event("UNDO_OCR_REGION_TEMP_COMMAND_APPLY", redo=bool(redo), hist_len=len(self.ocr_region_temp_history or []), throttle_ms=120)
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ OCR 임시 영역 복원 실패: {e}")
            except Exception:
                pass
            return False

    def start_ocr_analysis_region_selection(self, indices, label=""):
        if not indices:
            self.log("⚠️ OCR 분석 영역을 지정할 페이지가 없습니다.")
            return
        clean = []
        seen = set()
        for raw in indices:
            try:
                i = int(raw)
            except Exception:
                continue
            if 0 <= i < len(self.paths) and i not in seen:
                clean.append(i); seen.add(i)
        if not clean:
            self.log("⚠️ OCR 분석 영역을 지정할 페이지가 없습니다.")
            return
        self.ocr_region_target_indices = clean
        self.ocr_region_target_label = str(label or self._ocr_region_indices_label(clean))
        self.ocr_region_temp_history = []
        self.ocr_region_temp_by_page = {i: copy.deepcopy(self.data.get(i, {}).get('ocr_analysis_regions', []) or []) for i in clean}
        if self.idx not in self.ocr_region_temp_by_page:
            self.ocr_region_temp_by_page[self.idx] = copy.deepcopy(self.data.get(self.idx, {}).get('ocr_analysis_regions', []) or [])
        self.set_ocr_region_shape("rect", silent=True)
        self.set_tool('ocr_region_select')
        self.refresh_ocr_region_overlay()
        self.log(f"🔎 OCR 분석 영역 지정 시작: {self.ocr_region_target_label}")

    def add_ocr_analysis_region_payload(self, payload):
        if not isinstance(payload, dict):
            return
        before_temp_state = self._copy_ocr_region_temp_state() if hasattr(self, "_copy_ocr_region_temp_state") else None
        temp = getattr(self, "ocr_region_temp_by_page", None)
        targets = list(getattr(self, "ocr_region_target_indices", []) or [])
        if not isinstance(temp, dict) or not targets:
            targets = [self.idx]
            self.ocr_region_target_indices = targets
            self.ocr_region_target_label = self.tr_ui("현재 페이지")
            self.ocr_region_temp_by_page = {self.idx: copy.deepcopy(self.data.get(self.idx, {}).get('ocr_analysis_regions', []) or [])}
            temp = self.ocr_region_temp_by_page
        affected = []
        for i in targets:
            temp.setdefault(i, copy.deepcopy(self.data.get(i, {}).get('ocr_analysis_regions', []) or []))
            temp[i].append(copy.deepcopy(payload))
            affected.append(i)
        if self.idx not in temp:
            temp[self.idx] = copy.deepcopy(self.data.get(self.idx, {}).get('ocr_analysis_regions', []) or [])
            temp[self.idx].append(copy.deepcopy(payload))
            affected.append(self.idx)
        hist = getattr(self, "ocr_region_temp_history", None)
        if not isinstance(hist, list):
            self.ocr_region_temp_history = []
            hist = self.ocr_region_temp_history
        hist.append(affected)
        try:
            self.push_ocr_region_temp_command(before_temp_state, self._copy_ocr_region_temp_state(), reason="OCR 분석 영역 임시 추가")
        except Exception:
            pass
        self.refresh_ocr_region_overlay()
        self.update_undo_redo_buttons()
        self.log(f"➕ OCR 분석 영역 추가: {self._ocr_region_indices_label(targets)}")

    def finish_ocr_analysis_region_selection(self):
        targets = list(getattr(self, "ocr_region_target_indices", []) or [])
        temp = getattr(self, "ocr_region_temp_by_page", None)
        if not isinstance(temp, dict):
            self.set_tool(None)
            return

        box = QMessageBox(self)
        box.setWindowTitle(self.tr_ui("OCR 분석 영역 지정 종료"))
        box.setText(self.tr_ui("OCR 분석 영역 지정을 종료할까요?"))
        box.setInformativeText(self.tr_ui("아직 저장하지 않은 변경사항이 있을 수 있습니다. 종료하면 저장 여부를 한 번 더 선택할 수 있습니다."))
        exit_btn = box.addButton(self.tr_ui("종료하기"), QMessageBox.ButtonRole.AcceptRole)
        keep_btn = box.addButton(self.tr_ui("계속 지정하기"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep_btn)
        box.exec()
        if box.clickedButton() is not exit_btn:
            return

        save_box = QMessageBox(self)
        save_box.setWindowTitle(self.tr_ui("OCR 분석 영역 저장"))
        save_box.setText(self.tr_ui("변경한 OCR 분석 영역을 저장할까요?"))
        save_box.setInformativeText(self.tr_ui("저장하지 않고 종료하면 이번에 지정한 OCR 분석 영역은 적용되지 않습니다."))
        save_btn = save_box.addButton(self.tr_ui("저장하고 종료"), QMessageBox.ButtonRole.AcceptRole)
        discard_btn = save_box.addButton(self.tr_ui("저장하지 않고 종료"), QMessageBox.ButtonRole.DestructiveRole)
        save_box.setDefaultButton(save_btn)
        save_box.exec()

        if save_box.clickedButton() is save_btn:
            try:
                self.commit_current_page_ui_to_data(include_mask=False)
            except Exception:
                pass
            before_regions = {}
            after_regions = {}
            for i in targets:
                if i in self.data:
                    before_regions[i] = copy.deepcopy(self.data.get(i, {}).get('ocr_analysis_regions', []) or [])
                    after_regions[i] = copy.deepcopy(temp.get(i, []) or [])
                    self.data[i]['ocr_analysis_regions'] = copy.deepcopy(after_regions[i])
            try:
                self.push_ocr_analysis_region_command(
                    before_regions,
                    after_regions,
                    reason="OCR 분석 범위 지정",
                    page_indices=targets,
                )
            except Exception:
                pass
            self.auto_save_project()
            self.log(f"💾 OCR 분석 영역 저장: {self._ocr_region_indices_label(targets)}")
        else:
            self.log("↩️ OCR 분석 영역 변경사항 폐기")

        self.ocr_region_temp_by_page = None
        self.ocr_region_temp_history = []
        self.ocr_region_target_indices = []
        self.ocr_region_target_label = ""
        self.set_tool(None)
        self.refresh_ocr_region_overlay()

    def clear_current_ocr_analysis_regions(self):
        if not getattr(self, "paths", None):
            return
        msg = self.tr_ui("현재 페이지의 OCR 분석 영역만 지울까요?\n\n다른 페이지의 OCR 분석 영역은 유지됩니다.")
        if QMessageBox.question(self, self.tr_ui("현재 페이지 OCR 분석 범위 해제"), msg) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass
        curr = self.data.get(self.idx)
        before_regions = {self.idx: copy.deepcopy(curr.get('ocr_analysis_regions', []) or [])} if isinstance(curr, dict) else {}
        after_regions = {self.idx: []} if isinstance(curr, dict) else {}
        if isinstance(curr, dict):
            curr['ocr_analysis_regions'] = []
            try:
                self.push_ocr_analysis_region_command(
                    before_regions,
                    after_regions,
                    reason="현재 페이지 OCR 분석 범위 해제",
                    page_indices=[self.idx],
                )
            except Exception:
                pass
        temp = getattr(self, "ocr_region_temp_by_page", None)
        if isinstance(temp, dict):
            temp[self.idx] = []
            self.ocr_region_temp_history = []
        self.auto_save_project()
        self.refresh_ocr_region_overlay()
        try:
            QApplication.processEvents()
        except Exception:
            pass
        self.log("🧹 현재 페이지 OCR 분석 범위를 해제했습니다. 다른 페이지의 영역은 유지됩니다.")

    def clear_all_ocr_analysis_regions(self):
        if not getattr(self, "paths", None):
            return
        msg = self.tr_ui("모든 페이지의 OCR 분석 영역을 지울까요?\n\n지우면 OCR은 다시 전체 화면을 분석합니다.")
        if QMessageBox.question(self, self.tr_ui("OCR 분석 범위 해제"), msg) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass
        before_regions = {}
        after_regions = {}
        for page_idx, curr in list(self.data.items()):
            if isinstance(curr, dict):
                before_regions[page_idx] = copy.deepcopy(curr.get('ocr_analysis_regions', []) or [])
                after_regions[page_idx] = []
                curr['ocr_analysis_regions'] = []
        try:
            self.push_ocr_analysis_region_command(
                before_regions,
                after_regions,
                reason="OCR 분석 범위 해제",
                page_indices=list(before_regions.keys()),
            )
        except Exception:
            pass
        temp = getattr(self, "ocr_region_temp_by_page", None)
        if isinstance(temp, dict):
            for key in list(temp.keys()):
                temp[key] = []
            self.ocr_region_temp_history = []
        self.auto_save_project()
        try:
            self.view.clear_ocr_region_overlay()
        except Exception:
            pass
        self.refresh_ocr_region_overlay()
        try:
            QApplication.processEvents()
        except Exception:
            pass
        self.log("🧹 OCR 분석 범위를 해제했습니다. 이제 전체 화면을 분석합니다.")

    def undo_last_ocr_analysis_region_temp(self):
        temp = getattr(self, "ocr_region_temp_by_page", None)
        hist = getattr(self, "ocr_region_temp_history", None)
        if not isinstance(temp, dict) or not hist:
            return False
        affected = hist.pop()
        changed = False
        for i in affected or []:
            try:
                if i in temp and temp[i]:
                    temp[i].pop()
                    changed = True
            except Exception:
                pass
        if changed:
            self.refresh_ocr_region_overlay()
            self.update_undo_redo_buttons()
            self.log("↩️ OCR 분석 영역 1개 취소")
        return changed

    def _indices_have_ocr_analysis_regions(self, indices):
        for i in indices or []:
            try:
                curr = self.data.get(int(i), {}) if hasattr(self, "data") else {}
                if isinstance(curr, dict) and curr.get('ocr_analysis_regions'):
                    return True
            except Exception:
                continue
        return False

    def confirm_ocr_analysis_regions_before_run(self, indices):
        if not self._indices_have_ocr_analysis_regions(indices):
            return True
        msg = self.tr_ui("지정된 OCR 분석 영역이 있습니다. 지정된 영역만 분석할까요?")
        detail = self.tr_ui("아니오를 누르면 분석을 취소합니다. 전체 화면을 분석하려면 먼저 OCR 분석 범위 지정을 해제해 주세요.")
        box = QMessageBox(self)
        box.setWindowTitle(self.tr_ui("OCR 분석 영역 확인"))
        box.setText(msg)
        box.setInformativeText(detail)
        yes_btn = box.addButton(self.tr_ui("실행하기"), QMessageBox.ButtonRole.AcceptRole)
        no_btn = box.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(yes_btn)
        box.exec()
        return box.clickedButton() is yes_btn

    def _rect_edges_from_item(self, item):
        try:
            x, y, w, h = [float(v) for v in (item.get('rect') or [0, 0, 0, 0])[:4]]
            return x, y, x + max(0.0, w), y + max(0.0, h)
        except Exception:
            return 0.0, 0.0, 0.0, 0.0

    def _rect_overlap_area_for_items(self, a, b):
        ax1, ay1, ax2, ay2 = self._rect_edges_from_item(a)
        bx1, by1, bx2, by2 = self._rect_edges_from_item(b)
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        return (ix2 - ix1) * (iy2 - iy1)

    def _rect_center_inside_mask(self, item, mask):
        if mask is None:
            return False
        try:
            h, w = mask.shape[:2]
            x1, y1, x2, y2 = self._rect_edges_from_item(item)
            cx = max(0, min(w - 1, int(round((x1 + x2) / 2))))
            cy = max(0, min(h - 1, int(round((y1 + y2) / 2))))
            if mask[cy, cx] > 0:
                return True
            rx1 = max(0, min(w - 1, int(round(x1))))
            ry1 = max(0, min(h - 1, int(round(y1))))
            rx2 = max(0, min(w, int(round(x2))))
            ry2 = max(0, min(h, int(round(y2))))
            if rx2 <= rx1 or ry2 <= ry1:
                return False
            crop = mask[ry1:ry2, rx1:rx2]
            return bool(crop.size and cv2.countNonZero(crop) > 0)
        except Exception:
            return False

    def _merge_mask_by_ocr_regions(self, old_mask, new_mask, region_mask):
        if region_mask is None:
            return new_mask
        if isinstance(new_mask, np.ndarray):
            base_shape = new_mask.shape[:2]
        elif isinstance(old_mask, np.ndarray):
            base_shape = old_mask.shape[:2]
        else:
            return new_mask
        if not isinstance(old_mask, np.ndarray):
            old = np.zeros_like(new_mask) if isinstance(new_mask, np.ndarray) else np.zeros(base_shape, dtype=np.uint8)
        else:
            old = old_mask.copy()
        if old.shape[:2] != base_shape:
            old = cv2.resize(old, (base_shape[1], base_shape[0]), interpolation=cv2.INTER_NEAREST)
        if not isinstance(new_mask, np.ndarray):
            new = np.zeros_like(old)
        else:
            new = new_mask.copy()
            if new.shape[:2] != base_shape:
                new = cv2.resize(new, (base_shape[1], base_shape[0]), interpolation=cv2.INTER_NEAREST)
        rm = region_mask
        if rm.shape[:2] != base_shape:
            rm = cv2.resize(rm, (base_shape[1], base_shape[0]), interpolation=cv2.INTER_NEAREST)
        out = old.copy()
        sel = rm > 0
        out[sel] = new[sel]
        return out

    def merge_ocr_analysis_region_results(self, page_idx, new_data, new_mask_merge, new_mask_inpaint, ori_img=None):
        curr = self.data.get(page_idx, {}) if hasattr(self, "data") else {}
        regions = copy.deepcopy(curr.get('ocr_analysis_regions', []) or []) if isinstance(curr, dict) else []
        old_data = copy.deepcopy(curr.get('data', []) or []) if isinstance(curr, dict) else []
        if not regions or not old_data:
            return new_data, new_mask_merge, new_mask_inpaint
        try:
            if isinstance(ori_img, np.ndarray):
                h, w = ori_img.shape[:2]
            elif isinstance(new_mask_merge, np.ndarray):
                h, w = new_mask_merge.shape[:2]
            elif isinstance(curr.get('ori'), np.ndarray):
                h, w = curr.get('ori').shape[:2]
            else:
                return new_data, new_mask_merge, new_mask_inpaint
            region_mask = self.engine._ocr_regions_to_mask(regions, w, h)
        except Exception:
            region_mask = None
        if region_mask is None:
            return new_data, new_mask_merge, new_mask_inpaint

        new_items = copy.deepcopy(new_data or [])
        old_in_region = [idx for idx, item in enumerate(old_data) if self._rect_center_inside_mask(item, region_mask)]
        new_in_region = [idx for idx, item in enumerate(new_items) if self._rect_center_inside_mask(item, region_mask)]
        if not old_in_region:
            # 기존 번호가 없는 새 영역이면 새 OCR 결과를 뒤에 붙인다.
            merged = copy.deepcopy(old_data)
            max_id = 0
            for item in merged:
                try:
                    max_id = max(max_id, int(item.get('id') or 0))
                except Exception:
                    pass
            for ni in new_in_region:
                max_id += 1
                item = copy.deepcopy(new_items[ni])
                item['id'] = max_id
                merged.append(item)
            mm = self._merge_mask_by_ocr_regions(curr.get('mask_merge'), new_mask_merge, region_mask)
            mi = self._merge_mask_by_ocr_regions(curr.get('mask_inpaint'), new_mask_inpaint, region_mask)
            return merged, mm, mi

        used_new = set()
        merged = []
        for idx, old_item in enumerate(old_data):
            if idx not in old_in_region:
                merged.append(copy.deepcopy(old_item))
                continue
            best_idx = None
            best_score = 0.0
            for ni in new_in_region:
                if ni in used_new:
                    continue
                ni_item = new_items[ni]
                ov = self._rect_overlap_area_for_items(old_item, ni_item)
                ax1, ay1, ax2, ay2 = self._rect_edges_from_item(old_item)
                bx1, by1, bx2, by2 = self._rect_edges_from_item(ni_item)
                old_area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
                new_area = max(1.0, (bx2 - bx1) * (by2 - by1))
                score = ov / max(1.0, min(old_area, new_area))
                if score > best_score:
                    best_score = score
                    best_idx = ni
            if best_idx is not None and best_score >= 0.08:
                used_new.add(best_idx)
                updated = copy.deepcopy(old_item)
                old_id = old_item.get('id')
                old_trans = old_item.get('translated_text')
                for k, v in copy.deepcopy(new_items[best_idx]).items():
                    if k in ('id', 'translated_text'):
                        continue
                    updated[k] = v
                updated['id'] = old_id
                if old_trans is not None:
                    updated['translated_text'] = old_trans
                merged.append(updated)
            else:
                # 재OCR 결과가 없더라도 기존 번호/라인은 삭제하지 않는다.
                merged.append(copy.deepcopy(old_item))

        max_id = 0
        for item in merged:
            try:
                max_id = max(max_id, int(item.get('id') or 0))
            except Exception:
                pass
        for ni in new_in_region:
            if ni in used_new:
                continue
            max_id += 1
            item = copy.deepcopy(new_items[ni])
            item['id'] = max_id
            merged.append(item)

        mm = self._merge_mask_by_ocr_regions(curr.get('mask_merge'), new_mask_merge, region_mask)
        mi = self._merge_mask_by_ocr_regions(curr.get('mask_inpaint'), new_mask_inpaint, region_mask)
        self.log("🔁 지정 영역 OCR 결과를 기존 분석 데이터에 병합했습니다.")
        return merged, mm, mi

    def _ocr_provider_options(self):
        """Return the same OCR providers that are available in API Settings.

        Lite and Local share this dialog, so Local-only OCR providers must not
        appear in Lite Quick OCR.
        """
        options = [
            ("CLOVA OCR", "clova"),
            ("Google Vision OCR", "google_vision"),
        ]
        try:
            from ysb.editions.current import is_local_edition
            if is_local_edition():
                options.extend([
                    ("LOCAL Paddle OCR", "local_paddle_ocr"),
                    ("LOCAL Manga OCR", "local_manga_ocr"),
                ])
        except Exception:
            pass
        return options

    def _quick_ocr_provider_values(self):
        return [value for _label, value in self._ocr_provider_options()]

    def _ocr_language_options_for_quick(self, provider):
        provider = str(provider or "clova")
        if provider == "google_vision":
            return [("영어", "en"), ("일본어", "ja"), ("중국어", "zh"), ("한국어", "ko")]
        if provider == "local_paddle_ocr":
            return [("일본어", "ja"), ("영어", "en"), ("한국어", "ko"), ("중국어", "zh")]
        if provider == "local_manga_ocr":
            return [("일본어", "ja")]
        return [("일본어", "ja"), ("중국어", "zh"), ("한국어", "ko")]

    def _quick_ocr_provider_from_options(self):
        candidates = [
            str((getattr(self, "app_options", {}) or {}).get("quick_ocr_provider") or ""),
            str(getattr(self.api_settings, "selected_ocr_provider", "clova") or "clova"),
            "clova",
        ]
        allowed = set(self._quick_ocr_provider_values())
        for provider in candidates:
            if provider in allowed:
                return provider
        values = self._quick_ocr_provider_values()
        return values[0] if values else "clova"

    def _quick_ocr_language_from_options(self):
        return str((getattr(self, "app_options", {}) or {}).get("quick_ocr_language") or (self._current_ocr_language_value() if hasattr(self, "_current_ocr_language_value") else "ja") or "ja")

    def _quick_ocr_shortcut_conflict_label(self, seq_text):
        seq_text = str(seq_text or "").strip()
        if not seq_text:
            return ""
        try:
            target_seq = key_sequence_from_text(seq_text)
        except Exception:
            return ""
        for key, value in list(getattr(self.shortcut_settings, "shortcuts", {}).items()):
            if key == "quick_ocr_execute":
                continue
            if not getattr(self.shortcut_settings, "enabled", {}).get(key, True):
                continue
            try:
                other_seq = key_sequence_from_text(str(value or ""))
                if other_seq and not other_seq.isEmpty() and other_seq.matches(target_seq) == QKeySequence.SequenceMatch.ExactMatch:
                    return self.standard_shortcut_label(key) if hasattr(self, "standard_shortcut_label") else str(key)
            except Exception:
                continue
        for macro in getattr(self.shortcut_settings, "macros", []) or []:
            if not macro.get("enabled", True):
                continue
            try:
                other_seq = key_sequence_from_text(str(macro.get("shortcut", "") or ""))
                if other_seq and not other_seq.isEmpty() and other_seq.matches(target_seq) == QKeySequence.SequenceMatch.ExactMatch:
                    return str(macro.get("name") or "매크로")
            except Exception:
                continue
        return ""

    def open_quick_ocr_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("빠른 OCR"))
        dlg.resize(660, 430)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("빠른 OCR"), dlg)
        title.setObjectName("SettingsTitle")
        root.addWidget(title)

        desc = QLabel(self.tr_ui("빠른 OCR은 지정된 단축키를 사용할 때만 동작합니다. Ctrl+J는 이 설정창을 여는 단축키입니다."), dlg)
        desc.setObjectName("SettingsDescription")
        desc.setWordWrap(True)
        root.addWidget(desc)

        form_box = QFrame(dlg)
        form_box.setObjectName("SettingsItem")
        form_layout = QVBoxLayout(form_box)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(12)

        def add_setting_row(title_text, description_text, editor):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)
            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)
            item_title = QLabel(self.tr_ui(title_text), dlg)
            item_title.setObjectName("SettingsItemTitle")
            item_desc = QLabel(self.tr_ui(description_text), dlg)
            item_desc.setObjectName("SettingsDescription")
            item_desc.setWordWrap(True)
            text_box.addWidget(item_title)
            text_box.addWidget(item_desc)
            row.addLayout(text_box, 1)
            row.addWidget(editor, 0)
            form_layout.addLayout(row)

        cb_provider = QComboBox(dlg)
        for label, value in self._ocr_provider_options():
            cb_provider.addItem(self.tr_ui(label), value)
        self.set_combo_current_data(cb_provider, self._quick_ocr_provider_from_options())

        cb_lang = QComboBox(dlg)

        def reload_langs():
            provider = cb_provider.currentData() or "clova"
            old = cb_lang.currentData()
            cb_lang.blockSignals(True)
            cb_lang.clear()
            for label, value in self._ocr_language_options_for_quick(provider):
                cb_lang.addItem(self.tr_ui(label), value)
            self.set_combo_current_data(cb_lang, old or self._quick_ocr_language_from_options())
            cb_lang.blockSignals(False)

        cb_provider.currentIndexChanged.connect(lambda *_: reload_langs())
        reload_langs()

        add_setting_row(
            "OCR 모델",
            "빠른 OCR 실행에 사용할 OCR 모델을 선택합니다.",
            cb_provider,
        )
        add_setting_row(
            "언어",
            "빠른 OCR 실행에 사용할 인식 언어를 선택합니다.",
            cb_lang,
        )

        seq_widget = QWidget(dlg)
        seq_row = QHBoxLayout(seq_widget)
        seq_row.setContentsMargins(0, 0, 0, 0)
        seq_row.setSpacing(8)
        seq_edit = ConfirmingKeySequenceEdit(dlg)
        seq_edit.setMinimumWidth(170)
        try:
            seq_edit.setKeySequence(self.shortcut_settings.seq("quick_ocr_execute"))
        except Exception:
            seq_edit.setKeySequence(QKeySequence(""))
        btn_clear = QPushButton(self.tr_ui("비우기"), dlg)
        btn_clear.clicked.connect(seq_edit.clear)
        seq_row.addWidget(seq_edit, 1)
        seq_row.addWidget(btn_clear, 0)
        add_setting_row(
            "빠른 OCR 실행 단축키",
            "이 단축키를 누르면 바로 드래그 선택 모드로 들어갑니다. 빠른 OCR은 이 단축키로만 실제 실행됩니다.",
            seq_widget,
        )

        shortcut_row = QHBoxLayout()
        opener_seq = self.shortcut_settings.seq("work_quick_ocr").toString(QKeySequence.SequenceFormat.NativeText)
        shortcut_row.addWidget(QLabel(f"{self.tr_ui('설정창 단축키')}: {opener_seq or '-'}", dlg))
        shortcut_row.addStretch(1)
        shortcut_btn = QPushButton(self.tr_ui("단축키 관리 열기"), dlg)
        shortcut_btn.clicked.connect(lambda checked=False: self.open_shortcut_settings_dialog())
        shortcut_row.addWidget(shortcut_btn)
        form_layout.addLayout(shortcut_row)

        root.addWidget(form_box)
        root.addStretch(1)

        def apply_quick_ocr_settings():
            try:
                clean_seq = sequence_without_confirm_keys(seq_edit.keySequence())
                clean_text = key_sequence_to_portable(clean_seq).strip()
                current_text = key_sequence_to_portable(seq_edit.keySequence()).strip()
                if clean_text != current_text:
                    seq_edit.blockSignals(True)
                    try:
                        seq_edit.setKeySequence(clean_seq)
                    finally:
                        seq_edit.blockSignals(False)
                seq_text = clean_text
            except Exception:
                seq_text = key_sequence_to_portable(seq_edit.keySequence()).strip()
            conflict = self._quick_ocr_shortcut_conflict_label(seq_text)
            if conflict:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("단축키 충돌"),
                    self.tr_ui("이미 사용 중인 단축키입니다.") + f"\n\n{conflict}: {seq_text}",
                )
                return False

            self.app_options["quick_ocr_provider"] = cb_provider.currentData() or "clova"
            self.app_options["quick_ocr_language"] = cb_lang.currentData() or "ja"
            self.save_app_options_cache()

            try:
                self.shortcut_settings.enabled["quick_ocr_execute"] = bool(seq_text)
                self.shortcut_settings.shortcuts["quick_ocr_execute"] = seq_text
                ShortcutSettingsStore.save(self.shortcut_settings)
                self.shortcut_label_map = shortcut_label_map()
                self.apply_shortcuts()
            except Exception as e:
                QMessageBox.warning(dlg, self.tr_ui("단축키 저장 오류"), str(e))
                return False

            self.log(f"🔎 빠른 OCR 설정 저장: {cb_provider.currentText()} / {cb_lang.currentText()} / {seq_text or '단축키 없음'}")
            return True

        def on_ok():
            if apply_quick_ocr_settings():
                dlg.accept()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        root.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.show_ok_notice("빠른 OCR 설정 저장 완료", "빠른 OCR 설정이 저장되었습니다.")

    def _quick_ocr_popup_style(self):
        if str(getattr(self, "ui_theme", "dark") or "dark").lower() == "light":
            return (
                "QLabel { background:#ffffff; color:#111827; "
                "border:1px solid #D1C9CE; border-radius:0px; "
                "padding:6px 8px; font-size:12px; }"
            )
        return (
            "QLabel { background:#242329; color:#ffffff; "
            "border:1px solid #555056; border-radius:0px; "
            "padding:6px 8px; font-size:12px; }"
        )

    def show_quick_ocr_result_popup(self, text):
        text = str(text or "").strip()
        if not text:
            return
        try:
            popup = getattr(self, "quick_ocr_result_popup", None)
            if popup is None:
                popup = QLabel(self)
                popup.setObjectName("quickOcrResultPopup")
                popup.setWordWrap(True)
                popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                popup.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
                popup.hide()
                self.quick_ocr_result_popup = popup
            popup.setStyleSheet(self._quick_ocr_popup_style())
            popup.setText(text)
            popup.setMaximumWidth(520)
            popup.adjustSize()
            local = self.mapFromGlobal(QCursor.pos() + QPoint(16, 18))
            x = max(4, min(local.x(), max(4, self.width() - popup.width() - 4)))
            y = max(4, min(local.y(), max(4, self.height() - popup.height() - 4)))
            popup.move(x, y)
            popup.show()
            popup.raise_()
            try:
                self.audit_top_level_widgets("quick_ocr_popup", throttle_ms=1000)
            except Exception:
                pass
        except Exception:
            # 빠른 OCR 결과 표시는 보조 UI라서 실패해도 OCR 자체는 막지 않는다.
            pass

    def hide_quick_ocr_result_popup(self):
        try:
            popup = getattr(self, "quick_ocr_result_popup", None)
            if popup is not None:
                popup.hide()
        except Exception:
            pass

    def start_quick_ocr_selection(self):
        if not getattr(self, "paths", None):
            QMessageBox.information(self, self.tr_ui("이미지 없음"), self.tr_ui("먼저 프로젝트에 이미지를 불러와 주세요."))
            return
        if not self.ensure_engine_ready():
            return
        self.quick_ocr_provider = self._quick_ocr_provider_from_options()
        self.quick_ocr_language = self._quick_ocr_language_from_options()
        self.quick_ocr_latest_text = ""
        self.quick_ocr_drag_active = False
        self.set_tool('quick_ocr')
        self.log("🔎 빠른 OCR: 마우스를 누른 채 영역을 고정하면 OCR을 실행합니다.")

    def begin_quick_ocr_drag(self):
        self.quick_ocr_drag_active = True
        self.quick_ocr_latest_text = ""
        self.quick_ocr_worker_busy = False
        self.quick_ocr_active_request_id = None
        self.hide_quick_ocr_result_popup()

    def run_quick_ocr_region_live(self, rect_norm, request_id=None, image_path=None, source="main"):
        if not rect_norm or not getattr(self, "quick_ocr_drag_active", False):
            return
        if getattr(self, "quick_ocr_worker_busy", False):
            return
        target_idx = self.idx
        provider = getattr(self, "quick_ocr_provider", None) or self._quick_ocr_provider_from_options()
        language = getattr(self, "quick_ocr_language", None) or self._quick_ocr_language_from_options()
        self.quick_ocr_worker_busy = True
        self.quick_ocr_active_request_id = request_id
        self.quick_ocr_active_source = source or "main"
        self.log("🔎 빠른 OCR 실행 중...")
        input_path = image_path or self.get_inpainting_input_path(target_idx)
        self.quick_ocr_worker = QuickOCRWorker(
            self.engine,
            input_path,
            copy.deepcopy(rect_norm),
            provider=provider,
            language=language,
        )
        self.quick_ocr_worker.log.connect(self.log)
        self.quick_ocr_worker.finished.connect(lambda text, error=None, rid=request_id, src=source: self.on_quick_ocr_finished(text, error, rid, src))
        self.quick_ocr_worker.start()

    def run_quick_ocr_region(self, rect_norm):
        # 구버전 호출 호환용. 빠른 OCR은 이제 마우스를 누른 상태에서만 실행된다.
        self.run_quick_ocr_region_live(rect_norm, request_id=None)

    def on_quick_ocr_finished(self, text, error=None, request_id=None, source="main"):
        self.quick_ocr_worker_busy = False
        if error:
            if getattr(self, "quick_ocr_drag_active", False):
                QMessageBox.warning(self, self.tr_ui("빠른 OCR 오류"), str(error))
            return
        # 사용자가 아직 마우스를 누르고 있고, OCR 요청 이후 영역이 바뀌지 않은 경우에만 표시한다.
        try:
            if not getattr(self, "quick_ocr_drag_active", False):
                return
            if str(source or "main") == "source_compare":
                current_revision = getattr(self, "source_compare_quick_ocr_revision", None)
                current_rect = copy.deepcopy(getattr(self, "source_compare_quick_ocr_current_rect_norm", None))
            else:
                current_revision = getattr(self.view, "quick_ocr_revision", None)
                current_rect = copy.deepcopy(getattr(self.view, "quick_ocr_current_rect_norm", None))
            if request_id is not None and current_revision != request_id:
                # OCR 중에 사용자가 영역을 다시 움직였으면 오래된 결과는 버리고,
                # 현재 유지 중인 영역으로 한 번 더 실행을 시도한다.
                if current_rect:
                    QTimer.singleShot(0, lambda rn=current_rect, rid=current_revision, src=source: self.run_quick_ocr_region_live(rn, request_id=rid, source=src))
                return
        except Exception:
            return
        text = str(text or "").strip()
        self.quick_ocr_latest_text = text
        if text:
            # QToolTip은 시간이 지나면 자동으로 사라지므로 사용하지 않는다.
            # 빠른 OCR 결과는 마우스를 떼기 전까지 유지되는 전용 팝업으로 표시한다.
            self.show_quick_ocr_result_popup(text)
            self.log(f"🔎 빠른 OCR 결과: {text}")
        else:
            self.show_quick_ocr_result_popup(self.tr_ui("인식된 텍스트가 없습니다."))
            self.log("⚠️ 빠른 OCR에서 인식된 텍스트가 없습니다.")

    def finish_quick_ocr_drag(self):
        text = str(getattr(self, "quick_ocr_latest_text", "") or "").strip()
        self.quick_ocr_drag_active = False
        self.quick_ocr_active_request_id = None
        if text:
            QApplication.clipboard().setText(text)
            self.log(f"📋 빠른 OCR 결과를 클립보드에 복사했습니다: {text}")
        self.hide_quick_ocr_result_popup()
        try:
            QToolTip.hideText()
        except Exception:
            pass
        self.set_tool(None)

    def clear_source_compare_quick_ocr_preview(self):
        try:
            item = getattr(self, "source_compare_quick_ocr_preview_item", None)
            if item is not None and hasattr(self, "source_compare_scene"):
                self.source_compare_scene.removeItem(item)
        except Exception:
            pass
        self.source_compare_quick_ocr_preview_item = None

    def _source_compare_norm_rect_from_scene(self, rect):
        try:
            scene_rect = self.source_compare_scene.sceneRect()
            w = float(scene_rect.width())
            h = float(scene_rect.height())
            if w <= 0 or h <= 0:
                return None
            left = float(scene_rect.left())
            top = float(scene_rect.top())
            x1 = max(left, min(left + w, float(rect.left())))
            y1 = max(top, min(top + h, float(rect.top())))
            x2 = max(left, min(left + w, float(rect.right())))
            y2 = max(top, min(top + h, float(rect.bottom())))
            if x2 <= x1 or y2 <= y1:
                return None
            return [(x1 - left) / w, (y1 - top) / h, (x2 - left) / w, (y2 - top) / h]
        except Exception:
            return None

    def source_compare_quick_ocr_rect_payload(self, end_pos):
        if getattr(self, "source_compare_quick_ocr_start", None) is None:
            return None
        try:
            rect = QRectF(self.source_compare_quick_ocr_start, end_pos).normalized()
            return self._source_compare_norm_rect_from_scene(rect)
        except Exception:
            return None

    def draw_source_compare_quick_ocr_preview(self, end_pos):
        self.clear_source_compare_quick_ocr_preview()
        try:
            start = getattr(self, "source_compare_quick_ocr_start", None)
            if start is None or not hasattr(self, "source_compare_scene"):
                return
            rect = QRectF(start, end_pos).normalized()
            if rect.width() < 2 or rect.height() < 2:
                return
            pen = QPen(QColor(70, 135, 220, 220), 2)
            brush = QBrush(QColor(80, 160, 255, 70))
            item = self.source_compare_scene.addRect(rect, pen, brush)
            item.setZValue(87)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.source_compare_quick_ocr_preview_item = item
        except Exception:
            pass

    def _schedule_source_compare_quick_ocr_hold_check(self, end_pos):
        rect_norm = self.source_compare_quick_ocr_rect_payload(end_pos)
        old_rect = copy.deepcopy(getattr(self, "source_compare_quick_ocr_current_rect_norm", None))
        if not rect_norm:
            if old_rect is not None:
                self.source_compare_quick_ocr_current_rect_norm = None
                self.source_compare_quick_ocr_revision = int(getattr(self, "source_compare_quick_ocr_revision", 0) or 0) + 1
            return
        changed = True
        try:
            changed = self.view._quick_ocr_rect_changed_significantly(old_rect, rect_norm)
        except Exception:
            changed = old_rect != rect_norm
        if old_rect is not None and not changed:
            return
        self.source_compare_quick_ocr_current_rect_norm = copy.deepcopy(rect_norm)
        self.source_compare_quick_ocr_revision = int(getattr(self, "source_compare_quick_ocr_revision", 0) or 0) + 1
        try:
            latest = str(getattr(self, "quick_ocr_latest_text", "") or "").strip()
            if latest:
                self.show_quick_ocr_result_popup(latest)
        except Exception:
            pass
        try:
            timer = getattr(self, "source_compare_quick_ocr_hold_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._trigger_source_compare_quick_ocr_if_still_holding)
                self.source_compare_quick_ocr_hold_timer = timer
            timer.start(200)
        except Exception:
            pass

    def _trigger_source_compare_quick_ocr_if_still_holding(self):
        if getattr(getattr(self, "view", None), "draw_mode", None) != "quick_ocr":
            return
        if not getattr(self, "source_compare_quick_ocr_drawing", False):
            return
        rect_norm = copy.deepcopy(getattr(self, "source_compare_quick_ocr_current_rect_norm", None))
        if not rect_norm:
            return
        revision = int(getattr(self, "source_compare_quick_ocr_revision", 0) or 0)
        if revision == int(getattr(self, "source_compare_quick_ocr_last_requested_revision", -1) or -1):
            return
        self.source_compare_quick_ocr_last_requested_revision = revision
        self.run_quick_ocr_region_live(rect_norm, request_id=revision, source="source_compare")

    def handle_source_compare_quick_ocr_event(self, event):
        try:
            if getattr(getattr(self, "view", None), "draw_mode", None) != "quick_ocr":
                return False
            if not self.source_compare_is_visible():
                return False
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.source_compare_quick_ocr_drawing = True
                self.source_compare_quick_ocr_start = self.source_compare_view.mapToScene(event.pos())
                self.source_compare_quick_ocr_current_rect_norm = None
                self.source_compare_quick_ocr_revision = int(getattr(self, "source_compare_quick_ocr_revision", 0) or 0) + 1
                self.source_compare_quick_ocr_last_requested_revision = -1
                try:
                    timer = getattr(self, "source_compare_quick_ocr_hold_timer", None)
                    if timer is not None:
                        timer.stop()
                except Exception:
                    pass
                self.quick_ocr_active_source = "source_compare"
                self.begin_quick_ocr_drag()
                self.draw_source_compare_quick_ocr_preview(self.source_compare_quick_ocr_start)
                return True
            if et == QEvent.Type.MouseMove and getattr(self, "source_compare_quick_ocr_drawing", False):
                now = self.source_compare_view.mapToScene(event.pos())
                self.draw_source_compare_quick_ocr_preview(now)
                self._schedule_source_compare_quick_ocr_hold_check(now)
                return True
            if et == QEvent.Type.MouseButtonRelease and getattr(self, "source_compare_quick_ocr_drawing", False):
                self.source_compare_quick_ocr_drawing = False
                self.source_compare_quick_ocr_start = None
                self.source_compare_quick_ocr_current_rect_norm = None
                try:
                    timer = getattr(self, "source_compare_quick_ocr_hold_timer", None)
                    if timer is not None:
                        timer.stop()
                except Exception:
                    pass
                self.clear_source_compare_quick_ocr_preview()
                self.finish_quick_ocr_drag()
                return True
        except Exception:
            return False
        return False

    def reset_mode_to_original(self):
        """
        새 프로젝트/프로젝트 열기 시 이전 작업 탭 상태가 섞이지 않도록
        원본 탭으로 강제 이동한다.
        """
        self.last_mode = 0
        self.cb_mode.blockSignals(True)
        try:
            self.cb_mode.setCurrentIndex(0)
        finally:
            self.cb_mode.blockSignals(False)

    def cycle_work_tab(self):
        """
        작업 탭을 다음 탭으로 이동한다.
        마지막 탭이면 처음 탭으로 루프한다.
        """
        fw = QApplication.focusWidget()
        if isinstance(fw, (QTextEdit, QLineEdit)):
            return

        if self.cb_mode.count() <= 0:
            return

        next_index = (self.cb_mode.currentIndex() + 1) % self.cb_mode.count()
        self.cb_mode.setCurrentIndex(next_index)

    def load(self):
        try:
            self.audit_boundary_event("LOAD_ENTER", stack=True)
        except Exception:
            pass
        # load/ref_tab/mode_chg 직후 delayed view undo가 실제 편집처럼 dirty를 찍는 것을 막는다.
        try:
            self._suppress_view_dirty_until = __import__("time").time() + 0.9
        except Exception:
            pass
        if not self.paths:
            self.idx = 0
            if hasattr(self, "btn_page"):
                self.btn_page.setText("0 / 0")
            self.refresh_page_tabs()
            try:
                if hasattr(self, "view") and self.view is not None:
                    self.view.set_image(None)
            except Exception:
                pass
            try:
                self.ref_tab()
            except Exception:
                pass
            self.update_page_presence_interlocks()
            self.update_undo_redo_buttons()
            return

        if self.idx < 0:
            self.idx = 0
        if self.idx >= len(self.paths):
            self.idx = len(self.paths) - 1
        try:
            if hasattr(self, "activate_page_workbench"):
                self.activate_page_workbench(self.idx, None, clear_undo_on_page_change=True)
        except Exception:
            pass
        try:
            if not self.sync_page_tab_current_only():
                self.refresh_page_tabs()
        except Exception:
            self.refresh_page_tabs()
        self.update_page_presence_interlocks()
        p = self.paths[self.idx]
        self.btn_page.setText(f"{self.idx + 1} / {len(self.paths)}")

        if self.idx not in self.data:
            self.data[self.idx] = {
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
                'clean_path': None,
                'working_source': None,
                'working_source_path': None,
                'final_paint': None,
                'final_paint_path': None,
                'final_paint_above': None,
                'final_paint_above_path': None,
                'ocr_analysis_regions': [],
            }
        curr_page = self.data[self.idx]
        try:
            self.sync_text_effect_preview_checkbox_for_current_page()
        except Exception:
            try:
                self.text_effect_preview_enabled = True
            except Exception:
                pass
        try:
            current_mode = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else -1
        except Exception:
            current_mode = -1
        try:
            self.ensure_page_runtime_loaded(
                self.idx,
                include_ori=True,
                include_heavy=bool(current_mode == 4 or curr_page.get('use_inpainted_as_source') or curr_page.get('clean_path') or curr_page.get('working_source_path') or curr_page.get('final_paint_path') or curr_page.get('final_paint_above_path')),
                include_masks=bool(current_mode in (2, 3)),
            )
        except Exception:
            if curr_page.get('ori') is None and not curr_page.get('use_inpainted_as_source'):
                curr_page['ori'] = cv2.imdecode(np.fromfile(p, np.uint8), 1)
            try:
                self.touch_page_image_cache(self.idx)
                self.trim_page_image_cache(keep_indices=[self.idx])
            except Exception:
                pass
            if current_mode in (2, 3):
                try:
                    self.ensure_page_masks_loaded(self.idx)
                    self.touch_page_mask_cache(self.idx)
                    self.trim_page_mask_cache(keep_indices=[self.idx])
                except Exception:
                    pass

        self.set_mask_toggle_safely(bool(self.data[self.idx].get('mask_toggle_enabled', self.mask_toggle_enabled)))

        # load() 중 mode_chg()가 실행되면 뷰어에 이전 페이지 마스크가 남아 있을 수 있다.
        # 이때 자동 저장이 끼면 다른 페이지 마스크가 덮이므로 로딩 플래그로 차단한다.
        prev_loading = self.is_page_loading
        self.is_page_loading = True
        try:
            self.ref_tab()
            self.mode_chg(self.cb_mode.currentIndex())
        finally:
            self.is_page_loading = prev_loading
        try:
            self.schedule_progressive_page_load(self.idx)
        except Exception:
            pass

    def is_light_theme(self):
        return str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK).lower() == THEME_LIGHT

    def table_row_color(self, checked):
        # 우측 텍스트 표 행 색상은 테마에 따라 따로 관리한다.
        # 체크 해제 행은 작업 제외/비활성 표시이므로, 파란 음영 대신 Warm Graphite + 아주 약한 와인 톤으로 둔다.
        if self.is_light_theme():
            return QColor("#ffffff") if checked else QColor("#FBF5F6")
        return QColor("#171719") if checked else QColor("#211B1F")

    def table_text_color(self, checked=True):
        if self.is_light_theme():
            return QColor("#202124") if checked else QColor("#6F666D")
        return QColor("#E8E1E6") if checked else QColor("#A99FA5")

    def table_header_color(self):
        return QColor("#F0EAED") if self.is_light_theme() else QColor("#141416")

    def table_header_text_color(self):
        return QColor("#202124") if self.is_light_theme() else QColor("#CBC4C9")

    def table_check_widget_style(self, color):
        if self.is_light_theme():
            return f"QWidget {{ background:{color.name()}; border:none; }} QCheckBox {{ background:transparent; padding:0px; margin:0px; }}"
        return f"QWidget {{ background:{color.name()}; border:none; }} QCheckBox {{ background:transparent; padding:0px; margin:0px; }}"

    def repaint_text_table_theme(self):
        """테마 전환 직후 기존 우측 텍스트 표의 배경/글자색을 다시 칠한다."""
        if not hasattr(self, "tab") or self.tab is None:
            return
        self._table_check_lock = True
        self.tab.blockSignals(True)
        try:
            if self.tab.rowCount() > 0:
                self.clear_native_table_check_item(0)
                self.paint_all_row_header()
            for row in range(1, self.tab.rowCount()):
                self.clear_native_table_check_item(row)
                self.set_table_row_visual(row, self.get_table_check_state(row))
        finally:
            self.tab.blockSignals(False)
            self._table_check_lock = False

    def get_table_checkbox(self, row):
        widget = self.tab.cellWidget(row, 1)
        if widget:
            return widget.findChild(QCheckBox)
        return None

    def get_table_check_state(self, row):
        cb = self.get_table_checkbox(row)
        if cb is not None:
            return cb.isChecked()
        item = self.tab.item(row, 1)
        return item is not None and item.checkState() == Qt.CheckState.Checked

    def clear_native_table_check_item(self, row):
        """체크 표시는 cellWidget(QCheckBox) 하나만 사용한다.
        QTableWidgetItem의 CheckStateRole이 남아 있으면 테마 전환 후 기본 체크박스가
        같이 그려져 체크박스가 2개처럼 보일 수 있으므로 항상 제거한다.
        """
        try:
            item = self.tab.item(row, 1)
            if item is None:
                return
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item.setData(Qt.ItemDataRole.CheckStateRole, None)
        except Exception:
            pass

    def set_table_check_state(self, row, checked):
        cb = self.get_table_checkbox(row)
        if cb is not None:
            cb.blockSignals(True)
            try:
                cb.setChecked(bool(checked))
            finally:
                cb.blockSignals(False)
        self.clear_native_table_check_item(row)

    def make_center_check_widget(self, row, checked):
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        cb = QCheckBox()
        cb.setFixedSize(18, 18)
        cb.setStyleSheet("QCheckBox { background:transparent; padding:0px; margin:0px; } QCheckBox::indicator { width:14px; height:14px; border:1px solid #3A363B; background:#141416; } QCheckBox::indicator:checked { background:#8A4A52; border:1px solid #A85D66; }")
        cb.setChecked(bool(checked))
        cb.stateChanged.connect(lambda state, r=row: self.on_table_check_widget_changed(r, state))
        lay.addStretch()
        lay.addWidget(cb, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addStretch()
        return wrap

    def set_table_row_visual(self, row, checked):
        self.clear_native_table_check_item(row)
        color = self.table_row_color(checked)
        for c in range(self.tab.columnCount()):
            cell = self.tab.item(row, c)
            if cell:
                cell.setBackground(color)
                cell.setForeground(self.table_text_color(checked))
        widget = self.tab.cellWidget(row, 1)
        if widget:
            widget.setStyleSheet(self.table_check_widget_style(color))

    def paint_all_row_header(self):
        self.clear_native_table_check_item(0)
        bg = self.table_header_color()
        fg = self.table_header_text_color()
        for c in range(self.tab.columnCount()):
            cell = self.tab.item(0, c)
            if cell:
                cell.setBackground(bg)
                cell.setForeground(fg)
        widget = self.tab.cellWidget(0, 1)
        if widget:
            widget.setStyleSheet(self.table_check_widget_style(bg))

    def on_table_check_widget_changed(self, row, state):
        if self._table_check_lock:
            return
        self.apply_table_check_state(row, state in (Qt.CheckState.Checked, Qt.CheckState.Checked.value, 2))

    def apply_table_check_state(self, row, is_checked):
        if self.idx not in self.data:
            return

        curr_data = self.data.get(self.idx)
        if not curr_data or 'data' not in curr_data:
            return

        try:
            changed_for_undo = False
            if row == 0:
                changed_for_undo = any(bool(x.get('use_inpaint', True)) != bool(is_checked) for x in curr_data.get('data', []))
            else:
                data_index = row - 1
                if 0 <= data_index < len(curr_data.get('data', [])):
                    changed_for_undo = bool(curr_data['data'][data_index].get('use_inpaint', True)) != bool(is_checked)
            if changed_for_undo:
                self.undo_push_text_line('체크 상태 변경')
        except Exception:
            pass

        self._table_check_lock = True
        self.tab.blockSignals(True)
        try:
            if row == 0:
                for i, data_item in enumerate(curr_data['data']):
                    table_row = i + 1
                    data_item['use_inpaint'] = is_checked
                    self.set_table_check_state(table_row, is_checked)
                    self.set_table_row_visual(table_row, is_checked)
                self.set_table_check_state(0, is_checked)
                self.paint_all_row_header()
            else:
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr_data['data']):
                    return
                curr_data['data'][data_index]['use_inpaint'] = is_checked
                self.set_table_check_state(row, is_checked)
                self.set_table_row_visual(row, is_checked)

                all_checked = len(curr_data['data']) > 0 and all(x.get('use_inpaint', True) for x in curr_data['data'])
                self.set_table_check_state(0, all_checked)
                self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)
            self._table_check_lock = False

        if self.cb_mode.currentIndex() in [1, 2, 3]:
            self.refresh_boxes_only()
        elif self.cb_mode.currentIndex() == 4:
            self.sync_final_text_visibility_only()

        if row == 0:
            self.log((f"🔄 All check states auto-refreshed: {'ON' if is_checked else 'OFF'}" if self.ui_language == LANG_EN else f"🔄 전체 체크 상태 자동 갱신: {'ON' if is_checked else 'OFF'}"))
        else:
            data_index = row - 1
            if 0 <= data_index < len(curr_data['data']):
                self.log((f"🔄 Check state auto-refreshed: ID {curr_data['data'][data_index].get('id')} = {'ON' if is_checked else 'OFF'}" if self.ui_language == LANG_EN else f"🔄 체크 상태 자동 갱신: ID {curr_data['data'][data_index].get('id')} = {'ON' if is_checked else 'OFF'}"))
        try:
            self.schedule_deferred_auto_save_project()
        except Exception:
            self.auto_save_project()

    def ref_tab(self):
        try:
            self.audit_boundary_event("REF_TAB_ENTER", throttle_ms=250, stack=True)
        except Exception:
            pass
        curr = self.data.get(self.idx)
        if not curr:
            self._table_check_lock = True
            self.tab.blockSignals(True)
            try:
                self.tab.clearContents()
                self.tab.setRowCount(1)

                all_id_item = QTableWidgetItem("ALL")
                all_id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tab.setItem(0, 0, all_id_item)

                all_check_item = QTableWidgetItem("")
                all_check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tab.setItem(0, 1, all_check_item)
                self.tab.setCellWidget(0, 1, self.make_center_check_widget(0, False))

                self.tab.setItem(0, 2, QTableWidgetItem(self.tr_ui("전체 선택")))
                self.tab.setItem(0, 3, QTableWidgetItem(""))

                self.paint_all_row_header()
                for c in range(4):
                    item = self.tab.item(0, c)
                    if item:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
            finally:
                self.tab.blockSignals(False)
                self._table_check_lock = False

            self.tab.resizeRowsToContents()
            return

        d = curr.get('data', [])

        self._table_check_lock = True
        self.tab.blockSignals(True)
        try:
            self.tab.clearContents()
            self.tab.setRowCount(len(d) + 1)

            all_checked = len(d) > 0 and all(x.get('use_inpaint', True) for x in d)

            all_id_item = QTableWidgetItem("ALL")
            all_id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tab.setItem(0, 0, all_id_item)

            all_check_item = QTableWidgetItem("")
            all_check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tab.setItem(0, 1, all_check_item)
            self.tab.setCellWidget(0, 1, self.make_center_check_widget(0, all_checked))

            self.tab.setItem(0, 2, QTableWidgetItem(self.tr_ui("전체 선택")))
            self.tab.setItem(0, 3, QTableWidgetItem(""))

            self.paint_all_row_header()
            for c in range(4):
                item = self.tab.item(0, c)
                if item:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

            for i, x in enumerate(d):
                try:
                    self.sanitize_text_data_object_prefixes(x)
                except Exception:
                    pass
                row = i + 1
                is_checked = bool(x.get('use_inpaint', True))

                id_item = QTableWidgetItem(str(x.get('id', i + 1)))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tab.setItem(row, 0, id_item)

                check_item = QTableWidgetItem("")
                check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tab.setItem(row, 1, check_item)
                self.tab.setCellWidget(row, 1, self.make_center_check_widget(row, is_checked))

                if x.get('rasterized_text'):
                    display_text = str(x.get('text', '') or '')
                    display_trans = str(x.get('translated_text', '') or x.get('object_source_text', '') or '')
                    text_item = QTableWidgetItem(display_text)
                    trans_item = QTableWidgetItem("[객체] " + display_trans)
                    text_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    trans_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                else:
                    text_item = QTableWidgetItem(x.get('text', ''))
                    trans_item = QTableWidgetItem(x.get('translated_text', ''))
                text_item.setData(Qt.ItemDataRole.UserRole, str(x.get('text', '') or ''))
                trans_item.setData(Qt.ItemDataRole.UserRole, str(x.get('translated_text', '') or ''))
                self.tab.setItem(row, 2, text_item)
                self.tab.setItem(row, 3, trans_item)

                self.set_table_row_visual(row, is_checked)
        finally:
            self.tab.blockSignals(False)
            self._table_check_lock = False

        self.tab.resizeRowsToContents()

    def anal(self):
        if not self.ensure_engine_ready():
            return
        if not self.paths:
            self.log("⚠️ 이미지가 없습니다. 먼저 프로젝트에 이미지를 불러와 주세요.")
            return
        if not self.check_ocr_api_or_alert():
            return
        if not self.confirm_ocr_analysis_regions_before_run([self.idx]):
            self.log("↩️ OCR 분석 취소")
            return

        self.commit_current_page_ui_to_data(include_mask=False)

        target_idx = self.idx
        self.prepare_text_mask_slots_for_fresh_analysis(target_idx)
        self._long_task_cancel_requested = False
        self.prepare_task_progress_overlay("분석", "OCR/API 분석을 진행 중입니다.", total=0, cancellable=True)
        self.begin_busy_state("분석")
        self.w = AnalysisWorker(
            self.engine,
            self.get_inpainting_input_path(target_idx),
            analysis_regions=copy.deepcopy(self.data.get(target_idx, {}).get('ocr_analysis_regions', []) or []),
        )
        self._active_task_worker = self.w
        self.w.log.connect(lambda msg: self.handle_long_task_message(msg))
        self.w.finished.connect(
            lambda o, d, mm, mi, page_idx=target_idx:
                self.anal_end_for_page(page_idx, o, d, mm, mi, preserve_text_mask=False)
        )
        self.w.start()

    def reanalyze_mask(self):
        mode_idx = self.cb_mode.currentIndex()

        if mode_idx not in [2, 3]:
            return

        m = self.view.get_mask_np()
        if m is None:
            return

        target_idx = self.idx
        curr = self.data[target_idx]

        if mode_idx == 2:
            # 텍스트 마스크는 현재 토글 상태의 저장 슬롯에 저장
            self.set_active_mask(curr, m, mode_idx)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled

            # 워커에 넘길 기존 데이터는 복사본으로 넘긴다.
            # 그래야 재분석 중 기존 페이지 데이터가 직접 흔들리지 않는다.
            existing_data = copy.deepcopy(curr.get('data', []))

            if not self.check_ocr_api_or_alert():
                return

            self.begin_busy_state("텍스트 마스크 재분석")
            self.w = AnalysisWorker(
                self.engine,
                self.get_inpainting_input_path(target_idx),
                m.copy(),
                existing_data
            )
            self.w.log.connect(self.log)
            self.w.finished.connect(
                lambda o, d, mm, mi, page_idx=target_idx:
                    self.anal_end_for_page(page_idx, o, d, mm, mi, preserve_text_mask=True)
            )
            self.w.start()

        elif mode_idx == 3:
            # 페인팅 마스크는 재분석이 아니라 현재 페이지 저장만
            self.set_active_mask(curr, m, mode_idx)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
            self.log((f"💾 Painting mask saved for page {target_idx + 1}" if self.ui_language == LANG_EN else f"💾 {target_idx + 1}페이지 페인팅 마스크 저장됨"))
            self.auto_save_project()

    def prepare_text_mask_slots_for_fresh_analysis(self, page_idx):
        """
        일반 [분석]은 기존 텍스트 마스크를 기준으로 누적하지 않는다.
        재분석은 사용자가 칠한 마스크를 기준으로 보존해야 하지만,
        일반 분석은 OCR 결과로 mask_merge / mask_inpaint를 새로 만들기 때문에
        이전 텍스트 마스크가 화면/저장 슬롯에 남지 않도록 먼저 비운다.
        """
        curr = self.data.get(page_idx)
        if not curr:
            return
        try:
            curr['mask_merge'] = None
            curr['mask_inpaint'] = None
            curr['mask_merge_path'] = None
            curr['mask_inpaint_path'] = None
            # 텍스트 마스크는 ON/OFF 슬롯을 사용하지 않지만, 예전 버전/작업 캐시에서
            # 남아 있을 수 있는 보조 슬롯까지 같이 지워야 전체 분석이 항상 새 상태가 된다.
            curr['mask_merge_off'] = None
            curr['mask_merge_off_path'] = None
            # 일반 분석은 초기화에 가까운 작업이므로 기존 수동/자동 마스킹 슬롯을 모두 비운다.
            curr['mask_inpaint_off'] = None
            curr['mask_inpaint_off_path'] = None
            curr['mask_toggle_enabled'] = True
            if page_idx == getattr(self, 'idx', -1) and self.cb_mode.currentIndex() == 2:
                try:
                    self.view.set_user_mask_np(None)
                except Exception:
                    pass
        except Exception:
            pass

    def anal_end_for_page(self, page_idx, o, d, mm, mi, preserve_text_mask=False):
        """
        분석/재분석 결과를 시작 당시의 page_idx에만 반영한다.
        self.idx를 직접 쓰면 작업 도중 페이지 이동 시 다른 페이지를 덮어쓸 수 있다.

        preserve_text_mask=False: 일반 분석. 기존 텍스트 마스크 슬롯을 버리고 새 OCR 마스크로 교체한다.
        preserve_text_mask=True: 텍스트 마스크 재분석. 사용자가 칠한 재분석 마스크를 보존한다.
        """
        if page_idx < 0 or page_idx >= len(self.paths):
            self.end_busy_state("분석")
            return

        if page_idx not in self.data:
            self.data[page_idx] = {
                'ori': o,
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
                'clean_path': None,
                'working_source': None,
                'working_source_path': None,
                'final_paint': None,
                'final_paint_path': None,
                'final_paint_above': None,
                'final_paint_above_path': None,
                'ocr_analysis_regions': [],
            }

        old_inpaint_off = self.data[page_idx].get('mask_inpaint_off')
        if not preserve_text_mask:
            old_inpaint_off = None

        if preserve_text_mask:
            # 재분석은 사용자가 칠한 텍스트 마스크를 기준으로 OCR을 다시 거는 작업이다.
            # 따라서 워커가 반환한 mm(=재분석에 사용한 마스크)을 그대로 유지한다.
            self.data[page_idx].update({
                'ori': o,
                'data': d,
                'mask_merge': mm,
                'mask_inpaint': mi,
                'mask_toggle_enabled': True,
            })
            if self.data[page_idx].get('mask_merge_off') is None:
                self.data[page_idx]['mask_merge_off'] = None
            if self.data[page_idx].get('mask_inpaint_off') is None:
                self.data[page_idx]['mask_inpaint_off'] = old_inpaint_off
            self.log((
                f"✅ Text mask re-analysis applied to page {page_idx + 1} (manual mask preserved)"
                if self.ui_language == LANG_EN
                else f"✅ {page_idx + 1}페이지 텍스트 마스크 재분석 반영 완료 (재분석 마스크 보존)"
            ))
        else:
            # 일반 분석은 새 OCR 결과를 기준으로 텍스트 마스크를 다시 만드는 작업이다.
            # 단, OCR 분석 영역이 지정되어 있고 기존 분석 데이터가 있다면 전체 결과를 버리지 않고
            # 지정 영역 안의 기존 번호/라인만 새 OCR 결과로 업데이트한다.
            if self.data[page_idx].get('ocr_analysis_regions') and self.data[page_idx].get('data'):
                d, mm, mi = self.merge_ocr_analysis_region_results(page_idx, d, mm, mi, ori_img=o)
            # 이전 mask_merge/mask_inpaint가 남으면 분석을 반복해도 이전 상태가 섞여 보일 수 있으므로
            # 텍스트 마스크 계열은 명시적으로 새 결과로 교체한다.
            self.data[page_idx].update({
                'ori': o,
                'data': d,
                'mask_merge': mm.copy() if isinstance(mm, np.ndarray) else mm,
                'mask_inpaint': mi.copy() if isinstance(mi, np.ndarray) else mi,
                'mask_merge_off': None,
                # 일반 분석은 기존 마스킹 자료를 무시하고 새로 따는 작업이므로 OFF 마스크도 초기화한다.
                'mask_inpaint_off': None,
                'mask_toggle_enabled': True,
            })
            self.log((
                f"✅ Analysis applied to page {page_idx + 1} (text mask rebuilt)"
                if self.ui_language == LANG_EN
                else f"✅ {page_idx + 1}페이지 분석 결과 반영 완료 (텍스트 마스크 새로 생성)"
            ))

        # 현재 보고 있는 페이지가 작업 완료된 페이지일 때만 화면 갱신
        if page_idx == self.idx:
            self.ref_tab()

            # 분석/재분석 결과 반영 직후 분석도 탭으로 이동할 때,
            # 직전 텍스트/페인팅 마스크 화면에 남아 있던 구 마스크가 mode_chg에서
            # 새 분석 결과를 덮어쓰지 않도록 마스크 자동 커밋을 잠시 막는다.
            old_skip_mode_mask_commit = getattr(self, "_skip_mode_mask_commit", False)
            self._skip_mode_mask_commit = True
            try:
                if self.cb_mode.currentIndex() != 1:
                    self.cb_mode.setCurrentIndex(1)
                else:
                    self.mode_chg(1)
            finally:
                self._skip_mode_mask_commit = old_skip_mode_mask_commit

            # ON 강제 조건 1/2: 일반 분석 또는 텍스트 마스크 재분석 완료 직후에만 켠다.
            self.set_mask_toggle_safely(True)

        # ON 강제 조건 1/2: 분석 결과가 들어온 페이지는 분석 마스크 사용 상태로 저장한다.
        # 사용자가 이후 직접 OFF로 바꾸면 다시 임의로 ON시키지 않는다.
        self.data[page_idx]['mask_toggle_enabled'] = True

        self.auto_save_project()

        # 분석/재분석은 OCR/API 결과가 반영되는 작업 경계다.
        # 결과 반영 이후에는 이전 편집 Undo로 돌아가면 마스크/텍스트 상태가 꼬일 수 있으므로
        # 성공적으로 데이터에 적용된 뒤 Undo 체인을 끊는다.
        self.undo_break_boundary("reanalyze" if preserve_text_mask else "analysis")
        self._active_task_worker = None
        self.end_busy_state("텍스트 마스크 재분석" if preserve_text_mask else "분석")
        self.macro_mark_current_step_done("work_analyze")

    def _show_api_missing_and_open_settings(self, category, provider_name, detail_ko=None, detail_en=None):
        """API 설정 누락을 사용자에게 알리고 바로 API 관리창을 연다."""
        lang_en = getattr(self, "ui_language", LANG_KO) == LANG_EN
        category_map = {
            "ocr": ("OCR API", "OCR API"),
            "inpaint": ("인페인팅 API", "Inpainting API"),
            "translation": ("번역 API", "Translation API"),
        }
        category_ko, category_en = category_map.get(category, ("API", "API"))
        if lang_en:
            title = "API Settings Required"
            detail = detail_en or "Required API settings are missing."
            msg = (
                f"The selected {category_en} ({provider_name}) is not configured or its key is missing.\n"
                f"Please check the selected provider and fill in the required settings in [Options > API Settings].\n\n"
                f"Details: {detail}"
            )
            self.log(f"❌ {category_en} missing or invalid: {provider_name}")
        else:
            title = "API 설정 필요"
            detail = detail_ko or "필요한 API 설정이 비어 있습니다."
            msg = (
                f"선택된 {category_ko} ({provider_name}) 설정이 비어 있거나 키가 없습니다.\n"
                f"[옵션 > API 관리]에서 선택된 API와 필수 설정을 확인해 주세요.\n\n"
                f"상세: {detail}"
            )
            self.log(f"❌ {category_ko} 설정 누락: {provider_name}")
        QMessageBox.critical(self, title, msg)
        try:
            self.open_api_settings_dialog()
        except Exception as e:
            self.log((f"⚠️ Failed to open API Settings: {e}" if lang_en else f"⚠️ API 관리창 열기 실패: {e}"))
        return False

    def check_ocr_api_or_alert(self):
        """선택된 OCR/API/Local OCR 설정이 비어 있으면 작업 시작 전에 막는다."""
        settings = getattr(self, "api_settings", None) or ApiSettingsStore.load()
        provider = str(getattr(settings, "selected_ocr_provider", "clova") or "clova").lower()

        if provider in ("local_paddle_ocr", "local_manga_ocr"):
            try:
                from ysb.editions.current import is_local_edition
                local_name = "LOCAL Manga OCR" if provider == "local_manga_ocr" else "LOCAL Paddle OCR"
                if not is_local_edition():
                    QMessageBox.critical(
                        self,
                        "Local OCR 사용 불가",
                        f"{local_name}은 Local판 전용입니다.\nLite판에서는 CLOVA OCR 또는 Google Vision OCR을 선택해 주세요."
                    )
                    self.log(f"❌ {local_name}은 Local판에서만 사용할 수 있습니다.")
                    return False
                from ysb.engines.text_detection.comic_text_detector import ComicTextDetectorEngine
                ok, reason = ComicTextDetectorEngine().available()
                if not ok:
                    QMessageBox.critical(
                        self,
                        "Local OCR 준비 필요",
                        f"{local_name}을 실행할 수 없습니다.\n\n"
                        "comic_text_detector 런타임/모델 파일을 확인해 주세요.\n\n"
                        f"상세: {reason}"
                    )
                    self.log(f"❌ {local_name} 준비 실패: {reason}")
                    return False
                try:
                    from ysb.editions.local.local_dependency_check import paddleocr_available, manga_ocr_ready
                    if provider == "local_manga_ocr":
                        ok, detail = manga_ocr_ready()
                        if not ok:
                            QMessageBox.critical(
                                self,
                                "Manga OCR 설치 필요",
                                "LOCAL Manga OCR 문자 인식에 필요한 런타임 또는 모델을 찾을 수 없습니다.\n\n"
                                "배포판은 local_runtime/manga_ocr, 개발 환경은 setup_manga_ocr_v2_2_0.bat 실행 상태를 확인해 주세요.\n\n"
                                f"상세: {detail}"
                            )
                            self.log(f"❌ Manga OCR 준비 실패: {detail}")
                            return False
                    else:
                        if not paddleocr_available():
                            QMessageBox.critical(
                                self,
                                "PaddleOCR 설치 필요",
                                "LOCAL Paddle OCR 문자 인식에 필요한 paddleocr 패키지를 찾을 수 없습니다.\n\n"
                                "setup_local_core_venv_v2_1_0.bat을 다시 실행하거나 requirements/local.txt 설치 상태를 확인해 주세요."
                            )
                            self.log("❌ paddleocr 패키지를 찾을 수 없습니다.")
                            return False
                except Exception as e:
                    QMessageBox.critical(self, "Local OCR 확인 오류", f"Local OCR 설치 확인 중 오류가 발생했습니다.\n\n{e}")
                    self.log(f"❌ Local OCR 설치 확인 오류: {e}")
                    return False
                return True
            except Exception as e:
                QMessageBox.critical(self, "Local OCR 오류", f"Local OCR 준비 확인 중 오류가 발생했습니다.\n\n{e}")
                self.log(f"❌ Local OCR 준비 확인 오류: {e}")
                return False

        if provider == "google_vision":
            if not str(getattr(settings, "google_vision_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings(
                    "ocr",
                    "Google Vision OCR",
                    "Google Vision OCR API Key가 비어있습니다.",
                    "Google Vision OCR API Key is empty.",
                )
        else:
            missing = []
            if not str(getattr(settings, "clova_api_url", "") or "").strip():
                missing.append("Invoke URL")
            if not str(getattr(settings, "clova_secret_key", "") or "").strip():
                missing.append("Secret Key")
            if missing:
                return self._show_api_missing_and_open_settings(
                    "ocr",
                    "CLOVA OCR",
                    "CLOVA OCR " + ", ".join(missing) + " 설정이 비어있습니다.",
                    "CLOVA OCR " + ", ".join(missing) + " setting(s) are empty.",
                )
        return True

    def check_inpaint_api_or_alert(self):
        """선택된 인페인팅 API 설정이 비어 있으면 작업 시작 전에 막고 API 관리창을 연다."""
        settings = getattr(self, "api_settings", None) or ApiSettingsStore.load()
        provider = str(getattr(settings, "selected_inpaint_provider", "replicate_lama") or "replicate_lama").lower()
        provider_name_map = {
            "replicate_stable": "Replicate Stable Diffusion Inpainting",
            "gemini_inpaint": "Gemini Image Inpainting",
            "local_lama": "LOCAL LaMa",
            "local_sdxl_lightning": "LOCAL SDXL Lightning",
            "replicate_lama": "Replicate LaMa",
        }
        provider_name = provider_name_map.get(provider, "Replicate LaMa")

        if provider == "local_lama":
            try:
                from ysb.editions.current import is_local_edition
                if not is_local_edition():
                    return self._show_api_missing_and_open_settings(
                        "inpaint",
                        provider_name,
                        "LOCAL LaMa는 Local판 전용입니다.",
                        "LOCAL LaMa is only available in the Local edition.",
                    )
                from simple_lama_inpainting import SimpleLama  # noqa: F401
            except ImportError as e:
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "LOCAL LaMa 패키지가 설치되어 있지 않습니다. setup_local_core_venv_v2_1_0.bat를 실행해 주세요.",
                    "LOCAL LaMa package is not installed. Run setup_local_core_venv_v2_1_0.bat first.",
                )
            except Exception as e:
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    f"LOCAL LaMa 준비 확인 중 오류가 발생했습니다: {e}",
                    f"LOCAL LaMa readiness check failed: {e}",
                )
            return True

        if provider == "local_sdxl_lightning":
            try:
                from ysb.editions.current import is_local_edition
                if not is_local_edition():
                    return self._show_api_missing_and_open_settings(
                        "inpaint",
                        provider_name,
                        "LOCAL SDXL Lightning은 Local판 전용입니다.",
                        "LOCAL SDXL Lightning is only available in the Local edition.",
                    )
                import diffusers  # noqa: F401
            except ImportError as e:
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "LOCAL SDXL Lightning 패키지(diffusers 등)가 설치되어 있지 않습니다. 의존성 설치를 완료해 주세요.",
                    "LOCAL SDXL Lightning package (diffusers, etc.) is not installed. Please install dependencies.",
                )
            except Exception as e:
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    f"LOCAL SDXL Lightning 준비 확인 중 오류가 발생했습니다: {e}",
                    f"LOCAL SDXL Lightning readiness check failed: {e}",
                )
            return True

        if provider == "gemini_inpaint":
            if not str(getattr(settings, "gemini_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "Gemini API Key가 비어있습니다.",
                    "Gemini API Key is empty.",
                )
            if not str(getattr(settings, "gemini_inpaint_model", "") or "").strip():
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "Gemini 인페인팅 모델명이 비어있습니다.",
                    "Gemini inpainting model name is empty.",
                )
        elif provider == "replicate_stable":
            stable_token = str(getattr(settings, "stable_replicate_api_token", "") or getattr(settings, "replicate_api_token", "") or "").strip()
            if not stable_token:
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "Stable Replicate API Token이 비어있습니다.",
                    "Stable Replicate API Token is empty.",
                )
            if not str(getattr(settings, "stable_inpaint_model", "") or "").strip():
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "Stable Diffusion 인페인팅 모델명이 비어있습니다.",
                    "Stable Diffusion inpainting model name is empty.",
                )
        else:
            lama_token = str(getattr(settings, "lama_replicate_api_token", "") or getattr(settings, "replicate_api_token", "") or "").strip()
            if not lama_token:
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "LaMa Replicate API Token이 비어있습니다.",
                    "LaMa Replicate API Token is empty.",
                )
            if not str(getattr(settings, "repaint_model", "") or "").strip():
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "LaMa 인페인팅 모델명이 비어있습니다.",
                    "LaMa inpainting model name is empty.",
                )
        return True

    def check_translation_api_key_or_alert(self, provider=None):
        """번역 API 키가 없을 때 원문 반환으로 조용히 넘어가지 않게 UI에서 먼저 막는다."""
        settings = getattr(self, "api_settings", None) or ApiSettingsStore.load()
        provider = (provider or getattr(settings, "selected_translation_provider", "openai") or self.cb_trans_provider.currentData() or "openai").lower()

        if provider == "local":
            return True

        def _provider_display_name(code: str) -> str:
            mapping = {
                "openai": "OpenAI",
                "deepseek": "DeepSeek",
                "google": "Google Translate",
                "gemini": "Gemini",
                "custom": "Custom / OpenAI-Compatible",
            }
            return mapping.get((code or "").lower(), str(code or "OpenAI"))

        if provider in ("local_argos", "local_hf_jako", "local_hf_enko", "local_nllb"):
            # Legacy local translation providers are no longer supported.
            provider = "openai"

        provider_name = _provider_display_name(provider)

        if provider == "deepseek":
            if not str(getattr(settings, "deepseek_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings("translation", provider_name, "DeepSeek API Key가 비어있습니다.", "DeepSeek API Key is empty.")
        elif provider == "google":
            if not str(getattr(settings, "google_translate_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings("translation", provider_name, "Google Translate API Key가 비어있습니다.", "Google Translate API Key is empty.")
        elif provider == "gemini":
            if not str(getattr(settings, "gemini_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings("translation", provider_name, "Gemini API Key가 비어있습니다.", "Gemini API Key is empty.")
        elif provider == "custom":
            missing = []
            if not str(getattr(settings, "custom_translation_base_url", "") or "").strip():
                missing.append("Base URL")
            if not str(getattr(settings, "custom_translation_model", "") or "").strip():
                missing.append("Model")
            if not str(getattr(settings, "custom_translation_api_key", "") or "").strip():
                missing.append("API Key")
            if missing:
                return self._show_api_missing_and_open_settings(
                    "translation",
                    provider_name,
                    "Custom 번역 API " + ", ".join(missing) + " 설정이 비어있습니다.",
                    "Custom translation API " + ", ".join(missing) + " setting(s) are empty.",
                )
        else:
            if not str(getattr(settings, "openai_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings("translation", provider_name, "OpenAI API Key가 비어있습니다.", "OpenAI API Key is empty.")

        return True

    def trans(self):
        if not self.ensure_engine_ready():
            return
        if not self.paths:
            self.log("⚠️ 이미지가 없습니다. 먼저 프로젝트에 이미지를 불러와 주세요.")
            return
        if self.idx not in self.data:
            self.log("⚠️ 번역할 데이터가 없습니다.")
            return
        curr = self.data.get(self.idx)
        if not curr or not curr.get('data'):
            self.log("⚠️ 텍스트 박스가 없어서 번역할 게 없습니다.")
            return

        try:
            texts = []
            target_rows = []
            for row in range(1, self.tab.rowCount()):
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr['data']):
                    continue
                is_checked = self.get_table_check_state(row)
                curr['data'][data_index]['use_inpaint'] = is_checked
                if not is_checked:
                    continue
                item = self.tab.item(row, 2)
                texts.append(item.text() if item else "")
                target_rows.append(row)

            if not texts:
                self.log("⚠️ 체크된 번역 대상이 없습니다.")
                return

            provider = self.cb_trans_provider.currentData()
            if not self.check_translation_api_key_or_alert(provider):
                return
            chunk_size = self.get_current_translation_chunk_size()
            self.log(
                f"🌐 번역 엔진: {self.cb_trans_provider.currentText()} / "
                f"대상 {len(texts)}개 / 묶음 {chunk_size}개"
            )
            self._translation_target_rows = list(target_rows)
            self._translation_target_texts = list(texts)
            self._long_task_cancel_requested = False
            self.prepare_task_progress_overlay(
                "번역",
                f"번역 준비 중... 대상 {len(texts)}개 / 묶음 {chunk_size}개",
                total=len(texts),
                cancellable=True,
            )
            self.begin_busy_state("번역")
            self.translation_worker = TranslationWorker(
                self.engine,
                texts,
                provider=provider,
                chunk_size=chunk_size,
            )
            self._active_task_worker = self.translation_worker
            self.translation_worker.progress.connect(self.on_translation_worker_progress)
            self.translation_worker.finished.connect(self.on_translation_worker_finished)
            self.translation_worker.canceled.connect(self.on_translation_worker_canceled)
            self.translation_worker.error.connect(self.on_translation_worker_error)
            self.translation_worker.start()
            return

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log(f"❌ 번역 중 에러 발생: {e}")
            msg_text = self.tr_ui("에러가 발생했습니다:")
            QMessageBox.critical(self, self.tr_ui("번역 오류"), f"{msg_text}\n{e}")
        finally:
            try:
                tw = getattr(self, "translation_worker", None)
                if tw is None or not tw.isRunning():
                    self.end_busy_state("번역")
            except Exception:
                self.end_busy_state("번역")


    def on_translation_worker_progress(self, detail, current, total):
        self.handle_long_task_message(str(detail), current=current, total=total)

    def _apply_translation_results_to_current_page(self, res):
        curr = self.data.get(self.idx)
        if not curr or not curr.get('data'):
            return False
        target_rows = list(getattr(self, "_translation_target_rows", []) or [])
        texts = list(getattr(self, "_translation_target_texts", []) or [])
        if len(res) != len(target_rows):
            QMessageBox.warning(
                self,
                self.tr_ui("번역 개수 불일치"),
                self.tr_msg(f"요청 {len(target_rows)}개 / 응답 {len(res)}개\n\n밀림 방지를 위해 결과 반영을 중단했습니다."),
            )
            return False

        affected_ids = []
        # 번역 결과 반영은 분석/인페인팅과 같은 확정 작업 경계다.
        # 이전 편집 상태로 Ctrl+Z 되는 것을 막기 위해 별도 Undo 기록을 만들지 않는다.
        self.tab.blockSignals(True)
        try:
            for row, t in zip(target_rows, res):
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr['data']):
                    continue
                safe_text = str(t) if t is not None else ""
                curr['data'][data_index]['translated_text'] = safe_text
                affected_ids.append(curr['data'][data_index].get('id'))
                self.tab.setItem(row, 3, QTableWidgetItem(safe_text))
            self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)

        # 번역 결과도 현재 페이지 텍스트 데이터만 바뀌는 작업이다.
        # 최종결과 탭 전체 mode_chg 대신 해당 텍스트만 갱신한다.
        try:
            for row in target_rows:
                self.tab.resizeRowToContents(row)
        except Exception:
            self.tab.resizeRowsToContents()
        if self.cb_mode.currentIndex() == 4:
            if not self.refresh_final_text_items_by_ids(affected_ids):
                self.schedule_final_text_scene_refresh(80)
        try:
            self.finalize_text_change(ids=affected_ids, fields=['translated_text'], reason='번역 결과 반영', delay_ms=1800)
        except Exception:
            try:
                if hasattr(self, 'text_engine') and self.text_engine is not None:
                    self.text_engine.mark_dirty(int(getattr(self, 'idx', 0) or 0), affected_ids, ['translated_text'])
                self.mark_active_page_dirty('text')
                self.schedule_deferred_auto_save_project(1800)
            except Exception:
                pass
        self.undo_break_boundary("translation")
        return True

    def on_translation_worker_finished(self, res):
        try:
            if self._apply_translation_results_to_current_page(list(res or [])):
                self.log("✅ 번역 완료")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log(f"❌ 번역 결과 반영 중 오류: {e}")
            QMessageBox.critical(self, self.tr_ui("번역 오류"), f"{self.tr_ui('에러가 발생했습니다:')}\n{e}")
        finally:
            self._active_task_worker = None
            self.translation_worker = None
            self.end_busy_state("번역")
            self.macro_mark_current_step_done("work_translate")

    def on_translation_worker_canceled(self, partial):
        try:
            self.log(f"⏹️ 번역 취소됨: 받은 결과 {len(partial or [])}개는 반영하지 않았습니다.")
        finally:
            self._active_task_worker = None
            self.translation_worker = None
            self.end_busy_state("번역")

    def on_translation_worker_error(self, message):
        try:
            msg = f"❌ 번역 중 에러 발생: {message}"
            self.handle_long_task_message(msg)
        finally:
            self._active_task_worker = None
            self.translation_worker = None
            self.end_busy_state("번역")

    def clip_mask_to_checked_text_boxes(self, mask, data):
        """
        페인팅 마스크 토글 ON 전용:
        분석 기반 페인팅 마스크는 체크된 텍스트 박스 영역 안에서만 지우도록 제한한다.
        사용자가 ON 상태에서 박스 밖을 칠해도 실제 인페인팅 마스크에는 들어가지 않는다.
        """
        if mask is None:
            return None

        if mask.ndim == 3:
            gray = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY)
        else:
            gray = mask.copy()

        h, w = gray.shape[:2]
        allowed = np.zeros((h, w), dtype=np.uint8)

        for item in data or []:
            if not item.get('use_inpaint', True):
                continue
            rect = item.get('rect')
            if not rect or len(rect) < 4:
                continue
            try:
                rx, ry, rw, rh = [int(v) for v in rect[:4]]
            except Exception:
                continue

            x1 = max(0, rx)
            y1 = max(0, ry)
            x2 = min(w, rx + max(0, rw))
            y2 = min(h, ry + max(0, rh))
            if x2 > x1 and y2 > y1:
                allowed[y1:y2, x1:x2] = 255

        return cv2.bitwise_and(gray, allowed)

    def build_inpainting_payload_for_current_toggle(self, curr):
        """
        인페인팅 입력 분기:
        - 토글 ON: 분석 기반 페인팅 마스크를 체크된 텍스트 박스 안으로 제한한다.
        - 토글 OFF: 텍스트 박스/체크 상태를 무시하고 OFF 페인팅 마스크를 그대로 사용한다.
        """
        data = curr.get('data', [])
        if self.mask_toggle_enabled:
            mask = curr.get('mask_inpaint')
            if mask is not None:
                mask = self.clip_mask_to_checked_text_boxes(mask, data)
            return data, mask

        # OFF 상태는 분석 없이 직접 칠한 마스크로만 인페인팅한다.
        # engine.execute_inpainting()이 data의 체크박스 영역을 추가로 건드리지 않도록 data를 비워 넘긴다.
        return [], curr.get('mask_inpaint_off')

    def _get_inpaint_resize_limits(self, provider=None):
        provider = str(provider or "replicate_lama").strip().lower()
        if provider in ("local_lama", "local_sdxl_lightning"):
            return {
                "provider": provider,
                "provider_label": "LOCAL LaMa" if provider == "local_lama" else "LOCAL SDXL Lightning",
                "warn_max_side": 3000,
                "warn_max_pixels": 9_000_000,
                "target_max_side": 2800,
                "target_max_pixels": 7_500_000,
            }
        if provider == "replicate_lama":
            return {
                "provider": provider,
                "provider_label": "Replicate LaMa",
                "warn_max_side": 2800,
                "warn_max_pixels": 6_000_000,
                "target_max_side": 2200,
                "target_max_pixels": 4_000_000,
            }
        return None

    def _get_current_inpaint_provider(self):
        try:
            from ysb.engine.manga_engine import Config
            return str(getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama").strip().lower()
        except Exception:
            return "replicate_lama"

    def _inspect_inpaint_resize_plan(self, input_path, provider=None):
        limits = self._get_inpaint_resize_limits(provider or self._get_current_inpaint_provider())
        if not limits or not input_path or not os.path.exists(str(input_path)):
            return None
        try:
            img = cv2.imdecode(np.fromfile(str(input_path), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return None
            h, w = img.shape[:2]
        except Exception:
            return None

        max_side = max(int(w or 0), int(h or 0))
        total_pixels = int(max(0, w) * max(0, h))
        warn_max_side = int(limits.get("warn_max_side", 0) or 0)
        warn_max_pixels = int(limits.get("warn_max_pixels", 0) or 0)
        if (warn_max_side <= 0 or max_side <= warn_max_side) and (warn_max_pixels <= 0 or total_pixels <= warn_max_pixels):
            return None

        scale = 1.0
        target_max_side = int(limits.get("target_max_side", warn_max_side) or warn_max_side or 0)
        target_max_pixels = int(limits.get("target_max_pixels", warn_max_pixels) or warn_max_pixels or 0)
        if target_max_side > 0 and max_side > target_max_side:
            scale = min(scale, float(target_max_side) / float(max_side))
        if target_max_pixels > 0 and total_pixels > target_max_pixels:
            scale = min(scale, float(target_max_pixels / float(total_pixels)) ** 0.5)
        if scale >= 0.9999:
            return None

        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        return {
            "provider": limits.get("provider", provider),
            "provider_label": limits.get("provider_label", provider or "LaMa"),
            "source_path": str(input_path),
            "orig_width": int(w),
            "orig_height": int(h),
            "orig_megapixels": float(total_pixels) / 1_000_000.0,
            "target_width": int(new_w),
            "target_height": int(new_h),
            "target_megapixels": float(new_w * new_h) / 1_000_000.0,
            "warn_max_side": warn_max_side,
            "warn_max_pixels": warn_max_pixels,
            "target_max_side": target_max_side,
            "target_max_pixels": target_max_pixels,
        }

    def _write_resized_inpaint_request(self, page_idx, input_path, inpaint_mask, plan):
        if not isinstance(plan, dict):
            return input_path, inpaint_mask
        try:
            src_img = cv2.imdecode(np.fromfile(str(input_path), np.uint8), cv2.IMREAD_COLOR)
            if src_img is None:
                return input_path, inpaint_mask
            tw = int(plan.get("target_width", 0) or 0)
            th = int(plan.get("target_height", 0) or 0)
            if tw <= 0 or th <= 0:
                return input_path, inpaint_mask
            interp = cv2.INTER_AREA if tw < src_img.shape[1] or th < src_img.shape[0] else cv2.INTER_CUBIC
            resized = cv2.resize(src_img, (tw, th), interpolation=interp)
            base_dir = getattr(self, "project_dir", None) or os.path.dirname(str(input_path)) or os.getcwd()
            out_dir = os.path.join(base_dir, "_inpaint_resize_cache")
            os.makedirs(out_dir, exist_ok=True)
            provider = str(plan.get("provider") or "").strip().lower()
            # Replicate 업로드는 픽셀 수뿐 아니라 입력 파일 용량도 실패 요인이 될 수 있다.
            # 축소본을 PNG로 저장하면 원본 JPG보다 더 커질 수 있어 Replicate LaMa에는 JPG 임시 입력을 쓴다.
            ext = ".jpg" if provider == "replicate_lama" else ".png"
            out_path = os.path.join(out_dir, f"page_{int(page_idx)+1:04d}_{tw}x{th}{ext}")
            if ext == ".jpg":
                ok, buf = cv2.imencode(ext, resized, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            else:
                ok, buf = cv2.imencode(ext, resized, [int(cv2.IMWRITE_PNG_COMPRESSION), 6])
            if not ok:
                return input_path, inpaint_mask
            buf.tofile(out_path)
            resized_mask = inpaint_mask
            if inpaint_mask is not None:
                try:
                    resized_mask = cv2.resize(inpaint_mask, (tw, th), interpolation=cv2.INTER_NEAREST)
                except Exception:
                    resized_mask = inpaint_mask
            try:
                self.log(f"↘️ 인페인팅 입력 축소: {plan.get('orig_width')}x{plan.get('orig_height')} → {tw}x{th}")
            except Exception:
                pass
            return out_path, resized_mask
        except Exception:
            return input_path, inpaint_mask

    def _ask_single_inpaint_resize(self, page_idx, plan):
        if not isinstance(plan, dict):
            return "keep"
        title = self.tr_ui("인페인팅 해상도 확인")
        provider_label = str(plan.get("provider_label") or "LaMa")
        current_size = f"{int(plan.get('orig_width', 0))} x {int(plan.get('orig_height', 0))} ({float(plan.get('orig_megapixels', 0.0)):.1f}MP)"
        target_size = f"{int(plan.get('target_width', 0))} x {int(plan.get('target_height', 0))} ({float(plan.get('target_megapixels', 0.0)):.1f}MP)"
        warn_text = f"장변 {int(plan.get('warn_max_side', 0)):,}px / {float(int(plan.get('warn_max_pixels', 0))/1_000_000.0):.1f}MP"
        body = self.tr_ui("현재 이미지가 LaMa 권장 해상도를 넘을 수 있습니다.")
        detail = (
            f"{self.tr_ui('페이지')}: {int(page_idx) + 1}\n"
            f"{self.tr_ui('현재 이미지')}: {current_size}\n"
            f"{self.tr_ui('권장 기준')}: {provider_label} · {warn_text}\n"
            f"{self.tr_ui('인페인팅용 축소 예상')}: {target_size}"
        )
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(title)
        msg.setText(body)
        msg.setInformativeText(detail)
        resize_btn = msg.addButton(self.tr_ui("리사이즈 후 진행"), QMessageBox.ButtonRole.AcceptRole)
        keep_btn = msg.addButton(self.tr_ui("그대로 진행"), QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(resize_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == resize_btn:
            return "resize"
        if clicked == keep_btn:
            return "keep"
        return "cancel"

    def _prepare_single_inpaint_request_with_resize_prompt(self, page_idx, input_path, inpaint_mask):
        plan = self._inspect_inpaint_resize_plan(input_path, self._get_current_inpaint_provider())
        if not plan:
            return input_path, inpaint_mask, True
        decision = self._ask_single_inpaint_resize(page_idx, plan)
        if decision == "cancel":
            self.log("↩️ 인페인팅 리사이즈 취소")
            return input_path, inpaint_mask, False
        if decision != "resize":
            self.log("ℹ️ 인페인팅은 원본 해상도로 그대로 진행합니다.")
            return input_path, inpaint_mask, True
        new_path, new_mask = self._write_resized_inpaint_request(page_idx, input_path, inpaint_mask, plan)
        return new_path, new_mask, True

    def _ask_batch_inpaint_resize(self, selected_page_indices):
        provider = self._get_current_inpaint_provider()
        limits = self._get_inpaint_resize_limits(provider)
        self._batch_inpaint_resize_policy = None
        if not limits:
            return True

        overs = []
        for page_idx in list(selected_page_indices or []):
            try:
                input_path = self.get_inpainting_input_path(int(page_idx))
            except Exception:
                input_path = None
            plan = self._inspect_inpaint_resize_plan(input_path, provider)
            if plan:
                plan["page_idx"] = int(page_idx)
                overs.append(plan)

        if not overs:
            return True

        preview_lines = []
        for plan in overs[:6]:
            preview_lines.append(
                f"- {int(plan.get('page_idx', 0)) + 1}{self.tr_ui('페이지')}: "
                f"{int(plan.get('orig_width', 0))}x{int(plan.get('orig_height', 0))} → "
                f"{int(plan.get('target_width', 0))}x{int(plan.get('target_height', 0))}"
            )
        if len(overs) > 6:
            preview_lines.append(self.tr_ui("외 추가 페이지가 있습니다.").format(count=len(overs) - 6))

        provider_label = str(limits.get("provider_label") or "LaMa")
        warn_text = f"장변 {int(limits.get('warn_max_side', 0)):,}px / {float(int(limits.get('warn_max_pixels', 0))/1_000_000.0):.1f}MP"
        detail = (
            f"{self.tr_ui('기준 초과 페이지')}: {len(overs)}\n"
            f"{self.tr_ui('권장 기준')}: {provider_label} · {warn_text}\n\n"
            + "\n".join(preview_lines)
        )

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("일괄 인페인팅 해상도 확인"))
        msg.setText(self.tr_ui("선택한 페이지 중 일부가 LaMa 권장 해상도를 넘습니다."))
        msg.setInformativeText(detail)
        cb = QCheckBox(self.tr_ui("선택한 전체 페이지에 같은 기준으로 적용"), msg)
        cb.setChecked(True)
        msg.setCheckBox(cb)
        resize_btn = msg.addButton(self.tr_ui("리사이즈 후 진행"), QMessageBox.ButtonRole.AcceptRole)
        keep_btn = msg.addButton(self.tr_ui("그대로 진행"), QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(resize_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == cancel_btn:
            self.log("↩️ 인페인팅 리사이즈 취소")
            return False
        if clicked == keep_btn:
            self.log("ℹ️ 일괄 인페인팅은 원본 해상도로 그대로 진행합니다.")
            return True

        if cb.isChecked():
            apply_indices = [int(i) for i in selected_page_indices or []]
        else:
            apply_indices = [int(plan.get("page_idx", -1)) for plan in overs]
        self._batch_inpaint_resize_policy = {
            "enabled": True,
            "provider": provider,
            "target_max_side": int(limits.get("target_max_side", 0) or 0),
            "target_max_pixels": int(limits.get("target_max_pixels", 0) or 0),
            "warn_max_side": int(limits.get("warn_max_side", 0) or 0),
            "warn_max_pixels": int(limits.get("warn_max_pixels", 0) or 0),
            "page_indices": [int(i) for i in apply_indices if int(i) >= 0],
        }
        self.log(f"↘️ 일괄 인페인팅 리사이즈 적용 예정: {len(overs)}페이지 감지")
        return True

    def run_inpainting(self):
        if not self.ensure_engine_ready():
            return
        if not self.paths:
            self.log("⚠️ 이미지가 없습니다. 먼저 프로젝트에 이미지를 불러와 주세요.")
            return
        if not self.check_inpaint_api_or_alert():
            return

        page_idx = int(getattr(self, "idx", 0) or 0)
        curr = self.data.get(page_idx)
        if not curr:
            return

        # 인페인팅은 현재 작업 페이지를 고정해서 시작한다.
        # 작업 중 사용자가 다른 페이지로 이동해도 완료 결과는 page_idx에만 반영한다.
        self.commit_current_page_ui_to_data()
        try:
            self.ensure_page_masks_loaded(page_idx, keys=("mask_inpaint", "mask_inpaint_off"))
            self.touch_page_mask_cache(page_idx)
            self.trim_page_mask_cache(keep_indices=[page_idx])
        except Exception:
            pass

        input_path = self.get_inpainting_input_path(page_idx)
        if not input_path or not os.path.exists(input_path):
            self.log("⚠️ 인페인팅 입력 이미지 파일을 만들지 못했습니다.")
            return

        mask_toggle_enabled = bool(getattr(self, "mask_toggle_enabled", False))
        data = curr.get('data', [])
        if mask_toggle_enabled:
            inpaint_mask = curr.get('mask_inpaint')
            if inpaint_mask is not None:
                inpaint_mask = self.clip_mask_to_checked_text_boxes(inpaint_mask, data)
            inpaint_data = data
        else:
            inpaint_data = []
            inpaint_mask = curr.get('mask_inpaint_off')

        inpaint_mask = self.normalize_inpaint_mask_to_input_image(input_path, inpaint_mask)

        original_input_path = str(input_path)
        input_path, inpaint_mask, proceed_inpaint = self._prepare_single_inpaint_request_with_resize_prompt(page_idx, input_path, inpaint_mask)
        if not proceed_inpaint:
            return
        cleanup_input_path = str(input_path) if str(input_path) != original_input_path else None

        if not mask_toggle_enabled and inpaint_mask is None:
            self.log("⚠️ OFF 페인팅 마스크가 없습니다. 마스크 OFF 상태에서는 직접 칠한 마스크가 필요합니다.")
            return

        if inpaint_mask is not None and int(np.count_nonzero(inpaint_mask)) == 0:
            self.log("⚠️ 인페인팅 마스크가 비어 있습니다.")
            return

        self.log(f"🧾 인페인팅 입력: {input_path}")
        self._long_task_cancel_requested = False
        self._inpaint_target_page_idx = page_idx
        self.prepare_task_progress_overlay("인페인팅", f"{page_idx + 1}페이지 인페인팅 요청을 처리하는 중입니다.", total=0, cancellable=True)
        self.begin_busy_state("인페인팅")
        self.iw = InpaintWorker(self.engine, input_path, inpaint_data, inpaint_mask, page_idx=page_idx, cleanup_path=cleanup_input_path)
        self._active_task_worker = self.iw
        self.iw.log.connect(lambda msg: self.handle_long_task_message(msg))
        self.iw.finished.connect(self.inpaint_end)
        self.iw.start()

    def save_changed_page_without_ui_commit(self, page_idx):
        """worker 결과를 저장하되 현재 화면의 다른 페이지 UI를 target page에 덮지 않는다."""
        if not getattr(self, "project_dir", None):
            return
        try:
            if hasattr(self, 'flush_workspace_image_pages'):
                saved = self.flush_workspace_image_pages([page_idx], reason='inpaint_result', release_non_current=True)
                if saved:
                    self.has_unsaved_changes = True
                    return
        except Exception as e:
            try:
                self.log(f"⚠️ 인페인팅 이미지 즉시 저장 실패({page_idx + 1}p): {e}")
            except Exception:
                pass
        if getattr(self, "auto_save_enabled", False):
            try:
                self.save_project_store(self.project_store)
                if getattr(self, "ysbt_package_path", None) and not getattr(self, "is_temp_project", False):
                    try:
                        package_project(self.project_dir, self.ysbt_package_path)
                    except Exception as e:
                        self.has_unsaved_changes = True
                        self.log(f"⚠️ 인페인팅 결과 패키지 저장 실패({page_idx + 1}p): {e}")
                        return
                self.has_unsaved_changes = bool(getattr(self, "is_temp_project", False) or not getattr(self, "ysbt_package_path", None))
            except Exception as e:
                self.has_unsaved_changes = True
                self.log(f"⚠️ 인페인팅 결과 저장 실패({page_idx + 1}p): {e}")
        else:
            try:
                self.save_to_work_cache()
            except Exception as e:
                self.has_unsaved_changes = True
                self.log(f"⚠️ 인페인팅 작업 캐시 저장 실패({page_idx + 1}p): {e}")

    def inpaint_end(self, page_idx, bg):
        try:
            page_idx = int(page_idx)
        except Exception:
            page_idx = int(getattr(self, "_inpaint_target_page_idx", getattr(self, "idx", 0)) or 0)

        if not bg:
            self.log("⚠️ 식질 실패: 결과물이 비어있습니다.")
            self._active_task_worker = None
            self.end_busy_state("인페인팅")
            self.macro_mark_current_step_done("work_inpaint")
            return

        if page_idx < 0 or page_idx >= len(getattr(self, "paths", []) or []):
            self.log("⚠️ 인페인팅 결과를 반영할 페이지를 찾지 못했습니다.")
            self._active_task_worker = None
            self.end_busy_state("인페인팅")
            return

        curr = self.data.get(page_idx)
        if curr is None:
            curr = self.make_page_data_for_image(self.paths[page_idx])
            self.data[page_idx] = curr

        img = self.bg_clean_to_np_image(bg)
        if img is not None:
            img = self.normalize_image_to_original_size(page_idx, img)
            encoded = self.encode_np_image_to_png_bytes(img)
            curr['bg_clean'] = encoded if encoded is not None else bg

            # 인페인팅을 원본으로 쓰는 상태라면, 새 결과를 작업중 원본으로 갱신한다.
            if curr.get('use_inpainted_as_source'):
                self.set_working_source_image(curr, img, page_idx=page_idx)
        else:
            curr['bg_clean'] = bg

        curr['final_paint'] = None
        curr['final_paint_above'] = None
        try:
            if hasattr(self, 'mark_page_data_dirty_explicit'):
                self.mark_page_data_dirty_explicit(page_idx, 'clean_background')
        except Exception:
            pass

        same_page = (page_idx == int(getattr(self, "idx", -1) or -1))
        try:
            if hasattr(self, 'flush_workspace_image_pages'):
                self.flush_workspace_image_pages([page_idx], reason='inpaint_result', release_non_current=not same_page)
            else:
                self.save_changed_page_without_ui_commit(page_idx)
        except Exception as e:
            try:
                self.log(f"⚠️ 인페인팅 결과 workspace 저장 실패({page_idx + 1}p): {e}")
            except Exception:
                pass
            try:
                self.schedule_deferred_auto_save_project(300)
            except Exception:
                self.auto_save_project()

        if same_page:
            # 인페인팅 완료 후 현재 작업 탭을 강제로 최종결과로 넘기지 않는다.
            # 마스크 탭에서 실행했다면 마스크가 그대로 보여야 하고, 최종결과 탭이면 텍스트만 갱신한다.
            try:
                current_mode = int(self.cb_mode.currentIndex())
            except Exception:
                current_mode = 4
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            old_skip_commit = getattr(self, "_skip_mode_mask_commit", False)
            self._suppress_mode_undo = True
            self._skip_mode_mask_commit = True
            try:
                if current_mode == 4:
                    self.refresh_final_text_scene_preserving_selection()
                elif current_mode in (2, 3):
                    try:
                        self.ensure_page_masks_loaded(page_idx, keys=("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off"))
                    except Exception:
                        pass
                    self.mode_chg(current_mode)
                elif current_mode == 1:
                    self.refresh_boxes_only()
                else:
                    # 원본 탭 등은 화면을 굳이 다시 만들 필요가 없다.
                    pass
            finally:
                self._suppress_mode_undo = old_suppress
                self._skip_mode_mask_commit = old_skip_commit
            self.log(f"✅ {page_idx + 1}페이지 인페인팅 완료 (클린본 즉시 저장)")
        else:
            self.log(f"✅ {page_idx + 1}페이지 인페인팅 결과 저장 완료: 현재 작업 페이지는 건드리지 않았습니다.")

        # 인페인팅은 배경 이미지와 최종 페인팅 레이어 기준을 바꾸는 작업 경계다.
        self.undo_break_boundary("inpaint")
        self._active_task_worker = None
        self.end_busy_state("인페인팅")
        self.macro_mark_current_step_done("work_inpaint")

    def toggle_check_from_box(self, data_item):
        # 분석도 화면에서만 박스 클릭 토글 허용
        # 0: 원본 / 1: 분석도 / 2: 텍스트 마스크 / 3: 페인팅 마스크 / 4: 최종결과
        if self.cb_mode.currentIndex() != 1:
            return

        curr = self.data.get(self.idx)
        if not curr or 'data' not in curr:
            return

        try:
            data_index = curr['data'].index(data_item)
        except ValueError:
            return

        new_state = not data_item.get('use_inpaint', True)
        table_row = data_index + 1
        self.apply_table_check_state(table_row, new_state)
        self.log((f"🔄 Box click toggle: ID {data_item.get('id')} = {'ON' if new_state else 'OFF'}" if self.ui_language == LANG_EN else f"🔄 박스 클릭 토글: ID {data_item.get('id')} = {'ON' if new_state else 'OFF'}"))

    def refresh_boxes_only(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        for item in list(self.view.scene.items()):
            if item.zValue() >= 20:
                self.view.scene.removeItem(item)
        self.view.draw_static_boxes(curr.get('data', []))
        self.refresh_ocr_region_overlay()

    def refresh_after_text_line_change(self, autosave=True):
        """텍스트 라인/ID/체크 상태가 바뀐 뒤 현재 탭 표시를 즉시 갱신한다.

        분석도/텍스트 마스크/페인팅 마스크 탭은 왼쪽 번호 박스가 scene에
        따로 그려져 있으므로 data의 id만 바꿔서는 화면 번호가 갱신되지 않는다.
        최종결과 탭은 TypesettingItem을 다시 만들어야 선택/변형 영역까지 맞는다.
        """
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = 0

        if mode in (1, 2, 3):
            self.refresh_boxes_only()
        elif mode == 4:
            try:
                if hasattr(self, 'schedule_safe_text_scene_resync'):
                    self.schedule_safe_text_scene_resync(
                        reason='refresh_after_text_line_change',
                        delay_ms=40,
                        table_refresh=False,
                    )
                else:
                    old_suppress = getattr(self, "_suppress_mode_undo", False)
                    self._suppress_mode_undo = True
                    try:
                        self.mode_chg(4)
                    finally:
                        self._suppress_mode_undo = old_suppress
            except Exception:
                pass

        if autosave:
            self.auto_save_project()

    def refresh_text_only(self):
        curr = self.data.get(self.idx)
        if not curr:
            self.log("⚠️ 데이터가 없습니다.")
            return
        if not curr.get('bg_clean'):
            self.log("⚠️ 인페인팅을 먼저 해주세요.")
            return

        self.commit_current_page_ui_to_data()
        self.cb_mode.setCurrentIndex(4)
        self.mode_chg(4)
        self.log("✨ 텍스트 갱신 완료")
        self.auto_save_project()

    def on_text_item_moved(self, message):
        self.log(message)
        # 텍스트 이동 fast path에서는 TypesettingItem이 release 시점에 x_off/y_off를
        # page data에 직접 확정한다. 이 경우 scene 전체를 다시 훑는 flush는 중복이고,
        # 고해상도 확대 상태에서 놓는 순간 렉을 만든다.
        direct_flushed = False
        try:
            direct_flushed = bool(getattr(self, '_text_move_direct_data_flushed', False))
        except Exception:
            direct_flushed = False

        if direct_flushed:
            try:
                self.audit_boundary_event(
                    'TEXT_MOVE_DIRTY_FAST_PATH',
                    ids=','.join(sorted(getattr(self, '_text_move_direct_data_flushed_ids', set()) or [])),
                    flush_skipped=True,
                )
            except Exception:
                pass
        else:
            # 텍스트 이동은 scene item 위치와 data[x_off/y_off]를 즉시 맞춘다.
            # 이후 변형/고급옵션/스타일 변경이 data 기준으로 다시 그려도 이동 전 위치로 돌아가지 않게 한다.
            try:
                if hasattr(self, "flush_text_scene_geometry_to_data"):
                    changed = self.flush_text_scene_geometry_to_data(self.selected_text_data_items() if hasattr(self, "selected_text_data_items") else None, mark_dirty=True, reason="text item moved")
                    if not changed:
                        try:
                            self.audit_boundary_event('TEXT_MOVE_DIRTY_SKIPPED_NO_CHANGE', reason='flush returned false')
                        except Exception:
                            pass
            except Exception:
                pass

        try:
            if hasattr(self, 'note_ui_interaction_activity'):
                self.note_ui_interaction_activity(1200)
        except Exception:
            pass
        try:
            if hasattr(self, 'mark_current_page_for_recovery_checkpoint'):
                self.mark_current_page_for_recovery_checkpoint('text')
        except Exception:
            pass
        try:
            self.mark_active_page_dirty('text')
        except Exception:
            pass
        try:
            self.schedule_deferred_auto_save_project()
        except Exception:
            self.auto_save_project()
        finally:
            try:
                self._text_move_direct_data_flushed = False
                self._text_move_direct_data_flushed_ids = set()
            except Exception:
                pass

    def sync_final_text_visibility_only(self):
        """최종결과 탭에서 체크 ON/OFF만 반영할 때 scene 전체를 다시 만들지 않는다."""
        if not hasattr(self, "view") or getattr(self, "view", None) is None:
            return False
        if not hasattr(self.view, "scene") or self.view.scene is None:
            return False
        try:
            show_text = bool(self.cb_show_final_text.isChecked())
        except Exception:
            show_text = True
        changed = False
        try:
            for obj in list(self.view.scene.items()):
                if not isinstance(obj, TypesettingItem):
                    continue
                data = getattr(obj, 'data', None) or {}
                visible = bool(show_text and data.get('use_inpaint', True) and (str(data.get('translated_text', '') or '').strip() or data.get('force_show')))
                if obj.isVisible() != visible:
                    obj.setVisible(visible)
                    changed = True
        except Exception:
            return False
        return changed

    def _work_mode_base_key(self, page_idx, kind, curr=None):
        """Cheap scene base key for same-page tab switching.

        The key is intentionally page/kind based so Original/Analysis/Mask tabs
        can reuse the same base pixmap without a full scene rebuild.  Content
        changing operations still clear/reload the page or call the full image
        path elsewhere.
        """
        try:
            page_idx = int(page_idx)
        except Exception:
            page_idx = int(getattr(self, "idx", 0) or 0)
        kind = str(kind or "source")
        curr = curr if isinstance(curr, dict) else (self.data.get(page_idx) or {})
        try:
            if kind == "final":
                marker = curr.get("clean_path") or curr.get("bg_clean_path") or ""
                blob = curr.get("bg_clean")
                if isinstance(blob, (bytes, bytearray)):
                    marker = f"{marker}:bg{len(blob)}"
                return f"page:{page_idx}:final:{marker}"
            marker = self.paths[page_idx] if 0 <= page_idx < len(getattr(self, "paths", []) or []) else ""
            if curr.get("use_inpainted_as_source"):
                blob = curr.get("working_source") or curr.get("bg_clean")
                if isinstance(blob, (bytes, bytearray)):
                    marker = f"{marker}:work{len(blob)}"
                marker = f"{marker}:use_work"
            return f"page:{page_idx}:source:{marker}"
        except Exception:
            return f"page:{page_idx}:{kind}"

    def schedule_final_text_scene_refresh(self, delay_ms=120):
        """최종 텍스트 갱신을 가볍게 예약한다.

        가능한 경우 기존 TypesettingItem을 제자리에서 다시 그리며, 전체 mode_chg(4)는 폴백으로만 쓴다.
        """
        try:
            if self.cb_mode.currentIndex() != 4:
                return
        except Exception:
            return
        if getattr(self, "_text_transform_runtime_active", False):
            self._pending_final_text_scene_refresh = True
            return
        try:
            timer = getattr(self, '_final_text_light_refresh_timer', None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self.refresh_final_text_scene_preserving_selection)
                self._final_text_light_refresh_timer = timer
            timer.stop()
            timer.start(max(10, int(delay_ms or 120)))
        except Exception:
            self.refresh_final_text_scene_preserving_selection()

    def refresh_final_text_scene_preserving_selection(self):
        if self.cb_mode.currentIndex() != 4:
            return
        selected_ids = []
        try:
            selected_ids = [getattr(x, 'data', {}).get('id') for x in self.view.scene.selectedItems() if isinstance(x, TypesettingItem)]
            selected_ids = [x for x in selected_ids if x is not None]
        except Exception:
            selected_ids = []
        try:
            if hasattr(self, 'rebuild_current_page_text_layer_from_data') and self.rebuild_current_page_text_layer_from_data(selected_ids or None):
                return
        except Exception:
            pass
        # Scene/data mismatch or stale item references must not be fixed by immediate
        # mode_chg(4).  Queue a safe resync barrier so the current key/mouse/undo
        # event unwinds before live TypesettingItems are removed/recreated.
        try:
            if hasattr(self, 'schedule_safe_text_scene_resync'):
                self.schedule_safe_text_scene_resync(
                    reason='refresh_final_text_scene_preserving_selection',
                    selected_ids=selected_ids,
                    delay_ms=40,
                )
                return
        except Exception:
            pass
        # Last-ditch fallback only.
        old_suppress = getattr(self, "_suppress_mode_undo", False)
        self._suppress_mode_undo = True
        try:
            self.mode_chg(4)
            if selected_ids:
                self.reselect_text_items(selected_ids)
        finally:
            self._suppress_mode_undo = old_suppress

    def on_table_item_changed(self, item):
        try:
            self.tab.resizeRowToContents(item.row())
        except Exception:
            pass
        if self.idx not in self.data:
            return
        curr_data = self.data.get(self.idx)
        if not curr_data or 'data' not in curr_data:
            return

        row = item.row()
        col = item.column()

        # 텍스트 라인 수정은 현재 페이지 data 리스트만 저장하는 경량 Undo로 처리한다.
        # 비교 기준은 curr_data가 아니라 셀 생성 시 UserRole에 넣어둔 직전 텍스트다.
        # 이렇게 해야 표 편집/동기화 순서가 꼬여도 수정 전 상태를 안정적으로 잡을 수 있다.
        if row > 0 and col in (2, 3):
            data_index = row - 1
            if 0 <= data_index < len(curr_data['data']):
                key = 'text' if col == 2 else 'translated_text'
                new_text = self.strip_object_display_prefix_for_data(item.text() or '')
                role_old = item.data(Qt.ItemDataRole.UserRole)
                old_text = str(role_old if role_old is not None else curr_data['data'][data_index].get(key, '') or '')
                if new_text != str(item.text() or ''):
                    try:
                        item.setText(new_text)
                    except Exception:
                        pass
                if new_text != old_text:
                    target_id = curr_data['data'][data_index].get('id')
                    try:
                        before = self.text_engine.snapshot_items(curr_data.get('data', []), indexes=[data_index])
                        rec = self.text_engine.make_diff_record(
                            page_idx=int(getattr(self, 'idx', 0) or 0),
                            mode=int(self.cb_mode.currentIndex()),
                            reason='원문 텍스트 수정' if col == 2 else '번역문 텍스트 수정',
                            before_items=before,
                            selected_ids=[target_id],
                            fields=[key],
                        )
                        self.undo_push_page(rec, page_idx=getattr(self, 'idx', 0))
                    except Exception:
                        self.undo_push_text_line('원문 텍스트 수정' if col == 2 else '번역문 텍스트 수정')
                    curr_data['data'][data_index][key] = new_text
                    item.setData(Qt.ItemDataRole.UserRole, new_text)
                    if col == 3:
                        try:
                            self.shrink_text_rect_to_content(curr_data['data'][data_index])
                        except Exception:
                            pass
                    if self.cb_mode.currentIndex() == 4:
                        try:
                            if target_id is not None:
                                if not self.refresh_final_text_items_by_ids([target_id]):
                                    self.schedule_final_text_scene_refresh(60)
                            else:
                                self.schedule_final_text_scene_refresh(60)
                        except Exception:
                            self.schedule_final_text_scene_refresh(60)
                    try:
                        self.finalize_text_change(ids=[target_id], fields=[key], reason='표 텍스트 수정', delay_ms=1800)
                    except Exception:
                        try:
                            if hasattr(self, 'text_engine') and self.text_engine is not None:
                                self.text_engine.mark_dirty(int(getattr(self, 'idx', 0) or 0), [target_id], [key])
                            self.mark_active_page_dirty('text')
                            self.schedule_deferred_auto_save_project(1800)
                        except Exception:
                            pass
            return

        if col != 1:
            return

        # 체크박스는 현재 중앙 정렬용 QWidget으로 표시되지만,
        # 구버전 프로젝트/예외 상황에서 QTableWidgetItem 신호가 들어오면 같은 처리 함수로 넘긴다.
        try:
            is_checked = item.checkState() == Qt.CheckState.Checked
        except Exception:
            is_checked = self.get_table_check_state(row)
        self.apply_table_check_state(row, is_checked)

    def upd_map(self):
        curr_data = self.data[self.idx]
        active_count = 0
        self._table_check_lock = True
        self.tab.blockSignals(True)
        try:
            for row in range(1, self.tab.rowCount()):
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr_data['data']):
                    continue
                is_checked = self.get_table_check_state(row)
                curr_data['data'][data_index]['use_inpaint'] = is_checked
                if is_checked:
                    active_count += 1
                self.set_table_row_visual(row, is_checked)

            all_checked = active_count == len(curr_data['data']) and len(curr_data['data']) > 0
            self.set_table_check_state(0, all_checked)
            self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)
            self._table_check_lock = False

        if self.cb_mode.currentIndex() in [1, 2, 3]:
            self.refresh_boxes_only()
        self.log(f"🔄 갱신 완료 (활성: {active_count}개) - 비활성 행은 붉게 표시됨")
        try:
            self.schedule_deferred_auto_save_project()
        except Exception:
            self.auto_save_project()

    def schedule_deferred_auto_save_project(self, delay_ms=1800):
        """YSBT는 건드리지 않고 workspace 복구 체크포인트만 지연 저장한다.

        텍스트 드래그/줌/스타일 조정 중 매 프레임 저장하면 렉이 생긴다.
        그래서 호출부 호환 이름은 유지하되, 실제 동작은:
        - dirty/미저장 표시
        - 현재 페이지를 복구 체크포인트 대상으로 표시
        - delay_ms 뒤 workspace/project.json에 page delta 반영
        이 세 가지로 제한한다.
        """
        if (
            getattr(self, "_suppress_work_cache_dirty", False)
            or getattr(self, "is_loading_project", False)
            or not getattr(self, "project_dir", None)
            or not getattr(self, "paths", None)
        ):
            return
        try:
            self.auto_save_enabled = False
        except Exception:
            pass
        try:
            self.mark_current_page_for_recovery_checkpoint("checkpoint_text")
        except Exception:
            try:
                self.has_unsaved_changes = True
                self.update_window_title()
            except Exception:
                pass
        try:
            self.schedule_workspace_checkpoint(delay_ms, reason="deferred_auto_save")
        except Exception:
            try:
                self.auto_save_project()
            except Exception:
                pass

    def mode_chg(self, i):
        try:
            self.audit_boundary_event("MODE_CHG_ENTER", new_mode=i, old_mode=getattr(self, "_current_work_mode", getattr(self, "last_mode", None)), stack=True)
        except Exception:
            pass
        try:
            self._suppress_view_dirty_until = __import__("time").time() + 0.7
        except Exception:
            pass
        # cb_mode.currentIndexChanged는 콤보박스 값이 이미 바뀐 뒤 들어오므로,
        # 직전 탭은 cb_mode가 아니라 별도 추적값(_current_work_mode)을 기준으로 잡는다.
        old_mode_for_undo = int(getattr(self, "_current_work_mode", getattr(self, "last_mode", 0)) or 0)
        new_mode_for_undo = int(i)
        # 마스크 토글처럼 "같은 탭을 새 마스크 슬롯으로 다시 그리기" 위한 내부 갱신은
        # 사용자가 탭을 이동한 작업이 아니므로 Undo 스택에 탭 변경으로 기록하면 안 된다.
        suppress_mode_undo = bool(
            getattr(self, "_suppress_mode_undo", False)
            or getattr(self, "_mask_toggle_refreshing", False)
        )
        track_mode_change = (
            old_mode_for_undo != new_mode_for_undo
            and not suppress_mode_undo
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
            and not getattr(self, "_project_undo_restore_lock", False)
            and bool(getattr(self, "paths", []))
        )
        if track_mode_change:
            try:
                old_view_state = self.capture_view_state()
                self.project_ui_view_states[self.view_state_key(self.idx, old_mode_for_undo)] = old_view_state
                if hasattr(self, "layer_engine") and self.layer_engine is not None:
                    self.layer_engine.push_mode_undo(self, self.idx, old_mode_for_undo, new_mode_for_undo, old_view_state)
                    self.layer_engine.remember_mode_state(self.idx, old_mode_for_undo, old_view_state)
                else:
                    rec = self.make_ui_undo_record("작업 탭 변경", self.idx, mode=old_mode_for_undo)
                    rec["view_state"] = copy.deepcopy(old_view_state or {})
                    rec["view_only"] = True
                    rec["ui_only"] = True
                    rec["_undo_scope"] = "page"
                    self.undo_push_page(rec, page_idx=self.idx)
            except Exception:
                pass

        try:
            if hasattr(self, "layer_engine") and self.layer_engine is not None:
                self.layer_engine.begin_switch(self.idx, old_mode_for_undo, new_mode_for_undo)
        except Exception:
            pass

        if getattr(self, "inline_text_editor", None) is not None:
            self.finish_inline_text_edit(commit=True, refresh=False)

        # 이전 마스크 탭에서 벗어나기 전에 자동 반영.
        # 단, 페이지 로딩/일괄 작업 중에는 절대 화면 마스크를 저장하지 않는다.
        should_commit_mask_on_leave = True
        try:
            if hasattr(self, "layer_engine") and self.layer_engine is not None:
                should_commit_mask_on_leave = self.layer_engine.should_commit_mask_before_leave(self, self.idx, self.last_mode)
        except Exception:
            should_commit_mask_on_leave = True
        if (
            should_commit_mask_on_leave
            and not self.is_page_loading
            and not self.is_batch_running
            and not getattr(self, "_skip_mode_mask_commit", False)
            and self.last_mode in [2, 3]
        ):
            curr = self.data.get(self.idx)
            m = self.view.get_mask_np()
            if curr is not None and m is not None:
                self.set_active_mask(curr, m, self.last_mode)
                curr['mask_toggle_enabled'] = self.mask_toggle_enabled
                self.schedule_deferred_auto_save_project()

        should_commit_paint_on_leave = True
        try:
            if hasattr(self, "layer_engine") and self.layer_engine is not None:
                should_commit_paint_on_leave = self.layer_engine.should_commit_paint_before_leave(self, self.idx, self.last_mode)
        except Exception:
            should_commit_paint_on_leave = True
        if (
            should_commit_paint_on_leave
            and not self.is_page_loading
            and not self.is_batch_running
            and self.last_mode == 4
        ):
            curr = self.data.get(self.idx)
            if curr is not None and hasattr(self.view, "get_final_paint_png_bytes"):
                curr['final_paint'] = self.view.get_final_paint_png_bytes()
                if hasattr(self.view, "get_final_paint_above_png_bytes"):
                    curr['final_paint_above'] = self.view.get_final_paint_above_png_bytes()
                self.schedule_deferred_auto_save_project()

        # 사용자가 작업 탭을 바꾸면 브러시/지우개/요술봉/텍스트 입력 같은 도구는
        # 새 탭에서 그대로 이어지면 오작동하기 쉽다. 탭 이동은 항상 이동 모드로 정리한다.
        auto_move_on_tab_change = (
            old_mode_for_undo != new_mode_for_undo
            and not suppress_mode_undo
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
            and not getattr(self, "_project_undo_restore_lock", False)
        )
        if auto_move_on_tab_change and getattr(self.view, "draw_mode", None):
            self.set_tool(None)

        preserve_view_state = (not self.is_page_loading) and bool(self.view.scene.items())
        saved_transform = self.view.transform() if preserve_view_state else None
        saved_h_scroll = self.view.horizontalScrollBar().value() if preserve_view_state else None
        saved_v_scroll = self.view.verticalScrollBar().value() if preserve_view_state else None

        def restore_view_state_later():
            if not preserve_view_state or saved_transform is None:
                return

            def _restore():
                try:
                    self.view.setTransform(saved_transform)
                    if saved_h_scroll is not None:
                        self.view.horizontalScrollBar().setValue(saved_h_scroll)
                    if saved_v_scroll is not None:
                        self.view.verticalScrollBar().setValue(saved_v_scroll)
                except Exception:
                    pass

            # centerOn은 스크롤바 정수 반올림 때문에 반복 탭 이동 시 좌우로 누적 오차가 생길 수 있다.
            # 그래서 저장된 스크롤바 값을 직접 복원한다.
            QTimer.singleShot(0, _restore)
            QTimer.singleShot(60, _restore)

        self.last_mode = i
        self._current_work_mode = i
        self.update_paint_toolbar_visibility()

        curr = self.data.get(self.idx)
        if not curr:
            self.update_text_style_control_state([])
            self._hide_legacy_option_bars()
            try:
                self.refresh_shared_option_bar()
            except Exception:
                pass
            return

        if i != 4 and getattr(self.view, "draw_mode", None) == 'paste_text':
            self.set_tool(None)

        if i not in [2, 3, 4] and getattr(self.view, "draw_mode", None) == 'magic_wand':
            self.set_tool(None)
        if i not in [2, 3] and getattr(self.view, "draw_mode", None) in ('mask_wrap', 'mask_cut'):
            self.set_tool(None)
        if i not in [1, 2, 3] and getattr(self.view, "draw_mode", None) == 'ocr_region_select':
            self.set_tool(None)
        if i not in [2, 3, 4] and getattr(self.view, "draw_mode", None) == 'area_paint':
            self.set_tool(None)
        self._hide_legacy_option_bars()
        self.update_final_paint_option_bar_visibility()
        try:
            self.refresh_shared_option_bar()
        except Exception:
            pass

        source_img = self.get_source_display_image(self.idx)
        if i in (2, 3):
            try:
                self.ensure_page_masks_loaded(self.idx)
                self.touch_page_mask_cache(self.idx)
                self.trim_page_mask_cache(keep_indices=[self.idx])
            except Exception:
                pass

        # 3-5 후속 안정화: 같은 페이지 안의 작업탭 이동은 base image를 재사용한다.
        # 이전 set_image()/set_overlay() 전체 rebuild 경로는 큰 이미지에서 탭 전환 렉과
        # 불필요한 paint history clear를 만들었다.
        try:
            if i in (0, 1, 2, 3):
                self.view.set_layer_base_image(source_img, key=self._work_mode_base_key(self.idx, "source", curr), fit=not preserve_view_state, clear_paint_history=False)
                self.view.clear_mode_layers(clear_boxes=True, clear_text=True, clear_mask=True, clear_final_paint=True)
                if i == 1:
                    self.view.draw_static_boxes(curr['data'])
                elif i in (2, 3):
                    color = QColor(0, 0, 255, 100) if i == 3 else QColor(255, 0, 0, 100)
                    if hasattr(self.view, "set_mask_overlay_layer"):
                        self.view.set_mask_overlay_layer(self.get_active_mask(curr, i), color)
                    else:
                        self.view.set_overlay(source_img, self.get_active_mask(curr, i), color, fit=not preserve_view_state)
                    self.view.draw_static_boxes(curr['data'])
                self.refresh_ocr_region_overlay()
            elif i == 4:
                self.ensure_item_style_defaults_for_page(self.idx)
                final_base = self.final_base_image_for_page(self.idx)
                self.view.set_layer_base_image(final_base, key=self._work_mode_base_key(self.idx, "final", curr), fit=not preserve_view_state, clear_paint_history=False)
                self.view.clear_mode_layers(clear_boxes=True, clear_text=True, clear_mask=True, clear_final_paint=True)
                self.view.set_final_paint_overlay(curr.get('final_paint'), curr.get('final_paint_above'), fit=False)
                self.update_final_paint_z_order()
                self.view.draw_movable_texts(
                    curr['data'],
                    self.cb_font.currentFont().family(),
                    self.sb_font_size.value(),
                    self.sb_strk.value(),
                    show_text=self.cb_show_final_text.isChecked(),
                    text_color=self.default_text_color,
                    stroke_color=self.default_stroke_color,
                    align=self.default_align,
                )
        except Exception:
            # 안전 폴백: 가벼운 레이어 갱신에 실패하면 기존 전체 rebuild 경로로 복구한다.
            if i == 0:
                self.view.set_image(source_img, fit=not preserve_view_state)
                self.refresh_ocr_region_overlay()
            elif i == 1:
                self.view.set_image(source_img, fit=not preserve_view_state)
                self.view.draw_static_boxes(curr['data'])
                self.refresh_ocr_region_overlay()
            elif i == 2:
                self.view.set_overlay(source_img, self.get_active_mask(curr, 2), QColor(255, 0, 0, 100), fit=not preserve_view_state)
                self.view.draw_static_boxes(curr['data'])
                self.refresh_ocr_region_overlay()
            elif i == 3:
                self.view.set_overlay(source_img, self.get_active_mask(curr, 3), QColor(0, 0, 255, 100), fit=not preserve_view_state)
                self.view.draw_static_boxes(curr['data'])
                self.refresh_ocr_region_overlay()
            elif i == 4:
                self.ensure_item_style_defaults_for_page(self.idx)
                final_base = self.final_base_image_for_page(self.idx)
                self.view.set_image(final_base, fit=not preserve_view_state)
                self.view.set_final_paint_overlay(curr.get('final_paint'), curr.get('final_paint_above'), fit=False)
                self.update_final_paint_z_order()
                self.view.draw_movable_texts(
                    curr['data'],
                    self.cb_font.currentFont().family(),
                    self.sb_font_size.value(),
                    self.sb_strk.value(),
                    show_text=self.cb_show_final_text.isChecked(),
                    text_color=self.default_text_color,
                    stroke_color=self.default_stroke_color,
                    align=self.default_align,
                )

        restore_view_state_later()
        try:
            if hasattr(self, "layer_engine") and self.layer_engine is not None:
                self.layer_engine.end_switch(self.idx, i)
        except Exception:
            pass
        try:
            self.refresh_source_compare_view(fit=False)
            QTimer.singleShot(80, lambda: self.schedule_source_compare_sync(120))
        except Exception:
            pass

        if track_mode_change:
            try:
                self.remember_current_view_state()
                # 탭 변경은 현재 페이지 내부 보기 동작이다. 저장 dirty/project save를 깨우지 않는다.
                if hasattr(self, "layer_engine") and self.layer_engine is not None:
                    self.layer_engine.remember_mode_state(self.idx, i, self.capture_view_state())
            except Exception:
                pass

    def prev(self):
        if not self.paths:
            return

        try:
            self.prepare_current_page_boundary("page change")
        except Exception:
            try:
                self.undo_clear_current_page("page change")
            except Exception:
                pass
            self.commit_current_page_ui_to_data()
            self.remember_current_view_state()
        self.idx = (self.idx - 1) % len(self.paths)
        self.load()
        self.restore_current_view_state_later()
        self.schedule_current_page_tab_visible()

    def next(self):
        if not self.paths:
            return

        try:
            self.prepare_current_page_boundary("page change")
        except Exception:
            try:
                self.undo_clear_current_page("page change")
            except Exception:
                pass
            self.commit_current_page_ui_to_data()
            self.remember_current_view_state()
        self.idx = (self.idx + 1) % len(self.paths)
        self.load()
        self.restore_current_view_state_later()
        self.schedule_current_page_tab_visible()

    def jump_page(self):
        if not self.paths:
            return
        num, ok = QInputDialog.getInt(
            self,
            self.tr_ui("페이지 이동"),
            self.tr_msg(f"페이지 (1~{len(self.paths)}):"),
            self.idx + 1,
            1,
            len(self.paths),
        )
        if ok:
            if num - 1 == self.idx:
                return
            try:
                self.prepare_current_page_boundary("page change")
            except Exception:
                try:
                    self.undo_clear_current_page("page change")
                except Exception:
                    pass
                self.commit_current_page_ui_to_data()
                self.remember_current_view_state()
            self.idx = num - 1
            self.load()
            self.restore_current_view_state_later()
            self.schedule_current_page_tab_visible(center=True)

    def qt_pixmap_from_image_source(self, img):
        """출력용 Qt 렌더에 사용할 QPixmap을 만든다.
        viewer._np2pix와 같은 기준으로 BGR(OpenCV) 이미지를 Qt 화면 색상에 맞춘다.
        """
        try:
            if img is None:
                return QPixmap()

            if isinstance(img, (bytes, bytearray)):
                qimg = QImage.fromData(bytes(img))
                if not qimg.isNull():
                    return QPixmap.fromImage(qimg)
                return QPixmap()

            if isinstance(img, str):
                qimg = QImage(img)
                if not qimg.isNull():
                    return QPixmap.fromImage(qimg)
                # 한글/특수 경로 방어: cv2로 읽어서 다시 넘긴다.
                try:
                    arr = np.fromfile(img, np.uint8)
                    decoded = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                    if decoded is not None:
                        return self.qt_pixmap_from_image_source(decoded)
                except Exception:
                    pass
                return QPixmap()

            if isinstance(img, QImage):
                return QPixmap.fromImage(img)

            if isinstance(img, QPixmap):
                return img

            if isinstance(img, np.ndarray):
                if img.ndim == 2:
                    h, w = img.shape[:2]
                    qimg = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
                    return QPixmap.fromImage(qimg)

                if img.ndim == 3:
                    h, w, c = img.shape
                    if c == 3:
                        # OpenCV BGR → Qt RGB. viewer._np2pix와 동일한 처리.
                        qimg = QImage(img.data, w, h, c * w, QImage.Format.Format_RGB888).rgbSwapped().copy()
                        return QPixmap.fromImage(qimg)
                    if c == 4:
                        # RGBA 계열 페인트 레이어 등은 viewer 기준과 맞춰 그대로 처리한다.
                        qimg = QImage(img.data, w, h, c * w, QImage.Format.Format_RGBA8888).copy()
                        return QPixmap.fromImage(qimg)
        except Exception:
            pass
        return QPixmap()

    def save_qimage_for_output(self, qimg, path, image_format=None, quality=None):
        """QImage를 출력 옵션 형식(PNG/JPG/WebP)으로 저장한다.
        Qt 플러그인이 특정 형식을 지원하지 않는 경우 PIL로 한 번 더 시도한다.
        """
        fmt = normalize_output_image_format(image_format or self.current_output_image_format())
        quality = normalize_output_image_quality(quality if quality is not None else self.current_output_image_quality())
        try:
            os.makedirs(os.path.dirname(str(path)), exist_ok=True)
        except Exception:
            pass
        qfmt = qt_image_format_name(fmt)
        try:
            if qimg.save(str(path), qfmt, quality):
                return True
        except Exception:
            pass
        try:
            from PIL import Image
            img = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = img.width(), img.height()
            ptr = img.bits()
            ptr.setsize(img.sizeInBytes())
            arr = np.array(ptr, dtype=np.uint8).reshape((h, w, 4)).copy()
            pil = Image.fromarray(arr, "RGBA")
            params = {}
            pil_fmt = pil_image_format_name(fmt)
            if fmt == "jpg":
                bg = Image.new("RGB", pil.size, (255, 255, 255))
                try:
                    bg.paste(pil, mask=pil.getchannel("A"))
                except Exception:
                    bg.paste(pil.convert("RGB"))
                pil = bg
                params.update({"quality": quality, "subsampling": 0, "optimize": True})
            elif fmt == "webp":
                params.update({"quality": quality, "method": 6})
            elif fmt == "png":
                params.update({"optimize": True})
            pil.save(str(path), pil_fmt, **params)
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 출력 이미지 저장 실패({fmt}): {e}")
            except Exception:
                pass
            return False

    def save_bgr_image_for_output(self, bgr_image, path, image_format=None, quality=None):
        fmt = normalize_output_image_format(image_format or self.current_output_image_format())
        quality = normalize_output_image_quality(quality if quality is not None else self.current_output_image_quality())
        try:
            os.makedirs(os.path.dirname(str(path)), exist_ok=True)
        except Exception:
            pass
        ext = output_image_extension(fmt)
        params = []
        try:
            if fmt == "jpg":
                params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
            elif fmt == "webp" and hasattr(cv2, "IMWRITE_WEBP_QUALITY"):
                params = [int(cv2.IMWRITE_WEBP_QUALITY), int(quality)]
            elif fmt == "png":
                params = [int(cv2.IMWRITE_PNG_COMPRESSION), 6]
            ok, buf = cv2.imencode(ext, bgr_image, params)
            if ok:
                buf.tofile(str(path))
                return True
        except Exception:
            pass
        try:
            from PIL import Image
            rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            pil_fmt = pil_image_format_name(fmt)
            params = {}
            if fmt == "jpg":
                params.update({"quality": quality, "subsampling": 0, "optimize": True})
            elif fmt == "webp":
                params.update({"quality": quality, "method": 6})
            elif fmt == "png":
                params.update({"optimize": True})
            pil.save(str(path), pil_fmt, **params)
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 출력 이미지 저장 실패({fmt}): {e}")
            except Exception:
                pass
            return False

    def effective_output_text_render_scale(self, base_w, base_h):
        """Return export text render supersampling scale with a memory safety cap."""
        try:
            scale = float(self.current_output_text_render_scale())
        except Exception:
            scale = 1.0
        if scale < 1.0:
            scale = 1.0
        # A very large 3x/4x render can allocate multiple huge QImages.
        # Keep the cap conservative; final output still succeeds, only the render scale is reduced.
        try:
            pixels = max(1, int(base_w) * int(base_h))
            max_pixels = int(getattr(self, "output_text_render_max_pixels", 120_000_000) or 120_000_000)
            while scale > 1.0 and pixels * scale * scale > max_pixels:
                if scale >= 4.0:
                    scale = 3.0
                elif scale >= 3.0:
                    scale = 2.0
                elif scale >= 2.0:
                    scale = 1.0
                else:
                    scale = 1.0
                    break
        except Exception:
            pass
        return max(1.0, float(scale))

    def render_current_final_scene_to_image_qt(self, result_path):
        """현재 최종화면에 실제로 떠 있는 QGraphicsScene을 그대로 PNG로 저장한다.

        Result 출력은 화면에서 보이는 최종 결과와 같아야 한다.
        이전 방식은 data를 기준으로 TypesettingItem을 다시 만들어 렌더했기 때문에,
        텍스트 편집/영역 재설정/변형 직후의 화면 상태와 몇 픽셀 어긋날 수 있었다.
        최종화면 탭에서 출력할 때는 현재 scene 자체를 렌더해서 화면 기준을 최우선으로 맞춘다.
        """
        try:
            if not hasattr(self, 'cb_mode') or self.cb_mode.currentIndex() != 4:
                return False
            scene = self._safe_graphics_scene()
            if scene is None:
                return False

            rect = scene.sceneRect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                rect = scene.itemsBoundingRect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                return False

            w = max(1, int(round(rect.width())))
            h = max(1, int(round(rect.height())))

            # 출력 PNG에는 선택 박스/점선/변형 핸들이 찍히면 안 된다.
            # 현재 scene을 그대로 쓰되, 렌더 순간에만 보조 가이드를 숨긴다.
            text_items = []
            old_suppress = []
            old_export_mask = []
            try:
                for it in scene.items():
                    if isinstance(it, TypesettingItem):
                        text_items.append(it)
                        old_suppress.append(bool(getattr(it, 'suppress_guides', False)))
                        old_export_mask.append(bool(getattr(it, '_export_mask_stroke', False)))
                        it.suppress_guides = True
                        # Heavy mask-stroke rendering is output/preview-only.
                        # It is intentionally not used in the live editor because
                        # many thick glow/stroke texts make navigation sluggish.
                        it._export_mask_stroke = True
                        it.update()
            except RuntimeError:
                return False

            output_scale = self.effective_output_text_render_scale(w, h)
            if output_scale > 1.0:
                render_w = max(1, int(round(w * output_scale)))
                render_h = max(1, int(round(h * output_scale)))
                hi = QImage(render_w, render_h, QImage.Format.Format_ARGB32_Premultiplied)
                hi.fill(Qt.GlobalColor.white)
                painter = QPainter(hi)
                try:
                    try:
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    except Exception:
                        pass
                    scene.render(painter, QRectF(0, 0, render_w, render_h), rect)
                finally:
                    painter.end()
                out = hi.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGB32)
            else:
                out = QImage(w, h, QImage.Format.Format_RGB32)
                out.fill(Qt.GlobalColor.white)
                painter = QPainter(out)
                try:
                    try:
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    except Exception:
                        pass
                    scene.render(painter, QRectF(0, 0, w, h), rect)
                finally:
                    painter.end()

            for it, old, old_mask in zip(text_items, old_suppress, old_export_mask):
                try:
                    it.suppress_guides = old
                    it._export_mask_stroke = old_mask
                    it.update()
                except RuntimeError:
                    pass
                except Exception:
                    pass

            try:
                self.audit_boundary_event("EXPORT_CURRENT_SCENE_TEXT_RENDER", scale=output_scale, width=w, height=h, throttle_ms=100)
            except Exception:
                pass

            try:
                os.makedirs(os.path.dirname(result_path), exist_ok=True)
            except Exception:
                pass
            if self.save_qimage_for_output(out, result_path):
                return True

            try:
                tmp_path = os.path.join(os.path.dirname(result_path), '__ysb_current_scene_result_tmp' + output_image_extension(self.current_output_image_format()))
                if self.save_qimage_for_output(out, tmp_path):
                    shutil.move(tmp_path, result_path)
                    return True
            except Exception:
                pass
            return False
        except Exception as e:
            try:
                self.log(f"⚠️ 현재 최종화면 기준 출력 실패: {e}")
            except Exception:
                pass
            return False

    def render_final_tab_scene_for_export_qt(self, result_path):
        """최종 탭 화면을 실제로 한 번 그린 뒤 그 QGraphicsScene을 그대로 저장한다.

        출력 PNG는 사용자가 최종 탭에서 보는 화면과 일치해야 한다.
        현재 작업 탭이 최종결과가 아닐 때 기존 코드는 data만으로 별도 scene을 재구성했는데,
        자동 조판/텍스트 변형 직후에는 화면 렌더 경로와 재구성 렌더 경로가 갈라질 수 있었다.
        그래서 출력 시 잠깐 최종결과 탭을 그려 현재 프로그램 화면과 같은 경로로 렌더한다.
        """
        if not hasattr(self, 'cb_mode'):
            return False

        old_mode = int(self.cb_mode.currentIndex())
        old_suppress_mode_undo = bool(getattr(self, '_suppress_mode_undo', False))
        old_skip_mode_mask_commit = bool(getattr(self, '_skip_mode_mask_commit', False))
        old_batch_running = bool(getattr(self, 'is_batch_running', False))
        old_draw_mode = getattr(getattr(self, 'view', None), 'draw_mode', None)
        old_suppress_option = bool(getattr(self, '_suppress_shared_option_refresh', False))
        old_export_guard = bool(getattr(self, '_export_rendering_guard', False))

        try:
            # 탭 임시 이동은 사용자 작업이 아니므로 Undo/마스크 자동 반영/도구 전환 부작용을 막는다.
            # 또한 출력 렌더 중에는 상단 텍스트 선택 옵션 위젯이 갱신되면 안 된다.
            self._suppress_mode_undo = True
            self._skip_mode_mask_commit = True
            self.is_batch_running = True
            self._export_rendering_guard = True
            self._suppress_shared_option_refresh = True
            try:
                self._hide_legacy_option_bars()
                self._clear_shared_option_left()
            except Exception:
                pass

            if old_mode != 4:
                self.cb_mode.blockSignals(True)
                try:
                    self.cb_mode.setCurrentIndex(4)
                finally:
                    self.cb_mode.blockSignals(False)
                # blockSignals로 신호를 막았으므로 직접 최종 탭을 그린다.
                self.mode_chg(4)
            else:
                # 이미 최종 탭이어도 data 변경 직후일 수 있으므로 한 번 새로 그린다.
                self.mode_chg(4)

            try:
                QApplication.processEvents()
            except Exception:
                pass

            return self.render_current_final_scene_to_image_qt(result_path)
        except Exception as e:
            try:
                self.log(f"⚠️ 최종화면 동기화 출력 실패: {e}")
            except Exception:
                pass
            return False
        finally:
            try:
                self._suppress_mode_undo = old_suppress_mode_undo
                self._skip_mode_mask_commit = old_skip_mode_mask_commit
                self.is_batch_running = old_batch_running
                self._export_rendering_guard = old_export_guard
                self._suppress_shared_option_refresh = old_suppress_option
            except Exception:
                pass

            if old_mode != 4:
                try:
                    self.cb_mode.blockSignals(True)
                    self.cb_mode.setCurrentIndex(old_mode)
                    self.cb_mode.blockSignals(False)
                    self._suppress_mode_undo = True
                    self._skip_mode_mask_commit = True
                    self.is_batch_running = True
                    self._export_rendering_guard = True
                    self._suppress_shared_option_refresh = True
                    self.mode_chg(old_mode)
                except Exception:
                    pass
                finally:
                    try:
                        self._suppress_mode_undo = old_suppress_mode_undo
                        self._skip_mode_mask_commit = old_skip_mode_mask_commit
                        self.is_batch_running = old_batch_running
                        self._export_rendering_guard = old_export_guard
                        self._suppress_shared_option_refresh = old_suppress_option
                    except Exception:
                        pass

            try:
                if old_draw_mode and hasattr(self, 'view'):
                    self.view.draw_mode = old_draw_mode
            except Exception:
                pass

            # 단일 출력에서는 즉시 원래 옵션바를 복구한다.
            # 일괄 출력 중에는 페이지마다 옵션바를 다시 붙이지 않고 마지막에만 복구한다.
            try:
                if not bool(getattr(self, "_batch_export_streaming", False)) and hasattr(self, "refresh_shared_option_bar"):
                    self.refresh_shared_option_bar()
            except Exception:
                pass

    def render_final_result_image_qt(self, result_path, bg_image, paint_above_data=None):
        """최종 PNG를 Qt 최종화면과 같은 렌더러로 다시 저장한다.

        엔진의 PIL 렌더는 검수용으로 충분하지만, QGraphicsPath 기반 최종화면과
        폰트 메트릭/기준선이 달라 텍스트 좌표가 몇 픽셀씩 어긋날 수 있다.
        그래서 result/Result_XXXX.png는 실제 최종화면과 같은 TypesettingItem을
        오프스크린 QGraphicsScene에 올려 다시 렌더한다.
        """
        curr = self.data.get(self.idx)
        if not curr:
            return False

        bg_pix = self.qt_pixmap_from_image_source(bg_image)
        if bg_pix.isNull() or bg_pix.width() <= 0 or bg_pix.height() <= 0:
            return False

        scene = QGraphicsScene()
        bg_item = scene.addPixmap(bg_pix)
        bg_item.setZValue(0)
        scene.setSceneRect(QRectF(0, 0, bg_pix.width(), bg_pix.height()))

        visible_items = []
        for d in curr.get('data', []):
            if not d.get('use_inpaint', True):
                continue
            if not str(d.get('translated_text', '') or '').strip() and not d.get('force_show'):
                continue
            visible_items.append(d)

        total_items = len(visible_items)
        for order_idx, d in enumerate(visible_items):
            item = TypesettingItem(
                d,
                self.cb_font.currentFont().family(),
                self.sb_font_size.value(),
                self.sb_strk.value(),
                None,
                text_color=self.default_text_color,
                stroke_color=self.default_stroke_color,
                align=self.default_align,
            )
            # 출력 PNG에는 작업용 점선 박스/선택 박스/변형 핸들을 찍지 않는다.
            item.suppress_guides = True
            # Use the heavy Photoshop-like mask stroke only in export/output preview.
            item._export_mask_stroke = True
            item.setSelected(False)
            item.setZValue(30 + (total_items - order_idx))
            scene.addItem(item)

        if paint_above_data is not None and hasattr(self, "view") and hasattr(self.view, "_paint_qimage_from_data"):
            try:
                above_qimg = self.view._paint_qimage_from_data(paint_above_data, bg_pix.width(), bg_pix.height())
                if not above_qimg.isNull():
                    above_item = scene.addPixmap(QPixmap.fromImage(above_qimg))
                    above_item.setZValue(80)
            except Exception:
                pass

        # Output-only high quality text engine.  The editor preview stays light,
        # but exported files can spend a little more time supersampling text/effects.
        # The scale is selected in the output options dialog.
        try:
            base_w = int(bg_pix.width())
            base_h = int(bg_pix.height())
            output_scale = self.effective_output_text_render_scale(base_w, base_h)
        except Exception:
            base_w, base_h, output_scale = bg_pix.width(), bg_pix.height(), 1.0

        if output_scale > 1.0:
            render_w = max(1, int(round(base_w * output_scale)))
            render_h = max(1, int(round(base_h * output_scale)))
            hi = QImage(render_w, render_h, QImage.Format.Format_ARGB32_Premultiplied)
            hi.fill(Qt.GlobalColor.white)
            painter = QPainter(hi)
            try:
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                except Exception:
                    pass
                scene.render(
                    painter,
                    QRectF(0, 0, render_w, render_h),
                    QRectF(0, 0, base_w, base_h),
                )
            finally:
                painter.end()
                scene.clear()
            out = hi.scaled(base_w, base_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGB32)
        else:
            out = QImage(base_w, base_h, QImage.Format.Format_RGB32)
            out.fill(Qt.GlobalColor.white)
            painter = QPainter(out)
            try:
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                except Exception:
                    pass
                scene.render(
                    painter,
                    QRectF(0, 0, base_w, base_h),
                    QRectF(0, 0, base_w, base_h),
                )
            finally:
                painter.end()
                scene.clear()

        try:
            self.audit_boundary_event("EXPORT_QT_SUPERSAMPLE_RENDER", scale=output_scale, width=base_w, height=base_h, throttle_ms=100)
        except Exception:
            pass

        try:
            os.makedirs(os.path.dirname(result_path), exist_ok=True)
        except Exception:
            pass

        if self.save_qimage_for_output(out, result_path):
            return True

        # 일부 환경에서 한글 경로 저장이 실패할 때를 대비한 임시 파일 우회.
        try:
            tmp_path = os.path.join(os.path.dirname(result_path), "__ysb_qt_result_tmp" + output_image_extension(self.current_output_image_format()))
            if self.save_qimage_for_output(out, tmp_path):
                shutil.move(tmp_path, result_path)
                return True
        except Exception:
            pass
        return False

    def _load_output_preview_qimage(self, image_path):
        """Load the already-encoded export file back into a QImage for preview.

        This makes Export Preview show the same result the user would get after
        saving, including JPG/WebP quality loss.  Qt may not be able to read WebP
        on some systems, so Pillow is used as a fallback.
        """
        try:
            qimg = QImage(str(image_path))
            if not qimg.isNull():
                return qimg
        except Exception:
            pass
        try:
            from PIL import Image
            pil = Image.open(str(image_path)).convert("RGBA")
            w, h = pil.size
            arr = np.array(pil, dtype=np.uint8)
            return QImage(arr.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
        except Exception:
            return QImage()

    def show_output_preview(self):
        """Render and show the current page exactly as export will save it.

        Export Preview is not a separate approximate renderer.  It opens the same
        output options dialog, renders through the same current-page export path,
        writes the encoded image into a temporary result folder, reads that exact
        encoded file back, and displays it in the preview viewer.
        """
        curr = self.data.get(self.idx) if hasattr(self, 'data') else None
        if not curr:
            try:
                QMessageBox.information(self, self.tr_ui("출력 미리보기"), self.tr_msg("미리보기할 현재 페이지 데이터가 없습니다."))
            except Exception:
                pass
            return

        # Preview must use the same options as actual export.  If the user cancels
        # here, no preview is generated and no project data is touched.
        try:
            if not self.open_output_options_dialog():
                try:
                    self.log("↩️ 출력 미리보기 취소")
                except Exception:
                    pass
                return
        except Exception as e:
            try:
                QMessageBox.warning(self, self.tr_ui("출력 미리보기"), self.tr_msg(f"출력 옵션 창을 열지 못했습니다: {e}"))
            except Exception:
                pass
            return

        tmp_dir = None
        tmp_path = None
        old_batch_running = bool(getattr(self, 'is_batch_running', False))
        try:
            try:
                self.show_task_progress_overlay(
                    self.tr_ui("출력 미리보기"),
                    self.tr_ui("실제 출력과 동일한 옵션으로 미리보기를 생성하는 중입니다..."),
                    total=7,
                    cancellable=False,
                )
                QApplication.processEvents()
            except Exception:
                pass

            try:
                self.update_task_progress_overlay(current=1, total=7, detail=self.tr_ui("현재 페이지 데이터를 정리하는 중입니다."))
                QApplication.processEvents()
            except Exception:
                pass
            try:
                self.commit_current_page_ui_to_data()
            except Exception:
                pass
            try:
                if self.cb_mode.currentIndex() == 4 and hasattr(self.view, "get_final_paint_png_bytes"):
                    curr['final_paint'] = self.view.get_final_paint_png_bytes()
                    if hasattr(self.view, "get_final_paint_above_png_bytes"):
                        curr['final_paint_above'] = self.view.get_final_paint_above_png_bytes()
            except Exception:
                pass
            try:
                self.ensure_item_style_defaults_for_page(self.idx)
            except Exception:
                pass

            try:
                self.update_task_progress_overlay(current=2, total=7, detail=self.tr_ui("출력 배경과 페인팅 레이어를 준비하는 중입니다."))
                QApplication.processEvents()
            except Exception:
                pass
            export_bg = curr.get('bg_clean')
            if export_bg is None:
                export_bg = self.final_base_image_for_page(self.idx)
            if export_bg is None:
                export_bg = self.get_source_display_image(self.idx)
            if export_bg is None:
                self.ensure_page_source_path(self.idx)
                try:
                    export_bg = self.paths[self.idx]
                except Exception:
                    export_bg = None
            if curr.get('final_paint'):
                try:
                    base_img = self.bg_clean_to_np_image(export_bg)
                    export_img = self.compose_final_paint_on_bgr(base_img, curr.get('final_paint'))
                    export_bg = self.encode_np_image_to_png_bytes(export_img) or export_img
                except Exception:
                    pass

            tmp_dir = tempfile.mkdtemp(prefix="ysb_output_preview_exact_")
            output_stem = self.output_display_stem(self.idx)
            clean_stem = self.get_page_stem(self.idx)
            source_path_for_export = None
            try:
                source_path_for_export = self.paths[self.idx] if self.paths and self.idx < len(self.paths) else self.path_for_output_display(self.idx)
            except Exception:
                source_path_for_export = self.path_for_output_display(self.idx)
            try:
                result_ext = output_image_extension(self.current_output_image_format())
            except Exception:
                result_ext = ".png"
            tmp_path = os.path.join(tmp_dir, "result", f"Result_{safe_page_file_stem(output_stem, 'output')}{result_ext}")

            try:
                self.update_task_progress_overlay(current=3, total=7, detail=self.tr_ui("기본 출력 이미지를 생성하는 중입니다."))
                QApplication.processEvents()
            except Exception:
                pass
            try:
                self.is_batch_running = True
                self.engine.export_project_result(
                    curr['data'],
                    source_path_for_export,
                    export_bg,
                    self.cb_font.currentFont().family(),
                    self.sb_strk.value(),
                    self.sb_font_size.value(),
                    output_root=tmp_dir,
                    output_name_stem=output_stem,
                    clean_name_stem=clean_stem,
                    output_image_format=self.current_output_image_format(),
                    clean_image_format=self.current_clean_image_format(),
                    output_image_quality=self.current_output_image_quality(),
                    clean_image_quality=self.current_clean_image_quality(),
                )
            finally:
                self.is_batch_running = old_batch_running

            try:
                self.update_task_progress_overlay(current=4, total=7, detail=self.tr_ui("최종화면 기준으로 텍스트를 렌더링하는 중입니다."))
                QApplication.processEvents()
            except Exception:
                pass
            qt_result_rendered = False
            try:
                # Use the same high-fidelity path as actual single export.  This may
                # temporarily sync the Final Result tab, but it guarantees that the
                # preview and the file export use identical conditions.
                qt_result_rendered = self.render_final_tab_scene_for_export_qt(tmp_path)
            except Exception:
                qt_result_rendered = False

            if not qt_result_rendered:
                try:
                    self.update_task_progress_overlay(current=5, total=7, detail=self.tr_ui("최종 이미지를 재구성 렌더링하는 중입니다."))
                    QApplication.processEvents()
                except Exception:
                    pass
                qt_result_rendered = self.render_final_result_image_qt(tmp_path, export_bg, curr.get('final_paint_above'))

            if curr.get('final_paint_above') and (not qt_result_rendered) and os.path.exists(tmp_path):
                try:
                    self.update_task_progress_overlay(current=6, total=7, detail=self.tr_ui("텍스트 위 페인팅을 합성하는 중입니다."))
                    QApplication.processEvents()
                except Exception:
                    pass
                try:
                    result_img = cv2.imdecode(np.fromfile(tmp_path, np.uint8), cv2.IMREAD_COLOR)
                    if result_img is not None:
                        result_img = self.compose_final_paint_on_bgr(result_img, curr.get('final_paint_above'))
                        self.save_bgr_image_for_output(result_img, tmp_path)
                except Exception as e:
                    try:
                        self.log(f"⚠️ 텍스트 위 페인팅 미리보기 합성 실패: {e}")
                    except Exception:
                        pass

            if not os.path.exists(tmp_path):
                raise RuntimeError(self.tr_msg("출력 미리보기를 생성하지 못했습니다."))

            try:
                self.update_task_progress_overlay(current=7, total=7, detail=self.tr_ui("실제 출력 파일과 같은 포맷으로 미리보기를 확인하는 중입니다."))
                QApplication.processEvents()
            except Exception:
                pass
            img = self._load_output_preview_qimage(tmp_path)
            if img.isNull():
                raise RuntimeError(self.tr_msg("출력 미리보기 이미지를 읽지 못했습니다."))
            pix = QPixmap.fromImage(img)

            try:
                self.hide_task_progress_overlay()
            except Exception:
                pass

            self._show_output_preview_dialog(pix, tmp_dir=tmp_dir, tmp_result_path=tmp_path)
        except Exception as e:
            try:
                self.hide_task_progress_overlay()
            except Exception:
                pass
            try:
                QMessageBox.warning(self, self.tr_ui("출력 미리보기"), self.tr_msg(f"출력 미리보기 생성 실패: {e}"))
            except Exception:
                pass
            try:
                self.log(f"⚠️ 출력 미리보기 생성 실패: {e}")
            except Exception:
                pass
        finally:
            try:
                self.is_batch_running = old_batch_running
            except Exception:
                pass
            try:
                if tmp_dir and os.path.isdir(tmp_dir):
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def _publish_output_preview_files(self, tmp_dir, tmp_result_path=None, parent=None):
        """Copy the already-rendered Export Preview result into the real output folders.

        Export Preview now creates the same encoded files as an actual export inside
        a temporary output root.  Pressing [Export] in the preview dialog should not
        render again; it should publish those exact files so the preview and saved
        result remain identical.
        """
        tmp_root = Path(str(tmp_dir or ""))
        if not tmp_root.exists():
            raise RuntimeError(self.tr_msg("미리보기 임시 출력 폴더를 찾지 못했습니다."))

        tmp_result = Path(str(tmp_result_path or "")) if tmp_result_path else None
        if tmp_result is not None and (not tmp_result.exists()):
            tmp_result = None
        if tmp_result is None:
            result_candidates = []
            try:
                result_candidates = sorted((tmp_root / "result").glob("Result_*"))
            except Exception:
                result_candidates = []
            tmp_result = result_candidates[0] if result_candidates else None
        if tmp_result is None or not tmp_result.exists():
            raise RuntimeError(self.tr_msg("미리보기 결과 파일이 없습니다."))

        out_root = Path(str(self.get_output_root()))
        result_dir = out_root / "result"
        clean_dir = out_root / "clean"
        scripts_dir = out_root / "scripts"
        for d in (result_dir, clean_dir, scripts_dir):
            d.mkdir(parents=True, exist_ok=True)

        output_stem = safe_page_file_stem(self.output_display_stem(self.idx), "output")
        clean_source_stem = safe_page_file_stem(self.get_page_stem(self.idx), "clean")
        clean_stem = clean_source_stem if clean_source_stem.lower().startswith("clean_") else f"clean_{clean_source_stem}"

        # Remove old variants for this page before copying the exact preview files.
        try:
            self.remove_output_format_variants(result_dir, output_stem, "Result_")
        except Exception:
            pass
        try:
            self.remove_output_format_variants(clean_dir, clean_stem, "")
            self.remove_output_format_variants(clean_dir, clean_source_stem, "")
            self.remove_output_format_variants(clean_dir, output_stem, "Clean_")
        except Exception:
            pass
        try:
            old_script = scripts_dir / f"Script_{output_stem}.jsx"
            if old_script.exists():
                old_script.unlink()
        except Exception:
            pass

        copied = []
        for sub in ("clean", "result", "scripts"):
            src_dir = tmp_root / sub
            dst_dir = out_root / sub
            if not src_dir.exists():
                continue
            try:
                for src in src_dir.iterdir():
                    if not src.is_file():
                        continue
                    dst = dst_dir / src.name
                    try:
                        shutil.copy2(str(src), str(dst))
                        copied.append(str(dst))
                    except Exception:
                        shutil.copy(str(src), str(dst))
                        copied.append(str(dst))
            except Exception as e:
                try:
                    self.log(f"⚠️ 미리보기 출력 파일 복사 실패({sub}): {e}")
                except Exception:
                    pass

        if not copied:
            raise RuntimeError(self.tr_msg("미리보기 출력 파일을 저장하지 못했습니다."))

        try:
            self.log("✅ 미리보기 결과를 실제 출력 폴더에 저장했습니다.")
            for path in copied:
                self.log(f"   - {path}")
        except Exception:
            pass
        return copied

    def _show_output_preview_dialog(self, pixmap, tmp_dir=None, tmp_result_path=None):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("출력 미리보기"))
        try:
            dlg.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))
        except Exception:
            pass
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        title = QLabel(self.tr_ui("출력 미리보기"))
        title.setStyleSheet("font-size:18px;font-weight:700;")
        layout.addWidget(title)
        info = QLabel(self.tr_ui("현재 페이지가 실제 출력에서 어떻게 보일지 렌더링한 미리보기입니다. 텍스트 이펙트 미리보기가 꺼져 있어도 출력 기준 이펙트는 모두 적용됩니다."))
        info.setWordWrap(True)
        layout.addWidget(info)

        class OutputPreviewView(QGraphicsView):
            def __init__(self, pix, parent=None):
                super().__init__(parent)
                self._scene = QGraphicsScene(self)
                self._item = self._scene.addPixmap(pix)
                self._scene.setSceneRect(QRectF(0, 0, pix.width(), pix.height()))
                self.setScene(self._scene)
                self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
                self._fit_on_show = True

            def fit_to_window(self):
                rect = self._scene.sceneRect()
                if not rect.isNull():
                    self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
                    self._fit_on_show = False

            def actual_size(self):
                self.resetTransform()
                self._fit_on_show = False

            def zoom_by(self, factor):
                try:
                    factor = float(factor)
                except Exception:
                    factor = 1.0
                if factor <= 0:
                    return
                self.scale(factor, factor)
                self._fit_on_show = False

            def wheelEvent(self, event):
                try:
                    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                        delta = event.angleDelta().y()
                        self.zoom_by(1.25 if delta > 0 else 0.8)
                        event.accept()
                        return
                except Exception:
                    pass
                super().wheelEvent(event)

            def resizeEvent(self, event):
                super().resizeEvent(event)
                if self._fit_on_show:
                    QTimer.singleShot(0, self.fit_to_window)

        view = OutputPreviewView(pixmap, dlg)
        layout.addWidget(view, 1)

        bottom = QHBoxLayout()
        fit_btn = QPushButton(self.tr_ui("전체 보기"))
        fit_btn.clicked.connect(view.fit_to_window)
        bottom.addWidget(fit_btn)
        actual_btn = QPushButton(self.tr_ui("100%"))
        actual_btn.clicked.connect(view.actual_size)
        bottom.addWidget(actual_btn)
        zoom_out_btn = QPushButton(self.tr_ui("축소"))
        zoom_out_btn.clicked.connect(lambda: view.zoom_by(0.8))
        bottom.addWidget(zoom_out_btn)
        zoom_in_btn = QPushButton(self.tr_ui("확대"))
        zoom_in_btn.clicked.connect(lambda: view.zoom_by(1.25))
        bottom.addWidget(zoom_in_btn)
        bottom.addStretch(1)
        hint = QLabel(self.tr_ui("Ctrl+마우스휠로 확대/축소"))
        try:
            hint.setStyleSheet("color:#aaa;")
        except Exception:
            pass
        bottom.addWidget(hint)

        export_btn = QPushButton(self.tr_ui("출력"))
        export_btn.setToolTip(self.tr_ui("미리보기 이미지를 그대로 실제 출력 폴더에 저장하고 포토샵 스크립트도 함께 저장합니다."))

        def _export_preview_now():
            try:
                export_btn.setEnabled(False)
                export_btn.setText(self.tr_ui("출력 중..."))
                QApplication.processEvents()
                copied = self._publish_output_preview_files(tmp_dir, tmp_result_path, parent=dlg)
                export_btn.setText(self.tr_ui("출력 완료"))
                try:
                    QMessageBox.information(
                        dlg,
                        self.tr_ui("출력 미리보기"),
                        self.tr_msg("미리보기 결과를 실제 출력 폴더에 저장했습니다.")
                    )
                except Exception:
                    pass
            except Exception as e:
                try:
                    export_btn.setEnabled(True)
                    export_btn.setText(self.tr_ui("출력"))
                except Exception:
                    pass
                try:
                    QMessageBox.warning(
                        dlg,
                        self.tr_ui("출력 미리보기"),
                        self.tr_msg(f"미리보기 결과 출력 실패: {e}")
                    )
                except Exception:
                    pass
                try:
                    self.log(f"⚠️ 미리보기 결과 출력 실패: {e}")
                except Exception:
                    pass

        export_btn.clicked.connect(_export_preview_now)
        bottom.addWidget(export_btn)
        close_btn = QPushButton(self.tr_ui("닫기"))
        close_btn.clicked.connect(dlg.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        try:
            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else None
            max_w = int(geo.width() * 0.86) if geo else 1100
            max_h = int(geo.height() * 0.86) if geo else 820
        except Exception:
            max_w, max_h = 1100, 820
        try:
            dlg.resize(min(max_w, max(720, int(max_w))), min(max_h, max(560, int(max_h))))
        except Exception:
            dlg.resize(960, 720)
        QTimer.singleShot(0, view.fit_to_window)
        dlg.exec()

    def export_result(self, autosave=True, prompt_options=True):
        if prompt_options and not bool(getattr(self, "_suppress_export_options_dialog", False)):
            if not self.open_output_options_dialog():
                try:
                    self.log("↩️ 출력 취소")
                except Exception:
                    pass
                return
        curr = self.data.get(self.idx)
        if not curr:
            self.log("⚠️ 데이터 없음")
            return

        single_progress = not bool(getattr(self, "_batch_export_streaming", False))

        def _progress(current=None, total=6, detail=""):
            if not single_progress:
                return
            try:
                self.update_task_progress_overlay(current=current, total=total, detail=self.tr_ui(detail or "출력 진행 중..."))
                QApplication.processEvents()
            except Exception:
                pass

        if single_progress:
            try:
                self.show_task_progress_overlay(
                    self.tr_ui("개별 출력"),
                    self.tr_ui("출력 준비 중..."),
                    total=6,
                    cancellable=False,
                )
                QApplication.processEvents()
            except Exception:
                pass

        try:
            _progress(0, detail="현재 페이지 데이터를 정리하는 중입니다.")
            self.commit_current_page_ui_to_data()
            if self.cb_mode.currentIndex() == 4 and hasattr(self.view, "get_final_paint_png_bytes"):
                curr['final_paint'] = self.view.get_final_paint_png_bytes()
                if hasattr(self.view, "get_final_paint_above_png_bytes"):
                    curr['final_paint_above'] = self.view.get_final_paint_above_png_bytes()
            self.ensure_item_style_defaults_for_page(self.idx)
            export_bg = curr.get('bg_clean')
            if export_bg is None:
                export_bg = self.final_base_image_for_page(self.idx)
            if export_bg is None:
                export_bg = self.get_source_display_image(self.idx)
            if export_bg is None:
                self.ensure_page_source_path(self.idx)
                try:
                    export_bg = self.paths[self.idx]
                except Exception:
                    export_bg = None

            _progress(1, detail="출력 배경과 페인팅 레이어를 준비하는 중입니다.")
            if curr.get('final_paint'):
                base_img = self.bg_clean_to_np_image(export_bg)
                export_img = self.compose_final_paint_on_bgr(base_img, curr.get('final_paint'))
                export_bg = self.encode_np_image_to_png_bytes(export_img) or export_img
            self.ensure_page_source_path(self.idx)
            output_stem = self.output_display_stem(self.idx)
            source_path_for_export = self.paths[self.idx] if self.paths and self.idx < len(self.paths) else self.path_for_output_display(self.idx)

            _progress(2, detail="기본 출력 이미지를 생성하는 중입니다.")
            p = self.engine.export_project_result(
                curr['data'],
                source_path_for_export,
                export_bg,
                self.cb_font.currentFont().family(),
                self.sb_strk.value(),
                self.sb_font_size.value(),
                output_root=self.get_output_root(),
                output_name_stem=output_stem,
                clean_name_stem=self.get_page_stem(self.idx),
                output_image_format=self.current_output_image_format(),
                clean_image_format=self.current_clean_image_format(),
                output_image_quality=self.current_output_image_quality(),
                clean_image_quality=self.current_clean_image_quality(),
            )
            result_path = self.output_result_file_path(output_stem)

            # Result PNG는 포토샵 스크립트용 엔진 렌더(PIL)가 아니라 Qt 렌더로 다시 저장한다.
            # 최종화면 탭에서 출력하는 경우에는 data로 다시 조립하지 않고,
            # 현재 화면에 실제로 떠 있는 QGraphicsScene을 그대로 렌더한다.
            # 이렇게 해야 글꼴/영역 재설정/변형 직후의 화면과 출력 PNG가 1:1에 가깝게 맞는다.
            qt_result_rendered = False

            _progress(3, detail="최종화면 기준으로 텍스트를 렌더링하는 중입니다.")
            # Result PNG는 항상 최종결과 탭에서 보이는 화면과 같은 QGraphicsScene 렌더 경로를 사용한다.
            # 현재 탭이 최종결과가 아니어도 잠깐 최종 탭을 그린 뒤 저장하고 원래 탭으로 돌린다.
            qt_result_rendered = self.render_final_tab_scene_for_export_qt(result_path)
            if qt_result_rendered:
                self.log("🖼️ 최종화면 동기화 기준으로 최종 이미지 재저장")

            if not qt_result_rendered:
                _progress(4, detail="최종 이미지를 재구성 렌더링하는 중입니다.")
                qt_result_rendered = self.render_final_result_image_qt(result_path, export_bg, curr.get('final_paint_above'))
                if qt_result_rendered:
                    self.log("🖼️ 최종 이미지 Qt 재구성 렌더 기준으로 재저장")

            # 텍스트 위 페인팅 레이어는 텍스트 렌더링 이후 최종 PNG 위에 다시 합성한다.
            # 단, Qt 렌더가 성공한 경우에는 위 페인팅까지 함께 렌더했으므로 중복 합성하지 않는다.
            if curr.get('final_paint_above') and (not qt_result_rendered) and os.path.exists(result_path):
                _progress(5, detail="텍스트 위 페인팅을 합성하는 중입니다.")
                try:
                    result_img = cv2.imdecode(np.fromfile(result_path, np.uint8), cv2.IMREAD_COLOR)
                    if result_img is not None:
                        result_img = self.compose_final_paint_on_bgr(result_img, curr.get('final_paint_above'))
                        self.save_bgr_image_for_output(result_img, result_path)
                except Exception as e:
                    self.log(f"⚠️ 텍스트 위 페인팅 출력 합성 실패: {e}")

            _progress(6, detail="출력 완료")
            self.log(f"✅ 스크립트 저장: {p}")
            self.log(f"🖼️ 최종 이미지 저장: {result_path}")
            if autosave and not bool(getattr(self, "_batch_export_streaming", False)):
                self.auto_save_project()
        finally:
            if single_progress:
                try:
                    QTimer.singleShot(350, self.hide_task_progress_overlay)
                except Exception:
                    try:
                        self.hide_task_progress_overlay()
                    except Exception:
                        pass

    def macro_batch_page_selection(self):
        """매크로 실행 시작 시 1회 선택한 일괄 작업 페이지 범위를 반환한다."""
        if not getattr(self, "macro_running", False):
            return None, None
        indices = getattr(self, "_macro_batch_page_indices", None)
        if not isinstance(indices, (list, tuple)):
            return None, None
        valid = []
        seen = set()
        for raw in indices:
            try:
                i = int(raw)
            except Exception:
                continue
            if 0 <= i < len(self.paths) and i not in seen:
                valid.append(i)
                seen.add(i)
        if not valid:
            return None, None
        label = str(getattr(self, "_macro_batch_page_label", "") or self.tr_ui("전체 페이지"))
        return valid, label

    def choose_batch_page_indices_for_context(self, title, mode, *, default_all=False):
        """일반 실행은 페이지 선택창을 먼저 띄우고, 매크로 실행 중에는 공통 사전 선택값을 재사용한다."""
        try:
            if getattr(self, "macro_running", False):
                ctx = self.macro_batch_preflight_context_for_mode(mode) if hasattr(self, "macro_batch_preflight_context_for_mode") else {}
                if isinstance(ctx, dict):
                    indices = ctx.get("indices")
                    if isinstance(indices, (list, tuple)):
                        valid = []
                        seen = set()
                        for raw in indices:
                            try:
                                i = int(raw)
                            except Exception:
                                continue
                            if 0 <= i < len(self.paths) and i not in seen:
                                valid.append(i)
                                seen.add(i)
                        if valid:
                            label = str(ctx.get("label") or self.tr_ui("전체 페이지"))
                            self.log(f"🧩 [Macro] 일괄 페이지 범위 재사용: {title} / {label} / {len(valid)}페이지")
                            return valid, label
        except Exception:
            pass
        macro_indices, macro_label = self.macro_batch_page_selection()
        if macro_indices is not None:
            self.log(f"🧩 [Macro] 일괄 페이지 범위 재사용: {title} / {macro_label} / {len(macro_indices)}페이지")
            return macro_indices, macro_label
        if default_all:
            return list(range(len(self.paths))), self.tr_ui("전체 페이지")
        return self.choose_batch_page_indices(title, mode)

    def confirm_batch_operation(self, title, detail=None):
        # 매크로 안에 포함된 일괄 작업은 run_macro()에서 최초 1회만 확인한다.
        # 중간 단계마다 확인창이 뜨면 자동화 흐름이 끊기므로 여기서는 통과시킨다.
        if getattr(self, "macro_running", False):
            return True

        message = detail or f"{title}을(를) 실행할까요?"
        return QMessageBox.question(
            self,
            self.tr_msg(title),
            self.tr_msg(message),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes


    # ------------------------------------------------------------------
    # Batch job UX/policy helpers (QA7)
    # ------------------------------------------------------------------
    def batch_start_preview_delay_ms(self):
        """일괄 작업 시작 전 대상 페이지 수를 확인할 수 있게 최소 표시 시간을 둔다."""
        return 750

    def batch_mode_title(self, mode):
        return {
            "analyze": "일괄 분석",
            "reanalyze": "일괄 재분석",
            "translate": "일괄 번역",
            "inpaint": "일괄 인페인팅",
            "export": "일괄 출력",
            "extract_text": "일괄 지문 추출",
            "import_translation": "번역문 불러오기",
            "clear_translation": "일괄 번역문 내용 지우기",
            "clean_text": "일괄 텍스트 정리",
            "auto_text_size": "일괄 자동 텍스트 크기 조정",
            "auto_linebreak": "일괄 자동 줄 내림",
            "reset_text_rects": "일괄 현재 텍스트 기준으로 영역 재설정",
            "refresh": "일괄 텍스트 갱신",
        }.get(str(mode or ""), "일괄 작업")

    def batch_page_display_label(self, page_idx):
        try:
            page_no = int(page_idx) + 1
        except Exception:
            page_no = 0
        name = ""
        try:
            if 0 <= int(page_idx) < len(self.paths):
                name = os.path.basename(str(self.paths[int(page_idx)] or ""))
        except Exception:
            name = ""
        if not name:
            name = f"page{page_no:03d}"
        return f"{page_no}p - {name}"

    def wait_for_batch_preview(self, delay_ms=None):
        try:
            QApplication.processEvents()
            loop = QEventLoop()
            QTimer.singleShot(int(delay_ms or self.batch_start_preview_delay_ms()), loop.quit)
            loop.exec()
            QApplication.processEvents()
        except Exception:
            pass

    def _batch_result_new(self, title, mode, page_indices, page_label=""):
        return {
            "title": str(title or self.batch_mode_title(mode)),
            "mode": str(mode or "batch"),
            "page_label": str(page_label or ""),
            "total": len(page_indices or []),
            "done": [],
            "skipped": [],
            "failed": [],
            "pending": list(page_indices or []),
            "cancelled": False,
            "messages": [],
        }

    def _batch_result_record(self, page_idx, status="done", message=""):
        result = getattr(self, "_batch_result", None)
        if not isinstance(result, dict):
            return
        try:
            if page_idx in result.get("pending", []):
                result["pending"] = [x for x in result.get("pending", []) if x != page_idx]
        except Exception:
            pass
        status = str(status or "done").lower()
        if status not in ("done", "skipped", "failed"):
            status = "done"
        entry = {"index": page_idx, "label": self.batch_page_display_label(page_idx), "message": str(message or "")}
        result.setdefault(status, []).append(entry)
        if message:
            result.setdefault("messages", []).append(entry)

    def _batch_summary_text(self, result=None):
        result = result if isinstance(result, dict) else getattr(self, "_batch_result", {}) or {}
        title = str(result.get("title") or "일괄 작업")
        total = int(result.get("total") or 0)
        done = len(result.get("done") or [])
        skipped = len(result.get("skipped") or [])
        failed = len(result.get("failed") or [])
        pending = len(result.get("pending") or [])
        cancelled = bool(result.get("cancelled"))
        state = "취소됨" if cancelled else ("완료" if failed <= 0 else "완료(일부 실패)")
        lines = [
            f"{title} {state}",
            "",
            f"대상 페이지: {total}개",
            f"완료: {done}개",
            f"건너뜀: {skipped}개",
            f"실패: {failed}개",
            f"미처리: {pending}개",
        ]
        failed_items = result.get("failed") or []
        skipped_items = result.get("skipped") or []
        if failed_items:
            lines.append("")
            lines.append("실패한 페이지:")
            for item in failed_items[:8]:
                msg = item.get("message") or "오류"
                lines.append(f"- {item.get('label')}: {msg}")
            if len(failed_items) > 8:
                lines.append(f"- 외 {len(failed_items) - 8}개")
        if skipped_items:
            lines.append("")
            lines.append("건너뛴 페이지:")
            for item in skipped_items[:6]:
                msg = item.get("message") or "조건 없음"
                lines.append(f"- {item.get('label')}: {msg}")
            if len(skipped_items) > 6:
                lines.append(f"- 외 {len(skipped_items) - 6}개")
        lines.append("")
        lines.append("자세한 내용은 로그에서 확인할 수 있습니다.")
        return "\n".join(lines)

    def show_batch_result_summary(self, result=None):
        result = result if isinstance(result, dict) else getattr(self, "_batch_result", None)
        if not isinstance(result, dict):
            return
        try:
            if getattr(self, "macro_running", False) and hasattr(self, "macro_collect_batch_result"):
                if self.macro_collect_batch_result(result):
                    return
        except Exception:
            pass
        title = str(result.get("title") or "일괄 작업")
        text = self._batch_summary_text(result)
        try:
            if result.get("failed"):
                QMessageBox.warning(self, self.tr_ui(title), self.tr_msg(text))
            else:
                QMessageBox.information(self, self.tr_ui(title), self.tr_msg(text))
        except Exception:
            pass

    def batch_log_undo_boundary(self, reason):
        try:
            self.log(f"🧱 [Batch] Undo/Redo 스택 정리: {reason}")
        except Exception:
            pass
        try:
            self.undo_apply_boundary(f"batch_{reason}", "일괄 작업")
        except Exception:
            try:
                self.undo_clear_all_pages(reason=f"batch: {reason}")
            except Exception:
                pass

    def batch_prepare_progress(self, title, page_indices, page_label="", cancellable=True, start_delay=True):
        total = len(page_indices or [])
        lines = [f"대상 페이지: {total}개"]
        if page_label:
            lines[0] += f" ({page_label})"
        lines.extend([
            f"선택 페이지 진행: 0/{total}",
            "현재 페이지: 대기 중",
            "완료 0 / 건너뜀 0 / 실패 0",
            "잠시 후 작업을 시작합니다." if start_delay else "작업을 바로 시작합니다.",
        ])
        detail = "\n".join(lines)
        self.show_task_progress_overlay(title, detail, total=total, cancellable=cancellable)
        self.update_task_progress_overlay(current=0, total=total, detail=detail)
        try:
            QApplication.processEvents()
        except Exception:
            pass

    def batch_progress_detail(self, prefix, current, total, page_idx=None, extra=""):
        lines = [f"선택 페이지 진행: {current}/{total}"]
        if page_idx is not None:
            lines.append(f"현재 페이지: {self.batch_page_display_label(page_idx)}")
        else:
            lines.append("현재 페이지: 대기 중")
        done = len((getattr(self, "_batch_result", {}) or {}).get("done") or [])
        skipped = len((getattr(self, "_batch_result", {}) or {}).get("skipped") or [])
        failed = len((getattr(self, "_batch_result", {}) or {}).get("failed") or [])
        lines.append(f"완료 {done} / 건너뜀 {skipped} / 실패 {failed}")
        if extra:
            lines.append(str(extra))
        return "\n".join(lines)

    def run_page_queue_batch(self, title, mode, page_indices, page_label, page_func, *, visual=False, cancellable=True, restore_page=True, save_work_cache=True):
        """빠른 일괄 데이터 작업을 공통 페이지 큐로 실행한다.

        page_func(page_idx)는 (status, message) 또는 status 문자열을 반환한다.
        status: done / skipped / failed
        """
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(self, self.tr_ui("일괄 작업 중"), self.tr_msg("이미 일괄 작업이 진행 중입니다.\n현재 작업이 끝난 뒤 다시 실행해 주세요."))
            return None
        indices = []
        seen = set()
        for raw in page_indices or []:
            try:
                i = int(raw)
            except Exception:
                continue
            if 0 <= i < len(self.paths) and i not in seen:
                indices.append(i)
                seen.add(i)
        if not indices:
            self.log(f"⚠️ {title}: 작업할 페이지가 없습니다.")
            return None

        old_idx = int(getattr(self, "idx", 0) or 0)
        old_mode = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else 0
        result = self._batch_result_new(title, mode, indices, page_label)
        self._batch_result = result
        self._long_task_cancel_requested = False
        self.is_batch_running = True
        self.current_batch_mode = mode
        self.begin_busy_state(title)
        self.set_project_action_interlock(True)
        self.batch_log_undo_boundary("start")
        # visual=True인 분석/번역/인페인팅/출력류는 사용자가 처리 화면을 확인할 수 있도록
        # 시작 전 짧은 미리보기 시간을 둔다. 번역문 불러오기/텍스트 정리/자동 줄내림처럼
        # 화면 확인이 필요 없는 데이터 일괄 작업은 이 대기 시간을 건너뛴다.
        self.batch_prepare_progress(title, indices, page_label, cancellable=cancellable, start_delay=bool(visual))
        self.log(f"▶️ [Batch] {title} 시작: 대상 {len(indices)}개 ({page_label})")
        if visual:
            self.wait_for_batch_preview()
        else:
            try:
                QApplication.processEvents()
            except Exception:
                pass
        total = len(indices)
        completed = 0
        data_only = not bool(visual)
        # O단계: 데이터형 일괄 작업은 화면 없는 순차 처리로 유지한다.
        # 페이지를 실제로 넘기지 않고 data만 한 페이지씩 수정하며,
        # Undo는 일괄 작업 시작/종료 경계에서만 끊는다. 매 페이지마다
        # work cache 저장/Undo 경계/진행창 강제 갱신을 반복하면 300+장
        # 프로젝트에서 체감 속도가 크게 떨어진다.
        data_progress_interval = 5
        heavy_data_modes = {"import_clean_background", "use_background_as_source", "restore_original_source"}
        data_checkpoint_interval = None if str(mode or "") in heavy_data_modes else 25
        heavy_cleanup_interval = 3 if str(mode or "") == "import_clean_background" else 10
        data_changed_since_checkpoint = False
        try:
            for order, page_idx in enumerate(indices, 1):
                if bool(getattr(self, "_long_task_cancel_requested", False)):
                    result["cancelled"] = True
                    break
                try:
                    if (not data_only) or order == 1 or (order - 1) % data_progress_interval == 0:
                        self.update_task_progress_overlay(current=completed, total=total, detail=self.batch_progress_detail(title, completed, total, page_idx, "페이지 작업 중..."))
                    if visual:
                        self.show_batch_page_progress(page_idx, mode=mode, finished=False)
                    self.log(f"[Batch] 처리 시작: {order}/{total} - {self.batch_page_display_label(page_idx)}")
                    ret = page_func(page_idx)
                    if isinstance(ret, tuple):
                        status = ret[0] if len(ret) > 0 else "done"
                        message = ret[1] if len(ret) > 1 else ""
                    else:
                        status = ret or "done"
                        message = ""
                    self._batch_result_record(page_idx, status=status, message=message)
                    if str(status or "").lower() == "done":
                        data_changed_since_checkpoint = True
                    self.log(f"[Batch] 처리 {status}: {order}/{total} - {self.batch_page_display_label(page_idx)} {message or ''}".rstrip())
                except Exception as e:
                    self._batch_result_record(page_idx, status="failed", message=str(e))
                    self.log(f"[Batch] 처리 실패: {order}/{total} - {self.batch_page_display_label(page_idx)} - {e}")
                completed += 1

                if data_only:
                    # 데이터 작업은 페이지마다 디스크 저장하지 않고, 일정 단위로만 체크포인트 저장한다.
                    # 단, 클린본 불러오기처럼 이미지가 큰 작업은 일반 ProjectStore 저장 대신
                    # pending clean import 캐시를 쓰므로 여기서는 작업 캐시 저장을 건너뛴다.
                    if (
                        save_work_cache
                        and data_checkpoint_interval
                        and data_changed_since_checkpoint
                        and (completed % data_checkpoint_interval == 0 or completed >= total)
                    ):
                        try:
                            self.save_to_work_cache()
                            self.has_unsaved_changes = True
                            data_changed_since_checkpoint = False
                        except Exception as e:
                            self.log(f"⚠️ [Batch] 작업 캐시 체크포인트 저장 실패: {e}")
                else:
                    if save_work_cache:
                        try:
                            self.save_to_work_cache()
                            self.has_unsaved_changes = True
                        except Exception as e:
                            self.log(f"⚠️ [Batch] 작업 캐시 저장 실패: {e}")

                # 이미지 대량 데이터 작업은 페이지 처리 후 지역/Qt 캐시를 주기적으로 비운다.
                # 클린본 교체는 기존/신규 이미지가 겹치는 순간이 생길 수 있어 더 짧은 주기로 비운다.
                if data_only and str(mode or "") in heavy_data_modes and (completed % heavy_cleanup_interval == 0 or completed >= total):
                    try:
                        QPixmapCache.clear()
                    except Exception:
                        pass
                    try:
                        __import__("gc").collect()
                    except Exception:
                        pass

                # 일괄 작업은 작업 단위 자체가 Undo 경계다. 매 페이지마다 Undo를 다시 끊지 않는다.
                if (not data_only) or completed == total or completed % data_progress_interval == 0:
                    self.update_task_progress_overlay(current=completed, total=total, detail=self.batch_progress_detail(title, completed, total, page_idx, "페이지 작업 완료"))
                # 진행 UI는 QTimer 지연 갱신으로 처리한다.
                # 여기서 processEvents()를 호출하면 queued batch 신호가 현재 스택으로 재진입할 수 있다.
        finally:
            if data_only and save_work_cache and data_changed_since_checkpoint:
                try:
                    self.save_to_work_cache()
                    self.has_unsaved_changes = True
                except Exception as e:
                    self.log(f"⚠️ [Batch] 최종 작업 캐시 저장 실패: {e}")
            if restore_page and self.paths:
                try:
                    self.idx = max(0, min(old_idx, len(self.paths) - 1))
                    self.load()
                    if hasattr(self, "cb_mode") and 0 <= old_mode < self.cb_mode.count():
                        if self.cb_mode.currentIndex() != old_mode:
                            self.cb_mode.setCurrentIndex(old_mode)
                        else:
                            self.mode_chg(old_mode)
                except Exception:
                    pass
            self.batch_log_undo_boundary("finish")
            self.is_batch_running = False
            self.current_batch_mode = None
            self._active_task_worker = None
            self._batch_total = None
            self._batch_current_page_idx = None
            self.set_project_action_interlock(False)
            self.end_busy_state(title)
            try:
                self.hide_task_progress_overlay()
            except Exception:
                pass
            summary = self._batch_summary_text(result)
            self.log(summary.replace("\n", " | "))
            self.show_batch_result_summary(result)
        return result

    def release_batch_export_page_memory(self, page_index=None):
        """대용량 일괄 출력용 페이지 단위 메모리 정리.

        일괄 출력은 현재 화면과 같은 Qt 렌더 경로를 사용하므로, 한 페이지를 출력할 때마다
        QGraphicsScene/QImage/QPixmap/PIL/NumPy 참조가 여러 단계로 생길 수 있다.
        저장이 끝난 페이지는 즉시 화면 씬과 임시 레이어 참조를 비우고 Qt pixmap cache와
        Python GC를 돌려 다음 페이지가 이전 페이지 객체를 끌고 가지 않게 한다.
        """
        try:
            if not bool(getattr(self, "_batch_export_streaming", False)):
                return

            # 예약된 원본 비교창 동기화가 resize/paint 이후 늦게 실행되며 이미지를 다시 잡는 것을 막는다.
            try:
                self._source_compare_sync_pending = False
                self._source_compare_reverse_sync_pending = False
                if hasattr(self, "_block_source_compare_sync_temporarily"):
                    self._block_source_compare_sync_temporarily(180)
            except Exception:
                pass

            view = getattr(self, "view", None)
            try:
                if view is not None:
                    # 출력 직후 다음 페이지를 다시 load()할 것이므로 현재 작업 씬은 비워도 된다.
                    scene = getattr(view, "scene", None)
                    if scene is not None:
                        try:
                            scene.clear()
                        except Exception:
                            pass
                    for attr in (
                        "final_paint_item", "final_paint_above_item",
                        "final_paint_img", "final_paint_above_img",
                        "user_mask_item", "user_mask_img",
                        "paste_preview_item", "magic_wand_preview_item",
                        "mask_wrap_preview_item", "mask_cut_preview_item",
                        "ocr_region_preview_item", "quick_ocr_preview_item",
                    ):
                        try:
                            setattr(view, attr, None)
                        except Exception:
                            pass
            except Exception:
                pass

            # 클론창은 열린 상태를 유지하되, 일괄 출력 중 불필요하게 되살아나는 sync 예약만 비운다.
            try:
                if hasattr(self, "source_compare_quick_ocr_preview_item"):
                    self.source_compare_quick_ocr_preview_item = None
            except Exception:
                pass

            try:
                QPixmapCache.clear()
            except Exception:
                pass
            # 여기서 processEvents()를 돌리면 scene.clear()가 먼저 화면에 반영되어
            # 일괄 출력 진행창 뒤로 검은 화면이 번쩍이는 문제가 생긴다.
            # 캐시는 비우되 실제 화면 갱신은 다음 페이지 load()/진행창 update 타이밍에 맡긴다.
            gc.collect()
        except Exception as e:
            try:
                self.log(f"⚠️ 일괄 출력 페이지 메모리 정리 실패: {e}")
            except Exception:
                pass

    def run_batch_export_preview_sync(self, title="일괄 출력", page_indices=None, page_label=None):
        """일괄 출력도 개별 출력과 같은 최종화면(QGraphicsScene) 렌더 경로를 사용한다.

        기존 UniversalBatchWorker의 export 모드는 워커 스레드에서 engine.export_project_result()만 호출했다.
        그 경로는 data/PIL 기준 재구성 렌더라서, 최종결과 탭에 실제로 보이는 Qt 조판 화면과
        줄바꿈/기준선/변형 위치가 어긋날 수 있다. Qt 위젯/scene 렌더는 메인 스레드에서만 안전하므로
        일괄 출력만 메인 스레드 루프로 처리한다.
        """
        if not self.paths:
            self.log("⚠️ 파일 없음")
            return

        selected_indices = []
        seen = set()
        source_indices = page_indices if page_indices is not None else range(len(self.paths))
        for raw in source_indices:
            try:
                i = int(raw)
            except Exception:
                continue
            if 0 <= i < len(self.paths) and i not in seen:
                selected_indices.append(i)
                seen.add(i)
        if not selected_indices:
            self.log("⚠️ 출력할 페이지가 없습니다.")
            return

        old_idx = int(getattr(self, "idx", 0) or 0)
        old_mode = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else 0
        old_batch_mode = getattr(self, "current_batch_mode", None)
        old_streaming = bool(getattr(self, "_batch_export_streaming", False))
        total = len(selected_indices)
        ok_count = 0
        fail_count = 0
        self._batch_result = self._batch_result_new(title, "export", selected_indices, page_label or self.tr_ui('전체 페이지'))
        self._long_task_cancel_requested = False

        try:
            self.commit_current_page_ui_to_data()
        except Exception:
            pass

        export_ctx = self.macro_batch_preflight_context_for_mode("export") if hasattr(self, "macro_batch_preflight_context_for_mode") else {}
        if getattr(self, "macro_running", False) and (
            bool((export_ctx or {}).get("export_options_confirmed"))
            or bool(getattr(self, "_macro_preflight_export_options_confirmed", False))
        ):
            try:
                self.log("🧩 [Macro] 출력 옵션 재사용")
            except Exception:
                pass
        else:
            if not self.open_output_options_dialog():
                try:
                    self.log("↩️ 일괄 출력 취소")
                except Exception:
                    pass
                return

        self.is_batch_running = True
        self._batch_export_streaming = True
        self.current_batch_mode = "export"
        self.begin_busy_state(title)
        self.set_project_action_interlock(True)
        self.batch_log_undo_boundary("start")
        self.batch_prepare_progress(title, selected_indices, page_label or self.tr_ui('전체 페이지'), cancellable=True)
        self.log(f"📦 [Batch] 대용량 일괄 출력 모드: {total}/{len(self.paths)}페이지 ({page_label or self.tr_ui('전체 페이지')})")

        def _keep_export_progress_on_top():
            try:
                overlay = getattr(self, "_task_progress_overlay", None)
                if overlay is not None and overlay.isVisible():
                    overlay.raise_()
            except Exception:
                pass

        # 일괄 출력은 실제 최종결과 탭 렌더를 사용하지만, 매 페이지마다
        # 작업 탭 ↔ 최종결과 탭을 왕복하면 진행창 뒤 화면이 계속 번쩍인다.
        # 시작 시 한 번 최종결과 탭으로 고정하고, 끝날 때 원래 탭으로 복귀한다.
        try:
            if hasattr(self, "cb_mode") and self.cb_mode.currentIndex() != 4:
                self.cb_mode.blockSignals(True)
                try:
                    self.cb_mode.setCurrentIndex(4)
                finally:
                    self.cb_mode.blockSignals(False)
        except Exception:
            pass

        self.wait_for_batch_preview()
        _keep_export_progress_on_top()

        try:
            for seq_no, i in enumerate(selected_indices):
                if bool(getattr(self, "_long_task_cancel_requested", False)):
                    try:
                        self._batch_result["cancelled"] = True
                    except Exception:
                        pass
                    self.log("⏹️ 일괄 출력 취소 요청으로 중단")
                    break
                if i >= len(self.paths):
                    continue
                path = self.paths[i]
                base_name = os.path.basename(str(path or f"page{i + 1:03d}.png"))
                prefix = f"[{seq_no + 1}/{total} | {i + 1}p]"
                try:
                    self._batch_total = total
                    self._batch_progress_done = seq_no
                    self._batch_current_page_idx = i
                    self.update_task_progress_overlay(current=seq_no, total=total, detail=self.batch_progress_detail(title, seq_no, total, i, f"출력 중: {base_name}"))
                    _keep_export_progress_on_top()
                    self.log(f"{prefix} 출력: {base_name}")
                    self.idx = i
                    self.ensure_page_source_path(i)
                    # 진행 중에는 최종결과 탭을 유지한다. load() 직후 진행창을 다시 올려
                    # 씬 재구성/검은 빈 화면이 진행창을 덮는 것처럼 보이지 않게 한다.
                    try:
                        if hasattr(self, "cb_mode") and self.cb_mode.currentIndex() != 4:
                            self.cb_mode.blockSignals(True)
                            self.cb_mode.setCurrentIndex(4)
                            self.cb_mode.blockSignals(False)
                    except Exception:
                        pass
                    self.load()
                    _keep_export_progress_on_top()
                    QApplication.processEvents()
                    _keep_export_progress_on_top()

                    # export_result() 내부에서 최종결과 탭을 실제로 그린 뒤 그 scene을 저장한다.
                    # 이 경로를 타야 개별 출력과 일괄 출력의 결과가 같은 렌더러를 사용한다.
                    # 일괄 출력에서는 800MB+ YSBT가 매 페이지마다 통째로 자동저장되지 않게 막고,
                    # 페이지 저장 직후 씬/이미지 캐시를 해제한다.
                    self.export_result(autosave=False, prompt_options=False)
                    ok_count += 1
                    self._batch_result_record(i, status="done", message="출력 완료")
                    self._batch_progress_done = seq_no + 1
                    self.update_task_progress_overlay(current=seq_no + 1, total=total, detail=self.batch_progress_detail(title, seq_no + 1, total, i, "출력 완료"))
                    _keep_export_progress_on_top()
                    QApplication.processEvents()
                    _keep_export_progress_on_top()
                except Exception as e:
                    fail_count += 1
                    self._batch_result_record(i, status="failed", message=str(e))
                    self.log(f"{prefix} ❌ 출력 에러: {e}")
                finally:
                    self.release_batch_export_page_memory(i)
                    _keep_export_progress_on_top()

            if fail_count:
                self.log(f"✅ 일괄 출력 완료: 성공 {ok_count}개 / 실패 {fail_count}개")
            else:
                self.log(f"✅ 일괄 출력 완료! ({ok_count}/{total})")
        finally:
            # 원래 보던 페이지/작업 탭으로 복귀한다. 복귀 과정은 사용자 편집이 아니므로
            # mode_chg()의 Undo/마스크 커밋 부작용을 막는다.
            try:
                if self.paths:
                    self.idx = max(0, min(old_idx, len(self.paths) - 1))
                    self.cb_mode.blockSignals(True)
                    try:
                        self.cb_mode.setCurrentIndex(max(0, min(old_mode, self.cb_mode.count() - 1)))
                    finally:
                        self.cb_mode.blockSignals(False)
                    old_suppress = bool(getattr(self, '_suppress_mode_undo', False))
                    old_skip = bool(getattr(self, '_skip_mode_mask_commit', False))
                    try:
                        self._suppress_mode_undo = True
                        self._skip_mode_mask_commit = True
                        self.load()
                    finally:
                        self._suppress_mode_undo = old_suppress
                        self._skip_mode_mask_commit = old_skip
            except Exception:
                pass

            try:
                gc.collect()
                QPixmapCache.clear()
            except Exception:
                pass
            try:
                self.save_to_work_cache()
                self.has_unsaved_changes = True
            except Exception:
                pass
            self.batch_log_undo_boundary("finish")
            self.is_batch_running = False
            self._batch_export_streaming = old_streaming
            self.current_batch_mode = old_batch_mode
            self._batch_total = None
            self._batch_progress_done = 0
            self._batch_current_page_idx = None
            self.set_project_action_interlock(False)
            self.end_busy_state(title)
            try:
                self.hide_task_progress_overlay()
            except Exception:
                pass
            try:
                self._export_rendering_guard = False
                self._suppress_shared_option_refresh = False
                if hasattr(self, "refresh_shared_option_bar"):
                    self.refresh_shared_option_bar()
            except Exception:
                pass
            try:
                result = getattr(self, "_batch_result", None)
                if isinstance(result, dict):
                    summary = self._batch_summary_text(result)
                    self.log(summary.replace("\n", " | "))
                    self.show_batch_result_summary(result)
            except Exception:
                pass
            self.macro_mark_current_step_done(self.macro_batch_key_for_mode("export"))

    def parse_batch_page_selection_text(self, text, total_pages):
        """사용자 입력(1-3, 1~3, 1,2,3)을 0-base 페이지 인덱스 목록으로 변환한다."""
        raw = str(text or "").strip()
        if not raw:
            raise ValueError(self.tr_msg("페이지 선택 값을 입력해 주세요."))
        if total_pages <= 0:
            raise ValueError(self.tr_msg("작업할 페이지가 없습니다."))

        # 1 - 3 / 1 ~ 3처럼 공백이 들어간 범위도 허용한다.
        normalized = raw.replace("，", ",").replace("、", ",").replace("～", "~")
        normalized = re.sub(r"\s*([-~])\s*", r"\1", normalized)
        tokens = [t for t in re.split(r"[,\s]+", normalized) if t]
        if not tokens:
            raise ValueError(self.tr_msg("페이지 선택 값을 입력해 주세요."))

        selected = set()
        for token in tokens:
            range_match = re.fullmatch(r"(\d+)([-~])(\d+)", token)
            single_match = re.fullmatch(r"\d+", token)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(3))
                if start > end:
                    start, end = end, start
                if start < 1 or end > total_pages:
                    raise ValueError(self.tr_msg("페이지 범위가 프로젝트 페이지 수를 벗어났습니다."))
                for page_no in range(start, end + 1):
                    selected.add(page_no - 1)
            elif single_match:
                page_no = int(token)
                if page_no < 1 or page_no > total_pages:
                    raise ValueError(self.tr_msg("페이지 범위가 프로젝트 페이지 수를 벗어났습니다."))
                selected.add(page_no - 1)
            else:
                raise ValueError(self.tr_msg("페이지 선택 형식을 확인해 주세요."))

        if not selected:
            raise ValueError(self.tr_msg("작업할 페이지가 없습니다."))
        return sorted(selected)

    def choose_batch_page_indices(self, title, mode):
        """일괄 작업 실행 전에 전체/지정 페이지 범위를 고른다.

        배경을 원본으로 쓰기/원본으로 돌아가기는 단일 페이지로 빠르게 처리하는 경우가 많고,
        전체 페이지에 잘못 적용하면 위험하므로 현재 페이지 선택지를 최상단 기본값으로 제공한다.
        일반 일괄 작업은 기존처럼 전체 페이지/페이지 선택만 유지한다.
        """
        total_pages = len(self.paths)
        include_current_page = str(mode or "") in {"use_background_as_source", "restore_original_source"}
        try:
            current_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            current_idx = 0
        if current_idx < 0 or current_idx >= total_pages:
            current_idx = 0

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui(title))
        dialog.setModal(True)
        dialog.resize(440, 220 if include_current_page else 190)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        desc = QLabel(self.tr_ui("작업할 페이지 범위를 선택하세요."), dialog)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        rb_current = QRadioButton(self.tr_ui("현재 페이지"), dialog) if include_current_page else None
        rb_all = QRadioButton(self.tr_ui("전체 페이지"), dialog)
        rb_selected = QRadioButton(self.tr_ui("페이지 선택"), dialog)
        if rb_current is not None:
            rb_current.setChecked(True)
        else:
            rb_all.setChecked(True)

        edit_pages = QLineEdit(dialog)
        edit_pages.setPlaceholderText(self.tr_ui("예: 1-3, 1~3, 1,2,3"))
        edit_pages.setEnabled(False)

        selected_row = QHBoxLayout()
        selected_row.setContentsMargins(0, 0, 0, 0)
        selected_row.setSpacing(8)
        selected_row.addWidget(rb_selected)
        selected_row.addWidget(edit_pages, 1)

        if rb_current is not None:
            layout.addWidget(rb_current)
        layout.addWidget(rb_all)
        layout.addLayout(selected_row)

        note = QLabel(self.tr_ui("쉼표와 범위를 섞어서 입력할 수 있습니다."), dialog)
        note.setWordWrap(True)
        note.setStyleSheet("color: #8ea0b8;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        try:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("취소"))
        except Exception:
            pass
        layout.addWidget(buttons)

        def sync_enabled():
            edit_pages.setEnabled(rb_selected.isChecked())
            if rb_selected.isChecked():
                edit_pages.setFocus()

        rb_selected.toggled.connect(sync_enabled)
        rb_all.toggled.connect(sync_enabled)
        if rb_current is not None:
            rb_current.toggled.connect(sync_enabled)

        if rb_current is not None:
            result = {"accepted": False, "indices": [current_idx], "label": self.tr_ui("현재 페이지")}
        else:
            result = {"accepted": False, "indices": list(range(total_pages)), "label": self.tr_ui("전체 페이지")}

        def on_accept():
            try:
                if rb_current is not None and rb_current.isChecked():
                    result["indices"] = [current_idx]
                    result["label"] = self.tr_ui("현재 페이지")
                elif rb_selected.isChecked():
                    indices = self.parse_batch_page_selection_text(edit_pages.text(), total_pages)
                    result["indices"] = indices
                    result["label"] = edit_pages.text().strip()
                else:
                    result["indices"] = list(range(total_pages))
                    result["label"] = self.tr_ui("전체 페이지")
                result["accepted"] = True
                dialog.accept()
            except Exception as e:
                QMessageBox.warning(dialog, self.tr_ui("페이지 선택 오류"), str(e))

        buttons.accepted.connect(on_accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted or not result.get("accepted"):
            return None, None
        return result["indices"], result["label"]

    def run_batch(self, mode):
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(self, self.tr_ui("일괄 작업 중"), self.tr_msg("이미 일괄 작업이 진행 중입니다.\n현재 작업이 끝난 뒤 다시 실행해 주세요."))
            return
        if not self.ensure_engine_ready():
            return
        if not self.paths:
            self.log("⚠️ 파일 없음")
            return

        mode_names = {
            "analyze": "일괄 분석",
            "reanalyze": "일괄 재분석",
            "translate": "일괄 번역",
            "inpaint": "일괄 인페인팅",
            "refresh": "일괄 텍스트 갱신",
            "export": "일괄 출력",
        }
        title = mode_names.get(mode, "일괄 작업")

        if mode in ("analyze", "reanalyze"):
            if not self.check_ocr_api_or_alert():
                return
        if mode == "inpaint":
            if not self.check_inpaint_api_or_alert():
                return
        if mode == "translate":
            if not self.check_translation_api_key_or_alert(self.cb_trans_provider.currentData()):
                return
        selected_page_indices = list(range(len(self.paths)))
        selected_page_label = self.tr_ui("전체 페이지")
        if mode in ("analyze", "reanalyze", "translate", "inpaint", "export", "refresh"):
            selected_page_indices, selected_page_label = self.choose_batch_page_indices_for_context(title, mode)
            if selected_page_indices is None:
                self.log(f"↩️ {title} 취소")
                return
            if mode == "analyze":
                analyze_ctx = self.macro_batch_preflight_context_for_mode(mode) if hasattr(self, "macro_batch_preflight_context_for_mode") else {}
                if getattr(self, "macro_running", False) and (
                    bool((analyze_ctx or {}).get("ocr_regions_confirmed"))
                    or bool(getattr(self, "_macro_preflight_ocr_regions_confirmed", False))
                ):
                    try:
                        self.log("🧩 [Macro] OCR 분석 영역 확인값 재사용")
                    except Exception:
                        pass
                elif not self.confirm_ocr_analysis_regions_before_run(selected_page_indices):
                    self.log(f"↩️ {title} 취소")
                    return
        else:
            if getattr(self, "ui_language", LANG_KO) == LANG_EN:
                batch_message = f"Run {self.tr_ui(title)} on total {len(self.paths)} page(s)?"
            else:
                batch_message = f"{title}을(를) 총 {len(self.paths)}페이지에 실행합니다."
            if not self.confirm_batch_operation(title, batch_message):
                self.log(f"↩️ {title} 취소")
                return

        # 일괄 시작 전 현재 페이지의 UI 상태를 한 번만 확정한다.
        # 일괄 분석은 일반 분석과 동일하게 기존 마스크를 무시하고 새로 따야 하므로
        # 현재 화면 마스크를 데이터에 다시 저장하지 않는다.
        # 일괄 재분석은 현재 텍스트 마스크를 기준으로 하므로 반드시 마스크를 확정한다.
        self.commit_current_page_ui_to_data(include_mask=(mode != "analyze"))
        self.auto_save_project()

        self._batch_inpaint_resize_policy = None
        if mode == "inpaint":
            inpaint_ctx = self.macro_batch_preflight_context_for_mode(mode) if hasattr(self, "macro_batch_preflight_context_for_mode") else {}
            if getattr(self, "macro_running", False) and (
                bool((inpaint_ctx or {}).get("inpaint_resize_checked"))
                or bool(getattr(self, "_macro_preflight_inpaint_resize_checked", False))
            ):
                policy = (inpaint_ctx or {}).get("inpaint_resize_policy", None)
                if not isinstance(policy, dict):
                    policy = getattr(self, "_macro_preflight_inpaint_resize_policy", None)
                self._batch_inpaint_resize_policy = copy.deepcopy(policy) if isinstance(policy, dict) else None
                try:
                    self.log("🧩 [Macro] 인페인팅 리사이즈 정책 재사용")
                except Exception:
                    pass
            else:
                if not self._ask_batch_inpaint_resize(selected_page_indices):
                    self.log(f"↩️ {title} 취소")
                    return
        try:
            self._batch_return_page_idx = int(self.idx)
            self._batch_return_mode_idx = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else 0
        except Exception:
            self._batch_return_page_idx = int(getattr(self, "idx", 0) or 0)
            self._batch_return_mode_idx = 0

        if mode == "export":
            self.run_batch_export_preview_sync(title, page_indices=selected_page_indices, page_label=selected_page_label)
            return

        self.is_batch_running = True
        self.current_batch_mode = mode
        self._batch_progress_done = 0
        self._batch_total = len(selected_page_indices)
        self._long_task_cancel_requested = False
        self._batch_result = self._batch_result_new(title, mode, selected_page_indices, selected_page_label)
        self.begin_busy_state(title)
        self.set_project_action_interlock(True)
        self.batch_log_undo_boundary("start")
        self.batch_prepare_progress(title, selected_page_indices, selected_page_label, cancellable=True)

        self.log(f"▶️ [Batch] {title} 시작: {len(selected_page_indices)}/{len(self.paths)}페이지 ({selected_page_label})")
        self.wait_for_batch_preview()
        if bool(getattr(self, "_long_task_cancel_requested", False)):
            try:
                self._batch_result["cancelled"] = True
            except Exception:
                pass
            self.on_batch_finished(mode)
            return
        self.start_universal_batch_worker(mode, selected_page_indices)

    def start_universal_batch_worker(self, mode, selected_page_indices):
        self.bw = UniversalBatchWorker(self, mode, page_indices=selected_page_indices)
        self._active_task_worker = self.bw
        self.bw.progress.connect(lambda msg: self.handle_long_task_message(msg))
        if hasattr(self.bw, "active_item"):
            self.bw.active_item.connect(self.on_batch_item_started)
        self.bw.finished_item.connect(self.on_batch_item_finished)
        self.bw.finished_all.connect(lambda m=mode: self.on_batch_finished(m))
        self.bw.start()

    def batch_visual_mode_for(self, mode):
        return {
            "analyze": 1,
            "reanalyze": 1,
            "translate": 4,
            "inpaint": 4,
        }.get(str(mode or ""), self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0)

    def show_batch_page_progress(self, page_index, mode=None, finished=False):
        """일괄 작업 화면 갱신을 즉시 실행하지 않고 한 번만 예약한다.

        worker finished/started 신호가 몰릴 때 이 함수 안에서 load()/processEvents()를
        즉시 실행하면, 대기 중인 batch 신호가 현재 call stack 안으로 다시 들어와
        show_batch_page_progress -> on_batch_item_finished -> show_batch_page_progress 형태의
        재진입이 발생할 수 있다. 따라서 최신 상태만 저장하고 실제 화면 갱신은
        다음 이벤트 루프로 미룬다.
        """
        try:
            page_index = int(page_index)
        except Exception:
            return
        if page_index < 0 or page_index >= len(getattr(self, "paths", []) or []):
            return
        self._pending_batch_page_progress = (page_index, mode, bool(finished))
        self._schedule_batch_page_progress_flush()

    def _schedule_batch_page_progress_flush(self, delay_ms=0):
        try:
            if bool(getattr(self, "_batch_page_progress_flush_scheduled", False)):
                return
            self._batch_page_progress_flush_scheduled = True
            QTimer.singleShot(int(delay_ms or 0), self._flush_batch_page_progress)
        except Exception:
            try:
                self._batch_page_progress_flush_scheduled = False
            except Exception:
                pass

    def _flush_batch_page_progress(self):
        """예약된 일괄 작업 화면 갱신을 1회 처리한다.

        이 함수 안에서는 QApplication.processEvents()를 절대 호출하지 않는다.
        processEvents()는 queued signal을 현재 stack 안으로 끌고 들어와 batch progress
        재귀/stack overflow를 만들 수 있다.
        """
        if bool(getattr(self, "_batch_page_progress_flush_active", False)):
            # load()/mode_chg 중 다시 들어오면 현재 flush가 끝난 뒤 한 번만 재시도한다.
            self._batch_page_progress_flush_scheduled = False
            self._schedule_batch_page_progress_flush(delay_ms=30)
            return

        pending = getattr(self, "_pending_batch_page_progress", None)
        self._pending_batch_page_progress = None
        self._batch_page_progress_flush_scheduled = False
        if not pending:
            return

        try:
            page_index, mode, finished = pending
        except Exception:
            return
        try:
            page_index = int(page_index)
        except Exception:
            return
        if page_index < 0 or page_index >= len(getattr(self, "paths", []) or []):
            return

        self._batch_page_progress_flush_active = True
        try:
            append_log(
                getattr(getattr(self, "bw", None), "batch_log_path", None),
                "UI SHOW PAGE FLUSH BEGIN",
                index=page_index,
                mode=mode,
                finished=finished,
                memory=memory_text(),
            )
            self.idx = int(page_index)
            target_mode = self.batch_visual_mode_for(mode)
            if hasattr(self, "cb_mode") and 0 <= target_mode < self.cb_mode.count():
                if self.cb_mode.currentIndex() != target_mode:
                    self.cb_mode.setCurrentIndex(target_mode)
            self.load()
            append_log(
                getattr(getattr(self, "bw", None), "batch_log_path", None),
                "UI SHOW PAGE FLUSH DONE",
                index=page_index,
                mode=mode,
                finished=finished,
                memory=memory_text(),
            )
        except Exception as e:
            append_log(
                getattr(getattr(self, "bw", None), "batch_log_path", None),
                "UI SHOW PAGE FLUSH EXCEPTION",
                index=page_index,
                mode=mode,
                finished=finished,
                error=repr(e),
                memory=memory_text(),
            )
            try:
                self.log(f"⚠️ 일괄 작업 화면 갱신 실패: {e}")
            except Exception:
                pass
        finally:
            self._batch_page_progress_flush_active = False
            # 처리 중 더 최신 페이지가 예약되었으면 다음 이벤트 루프에서 한 번만 이어 처리한다.
            if getattr(self, "_pending_batch_page_progress", None) is not None:
                self._schedule_batch_page_progress_flush(delay_ms=0)

    def on_batch_item_started(self, i, mode=None):
        append_log(getattr(getattr(self, "bw", None), "batch_log_path", None), "UI BATCH ITEM STARTED", index=i, mode=mode, memory=memory_text())
        try:
            self._batch_current_page_idx = int(i)
            done = int(getattr(self, "_batch_progress_done", 0) or 0)
            total = int(getattr(self, "_batch_total", len(self.paths)) or len(self.paths))
            self.update_task_progress_overlay(
                current=done,
                total=total,
                detail=self.batch_progress_detail(mode, done, total, i, "페이지 작업 중..."),
            )
        except Exception:
            pass
        self.show_batch_page_progress(i, mode=mode, finished=False)

    def on_batch_item_finished(self, i, payload=None):
        append_log(
            getattr(getattr(self, "bw", None), "batch_log_path", None),
            "UI BATCH ITEM FINISHED ENTER",
            index=i,
            payload_keys=list((payload or {}).keys()) if isinstance(payload, dict) else type(payload).__name__,
            memory=memory_text(),
        )
        payload_status = "done"
        payload_message = ""
        try:
            if isinstance(payload, dict):
                payload_status = str(payload.pop('_batch_status', 'done') or 'done')
                payload_message = str(payload.pop('_batch_message', '') or '')
        except Exception:
            payload_status = "done"
            payload_message = ""
        # workers.py가 payload를 넘기는 새 구조와, main.data를 직접 갱신하는 구 구조를 모두 지원한다.
        # 일괄 중에는 self.load()를 호출하지 않는다. 화면에 남은 마스크가 다른 페이지에 저장될 수 있기 때문.
        if i < 0 or i >= len(self.paths):
            try:
                if hasattr(getattr(self, "bw", None), "mark_item_applied"):
                    self.bw.mark_item_applied(i)
            except Exception:
                pass
            return

        if i not in self.data:
            self.data[i] = {
                'ori': None,
                'data': [],
                'mask_merge': None,
                'mask_inpaint': None,
                'mask_merge_off': None,
                'mask_inpaint_off': None,
                'mask_toggle_enabled': False,
                'use_inpainted_as_source': False,
                'bg_clean': None,
                'clean_path': None,
                'working_source': None,
                'working_source_path': None,
                'final_paint': None,
                'final_paint_path': None,
                'final_paint_above': None,
                'final_paint_above_path': None,
                'ocr_analysis_regions': [],
            }

        if payload:
            curr = self.data[i]
            append_log(
                getattr(getattr(self, "bw", None), "batch_log_path", None),
                "UI PAYLOAD APPLY BEGIN",
                index=i,
                payload_keys=list(payload.keys()),
                ori=numpy_shape_text(payload.get('ori')),
                mask_merge=numpy_shape_text(payload.get('mask_merge')),
                mask_inpaint=numpy_shape_text(payload.get('mask_inpaint')),
                data_count=len(payload.get('data') or []) if isinstance(payload.get('data'), list) else 0,
                memory=memory_text(),
            )
            if getattr(self, "current_batch_mode", None) == "analyze" and curr.get('ocr_analysis_regions') and curr.get('data'):
                try:
                    md, mm, mi = self.merge_ocr_analysis_region_results(i, payload.get('data', []), payload.get('mask_merge'), payload.get('mask_inpaint'), ori_img=payload.get('ori'))
                    payload['data'] = md
                    payload['mask_merge'] = mm
                    payload['mask_inpaint'] = mi
                except Exception as e:
                    self.log(f"⚠️ 지정 영역 OCR 병합 실패: {e}")
            if getattr(self, "current_batch_mode", None) in ("analyze", "reanalyze"):
                try:
                    self.spill_payload_masks_to_disk(i, curr, payload)
                    append_log(
                        getattr(getattr(self, "bw", None), "batch_log_path", None),
                        "UI PAYLOAD MASK SPILL DONE",
                        index=i,
                        mask_merge_path=curr.get('mask_merge_path'),
                        mask_inpaint_path=curr.get('mask_inpaint_path'),
                        memory=memory_text(),
                    )
                except Exception as e:
                    self.log(f"⚠️ 일괄 분석 마스크 디스크 저장 실패: {e}")

            for key, value in payload.items():
                if key == 'ori' or str(key).startswith('_batch_'):
                    continue
                if isinstance(value, np.ndarray):
                    curr[key] = value.copy()
                else:
                    curr[key] = value

            # 일괄 인페인팅으로 bg_clean이 새로 들어오면,
            # 원본으로 반영하지 않은 최종 페인팅 레이어는 새 결과 기준으로 초기화한다.
            append_log(getattr(getattr(self, "bw", None), "batch_log_path", None), "UI PAYLOAD APPLY DONE", index=i, memory=memory_text())

            if getattr(self, "current_batch_mode", None) == "inpaint" and "bg_clean" in payload:
                img = self.bg_clean_to_np_image(curr.get('bg_clean'))
                if img is not None:
                    img = self.normalize_image_to_original_size(i, img)
                    encoded = self.encode_np_image_to_png_bytes(img)
                    if encoded is not None:
                        curr['bg_clean'] = encoded
                    if curr.get('use_inpainted_as_source'):
                        self.set_working_source_image(curr, img, page_idx=i)
                curr['final_paint'] = None
                curr['final_paint_above'] = None
                try:
                    self.mark_page_data_dirty_explicit(i, 'clean_background')
                except Exception:
                    pass

        # ON 강제 조건 3: 일괄 분석/재분석으로 결과가 들어온 페이지는 분석 마스크 사용 상태로 저장한다.
        if getattr(self, "current_batch_mode", None) in ("analyze", "reanalyze"):
            if getattr(self, "current_batch_mode", None) == "analyze":
                # 일반 일괄 분석도 개별 분석과 동일하게 이전 텍스트 마스크를 누적하지 않는다.
                # worker payload의 mask_merge / mask_inpaint가 새 기준이며, 이전 보조 텍스트 마스크는 비운다.
                self.data[i]['mask_merge_off'] = None
                self.data[i]['mask_inpaint_off'] = None
            self.data[i]['mask_toggle_enabled'] = True

        if getattr(self, "current_batch_mode", None) in ("analyze", "reanalyze", "translate", "inpaint"):
            self.show_batch_page_progress(i, mode=getattr(self, "current_batch_mode", None), finished=True)
        try:
            self._batch_result_record(i, status=payload_status, message=payload_message)
            self._batch_progress_done = int(getattr(self, "_batch_progress_done", 0) or 0) + 1
            batch_total = int(getattr(self, "_batch_total", len(self.paths)) or len(self.paths))
            self.update_task_progress_overlay(
                current=self._batch_progress_done,
                total=batch_total,
                detail=self.batch_progress_detail(getattr(self, "current_batch_mode", None), self._batch_progress_done, batch_total, i, payload_message or "페이지 작업 완료"),
            )
            # 이미지-heavy 일괄 인페인팅은 페이지 하나를 처리할 때마다 clean 파일을 즉시 flush하고
            # 메모리를 털어야 다음 페이지에서 피크가 누적되지 않는다.
            if getattr(self, "current_batch_mode", None) == "inpaint":
                try:
                    self.mark_page_data_dirty_explicit(i, 'clean_background')
                except Exception:
                    pass
                try:
                    if hasattr(self, 'flush_workspace_image_pages'):
                        self.flush_workspace_image_pages([i], reason='batch_inpaint_item', release_non_current=True)
                    else:
                        self.save_to_work_cache()
                except Exception as e:
                    self.log(f"⚠️ [Batch] 인페인팅 페이지 즉시 저장 실패: {e}")
            elif getattr(self, "current_batch_mode", None) not in ("analyze", "reanalyze"):
                self.save_to_work_cache()
            else:
                append_log(getattr(getattr(self, "bw", None), "batch_log_path", None), "UI BATCH ITEM CACHE SAVE SKIPPED", index=i, mode=getattr(self, "current_batch_mode", None), memory=memory_text())
            self.has_unsaved_changes = True
            # O단계: 일괄 작업은 시작/종료가 Undo 경계다.
            # 페이지마다 Undo를 다시 끊으면 불필요한 스택 정리와 로그가 반복되어 느려진다.
        except Exception as e:
            try:
                self.log(f"⚠️ [Batch] 페이지 완료 처리 실패: {e}")
            except Exception:
                pass
        try:
            if hasattr(getattr(self, "bw", None), "mark_item_applied"):
                self.bw.mark_item_applied(i)
        except Exception:
            pass
        append_log(getattr(getattr(self, "bw", None), "batch_log_path", None), "UI BATCH ITEM FINISHED DONE", index=i, status=payload_status, payload_message=payload_message, memory=memory_text())

    def save_batch_results_without_ui_commit(self):
        """일괄 결과를 복구용 작업 캐시에 저장한다.

        자동저장 기능은 폐지되었으므로, 일괄 작업 결과도 실제 YSBT 패키지에
        즉시 반영하지 않는다. 튕김 복구용 작업 캐시에만 저장하고, 실제 YSBT 확정은
        사용자가 프로젝트 저장/다른 이름으로 저장을 눌렀을 때 수행한다.
        """
        if not getattr(self, "project_dir", None):
            return
        try:
            self.save_to_work_cache()
            self.has_unsaved_changes = True
            self.log("💾 [Batch] 작업 캐시에 일괄 작업 결과 저장")
        except Exception as e:
            self.has_unsaved_changes = True
            self.log(f"⚠️ [Batch] 작업 캐시 저장 실패: {e}")

    def on_batch_finished(self, mode):
        append_log(getattr(getattr(self, "bw", None), "batch_log_path", None), "UI BATCH FINISHED ENTER", mode=mode, memory=memory_text())
        try:
            if getattr(getattr(self, "bw", None), "is_running", True) is False or bool(getattr(self, "_long_task_cancel_requested", False)):
                if isinstance(getattr(self, "_batch_result", None), dict):
                    self._batch_result["cancelled"] = True
        except Exception:
            pass
        self.is_batch_running = False
        self.set_project_action_interlock(False)
        self._batch_inpaint_resize_policy = None

        # ON 강제 조건 3: 일괄 분석 완료 직후 현재 페이지 체크박스도 ON으로 맞춘다.
        if mode in ("analyze", "reanalyze"):
            if self.idx in self.data:
                self.data[self.idx]['mask_toggle_enabled'] = True
            self.set_mask_toggle_safely(True)

        # 일괄 분석/재분석은 페이지 작업을 이어 붙인 매크로다.
        # 프로젝트/작업캐시 저장은 사용자가 명시 저장할 때만 수행한다.
        if mode in ("analyze", "reanalyze"):
            self.has_unsaved_changes = True
            append_log(getattr(getattr(self, "bw", None), "batch_log_path", None), "UI BATCH FINISH CACHE SAVE SKIPPED", mode=mode, memory=memory_text())
            try:
                self.log("ℹ️ 일괄 분석/재분석 결과는 현재 프로젝트에만 반영했습니다. 필요하면 [프로젝트 저장]으로 확정하세요.")
            except Exception:
                pass
        else:
            self.save_batch_results_without_ui_commit()

        if self.paths:
            try:
                return_idx = int(getattr(self, "_batch_return_page_idx", self.idx) or 0)
            except Exception:
                return_idx = self.idx
            self.idx = max(0, min(return_idx, len(self.paths) - 1))
            self.load()

        if mode in ("analyze", "reanalyze"):
            # 일괄 분석/재분석 완료 후 원래 작업 페이지의 분석도로 복귀
            if self.cb_mode.currentIndex() != 1:
                self.cb_mode.setCurrentIndex(1)
            else:
                self.mode_chg(1)

        elif mode == "inpaint":
            # 일괄 인페인팅 완료 후 원래 작업 페이지의 최종결과 화면으로 복귀
            if self.cb_mode.currentIndex() != 4:
                self.cb_mode.setCurrentIndex(4)
            else:
                self.mode_chg(4)

        # 일괄 분석/번역/인페인팅은 여러 페이지에 외부/API 결과를 반영하는 작업 경계다.
        # 성공적으로 전체 흐름이 끝난 뒤 이전 Undo 스택을 끊는다.
        batch_boundary_kind = {
            "analyze": "batch_analysis",
            "reanalyze": "batch_reanalysis",
            "translate": "batch_translation",
            "inpaint": "batch_inpaint",
            "export": "batch_export",
        }.get(mode, "batch_finish")
        self.batch_log_undo_boundary("finish")

        append_log(getattr(getattr(self, "bw", None), "batch_log_path", None), "UI BATCH FINISHED DONE", mode=mode, memory=memory_text())
        self.current_batch_mode = None
        self._active_task_worker = None
        # 완료된 UniversalBatchWorker 객체가 self.bw에 남아 있으면
        # macro_batch_is_busy()가 이전 worker 상태를 보고 다음 매크로 일괄 단계로
        # 넘어가지 못할 수 있다. 완료 콜백에서 UI 반영을 끝낸 뒤 참조를 비운다.
        try:
            self.bw = None
        except Exception:
            pass
        self._batch_total = None
        self._batch_current_page_idx = None
        self.end_busy_state({
            "analyze": "일괄 분석",
            "reanalyze": "일괄 재분석",
            "translate": "일괄 번역",
            "inpaint": "일괄 인페인팅",
            "export": "일괄 출력",
        }.get(mode, "일괄 작업"))
        try:
            self.hide_task_progress_overlay()
        except Exception:
            pass
        try:
            result = getattr(self, "_batch_result", None)
            if isinstance(result, dict):
                summary = self._batch_summary_text(result)
                self.log(summary.replace("\n", " | "))
                self.show_batch_result_summary(result)
        except Exception:
            pass
        self.macro_mark_current_step_done(self.macro_batch_key_for_mode(mode))

    def _event_matches_shortcut(self, event, key_name):
        seq = self.shortcut_settings.seq(key_name)
        if not seq or seq.isEmpty():
            return False
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return False
        try:
            mods_value = event.modifiers().value
        except AttributeError:
            mods_value = int(event.modifiers())
        pressed = QKeySequence(mods_value | key)
        return pressed.matches(seq) == QKeySequence.SequenceMatch.ExactMatch

    def keyReleaseEvent(self, event):
        try:
            if getattr(self, "_page_full_name_popup_hold_by_shortcut", False) and not event.isAutoRepeat():
                self.hide_current_page_full_name()
                event.accept()
                return
            if getattr(self, "_page_list_popup_hold_by_shortcut", False) and not event.isAutoRepeat():
                self.hide_page_tab_menu()
                event.accept()
                return
        except Exception:
            pass
        super().keyReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.is_text_transform_active() and (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.end_active_text_transform(refresh=True)
            event.accept()
            return

        key = event.key()

        if key == Qt.Key.Key_Escape:
            handled_escape = False
            try:
                if getattr(self, "inline_text_editor", None) is not None:
                    self.finish_inline_text_edit(commit=False, refresh=True)
                    handled_escape = True
            except Exception:
                handled_escape = True
            if not handled_escape:
                try:
                    if self.is_text_transform_active():
                        self.end_active_text_transform(refresh=True, quiet=False, clear_selection=True)
                        handled_escape = True
                except Exception:
                    try:
                        self.clear_text_transform_modes()
                        handled_escape = True
                    except Exception:
                        pass
            if handled_escape:
                old_suppress = getattr(self, "_suppress_shared_option_refresh", False)
                self._suppress_shared_option_refresh = True
                try:
                    if getattr(self, "view", None) is not None and getattr(self.view, "scene", None) is not None:
                        self.view.scene.clearSelection()
                except Exception:
                    pass
                finally:
                    self._suppress_shared_option_refresh = old_suppress
                try:
                    self.refresh_shared_option_bar()
                except Exception:
                    pass
                try:
                    fw = QApplication.focusWidget()
                    if fw is not None:
                        fw.clearFocus()
                    if getattr(self, "view", None) is not None:
                        self.view.setFocus(Qt.FocusReason.OtherFocusReason)
                except Exception:
                    pass
                event.accept()
                return

        # F2: 현재 편집 가능한 텍스트/이름 칸은 전체 선택.
        # 선택된 텍스트 영역/우측 텍스트 행이면 번역문 수정으로 바로 진입.
        if key == Qt.Key.Key_F2:
            fw = QApplication.focusWidget()
            if isinstance(fw, QLineEdit):
                fw.setFocus()
                fw.selectAll()
                event.accept()
                return
            if isinstance(fw, (QTextEdit, QPlainTextEdit)):
                cur = fw.textCursor()
                cur.select(QTextCursor.SelectionType.Document)
                fw.setTextCursor(cur)
                event.accept()
                return
            if self.edit_selected_translation_text_f2():
                event.accept()
                return

        # 텍스트/숫자 입력 중에는 Backspace/숫자/방향키 등이 전역 단축키로 새지 않게 한다.
        # 특히 QSpinBox가 포커스를 가진 상태에서 valueChanged/UI 갱신이 얽히면
        # OCR 언어 콤보박스로 포커스가 튀는 문제가 생길 수 있다.
        fw = QApplication.focusWidget()
        input_target = None
        try:
            input_target = self.current_single_line_input_widget(fw)
        except Exception:
            input_target = None
        if isinstance(fw, (QTextEdit, QLineEdit, QPlainTextEdit)) or isinstance(input_target, (QAbstractSpinBox, QComboBox, QFontComboBox, QKeySequenceEdit)):
            mods_for_edit = event.modifiers()
            # 단일 수치/콤보/라인 입력칸에서는 Enter/Esc가 포커스 탈출로 동작해야 한다.
            # 그냥 super()로 넘기면 Qt의 focus traversal 때문에 OCR 언어 콤보박스로 포커스가 이동할 수 있다.
            if input_target is not None and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                if key == Qt.Key.Key_Escape:
                    if self.escape_single_line_input_focus_first(input_target):
                        event.accept()
                        return
                elif not (mods_for_edit & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier)):
                    if self.finish_single_line_input_by_enter(input_target):
                        event.accept()
                        return
            # 멀티라인/일반 텍스트 편집 중 Ctrl+Z/Y만 기존 YSB 전역 Undo/Redo로 유지한다.
            if isinstance(fw, (QTextEdit, QPlainTextEdit, QLineEdit)):
                if (mods_for_edit & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_Z:
                    self.handle_global_undo_shortcut()
                    event.accept()
                    return
                if (mods_for_edit & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_Y:
                    self.handle_general_redo()
                    event.accept()
                    return
            super().keyPressEvent(event)
            return

        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        # 페이지 목록 단축키는 누르고 있는 동안만 표시하고, 키를 떼면 즉시 닫는다.
        if self._event_matches_shortcut(event, "work_page_list"):
            if not event.isAutoRepeat():
                try:
                    self._page_list_popup_hold_by_shortcut = True
                    self.show_page_tab_menu(hold_by_shortcut=True)
                except TypeError:
                    self.show_page_tab_menu()
            event.accept()
            return

        # 현재 페이지 이름 팝업도 누르고 있는 동안만 표시한다.
        if self._event_matches_shortcut(event, "work_page_full_name"):
            if not event.isAutoRepeat():
                try:
                    self._page_full_name_popup_hold_by_shortcut = True
                    self.show_current_page_full_name()
                except Exception:
                    pass
            event.accept()
            return

        # Alt+숫자: 작업탭 직접 이동
        if alt and key in (
            Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4, Qt.Key.Key_5
        ):
            tab_index = {
                Qt.Key.Key_1: 0,
                Qt.Key.Key_2: 1,
                Qt.Key.Key_3: 2,
                Qt.Key.Key_4: 3,
                Qt.Key.Key_5: 4,
            }.get(key)
            if tab_index is not None and tab_index < self.cb_mode.count():
                self.cb_mode.setCurrentIndex(tab_index)
                return

        if key == Qt.Key.Key_Delete:
            if self.cb_mode.currentIndex() == 4 and self.selected_text_data_items():
                self.delete_text_data_items(ask=True)
                return
            if getattr(self, "tab", None) is not None and self.tab.hasFocus() and self.selected_table_text_ids():
                self.delete_text_data_items(ask=True)
                return

        if self.cb_mode.currentIndex() == 4 and key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            # 방향키는 선택 텍스트를 1px 이동한다. Shift+방향키는 빠른 10px 이동.
            # Ctrl/Alt 조합은 다른 단축키와 충돌할 수 있으므로 여기서는 잡지 않는다.
            if not ctrl and not alt and self.selected_text_data_items():
                step = 10 if shift else 1
                dx = -step if key == Qt.Key.Key_Left else (step if key == Qt.Key.Key_Right else 0)
                dy = -step if key == Qt.Key.Key_Up else (step if key == Qt.Key.Key_Down else 0)
                if self.nudge_selected_text_items(dx, dy):
                    event.accept()
                    return

        if ctrl and key == Qt.Key.Key_C:
            if self.cb_mode.currentIndex() == 4 and self.selected_text_data_items():
                self.copy_text_data_items()
                return

        if self.cb_mode.currentIndex() == 4 and self._event_matches_shortcut(event, "text_paste_same_position"):
            self.paste_text_clipboard_same_position()
            return

        if ctrl and key == Qt.Key.Key_V:
            if self.cb_mode.currentIndex() == 4:
                if self.enter_text_paste_mode():
                    return

        if self.cb_mode.currentIndex() == 4:
            if self._event_matches_shortcut(event, "text_font_size"):
                self.set_text_detail_focus("sb_font_size")
                return
            if self._event_matches_shortcut(event, "text_stroke_size"):
                self.set_text_detail_focus("sb_strk")
                return
            if self._event_matches_shortcut(event, "text_line_spacing"):
                self.set_text_detail_focus("sb_line_spacing")
                return
            if self._event_matches_shortcut(event, "text_letter_spacing"):
                self.set_text_detail_focus("sb_letter_spacing")
                return
            if self._event_matches_shortcut(event, "text_char_width"):
                self.set_text_detail_focus("sb_char_width")
                return
            if self._event_matches_shortcut(event, "text_char_height"):
                self.set_text_detail_focus("sb_char_height")
                return
            if self._event_matches_shortcut(event, "text_bold_toggle"):
                self.toggle_bold()
                return
            if self._event_matches_shortcut(event, "text_italic_toggle"):
                self.toggle_italic()
                return
            if self._event_matches_shortcut(event, "text_strike_toggle"):
                self.toggle_strike()
                return

        # ESC 동작:
        # - 그림판/요술봉 도구 사용 중이면 무조건 이동 모드로 복귀
        # - 최종 화면에서 텍스트가 선택되어 있으면 전체 선택 해제
        if key == Qt.Key.Key_Escape:
            if getattr(self.view, "draw_mode", None):
                self.set_tool(None)
                try:
                    fw = QApplication.focusWidget()
                    if fw is not None:
                        fw.clearFocus()
                    self.view.setFocus(Qt.FocusReason.OtherFocusReason)
                except Exception:
                    pass
                self.log("↔️ 이동 모드")
                return
            if self.cb_mode.currentIndex() == 4:
                self.view.scene.clearSelection()
                try:
                    if getattr(self, "tab", None) is not None:
                        self.tab.clearSelection()
                except Exception:
                    pass
                self.on_scene_selection_changed()
                try:
                    fw = QApplication.focusWidget()
                    if fw is not None:
                        fw.clearFocus()
                    self.view.setFocus(Qt.FocusReason.OtherFocusReason)
                except Exception:
                    pass
                self.log("선택 해제")
                return

        # 그림판/마스크/최종 페인팅 도구 단축키는 관련 탭에서만 사용한다.
        paint_keys = [
            "paint_magic_select", "paint_magic_expand",
            "paint_magic_tolerance_inc", "paint_magic_tolerance_dec",
            "paint_magic_expand_inc", "paint_magic_expand_dec",
            "paint_mask_cut", "paint_area_fill",
            "paint_brush", "paint_erase", "paint_move",
            "paint_zoom_out", "paint_zoom_in", "paint_reanalyze", "paint_undo", "paint_redo",
            "final_paint_color", "paint_area_fill", "final_paint_to_background", "final_text_tool",
            "final_paint_above_toggle", "final_paint_opacity_inc", "final_paint_opacity_dec",
        ]
        if self.cb_mode.currentIndex() not in (2, 3, 4):
            for paint_key in paint_keys:
                if self._event_matches_shortcut(event, paint_key):
                    return

        # 요술봉 전용 단축키
        if self._event_matches_shortcut(event, "paint_magic_select"):
            self.set_tool('magic_wand')
            return
        if self._event_matches_shortcut(event, "paint_magic_expand"):
            self.expand_magic_wand_selection()
            return
        if self._event_matches_shortcut(event, "paint_magic_fill"):
            self.fill_magic_wand_mask()
            return
        if self._event_matches_shortcut(event, "paint_magic_tolerance_inc"):
            self.adjust_magic_tolerance(+1)
            return
        if self._event_matches_shortcut(event, "paint_magic_tolerance_dec"):
            self.adjust_magic_tolerance(-1)
            return
        if self._event_matches_shortcut(event, "paint_magic_expand_inc"):
            self.adjust_magic_expand_range(+1)
            return
        if self._event_matches_shortcut(event, "paint_magic_expand_dec"):
            self.adjust_magic_expand_range(-1)
            return
        if self._event_matches_shortcut(event, "paint_mask_wrap"):
            self.set_tool('mask_wrap')
            return
        if self._event_matches_shortcut(event, "paint_mask_cut"):
            self.set_tool('mask_cut')
            return
        if self.cb_mode.currentIndex() in (2, 3) and self._event_matches_shortcut(event, "paint_area_fill"):
            self.set_tool("area_paint")
            return
        if self._event_matches_shortcut(event, "work_quick_ocr"):
            self.open_quick_ocr_dialog()
            return
        if self._event_matches_shortcut(event, "quick_ocr_execute"):
            self.start_quick_ocr_selection()
            return
        if getattr(self.view, "draw_mode", None) == 'ocr_region_select':
            if self._event_matches_shortcut(event, "paint_mask_wrap_rect"):
                self.set_ocr_region_shape('rect')
                return
            if self._event_matches_shortcut(event, "paint_mask_wrap_free"):
                self.set_ocr_region_shape('free')
                return
        if getattr(self.view, "draw_mode", None) in ('mask_wrap', 'mask_cut', 'area_paint'):
            if self._event_matches_shortcut(event, "paint_mask_wrap_rect"):
                if getattr(self.view, "draw_mode", None) == 'mask_cut':
                    self.set_mask_cut_shape('rect')
                elif getattr(self.view, "draw_mode", None) == 'area_paint':
                    self.set_area_paint_shape('rect')
                else:
                    self.set_mask_wrap_shape('rect')
                return
            if self._event_matches_shortcut(event, "paint_mask_wrap_free"):
                if getattr(self.view, "draw_mode", None) == 'mask_cut':
                    self.set_mask_cut_shape('free')
                elif getattr(self.view, "draw_mode", None) == 'area_paint':
                    self.set_area_paint_shape('free')
                else:
                    self.set_mask_wrap_shape('free')
                return

        if self._event_matches_shortcut(event, "work_tab_cycle"):
            self.cycle_work_tab()
            return
        if self._event_matches_shortcut(event, "work_page_prev"):
            self.prev()
            return
        if self._event_matches_shortcut(event, "work_page_next"):
            self.next()
            return

        # 최종 화면에서는 F1/글꼴 선택 단축키로 전용 글꼴 선택창을 연다.
        # 텍스트가 선택되어 있으면 선택 텍스트에 적용하고, 없으면 기본 글꼴을 바꾼다.
        if self.cb_mode.currentIndex() == 4 and self._event_matches_shortcut(event, "item_font_select"):
            self.open_font_select_dialog()
            return

        # 최종 화면에서 텍스트를 선택한 상태일 때만 작동하는 개별 텍스트 단축키
        if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
            if self._event_matches_shortcut(event, "text_transform_toggle"):
                self.toggle_selected_text_transform_quick()
                return
            if self._event_matches_shortcut(event, "text_effect_gradient"):
                self.open_selected_text_gradient_dialog()
                return
            if self._event_matches_shortcut(event, "text_skew_toggle"):
                self.toggle_selected_text_skew_quick()
                return
            if self._event_matches_shortcut(event, "text_trapezoid_toggle"):
                self.toggle_selected_text_trapezoid_quick()
                return
            if self._event_matches_shortcut(event, "text_arc_toggle"):
                self.toggle_selected_text_arc_quick()
                return
            if self._event_matches_shortcut(event, "text_rasterize"):
                self.rasterize_selected_text_quick()
                return
            if self._event_matches_shortcut(event, "item_font_select"):
                self.open_font_select_dialog()
                return
            if self._event_matches_shortcut(event, "item_font_inc"):
                items = self.selected_text_items()
                if items:
                    # TextEngine 2차: 선택 텍스트만 즉시 갱신하고 scene 전체/mode_chg는 깨우지 않는다.
                    current = int(items[0].data.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value())
                    self.apply_style_to_selected(font_size=current + 1)
                return
            if self._event_matches_shortcut(event, "item_font_dec"):
                items = self.selected_text_items()
                if items:
                    current = int(items[0].data.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value())
                    self.apply_style_to_selected(font_size=max(1, current - 1))
                return
            if self._event_matches_shortcut(event, "item_align_left"):
                self.apply_style_to_selected(align="left")
                return
            if self._event_matches_shortcut(event, "item_align_center"):
                self.apply_style_to_selected(align="center")
                return
            if self._event_matches_shortcut(event, "item_align_right"):
                self.apply_style_to_selected(align="right")
                return
            if self._event_matches_shortcut(event, "item_stroke_inc"):
                items = self.selected_text_items()
                if items:
                    current = int(items[0].data.get('stroke_width', self.sb_strk.value()) or 0)
                    self.apply_style_to_selected(stroke_width=current + 1)
                return
            if self._event_matches_shortcut(event, "item_stroke_dec"):
                items = self.selected_text_items()
                if items:
                    current = int(items[0].data.get('stroke_width', self.sb_strk.value()) or 0)
                    self.apply_style_to_selected(stroke_width=max(0, current - 1))
                return
            if self._event_matches_shortcut(event, "item_text_color"):
                self.pick_color("item_text")
                return
            if self._event_matches_shortcut(event, "item_stroke_color"):
                self.pick_color("item_stroke")
                return

        if self.cb_mode.currentIndex() == 4:
            if self._event_matches_shortcut(event, "text_transform_toggle"):
                active = self.current_transform_data_item() if hasattr(self, "current_transform_data_item") else None
                if active is not None:
                    self.toggle_text_transform_mode(active)
                    return
            if self._event_matches_shortcut(event, "final_paint_color"):
                self.pick_color("final_paint")
                return
            if self._event_matches_shortcut(event, "paint_area_fill"):
                self.set_tool("area_paint")
                return
            if self._event_matches_shortcut(event, "final_paint_to_background"):
                self.use_final_background_as_source()
                return
            if self._event_matches_shortcut(event, "final_text_tool"):
                self.set_tool("final_text")
                return
            if self._event_matches_shortcut(event, "final_paint_above_toggle"):
                self.toggle_final_paint_above_text()
                return
            if self._event_matches_shortcut(event, "final_paint_opacity_inc"):
                self.adjust_final_paint_opacity(+5)
                return
            if self._event_matches_shortcut(event, "final_paint_opacity_dec"):
                self.adjust_final_paint_opacity(-5)
                return

        if self._event_matches_shortcut(event, "paint_brush"):
            self.set_tool('draw')
            return
        if self._event_matches_shortcut(event, "paint_erase"):
            self.set_tool('erase')
            return
        if self._event_matches_shortcut(event, "paint_move"):
            self.set_tool(None)
            return
        if self._event_matches_shortcut(event, "paint_zoom_out"):
            self.adjust_brush_size(-1)
            return
        if self._event_matches_shortcut(event, "paint_zoom_in"):
            self.adjust_brush_size(+1)
            return
        if self._event_matches_shortcut(event, "paint_reanalyze"):
            self.reanalyze_mask()
            return
        if self._event_matches_shortcut(event, "paint_undo"):
            self.handle_general_undo()
            return
        if self._event_matches_shortcut(event, "paint_redo"):
            self.handle_general_redo()
            return

        super().keyPressEvent(event)

