from ysb.ui.main_window_support import *


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
        """요술봉 미리보기 상태를 전역 Undo 스택에 같이 저장한다."""
        try:
            active = bool(getattr(getattr(self, 'view', None), 'draw_mode', None) == 'magic_wand')
        except Exception:
            active = False
        return {
            "active": active,
            "mask": self.magic_wand_mask.copy() if isinstance(getattr(self, 'magic_wand_mask', None), np.ndarray) else None,
            "seed": tuple(self.magic_wand_seed) if getattr(self, 'magic_wand_seed', None) else None,
            "seeds": [tuple(x) for x in (getattr(self, 'magic_wand_seeds', []) or [])],
        }

    def restore_magic_wand_state(self, state):
        """Undo 복원 후 요술봉 선택/확장 상태를 화면에 다시 그린다."""
        if not isinstance(state, dict):
            self.clear_magic_wand_selection()
            return False
        mask = state.get('mask')
        self.magic_wand_mask = mask.copy() if isinstance(mask, np.ndarray) else None
        self.magic_wand_seeds = [tuple(x) for x in (state.get('seeds') or [])]
        self.magic_wand_seed = tuple(state.get('seed')) if state.get('seed') else (self.magic_wand_seeds[-1] if self.magic_wand_seeds else None)
        if state.get('active') and self.cb_mode.currentIndex() in [2, 3]:
            try:
                self.set_tool('magic_wand')
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

    def push_magic_wand_history(self):
        mask = self.magic_wand_mask.copy() if isinstance(self.magic_wand_mask, np.ndarray) else None
        seeds = list(getattr(self, "magic_wand_seeds", []) or [])
        self.magic_wand_history.append((mask, seeds))
        if len(self.magic_wand_history) > 20:
            self.magic_wand_history.pop(0)

    def undo_magic_wand_selection(self):
        if not getattr(self, "magic_wand_history", None):
            self.log("⚠️ 되돌릴 요술봉 선택이 없습니다.")
            return False
        mask, seeds = self.magic_wand_history.pop()
        self.magic_wand_mask = mask
        self.magic_wand_seeds = list(seeds or [])
        self.magic_wand_seed = self.magic_wand_seeds[-1] if self.magic_wand_seeds else None
        if self.magic_wand_mask is not None:
            self.view.draw_magic_wand_preview(self.magic_wand_mask)
        else:
            self.view.clear_magic_wand_preview()
        self.log("↩️ 요술봉 선택 되돌림")
        return True

    def clear_magic_wand_selection(self):
        self.magic_wand_mask = None
        self.magic_wand_seed = None
        self.magic_wand_seeds = []
        self.magic_wand_history = []
        if hasattr(self, "view") and hasattr(self.view, "clear_magic_wand_preview"):
            self.view.clear_magic_wand_preview()

    def current_magic_source_image(self):
        return self.get_source_display_image(self.idx)

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
                    btn.setStyleSheet("font-weight:bold; background:#2f80ed; color:white;")
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

            color = QColor(0, 0, 255, 150) if mode == 3 else QColor(255, 0, 0, 150)
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

            color = QColor(0, 0, 255, 150) if mode == 3 else QColor(255, 0, 0, 150)
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
        if self.cb_mode.currentIndex() not in [2, 3]:
            self.log("⚠️ 요술봉은 텍스트 마스크/페인팅 마스크 탭에서만 사용할 수 있습니다.")
            return

        img = self.current_magic_source_image()
        if img is None:
            self.log("⚠️ 요술봉 기준 이미지가 없습니다.")
            return

        h, w = img.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return

        tol = int(self.sb_magic_tolerance.value()) if hasattr(self, "sb_magic_tolerance") else 20
        try:
            self.push_project_undo("요술봉 선택")
        except Exception:
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

        self.view.draw_magic_wand_preview(self.magic_wand_mask)
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

        return flood_mask[1:h + 1, 1:w + 1].copy()

    def on_magic_wand_tolerance_changed(self, value):
        # 허용범위를 바꾸면 누적 클릭 지점 전체를 기준으로 미리보기를 다시 계산한다.
        # 단, 영역확장 후 허용범위를 바꾸면 확장 상태는 재계산된다.
        if self.view.draw_mode != 'magic_wand':
            return
        seeds = list(getattr(self, "magic_wand_seeds", []) or [])
        if not seeds:
            return
        try:
            self.push_project_undo("요술봉 허용범위 변경")
        except Exception:
            pass
        img = self.current_magic_source_image()
        if img is None:
            return

        merged = None
        for seed in seeds:
            part = self.build_magic_wand_mask(img, seed, int(value))
            merged = part if merged is None else cv2.bitwise_or(merged.astype(np.uint8), part.astype(np.uint8))

        self.magic_wand_mask = merged
        self.view.draw_magic_wand_preview(self.magic_wand_mask)

    def expand_magic_wand_selection(self):
        if self.magic_wand_mask is None:
            self.log("⚠️ 먼저 요술봉으로 영역을 선택하세요.")
            return

        amount = int(self.sb_magic_expand.value()) if hasattr(self, "sb_magic_expand") else 3
        if amount <= 0:
            self.view.draw_magic_wand_preview(self.magic_wand_mask)
            return

        try:
            self.push_project_undo("요술봉 영역확장")
        except Exception:
            self.push_magic_wand_history()
        kernel_size = amount * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        self.magic_wand_mask = cv2.dilate(self.magic_wand_mask, kernel, iterations=1)
        self.view.draw_magic_wand_preview(self.magic_wand_mask)
        self.log(f"요술봉 영역확장: {amount}px")

    def fill_magic_wand_mask(self):
        if self.magic_wand_mask is None:
            self.log("⚠️ 먼저 요술봉으로 영역을 선택하세요.")
            return

        if self.cb_mode.currentIndex() not in [2, 3]:
            self.log("⚠️ 마스킹 칠하기는 텍스트 마스크/페인팅 마스크 탭에서만 가능합니다.")
            return

        if self.view.user_mask_item is None:
            self.log(self.tr_ui("⚠️ 현재 탭에 마스크 레이어가 없습니다."))
            return

        try:
            self.commit_current_page_ui_to_data(include_mask=True)
            self.push_project_undo("요술봉 마스킹 칠하기")
        except Exception:
            pass

        before = self.view.get_mask_np()
        if before is None:
            before = np.zeros_like(self.magic_wand_mask, dtype=np.uint8)

        combined = cv2.bitwise_or(before, self.magic_wand_mask.astype(np.uint8))
        color = QColor(0, 0, 255, 150) if self.cb_mode.currentIndex() == 3 else QColor(255, 0, 0, 150)
        self.view.set_user_mask_np(combined, color)
        self.clear_magic_wand_selection()
        self.on_view_mask_edited()
        self.log("요술봉 선택 영역을 현재 마스크에 칠했습니다.")

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
            if right_layout is None or controls is None:
                return
            # 우측 고정 영역은 원본 비교 컨트롤 전용이다. 도구 옵션은 왼쪽 영역만 사용한다.
            while right_layout.count():
                item = right_layout.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.setParent(None)
            visible = self.source_compare_is_visible() if hasattr(self, "source_compare_is_visible") else False
            if visible:
                right_layout.addWidget(controls)
                controls.show()
            else:
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
            elif mode == 4 and draw_mode in ("draw", "erase"):
                self._shared_add_label("브러시")
                self._shared_add_label("불투명도")
                add_widget(getattr(self, "sb_final_paint_opacity", None))
                populated = True
            elif mode == 4 and draw_mode == "area_paint":
                self._shared_add_label(self.tr_ui("영역 페인팅"))
                add_widget(getattr(self, "btn_area_paint_rect", None))
                add_widget(getattr(self, "btn_area_paint_free", None))
                self._shared_add_label(self.tr_ui("선택한 영역을 현재 최종 페인팅 색상으로 채웁니다."))
                populated = True
            elif mode in (2, 3) and draw_mode == "magic_wand":
                self._shared_add_label("요술봉")
                self._shared_add_label("RGB 허용범위")
                add_widget(getattr(self, "sb_magic_tolerance", None))
                add_widget(getattr(self, "btn_magic_expand", None))
                self._shared_add_label("확장 범위")
                add_widget(getattr(self, "sb_magic_expand", None))
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
            elif mode in (1, 2, 3) and draw_mode == "ocr_region_select":
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
                timer.setInterval(50)
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

        The clone follows real work-view interactions, but splitter resizing is layout-only
        and must not move image coordinates.
        """
        try:
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
                    if self._source_compare_sync_blocked() or getattr(self, "_source_compare_user_driving", False):
                        return
                    self.sync_source_compare_from_main()
                except Exception:
                    self._source_compare_sync_pending = False
            QTimer.singleShot(max(0, int(delay)), _run)
        except Exception:
            try:
                self._source_compare_sync_pending = False
            except Exception:
                pass

    def refresh_source_compare_view(self, fit=False):
        if not self.source_compare_is_visible():
            return
        try:
            img = self.get_source_display_image(self.idx)
            scene = self.source_compare_scene
            scene.clear()
            pix = self.qt_pixmap_from_image_source(img)
            if pix is None or pix.isNull():
                return
            scene.addPixmap(pix)
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
                    if self._source_compare_sync_blocked():
                        return
                    self.sync_main_from_source_compare()
                except Exception:
                    self._source_compare_reverse_sync_pending = False
            QTimer.singleShot(max(0, int(delay)), _run)
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
            self.schedule_source_compare_sync(0)
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
            self.schedule_main_sync_from_source_compare(0)
        except Exception:
            pass

    def set_tool(self, m):
        mode = self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0

        if m == 'magic_wand' and mode not in [2, 3]:
            self.log("⚠️ 요술봉은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.")
            return
        if m == 'mask_wrap' and mode not in [2, 3]:
            self.log("⚠️ 마스크 랩핑은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.")
            return
        if m == 'mask_cut' and mode not in [2, 3]:
            self.log(self.tr_ui("⚠️ 마스크 커팅은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요."))
            return
        if m == 'final_text' and mode != 4:
            self.log("⚠️ 텍스트 도구는 최종화면에서만 사용할 수 있습니다.")
            return
        if m == 'area_paint' and mode != 4:
            self.log("⚠️ 영역 페인팅은 최종화면에서만 사용할 수 있습니다.")
            return
        if m == 'paste_text' and mode != 4:
            self.log("⚠️ 텍스트 붙여넣기는 최종화면에서만 사용할 수 있습니다.")
            return
        if m == 'raster_erase' and mode != 4:
            self.log("⚠️ " + self.tr_ui("객체 일부 지우기는 최종화면에서만 사용할 수 있습니다."))
            return
        if m == 'ocr_region_select' and mode in [0, 4]:
            self.log("⚠️ OCR 분석 영역 지정은 분석도/마스크 탭에서 사용하세요.")
            return
        if m in ('draw', 'erase') and mode not in [2, 3, 4]:
            self.log("⚠️ 브러시/지우개는 마스크 탭 또는 최종화면에서만 사용할 수 있습니다.")
            return

        if m != 'paste_text':
            self.text_paste_pending = False
            try:
                self.view.clear_paste_preview()
            except Exception:
                pass

        self.view.draw_mode = m
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag if m else QGraphicsView.DragMode.ScrollHandDrag)
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
                    btn.setStyleSheet("font-weight:bold; background:#2f80ed; color:white;")
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
        if hasattr(self, "cb_mode") and self.cb_mode.currentIndex() in (0, 4):
            self.cb_mode.setCurrentIndex(1)
        self.set_ocr_region_shape("rect", silent=True)
        self.set_tool('ocr_region_select')
        self.refresh_ocr_region_overlay()
        self.log(f"🔎 OCR 분석 영역 지정 시작: {self.ocr_region_target_label}")

    def add_ocr_analysis_region_payload(self, payload):
        if not isinstance(payload, dict):
            return
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
                self.push_project_undo("OCR 분석 범위 지정")
            except Exception:
                pass
            for i in targets:
                if i in self.data:
                    self.data[i]['ocr_analysis_regions'] = copy.deepcopy(temp.get(i, []) or [])
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
            self.push_project_undo("현재 페이지 OCR 분석 범위 해제")
        except Exception:
            pass
        curr = self.data.get(self.idx)
        if isinstance(curr, dict):
            curr['ocr_analysis_regions'] = []
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
            self.push_project_undo("OCR 분석 범위 해제")
        except Exception:
            pass
        for curr in self.data.values():
            if isinstance(curr, dict):
                curr['ocr_analysis_regions'] = []
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
                "border:1px solid #cfd7e5; border-radius:0px; "
                "padding:6px 8px; font-size:12px; }"
            )
        return (
            "QLabel { background:#1f2430; color:#ffffff; "
            "border:1px solid #4b5563; border-radius:0px; "
            "padding:6px 8px; font-size:12px; }"
        )

    def show_quick_ocr_result_popup(self, text):
        text = str(text or "").strip()
        if not text:
            return
        try:
            popup = getattr(self, "quick_ocr_result_popup", None)
            if popup is None:
                flags = (
                    Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.Tool
                    | Qt.WindowType.WindowStaysOnTopHint
                )
                popup = QLabel(None, flags=flags)
                popup.setObjectName("quickOcrResultPopup")
                popup.setWordWrap(True)
                popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                popup.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
                self.quick_ocr_result_popup = popup
            popup.setStyleSheet(self._quick_ocr_popup_style())
            popup.setText(text)
            popup.setMaximumWidth(520)
            popup.adjustSize()
            pos = QCursor.pos() + QPoint(16, 18)
            popup.move(pos)
            popup.show()
            popup.raise_()
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
        self.refresh_page_tabs()
        self.update_page_presence_interlocks()
        p = self.paths[self.idx]
        self.btn_page.setText(f"{self.idx + 1} / {len(self.paths)}")

        if self.idx not in self.data:
            self.data[self.idx] = {
                'ori': cv2.imdecode(np.fromfile(p, np.uint8), 1),
                'data': [],
                'mask_merge': None,
                'mask_inpaint': None,
                'mask_merge_off': None,
                'mask_inpaint_off': None,
                'mask_toggle_enabled': False,
                'use_inpainted_as_source': False,
                'bg_clean': None,
                'working_source': None,
                'final_paint': None,
                'final_paint_above': None,
                'ocr_analysis_regions': [],
            }
        elif self.data[self.idx].get('ori') is None:
            self.data[self.idx]['ori'] = cv2.imdecode(np.fromfile(p, np.uint8), 1)

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

    def is_light_theme(self):
        return str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK).lower() == THEME_LIGHT

    def table_row_color(self, checked):
        # 우측 텍스트 표 행 색상은 테마에 따라 따로 관리한다.
        # 체크 ON/OFF는 색으로 구분하되, 화이트 테마에서는 어두운 배경이 남지 않게 한다.
        if self.is_light_theme():
            return QColor("#ffffff") if checked else QColor("#fff1f1")
        return QColor("#2b2e34") if checked else QColor("#4a2b2b")

    def table_text_color(self, checked=True):
        return QColor("#202124") if self.is_light_theme() else QColor("#f2f2f2")

    def table_header_color(self):
        return QColor("#eef1f6") if self.is_light_theme() else QColor("#31343a")

    def table_header_text_color(self):
        return QColor("#202124") if self.is_light_theme() else QColor("#f2f2f2")

    def table_check_widget_style(self, color):
        border = "#d7dbe3" if self.is_light_theme() else "#4a4d55"
        return f"background:{color.name()}; border:none;"

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
        cb.setStyleSheet("QCheckBox { padding:0px; margin:0px; } QCheckBox::indicator { width:14px; height:14px; }")
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
                self.push_project_undo('체크 상태 변경')
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
            self.mode_chg(4)

        if row == 0:
            self.log((f"🔄 All check states auto-refreshed: {'ON' if is_checked else 'OFF'}" if self.ui_language == LANG_EN else f"🔄 전체 체크 상태 자동 갱신: {'ON' if is_checked else 'OFF'}"))
        else:
            data_index = row - 1
            if 0 <= data_index < len(curr_data['data']):
                self.log((f"🔄 Check state auto-refreshed: ID {curr_data['data'][data_index].get('id')} = {'ON' if is_checked else 'OFF'}" if self.ui_language == LANG_EN else f"🔄 체크 상태 자동 갱신: ID {curr_data['data'][data_index].get('id')} = {'ON' if is_checked else 'OFF'}"))
        self.auto_save_project()

    def ref_tab(self):
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
            # 텍스트 마스크는 ON/OFF 슬롯을 사용하지 않지만, 예전 버전/작업 캐시에서
            # 남아 있을 수 있는 보조 슬롯까지 같이 지워야 전체 분석이 항상 새 상태가 된다.
            curr['mask_merge_off'] = None
            # 일반 분석은 초기화에 가까운 작업이므로 기존 수동/자동 마스킹 슬롯을 모두 비운다.
            curr['mask_inpaint_off'] = None
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
                'mask_toggle_enabled': False,
                'use_inpainted_as_source': False,
                'bg_clean': None,
                'working_source': None,
                'final_paint': None,
                'final_paint_above': None,
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
        self.break_undo_chain("reanalyze" if preserve_text_mask else "analysis")
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

        self.tab.blockSignals(True)
        try:
            for row, t in zip(target_rows, res):
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr['data']):
                    continue
                safe_text = str(t) if t is not None else ""
                curr['data'][data_index]['translated_text'] = safe_text
                self.tab.setItem(row, 3, QTableWidgetItem(safe_text))
            self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)

        self.tab.resizeRowsToContents()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.break_undo_chain("translation")
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

    def run_inpainting(self):
        if not self.ensure_engine_ready():
            return
        if not self.paths:
            self.log("⚠️ 이미지가 없습니다. 먼저 프로젝트에 이미지를 불러와 주세요.")
            return
        if not self.check_inpaint_api_or_alert():
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        self.commit_current_page_ui_to_data()
        input_path = self.get_inpainting_input_path(self.idx)
        if not input_path or not os.path.exists(input_path):
            self.log("⚠️ 인페인팅 입력 이미지 파일을 만들지 못했습니다.")
            return

        inpaint_data, inpaint_mask = self.build_inpainting_payload_for_current_toggle(curr)
        inpaint_mask = self.normalize_inpaint_mask_to_input_image(input_path, inpaint_mask)

        if not self.mask_toggle_enabled and inpaint_mask is None:
            self.log("⚠️ OFF 페인팅 마스크가 없습니다. 마스크 OFF 상태에서는 직접 칠한 마스크가 필요합니다.")
            return

        if inpaint_mask is not None and int(np.count_nonzero(inpaint_mask)) == 0:
            self.log("⚠️ 인페인팅 마스크가 비어 있습니다.")
            return

        self.log(f"🧾 인페인팅 입력: {input_path}")
        self._long_task_cancel_requested = False
        self.prepare_task_progress_overlay("인페인팅", "인페인팅 요청을 처리하는 중입니다.", total=0, cancellable=True)
        self.begin_busy_state("인페인팅")
        self.iw = InpaintWorker(self.engine, input_path, inpaint_data, inpaint_mask)
        self._active_task_worker = self.iw
        self.iw.log.connect(lambda msg: self.handle_long_task_message(msg))
        self.iw.finished.connect(self.inpaint_end)
        self.iw.start()

    def inpaint_end(self, bg):
        if not bg:
            self.log("⚠️ 식질 실패: 결과물이 비어있습니다.")
            self.end_busy_state("인페인팅")
            self.macro_mark_current_step_done("work_inpaint")
            return

        curr = self.data[self.idx]

        img = self.bg_clean_to_np_image(bg)
        if img is not None:
            img = self.normalize_image_to_original_size(self.idx, img)
            encoded = self.encode_np_image_to_png_bytes(img)
            curr['bg_clean'] = encoded if encoded is not None else bg

            # 인페인팅을 원본으로 쓰는 상태라면, 새 결과를 작업중 원본으로 갱신한다.
            # 이렇게 해야 1차 인페인팅 결과 위에 2차/3차 인페인팅을 계속 덧칠하는 흐름이 된다.
            if curr.get('use_inpainted_as_source'):
                self.set_working_source_image(curr, img)
        else:
            curr['bg_clean'] = bg

        # 최종화면 브러시 페인팅은 "출력 전 임시 보정 레이어"다.
        # 원본으로 반영(Alt+P)하지 않은 상태에서 다시 인페인팅하면,
        # 새 인페인팅 결과를 기준으로 초기화되어야 하므로 페인팅 레이어를 비운다.
        curr['final_paint'] = None
        curr['final_paint_above'] = None

        self.auto_save_project()
        self.refresh_text_only()

        # 인페인팅은 배경 이미지와 최종 페인팅 레이어 기준을 바꾸는 작업 경계다.
        # 성공 반영 후 이전 Undo 스택을 끊어 인페인팅 전 상태로 되돌아가지 않게 한다.
        self.break_undo_chain("inpaint")
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
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress

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
        self.auto_save_project()

    def on_table_item_changed(self, item):
        self.tab.resizeRowsToContents()
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
                new_text = str(item.text() or '')
                role_old = item.data(Qt.ItemDataRole.UserRole)
                old_text = str(role_old if role_old is not None else curr_data['data'][data_index].get(key, '') or '')
                if new_text != old_text:
                    self.push_text_line_undo('원문 텍스트 수정' if col == 2 else '번역문 텍스트 수정')
                    curr_data['data'][data_index][key] = new_text
                    item.setData(Qt.ItemDataRole.UserRole, new_text)
                    if col == 3:
                        try:
                            self.shrink_text_rect_to_content(curr_data['data'][data_index])
                        except Exception:
                            pass
                    if self.cb_mode.currentIndex() == 4:
                        old_suppress = getattr(self, "_suppress_mode_undo", False)
                        self._suppress_mode_undo = True
                        try:
                            self.mode_chg(4)
                        finally:
                            self._suppress_mode_undo = old_suppress
                    self.auto_save_project()
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
        self.auto_save_project()

    def mode_chg(self, i):
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
                self.project_ui_view_states[self.view_state_key(self.idx, old_mode_for_undo)] = self.capture_view_state()
                rec = self.make_ui_undo_record("작업 탭 변경", self.idx, mode=old_mode_for_undo)
                rec["view_state"] = copy.deepcopy(self.project_ui_view_states.get(self.view_state_key(self.idx, old_mode_for_undo)) or {})
                self.append_project_undo_record(rec)
            except Exception:
                pass

        if getattr(self, "inline_text_editor", None) is not None:
            self.finish_inline_text_edit(commit=True, refresh=False)

        # 이전 마스크 탭에서 벗어나기 전에 자동 반영.
        # 단, 페이지 로딩/일괄 작업 중에는 절대 화면 마스크를 저장하지 않는다.
        if (
            not self.is_page_loading
            and not self.is_batch_running
            and not getattr(self, "_skip_mode_mask_commit", False)
            and self.last_mode in [2, 3]
        ):
            curr = self.data.get(self.idx)
            m = self.view.get_mask_np()
            if curr is not None and m is not None:
                self.set_active_mask(curr, m, self.last_mode)
                curr['mask_toggle_enabled'] = self.mask_toggle_enabled
                self.auto_save_project()

        if (
            not self.is_page_loading
            and not self.is_batch_running
            and self.last_mode == 4
        ):
            curr = self.data.get(self.idx)
            if curr is not None and hasattr(self.view, "get_final_paint_png_bytes"):
                curr['final_paint'] = self.view.get_final_paint_png_bytes()
                if hasattr(self.view, "get_final_paint_above_png_bytes"):
                    curr['final_paint_above'] = self.view.get_final_paint_above_png_bytes()
                self.auto_save_project()

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
            QTimer.singleShot(30, _restore)
            QTimer.singleShot(80, _restore)

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

        if i not in [2, 3] and getattr(self.view, "draw_mode", None) in ('magic_wand', 'mask_wrap', 'mask_cut'):
            self.set_tool(None)
        if i not in [1, 2, 3] and getattr(self.view, "draw_mode", None) == 'ocr_region_select':
            self.set_tool(None)
        if i != 4 and getattr(self.view, "draw_mode", None) == 'area_paint':
            self.set_tool(None)
        self._hide_legacy_option_bars()
        self.update_final_paint_option_bar_visibility()
        try:
            self.refresh_shared_option_bar()
        except Exception:
            pass

        source_img = self.get_source_display_image(self.idx)

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
            self.refresh_source_compare_view(fit=False)
            QTimer.singleShot(30, lambda: self.schedule_source_compare_sync(0))
        except Exception:
            pass

        if track_mode_change:
            try:
                self.remember_current_view_state()
                self.auto_save_project()
            except Exception:
                pass

    def prev(self):
        if not self.paths:
            return

        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        self.idx = (self.idx - 1) % len(self.paths)
        self.load()
        self.restore_current_view_state_later()
        self.schedule_current_page_tab_visible()

    def next(self):
        if not self.paths:
            return

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
            try:
                for it in scene.items():
                    if isinstance(it, TypesettingItem):
                        text_items.append(it)
                        old_suppress.append(bool(getattr(it, 'suppress_guides', False)))
                        it.suppress_guides = True
                        it.update()
            except RuntimeError:
                return False

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
                for it, old in zip(text_items, old_suppress):
                    try:
                        it.suppress_guides = old
                        it.update()
                    except RuntimeError:
                        pass
                    except Exception:
                        pass

            try:
                os.makedirs(os.path.dirname(result_path), exist_ok=True)
            except Exception:
                pass
            if out.save(result_path, 'PNG'):
                return True

            try:
                tmp_path = os.path.join(os.path.dirname(result_path), '__ysb_current_scene_result_tmp.png')
                if out.save(tmp_path, 'PNG'):
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

        try:
            # 탭 임시 이동은 사용자 작업이 아니므로 Undo/마스크 자동 반영/도구 전환 부작용을 막는다.
            self._suppress_mode_undo = True
            self._skip_mode_mask_commit = True
            self.is_batch_running = True

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
                    self.mode_chg(old_mode)
                except Exception:
                    pass
                finally:
                    try:
                        self._suppress_mode_undo = old_suppress_mode_undo
                        self._skip_mode_mask_commit = old_skip_mode_mask_commit
                        self.is_batch_running = old_batch_running
                    except Exception:
                        pass

            try:
                if old_draw_mode and hasattr(self, 'view'):
                    self.view.draw_mode = old_draw_mode
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

        out = QImage(bg_pix.width(), bg_pix.height(), QImage.Format.Format_RGB32)
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
                QRectF(0, 0, bg_pix.width(), bg_pix.height()),
                QRectF(0, 0, bg_pix.width(), bg_pix.height()),
            )
        finally:
            painter.end()
            scene.clear()

        try:
            os.makedirs(os.path.dirname(result_path), exist_ok=True)
        except Exception:
            pass

        if out.save(result_path, "PNG"):
            return True

        # 일부 환경에서 한글 경로 저장이 실패할 때를 대비한 임시 파일 우회.
        try:
            tmp_path = os.path.join(os.path.dirname(result_path), "__ysb_qt_result_tmp.png")
            if out.save(tmp_path, "PNG"):
                shutil.move(tmp_path, result_path)
                return True
        except Exception:
            pass
        return False

    def export_result(self):
        curr = self.data.get(self.idx)
        if not curr:
            self.log("⚠️ 데이터 없음")
            return
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

        if curr.get('final_paint'):
            base_img = self.bg_clean_to_np_image(export_bg)
            export_img = self.compose_final_paint_on_bgr(base_img, curr.get('final_paint'))
            export_bg = self.encode_np_image_to_png_bytes(export_img) or export_img
        self.ensure_page_source_path(self.idx)
        output_stem = self.output_display_stem(self.idx)
        source_path_for_export = self.paths[self.idx] if self.paths and self.idx < len(self.paths) else self.path_for_output_display(self.idx)
        p = self.engine.export_project_result(
            curr['data'],
            source_path_for_export,
            export_bg,
            self.cb_font.currentFont().family(),
            self.sb_strk.value(),
            self.sb_font_size.value(),
            output_root=self.get_output_root(),
            output_name_stem=output_stem,
        )
        result_path = os.path.join(self.get_output_root(), "result", f"Result_{output_stem}.png")

        # Result PNG는 포토샵 스크립트용 엔진 렌더(PIL)가 아니라 Qt 렌더로 다시 저장한다.
        # 최종화면 탭에서 출력하는 경우에는 data로 다시 조립하지 않고,
        # 현재 화면에 실제로 떠 있는 QGraphicsScene을 그대로 렌더한다.
        # 이렇게 해야 글꼴/영역 재설정/변형 직후의 화면과 출력 PNG가 1:1에 가깝게 맞는다.
        qt_result_rendered = False

        # Result PNG는 항상 최종결과 탭에서 보이는 화면과 같은 QGraphicsScene 렌더 경로를 사용한다.
        # 현재 탭이 최종결과가 아니어도 잠깐 최종 탭을 그린 뒤 저장하고 원래 탭으로 돌린다.
        qt_result_rendered = self.render_final_tab_scene_for_export_qt(result_path)
        if qt_result_rendered:
            self.log("🖼️ 최종화면 동기화 기준으로 최종 이미지 재저장")

        if not qt_result_rendered:
            qt_result_rendered = self.render_final_result_image_qt(result_path, export_bg, curr.get('final_paint_above'))
            if qt_result_rendered:
                self.log("🖼️ 최종 이미지 Qt 재구성 렌더 기준으로 재저장")

        # 텍스트 위 페인팅 레이어는 텍스트 렌더링 이후 최종 PNG 위에 다시 합성한다.
        # 단, Qt 렌더가 성공한 경우에는 위 페인팅까지 함께 렌더했으므로 중복 합성하지 않는다.
        if curr.get('final_paint_above') and (not qt_result_rendered) and os.path.exists(result_path):
            try:
                result_img = cv2.imdecode(np.fromfile(result_path, np.uint8), cv2.IMREAD_COLOR)
                if result_img is not None:
                    result_img = self.compose_final_paint_on_bgr(result_img, curr.get('final_paint_above'))
                    ok, buf = cv2.imencode(".png", result_img)
                    if ok:
                        buf.tofile(result_path)
            except Exception as e:
                self.log(f"⚠️ 텍스트 위 페인팅 출력 합성 실패: {e}")

        self.log(f"✅ 스크립트 저장: {p}")
        self.log(f"🖼️ 최종 이미지 저장: {result_path}")
        self.auto_save_project()

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

    def run_batch_export_preview_sync(self, title="일괄 출력"):
        """일괄 출력도 개별 출력과 같은 최종화면(QGraphicsScene) 렌더 경로를 사용한다.

        기존 UniversalBatchWorker의 export 모드는 워커 스레드에서 engine.export_project_result()만 호출했다.
        그 경로는 data/PIL 기준 재구성 렌더라서, 최종결과 탭에 실제로 보이는 Qt 조판 화면과
        줄바꿈/기준선/변형 위치가 어긋날 수 있다. Qt 위젯/scene 렌더는 메인 스레드에서만 안전하므로
        일괄 출력만 메인 스레드 루프로 처리한다.
        """
        if not self.paths:
            self.log("⚠️ 파일 없음")
            return

        old_idx = int(getattr(self, "idx", 0) or 0)
        old_mode = int(self.cb_mode.currentIndex()) if hasattr(self, "cb_mode") else 0
        old_batch_mode = getattr(self, "current_batch_mode", None)
        total = len(self.paths)
        ok_count = 0
        fail_count = 0

        self.is_batch_running = True
        self.current_batch_mode = "export"
        self.begin_busy_state(title)
        self.set_project_action_interlock(True)

        try:
            for i, path in enumerate(list(self.paths)):
                if i >= len(self.paths):
                    break
                base_name = os.path.basename(str(path or f"page{i + 1:03d}.png"))
                prefix = f"[{i + 1}/{total}]"
                try:
                    self.log(f"{prefix} 출력: {base_name}")
                    self.idx = i
                    self.ensure_page_source_path(i)
                    self.load()
                    QApplication.processEvents()

                    # export_result() 내부에서 최종결과 탭을 실제로 그린 뒤 그 scene을 저장한다.
                    # 이 경로를 타야 개별 출력과 일괄 출력의 결과가 같은 렌더러를 사용한다.
                    self.export_result()
                    ok_count += 1
                    QApplication.processEvents()
                except Exception as e:
                    fail_count += 1
                    self.log(f"{prefix} ❌ 출력 에러: {e}")

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

            self.auto_save_project()
            self.is_batch_running = False
            self.current_batch_mode = old_batch_mode
            self.set_project_action_interlock(False)
            self.end_busy_state(title)
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
        """일괄 분석/번역/인페인팅 실행 전에 전체/지정 페이지 범위를 고른다."""
        total_pages = len(self.paths)
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui(title))
        dialog.setModal(True)
        dialog.resize(440, 190)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        desc = QLabel(self.tr_ui("작업할 페이지 범위를 선택하세요."), dialog)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        rb_all = QRadioButton(self.tr_ui("전체 페이지"), dialog)
        rb_selected = QRadioButton(self.tr_ui("페이지 선택"), dialog)
        rb_all.setChecked(True)

        edit_pages = QLineEdit(dialog)
        edit_pages.setPlaceholderText(self.tr_ui("예: 1-3, 1~3, 1,2,3"))
        edit_pages.setEnabled(False)

        selected_row = QHBoxLayout()
        selected_row.setContentsMargins(0, 0, 0, 0)
        selected_row.setSpacing(8)
        selected_row.addWidget(rb_selected)
        selected_row.addWidget(edit_pages, 1)

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

        result = {"accepted": False, "indices": list(range(total_pages)), "label": self.tr_ui("전체 페이지")}

        def on_accept():
            try:
                if rb_selected.isChecked():
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
            "translate": "일괄 번역",
            "inpaint": "일괄 인페인팅",
            "refresh": "일괄 텍스트 갱신",
            "export": "일괄 출력",
        }
        title = mode_names.get(mode, "일괄 작업")

        if mode == "analyze":
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
        if mode in ("analyze", "translate", "inpaint"):
            selected_page_indices, selected_page_label = self.choose_batch_page_indices(title, mode)
            if selected_page_indices is None:
                self.log(f"↩️ {title} 취소")
                return
            if mode == "analyze" and not self.confirm_ocr_analysis_regions_before_run(selected_page_indices):
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
        self.commit_current_page_ui_to_data(include_mask=(mode != "analyze"))
        self.auto_save_project()

        if mode == "export":
            self.run_batch_export_preview_sync(title)
            return

        self.is_batch_running = True
        self.current_batch_mode = mode
        self._batch_progress_done = 0
        self._batch_total = len(selected_page_indices)
        self._long_task_cancel_requested = False
        self.prepare_task_progress_overlay(title, f"{title} 준비 중... ({self._batch_total}/{len(self.paths)}페이지)", total=self._batch_total, cancellable=True)
        self.begin_busy_state(title)
        self.set_project_action_interlock(True)

        self.log(f"▶️ {title} 시작: {len(selected_page_indices)}/{len(self.paths)}페이지 ({selected_page_label})")
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
            "translate": 4,
            "inpaint": 4,
        }.get(str(mode or ""), self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0)

    def show_batch_page_progress(self, page_index, mode=None, finished=False):
        """일괄 작업 중 현재 처리/완료된 페이지를 화면에 보여준다.

        일괄 작업은 worker 스레드가 self.data에 결과를 넘기고, 메인 스레드가
        그 결과를 반영한다. 이때 화면을 전혀 움직이지 않으면 멈춘 것처럼 보여서
        현재 페이지를 따라가게 하되, 화면 상태를 data로 다시 커밋하지는 않는다.
        """
        try:
            if page_index < 0 or page_index >= len(self.paths):
                return
            self.idx = int(page_index)
            target_mode = self.batch_visual_mode_for(mode)
            if hasattr(self, "cb_mode") and 0 <= target_mode < self.cb_mode.count():
                if self.cb_mode.currentIndex() != target_mode:
                    self.cb_mode.setCurrentIndex(target_mode)
            self.load()
            try:
                QApplication.processEvents()
            except Exception:
                pass
        except Exception as e:
            try:
                self.log(f"⚠️ 일괄 작업 화면 갱신 실패: {e}")
            except Exception:
                pass

    def on_batch_item_started(self, i, mode=None):
        self.show_batch_page_progress(i, mode=mode, finished=False)

    def on_batch_item_finished(self, i, payload=None):
        try:
            self._batch_progress_done = int(getattr(self, "_batch_progress_done", 0) or 0) + 1
            batch_total = int(getattr(self, "_batch_total", len(self.paths)) or len(self.paths))
            self.update_task_progress_overlay(current=self._batch_progress_done, total=batch_total, detail=f"일괄 작업 진행: {self._batch_progress_done}/{batch_total}")
        except Exception:
            pass
        # workers.py가 payload를 넘기는 새 구조와, main.data를 직접 갱신하는 구 구조를 모두 지원한다.
        # 일괄 중에는 self.load()를 호출하지 않는다. 화면에 남은 마스크가 다른 페이지에 저장될 수 있기 때문.
        if i < 0 or i >= len(self.paths):
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
                'working_source': None,
                'final_paint': None,
                'final_paint_above': None,
                'ocr_analysis_regions': [],
            }

        if payload:
            curr = self.data[i]
            if getattr(self, "current_batch_mode", None) == "analyze" and curr.get('ocr_analysis_regions') and curr.get('data'):
                try:
                    md, mm, mi = self.merge_ocr_analysis_region_results(i, payload.get('data', []), payload.get('mask_merge'), payload.get('mask_inpaint'), ori_img=payload.get('ori'))
                    payload['data'] = md
                    payload['mask_merge'] = mm
                    payload['mask_inpaint'] = mi
                except Exception as e:
                    self.log(f"⚠️ 지정 영역 OCR 병합 실패: {e}")
            for key, value in payload.items():
                if isinstance(value, np.ndarray):
                    curr[key] = value.copy()
                else:
                    curr[key] = value

            # 일괄 인페인팅으로 bg_clean이 새로 들어오면,
            # 원본으로 반영하지 않은 최종 페인팅 레이어는 새 결과 기준으로 초기화한다.
            if getattr(self, "current_batch_mode", None) == "inpaint" and "bg_clean" in payload:
                img = self.bg_clean_to_np_image(curr.get('bg_clean'))
                if img is not None:
                    img = self.normalize_image_to_original_size(i, img)
                    encoded = self.encode_np_image_to_png_bytes(img)
                    if encoded is not None:
                        curr['bg_clean'] = encoded
                    if curr.get('use_inpainted_as_source'):
                        self.set_working_source_image(curr, img)
                curr['final_paint'] = None
                curr['final_paint_above'] = None

        # ON 강제 조건 3: 일괄 분석으로 결과가 들어온 페이지는 분석 마스크 사용 상태로 저장한다.
        if getattr(self, "current_batch_mode", None) == "analyze":
            # 일반 일괄 분석도 개별 분석과 동일하게 이전 텍스트 마스크를 누적하지 않는다.
            # worker payload의 mask_merge / mask_inpaint가 새 기준이며, 이전 보조 텍스트 마스크는 비운다.
            self.data[i]['mask_merge_off'] = None
            self.data[i]['mask_inpaint_off'] = None
            self.data[i]['mask_toggle_enabled'] = True

        if getattr(self, "current_batch_mode", None) in ("analyze", "translate", "inpaint"):
            self.show_batch_page_progress(i, mode=getattr(self, "current_batch_mode", None), finished=True)

    def save_batch_results_without_ui_commit(self):
        """일괄 결과를 저장하되 현재 화면 UI를 data에 다시 덮어쓰지 않는다.

        일괄 작업 중 화면은 진행 상황 표시용으로 페이지를 따라간다.
        여기서 auto_save_project()를 그대로 호출하면 commit_current_page_ui_to_data()가
        아직 갱신 전/이전 페이지의 화면 위젯 상태를 현재 페이지 data에 덮어써서
        취소 시 먼저 끝난 페이지 결과가 사라질 수 있다.
        """
        if not getattr(self, "project_dir", None):
            return
        if getattr(self, "auto_save_enabled", False):
            self.save_project_store(self.project_store)
            if getattr(self, "ysbt_package_path", None) and not getattr(self, "is_temp_project", False):
                try:
                    package_project(self.project_dir, self.ysbt_package_path)
                except Exception as e:
                    self.has_unsaved_changes = True
                    self.log(f"⚠️ 일괄 작업 결과 패키지 저장 실패: {e}")
                    return
            self.has_unsaved_changes = bool(getattr(self, "is_temp_project", False) or not getattr(self, "ysbt_package_path", None))
        else:
            self.save_to_work_cache()

    def on_batch_finished(self, mode):
        self.is_batch_running = False
        self.set_project_action_interlock(False)

        # ON 강제 조건 3: 일괄 분석 완료 직후 현재 페이지 체크박스도 ON으로 맞춘다.
        if mode == "analyze":
            if self.idx in self.data:
                self.data[self.idx]['mask_toggle_enabled'] = True
            self.set_mask_toggle_safely(True)

        # 일괄 종료 후 한 번만 저장/로드한다.
        # 일반 auto_save_project()는 현재 화면 UI를 data에 커밋하므로
        # 취소된 일괄 작업의 이미 완료된 페이지 결과를 덮어쓸 수 있다.
        self.save_batch_results_without_ui_commit()

        if self.paths:
            self.load()

        if mode == "analyze":
            # 일괄 분석 완료 후 분석도로 이동
            if self.cb_mode.currentIndex() != 1:
                self.cb_mode.setCurrentIndex(1)
            else:
                self.mode_chg(1)

        elif mode == "inpaint":
            # 일괄 인페인팅 완료 후 최종결과 화면으로 이동
            if self.cb_mode.currentIndex() != 4:
                self.cb_mode.setCurrentIndex(4)
            else:
                self.mode_chg(4)

        # 일괄 분석/번역/인페인팅은 여러 페이지에 외부/API 결과를 반영하는 작업 경계다.
        # 성공적으로 전체 흐름이 끝난 뒤 이전 Undo 스택을 끊는다.
        batch_boundary_kind = {
            "analyze": "batch_analysis",
            "translate": "batch_translation",
            "inpaint": "batch_inpaint",
        }.get(mode)
        if batch_boundary_kind:
            self.break_undo_chain(batch_boundary_kind)

        self.current_batch_mode = None
        self._active_task_worker = None
        self._batch_total = None
        self.end_busy_state({
            "analyze": "일괄 분석",
            "translate": "일괄 번역",
            "inpaint": "일괄 인페인팅",
            "export": "일괄 출력",
        }.get(mode, "일괄 작업"))
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

        if ctrl and key == Qt.Key.Key_C:
            if self.cb_mode.currentIndex() == 4 and self.selected_text_data_items():
                self.copy_text_data_items()
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
                self.log("↔️ 이동 모드")
                return
            if self.cb_mode.currentIndex() == 4:
                self.view.scene.clearSelection()
                self.on_scene_selection_changed()
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
                self.push_page_text_undo('텍스트 글자 크기 증가')
                for item in self.selected_text_items():
                    item.data['font_size'] = int(item.data.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()) + 1
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
                return
            if self._event_matches_shortcut(event, "item_font_dec"):
                self.push_page_text_undo('텍스트 글자 크기 감소')
                for item in self.selected_text_items():
                    item.data['font_size'] = max(1, int(item.data.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()) - 1)
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
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
                self.push_page_text_undo('텍스트 획 증가')
                for item in self.selected_text_items():
                    item.data['stroke_width'] = int(item.data.get('stroke_width', self.sb_strk.value()) or 0) + 1
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
                return
            if self._event_matches_shortcut(event, "item_stroke_dec"):
                self.push_page_text_undo('텍스트 획 감소')
                for item in self.selected_text_items():
                    item.data['stroke_width'] = max(0, int(item.data.get('stroke_width', self.sb_strk.value()) or 0) - 1)
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
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
                self.apply_final_paint_to_background()
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
            self.view.brush_size = max(1, self.view.brush_size - 5)
            self.log(f"➖ 브러시: {self.view.brush_size}")
            return
        if self._event_matches_shortcut(event, "paint_zoom_in"):
            self.view.brush_size += 5
            self.log(f"➕ 브러시: {self.view.brush_size}")
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

