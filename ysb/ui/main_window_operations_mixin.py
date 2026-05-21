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
        if hasattr(self, "cb_trans_provider"):
            self.cb_trans_provider.blockSignals(True)
            try:
                self.set_combo_current_data(self.cb_trans_provider, getattr(self.api_settings, "selected_translation_provider", "openai"))
                self.on_translation_provider_changed(save=False)
            finally:
                self.cb_trans_provider.blockSignals(False)
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
        if m == 'paste_text' and mode != 4:
            self.log("⚠️ 텍스트 붙여넣기는 최종화면에서만 사용할 수 있습니다.")
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
        if hasattr(self, "magic_wand_bar"):
            self.magic_wand_bar.setVisible(m == 'magic_wand' and mode in [2, 3])
        if hasattr(self, "mask_wrap_bar"):
            self.mask_wrap_bar.setVisible(m == 'mask_wrap' and mode in [2, 3])
        if hasattr(self, "mask_cut_bar"):
            self.mask_cut_bar.setVisible(m == 'mask_cut' and mode in [2, 3])
        if m != 'magic_wand':
            self.clear_magic_wand_selection()
        if m != 'mask_wrap' and hasattr(self.view, "clear_mask_wrap_preview"):
            self.view.clear_mask_wrap_preview()
        if m != 'mask_cut' and hasattr(self.view, "clear_mask_cut_preview"):
            self.view.clear_mask_cut_preview()

        self.update_final_paint_option_bar_visibility()

        if m == 'final_text':
            self.log("🔤 도구: 텍스트")
        elif m == 'paste_text':
            self.log("📋 도구: 텍스트 붙여넣기 위치 지정")
        elif m == 'draw':
            self.log("🖌️ 도구: 브러시")
        elif m == 'erase':
            self.log("🧼 도구: 지우개")
        elif m == 'mask_wrap':
            self.log("🩹 도구: 마스크 랩핑")
        elif m == 'mask_cut':
            self.log(self.tr_ui("🔪 도구: 마스크 커팅"))
        elif m is None:
            self.log("✋ 도구: 이동")

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

                text_item = QTableWidgetItem(x.get('text', ''))
                text_item.setData(Qt.ItemDataRole.UserRole, str(x.get('text', '') or ''))
                trans_item = QTableWidgetItem(x.get('translated_text', ''))
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

        self.commit_current_page_ui_to_data(include_mask=False)

        target_idx = self.idx
        self.prepare_text_mask_slots_for_fresh_analysis(target_idx)
        self.begin_busy_state("분석")
        self.w = AnalysisWorker(self.engine, self.get_inpainting_input_path(target_idx))
        self.w.log.connect(self.log)
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
        """선택된 OCR API 설정이 비어 있으면 작업 시작 전에 막고 API 관리창을 연다."""
        settings = getattr(self, "api_settings", None) or ApiSettingsStore.load()
        provider = str(getattr(settings, "selected_ocr_provider", "clova") or "clova").lower()
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
            "replicate_lama": "Replicate LaMa",
        }
        provider_name = provider_name_map.get(provider, "Replicate LaMa")

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
            self.log("⏳ 번역 요청 중... (화면이 잠시 멈출 수 있습니다)")
            QApplication.processEvents()

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
            self.begin_busy_state("번역")
            chunk_size = self.get_current_translation_chunk_size()
            self.log(
                f"🌐 번역 엔진: {self.cb_trans_provider.currentText()} / "
                f"대상 {len(texts)}개 / 묶음 {chunk_size}개"
            )
            res = self.engine.translate_text_batch(
                texts,
                provider=provider,
                chunk_size=chunk_size
            )

            if len(res) != len(texts):
                QMessageBox.warning(self, self.tr_ui("번역 개수 불일치"), self.tr_msg(f"요청 {len(texts)}개 / 응답 {len(res)}개\n\n밀림 방지를 위해 결과 반영을 중단했습니다."))
                return

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

            # 최종 화면에서 번역을 실행한 경우, 번역문 갱신 후 화면도 한 번 갱신한다.
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)

            self.log("✅ 번역 완료")
            self.auto_save_project()

            # 번역은 외부/API 결과를 텍스트 라인에 반영하는 작업 경계다.
            # 성공 반영 후 이전 Undo 스택을 끊어 번역 전 편집 상태로 돌아가지 않게 한다.
            self.break_undo_chain("translation")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log(f"❌ 번역 중 에러 발생: {e}")
            QMessageBox.critical(self, self.tr_ui("번역 오류"), f"{self.tr_ui("에러가 발생했습니다:")}\n{e}")
        finally:
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
        self.begin_busy_state("인페인팅")
        self.iw = InpaintWorker(self.engine, input_path, inpaint_data, inpaint_mask)
        self.iw.log.connect(self.log)
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
            if hasattr(self, "magic_wand_bar"):
                self.magic_wand_bar.hide()
            if hasattr(self, "mask_wrap_bar"):
                self.mask_wrap_bar.hide()
            if hasattr(self, "final_edit_bar"):
                self.final_edit_bar.hide()
            return

        if i != 4 and getattr(self.view, "draw_mode", None) == 'paste_text':
            self.set_tool(None)

        if i not in [2, 3] and getattr(self.view, "draw_mode", None) in ('magic_wand', 'mask_wrap'):
            self.set_tool(None)
        elif hasattr(self, "magic_wand_bar"):
            self.magic_wand_bar.setVisible(getattr(self.view, "draw_mode", None) == 'magic_wand' and i in [2, 3])
        if hasattr(self, "mask_wrap_bar"):
            self.mask_wrap_bar.setVisible(getattr(self.view, "draw_mode", None) == 'mask_wrap' and i in [2, 3])
        self.final_edit_bar.hide()
        self.update_final_paint_option_bar_visibility()

        source_img = self.get_source_display_image(self.idx)

        if i == 0:
            self.view.set_image(source_img, fit=not preserve_view_state)
        elif i == 1:
            self.view.set_image(source_img, fit=not preserve_view_state)
            self.view.draw_static_boxes(curr['data'])
        elif i == 2:
            self.view.set_overlay(source_img, self.get_active_mask(curr, 2), QColor(255, 0, 0, 100), fit=not preserve_view_state)
            self.view.draw_static_boxes(curr['data'])
        elif i == 3:
            self.view.set_overlay(source_img, self.get_active_mask(curr, 3), QColor(0, 0, 255, 100), fit=not preserve_view_state)
            self.view.draw_static_boxes(curr['data'])
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
        self.begin_busy_state(title)
        self.set_project_action_interlock(True)

        self.bw = UniversalBatchWorker(self, mode)
        self.bw.progress.connect(self.log)
        self.bw.finished_item.connect(self.on_batch_item_finished)
        self.bw.finished_all.connect(lambda m=mode: self.on_batch_finished(m))
        self.bw.start()

    def on_batch_item_finished(self, i, payload=None):
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
            }

        if payload:
            curr = self.data[i]
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

    def on_batch_finished(self, mode):
        self.is_batch_running = False
        self.set_project_action_interlock(False)

        # ON 강제 조건 3: 일괄 분석 완료 직후 현재 페이지 체크박스도 ON으로 맞춘다.
        if mode == "analyze":
            if self.idx in self.data:
                self.data[self.idx]['mask_toggle_enabled'] = True
            self.set_mask_toggle_safely(True)

        # 일괄 종료 후 한 번만 저장/로드한다.
        self.auto_save_project()

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

        # 텍스트 편집 중에도 Ctrl+Z는 YSB 전역 Undo로 처리한다.
        # 일반 글자 입력/복사/붙여넣기 등은 기존 편집기 동작을 우선한다.
        fw = QApplication.focusWidget()
        if isinstance(fw, (QTextEdit, QLineEdit)):
            mods_for_edit = event.modifiers()
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
            if self.cb_mode.currentIndex() == 4 and self.text_clipboard:
                self.enter_text_paste_mode()
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
            "paint_mask_cut",
            "paint_brush", "paint_erase", "paint_move",
            "paint_zoom_out", "paint_zoom_in", "paint_reanalyze", "paint_undo", "paint_redo",
            "final_paint_color", "final_paint_to_background", "final_text_tool",
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
        if getattr(self.view, "draw_mode", None) in ('mask_wrap', 'mask_cut'):
            if self._event_matches_shortcut(event, "paint_mask_wrap_rect"):
                if getattr(self.view, "draw_mode", None) == 'mask_cut':
                    self.set_mask_cut_shape('rect')
                else:
                    self.set_mask_wrap_shape('rect')
                return
            if self._event_matches_shortcut(event, "paint_mask_wrap_free"):
                if getattr(self.view, "draw_mode", None) == 'mask_cut':
                    self.set_mask_cut_shape('free')
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
            if self._event_matches_shortcut(event, "final_paint_color"):
                self.pick_color("final_paint")
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

