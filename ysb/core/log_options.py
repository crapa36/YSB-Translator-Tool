# -*- coding: utf-8 -*-
"""User-configurable audit log event registry.

This module centralizes which engine-boundary audit events are normally written.
The UI can toggle each event without changing code.
"""
from __future__ import annotations

from fnmatch import fnmatch
import json
from datetime import datetime, timezone

from ysb.core.cache_utils import get_cache_file

# Legacy keys kept only for migration from app_options.json.
LOG_OPTIONS_APP_KEY = 'audit_log_event_enabled_map'
LOG_UNREGISTERED_APP_KEY = 'audit_log_unregistered_enabled'

LOG_OUTPUT_SETTINGS_FILE_NAME = 'log_output_settings.json'
LOG_OUTPUT_SETTINGS_SCHEMA_VERSION = 1
LOG_OUTPUT_SETTINGS_CACHE_KIND = 'log_output_settings'

LOG_EVENT_REGISTRY = [{'event': 'ACTIVE_OCR_MASK_CLIP', 'group': '마스크/페인팅', 'label': 'ACTIVE_OCR_MASK_CLIP', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'ACTIVE_OCR_MASK_CLIP_DETAIL', 'group': '마스크/페인팅', 'label': 'ACTIVE_OCR_MASK_CLIP_DETAIL', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'APP_INIT', 'group': '시스템', 'label': 'APP_INIT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'AUDIT_INIT', 'group': '시스템', 'label': 'AUDIT_INIT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'BATCH_ITEM_WORK_CACHE_SAVE_DONE', 'group': '일괄 작업', 'label': 'BATCH_ITEM_WORK_CACHE_SAVE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'BATCH_PAGE_DIRTY_MARKED', 'group': '일괄 작업', 'label': 'BATCH_PAGE_DIRTY_MARKED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'BATCH_PAGE_PROGRESS_VIEW_BEGIN', 'group': '일괄 작업', 'label': 'BATCH_PAGE_PROGRESS_VIEW_BEGIN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'BATCH_PAGE_PROGRESS_VIEW_DONE', 'group': '일괄 작업', 'label': 'BATCH_PAGE_PROGRESS_VIEW_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'BATCH_TRANSLATION_TIMING', 'group': '일괄 작업', 'label': 'BATCH_TRANSLATION_TIMING', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'BATCH_WORK_CACHE_CHECKPOINT_DONE', 'group': '저장/프로젝트', 'label': 'BATCH_WORK_CACHE_CHECKPOINT_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'BATCH_WORK_CACHE_CHECKPOINT_ENTER', 'group': '저장/프로젝트', 'label': 'BATCH_WORK_CACHE_CHECKPOINT_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'CHECKPOINT_DIRTY_HYDRATED_FROM_PROJECT_DIRTY', 'group': '기타', 'label': 'CHECKPOINT_DIRTY_HYDRATED_FROM_PROJECT_DIRTY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'CLEAN_IMPORT_', 'group': '기타', 'label': 'CLEAN_IMPORT_', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'CLEAR_TRANSLATION_CURRENT_ENTER', 'group': '기타', 'label': 'CLEAR_TRANSLATION_CURRENT_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'DIALOG_FIRST_PAINT', 'group': 'UI 진단', 'label': 'DIALOG_FIRST_PAINT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'DIALOG_HIDE_EVENT', 'group': 'UI 진단', 'label': 'DIALOG_HIDE_EVENT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'DIALOG_SHOW_EVENT', 'group': 'UI 진단', 'label': 'DIALOG_SHOW_EVENT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'ENSURE_ENGINES', 'group': '시스템', 'label': 'ENSURE_ENGINES', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'EXPORT_CURRENT_SCENE_TEXT_RENDER', 'group': '출력', 'label': 'EXPORT_CURRENT_SCENE_TEXT_RENDER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'EXPORT_QT_SUPERSAMPLE_RENDER', 'group': '출력', 'label': 'EXPORT_QT_SUPERSAMPLE_RENDER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'HIDE_BACKGROUND_APPLIED', 'group': '기타', 'label': 'HIDE_BACKGROUND_APPLIED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'INLINE_EDITOR_GLOBAL_ACTION_BLOCKED', 'group': '기타', 'label': 'INLINE_EDITOR_GLOBAL_ACTION_BLOCKED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'INLINE_EDITOR_SHORTCUT_OVERRIDE_BLOCKED', 'group': '기타', 'label': 'INLINE_EDITOR_SHORTCUT_OVERRIDE_BLOCKED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'INLINE_TEXT_EDITOR_GLOBAL_SHORTCUT_ROUTED_LOCAL', 'group': '기타', 'label': 'INLINE_TEXT_EDITOR_GLOBAL_SHORTCUT_ROUTED_LOCAL', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'LOAD_ENTER', 'group': '뷰/페이지 전환', 'label': 'LOAD_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MAGIC_WAND_HISTORY_PUSH', 'group': '마스크/페인팅', 'label': 'MAGIC_WAND_HISTORY_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MAGIC_WAND_REDO', 'group': '마스크/페인팅', 'label': 'MAGIC_WAND_REDO', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MAGIC_WAND_UNDO', 'group': '마스크/페인팅', 'label': 'MAGIC_WAND_UNDO', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_CLEAR_REMOVED_ITEMS', 'group': '마스크/페인팅', 'label': 'MASK_CLEAR_REMOVED_ITEMS', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_CLEAR_REMOVED_ITEMS_PRESERVE_ALL', 'group': '마스크/페인팅', 'label': 'MASK_CLEAR_REMOVED_ITEMS_PRESERVE_ALL', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_CLEAR_TEXT_ITEM', 'group': '마스크/페인팅', 'label': 'MASK_CLEAR_TEXT_ITEM', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_CLEAR_TEXT_ITEM_PRESERVE_ALL', 'group': '마스크/페인팅', 'label': 'MASK_CLEAR_TEXT_ITEM_PRESERVE_ALL', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_LEAVE_COMMIT_SKIPPED', 'group': '마스크/페인팅', 'label': 'MASK_LEAVE_COMMIT_SKIPPED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_OVERLAY_DISPLAY', 'group': '마스크/페인팅', 'label': 'MASK_OVERLAY_DISPLAY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_SET_ACTIVE', 'group': '마스크/페인팅', 'label': 'MASK_SET_ACTIVE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_TOGGLE_CHANGE_BEGIN', 'group': '마스크/페인팅', 'label': 'MASK_TOGGLE_CHANGE_BEGIN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_TOGGLE_CHANGE_DONE', 'group': '마스크/페인팅', 'label': 'MASK_TOGGLE_CHANGE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_TOGGLE_STORE_VIEW_MASK', 'group': '마스크/페인팅', 'label': 'MASK_TOGGLE_STORE_VIEW_MASK', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MASK_VIEW_TO_DATA_COMMIT_SKIPPED', 'group': '마스크/페인팅', 'label': 'MASK_VIEW_TO_DATA_COMMIT_SKIPPED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MENU_ABOUT_TO_SHOW_DONE', 'group': 'UI 진단', 'label': 'MENU_ABOUT_TO_SHOW_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MENU_ABOUT_TO_SHOW_ENTER', 'group': 'UI 진단', 'label': 'MENU_ABOUT_TO_SHOW_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MENU_BAR_MOUSE_MOVE', 'group': 'UI 진단', 'label': 'MENU_BAR_MOUSE_MOVE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MENU_BAR_MOUSE_PRESS', 'group': 'UI 진단', 'label': 'MENU_BAR_MOUSE_PRESS', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MENU_BAR_MOUSE_RELEASE', 'group': 'UI 진단', 'label': 'MENU_BAR_MOUSE_RELEASE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MENU_HIDE_EVENT', 'group': 'UI 진단', 'label': 'MENU_HIDE_EVENT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MENU_LOG_CONNECT_ERROR', 'group': 'UI 진단', 'label': 'MENU_LOG_CONNECT_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'MENU_LOG_SETUP_ERROR', 'group': 'UI 진단', 'label': 'MENU_LOG_SETUP_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'MENU_SHOW_EVENT', 'group': 'UI 진단', 'label': 'MENU_SHOW_EVENT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MODE_CHG_ENTER', 'group': '뷰/페이지 전환', 'label': 'MODE_CHG_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MODE_CHG_FINAL_TEXT_DRAW_DONE', 'group': '뷰/페이지 전환', 'label': 'MODE_CHG_FINAL_TEXT_DRAW_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MODE_CHG_FINAL_TEXT_DRAW_REQUEST', 'group': '뷰/페이지 전환', 'label': 'MODE_CHG_FINAL_TEXT_DRAW_REQUEST', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'MODE_CHG_LAYER_REFRESH_EXCEPTION', 'group': '뷰/페이지 전환', 'label': 'MODE_CHG_LAYER_REFRESH_EXCEPTION', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'NATIVE_TOOLTIP_BLOCKED', 'group': 'UI 진단', 'label': 'NATIVE_TOOLTIP_BLOCKED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'NATIVE_TOOLTIP_BLOCKED_BY_SETTING', 'group': 'UI 진단', 'label': 'NATIVE_TOOLTIP_BLOCKED_BY_SETTING', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PAGE_DIRTY', 'group': '기타', 'label': 'PAGE_DIRTY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PAGE_VIEW_STATE_ONLY', 'group': '기타', 'label': 'PAGE_VIEW_STATE_ONLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PAGE_VIEW_UNDO_RECORDED_UI_ONLY', 'group': '기타', 'label': 'PAGE_VIEW_UNDO_RECORDED_UI_ONLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PAINT_UNDO_ATTEMPT', 'group': '기타', 'label': 'PAINT_UNDO_ATTEMPT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PAINT_UNDO_BLOCKED_NO_VIEW_HISTORY', 'group': '기타', 'label': 'PAINT_UNDO_BLOCKED_NO_VIEW_HISTORY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PAINT_UNDO_MARKER_PUSH', 'group': '기타', 'label': 'PAINT_UNDO_MARKER_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PRESET_DIALOG_BUILD_DONE', 'group': 'UI 진단', 'label': 'PRESET_DIALOG_BUILD_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PRESET_DIALOG_BUILD_ENTER', 'group': 'UI 진단', 'label': 'PRESET_DIALOG_BUILD_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PRESET_DIALOG_EXEC_ENTER', 'group': 'UI 진단', 'label': 'PRESET_DIALOG_EXEC_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PRESET_DIALOG_EXEC_RETURN', 'group': 'UI 진단', 'label': 'PRESET_DIALOG_EXEC_RETURN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PRESET_DIALOG_RESTORE_DONE', 'group': 'UI 진단', 'label': 'PRESET_DIALOG_RESTORE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PRESET_DIALOG_RESTORE_ENTER', 'group': 'UI 진단', 'label': 'PRESET_DIALOG_RESTORE_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PRESET_DIALOG_RESTORE_REFRESH_DONE', 'group': 'UI 진단', 'label': 'PRESET_DIALOG_RESTORE_REFRESH_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PROJECT_DELTA_SAVE_DONE', 'group': '저장/프로젝트', 'label': 'PROJECT_DELTA_SAVE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'PROJECT_DELTA_SAVE_ENTER', 'group': '저장/프로젝트', 'label': 'PROJECT_DELTA_SAVE_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PROJECT_DELTA_SAVE_SKIP_NO_CHECKPOINT', 'group': '저장/프로젝트', 'label': 'PROJECT_DELTA_SAVE_SKIP_NO_CHECKPOINT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PROJECT_IMAGE_DELTA_SAVE_DONE', 'group': '저장/프로젝트', 'label': 'PROJECT_IMAGE_DELTA_SAVE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PROJECT_IMAGE_DELTA_SAVE_ENTER', 'group': '저장/프로젝트', 'label': 'PROJECT_IMAGE_DELTA_SAVE_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PROJECT_PAGE_JOURNAL_SAVE_DONE', 'group': '저장/프로젝트', 'label': 'PROJECT_PAGE_JOURNAL_SAVE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PROJECT_PAGE_JOURNAL_SAVE_ENTER', 'group': '저장/프로젝트', 'label': 'PROJECT_PAGE_JOURNAL_SAVE_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'PROJECT_STORE_SAVE_ENTER', 'group': '저장/프로젝트', 'label': 'PROJECT_STORE_SAVE_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'PROJECT_UI_SHOW_FINAL_TEXT_FORCE_ON_LOAD', 'group': '저장/프로젝트', 'label': 'PROJECT_UI_SHOW_FINAL_TEXT_FORCE_ON_LOAD', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'QUICK_OCR_DIALOG_CLOSED', 'group': '번역/OCR', 'label': 'QUICK_OCR_DIALOG_CLOSED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'QUICK_OCR_DIALOG_OPEN_ENTER', 'group': '번역/OCR', 'label': 'QUICK_OCR_DIALOG_OPEN_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'QUICK_OCR_DIALOG_OPEN_ERROR', 'group': '번역/OCR', 'label': 'QUICK_OCR_DIALOG_OPEN_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'QUICK_OCR_DIALOG_REQUEST', 'group': '번역/OCR', 'label': 'QUICK_OCR_DIALOG_REQUEST', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'REF_TAB_ENTER', 'group': '뷰/페이지 전환', 'label': 'REF_TAB_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'SAVE_AS_PAGE_COUNT_GUARD_ABORT', 'group': '저장/프로젝트', 'label': 'SAVE_AS_PAGE_COUNT_GUARD_ABORT', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'SAVE_AS_PAGE_COUNT_GUARD_OK', 'group': '저장/프로젝트', 'label': 'SAVE_AS_PAGE_COUNT_GUARD_OK', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'SAVE_AS_PAGE_COUNT_SNAPSHOT', 'group': '저장/프로젝트', 'label': 'SAVE_AS_PAGE_COUNT_SNAPSHOT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'SAVE_AS_PATHS_EXTENDED_FOR_PAGE_GUARD', 'group': '저장/프로젝트', 'label': 'SAVE_AS_PATHS_EXTENDED_FOR_PAGE_GUARD', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'SAVE_DIRTY_DIAG', 'group': '저장/프로젝트', 'label': 'SAVE_DIRTY_DIAG', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'SAVE_PROJECT_ENTER', 'group': '저장/프로젝트', 'label': 'SAVE_PROJECT_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'SAVE_PROJECT_SKIPPED_NO_CHANGES', 'group': '저장/프로젝트', 'label': 'SAVE_PROJECT_SKIPPED_NO_CHANGES', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'SETTINGS_DIALOG_BUILD_DONE', 'group': 'UI 진단', 'label': 'SETTINGS_DIALOG_BUILD_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'SETTINGS_DIALOG_BUILD_ENTER', 'group': 'UI 진단', 'label': 'SETTINGS_DIALOG_BUILD_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'SETTINGS_DIALOG_EXEC_ENTER', 'group': 'UI 진단', 'label': 'SETTINGS_DIALOG_EXEC_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'SETTINGS_DIALOG_EXEC_RETURN', 'group': 'UI 진단', 'label': 'SETTINGS_DIALOG_EXEC_RETURN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'STARTUP_EXTERNAL_OPEN_DEFERRED', 'group': '시스템', 'label': 'STARTUP_EXTERNAL_OPEN_DEFERRED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'STARTUP_EXTERNAL_OPEN_DEFERRED_RUN', 'group': '시스템', 'label': 'STARTUP_EXTERNAL_OPEN_DEFERRED_RUN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_APPLIED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_APPLIED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_BOX_RESOLVED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_BOX_RESOLVED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_CANDIDATE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_CANDIDATE', 'description': '자동 텍스트 조정 후보 계산 상세입니다. 로그가 매우 커질 수 있습니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_CANDIDATE_REJECTED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_CANDIDATE_REJECTED', 'description': '자동 텍스트 조정 후보 계산 상세입니다. 로그가 매우 커질 수 있습니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_CANDIDATE_SUMMARY', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_CANDIDATE_SUMMARY', 'description': '자동 텍스트 조정 후보 계산 상세입니다. 로그가 매우 커질 수 있습니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_CHOSEN', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_CHOSEN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_FINAL_OVERLAP_AFTER_BOUNDARY_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FINAL_OVERLAP_AFTER_BOUNDARY_DONE', 'description': '텍스트가 이미지 캔버스를 넘는지 검사/수정하는 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_FINAL_OVERLAP_RECHECK_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FINAL_OVERLAP_RECHECK_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_FINAL_OVERLAP_RECHECK_ERROR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FINAL_OVERLAP_RECHECK_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_FINAL_OVERLAP_RECHECK_START', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FINAL_OVERLAP_RECHECK_START', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_FINAL_RENDER_OVERLAP_PAIR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FINAL_RENDER_OVERLAP_PAIR', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_FIRST_PASS_START', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FIRST_PASS_START', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_FIT_RECT_USED_WITHOUT_RECT_MUTATION', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FIT_RECT_USED_WITHOUT_RECT_MUTATION', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_FONT_LOOP_ENTER', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FONT_LOOP_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_FORCE_ENTER', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_FORCE_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_PASS_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_PASS_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_PASS_START', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_PASS_START', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_SHRINK', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_SHRINK', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_SHRINK_BLOCKED_BY_READABLE_FLOOR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_SHRINK_BLOCKED_BY_READABLE_FLOOR', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_ITEM_ENTER', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_ITEM_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_LANG', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_LANG', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_LINE_COMPACTED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_LINE_COMPACTED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_LINE_COMPACT_SKIPPED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_LINE_COMPACT_SKIPPED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_MANGA_RESULT', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_MANGA_RESULT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_APPLIED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_APPLIED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_PASS_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_PASS_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_PASS_ERROR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_PASS_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_PASS_START', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_MEDIAN_FLOOR_PASS_START', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_NARROW_EDGE_FIT_RECT_EXPANDED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_NARROW_EDGE_FIT_RECT_EXPANDED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_NARROW_EDGE_FIT_RECT_EXPAND_ERROR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_NARROW_EDGE_FIT_RECT_EXPAND_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_NEIGHBOR_SCAN_SKIPPED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_NEIGHBOR_SCAN_SKIPPED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_NEIGHBOR_TEXT_RECTS', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_NEIGHBOR_TEXT_RECTS', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_FIXED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_FIXED', 'description': '텍스트가 이미지 캔버스를 넘는지 검사/수정하는 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_PASS_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_PASS_DONE', 'description': '텍스트가 이미지 캔버스를 넘는지 검사/수정하는 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_PASS_START', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_PASS_START', 'description': '텍스트가 이미지 캔버스를 넘는지 검사/수정하는 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_UNRESOLVED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_UNRESOLVED', 'description': '텍스트가 이미지 캔버스를 넘는지 검사/수정하는 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_VIOLATION', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_BOUNDARY_VIOLATION', 'description': '텍스트가 이미지 캔버스를 넘는지 검사/수정하는 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAGE_ITEM_SCAN', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_ITEM_SCAN', 'description': '텍스트 item별 스캔 상세입니다. 일괄 작업에서 로그가 크게 늘어납니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PAGE_POSTPASS_BEGIN', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_POSTPASS_BEGIN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PAGE_POSTPASS_DEFERRED_ERROR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_POSTPASS_DEFERRED_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAGE_POSTPASS_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_POSTPASS_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAGE_SCAN_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_SCAN_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAGE_SCAN_ERROR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_SCAN_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAGE_SCAN_START', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAGE_SCAN_START', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAIRWISE_CHECK', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAIRWISE_CHECK', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PAIRWISE_FONT_OFFSET', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAIRWISE_FONT_OFFSET', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PAIRWISE_INNER_OFFSET', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAIRWISE_INNER_OFFSET', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PAIRWISE_PASS_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAIRWISE_PASS_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAIRWISE_PASS_ERROR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAIRWISE_PASS_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_PAIRWISE_PASS_START', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PAIRWISE_PASS_START', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_POSTPASS_PIPELINE_LOCKED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_POSTPASS_PIPELINE_LOCKED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_PROTECTED_STYLE_RESTORED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_PROTECTED_STYLE_RESTORED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_RESULT', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_RESULT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_REWRAP_PRESERVE_LINES', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_REWRAP_PRESERVE_LINES', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_ROUTE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_ROUTE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SAFE_GROW_APPLIED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SAFE_GROW_APPLIED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SAFE_GROW_NO_FIT', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SAFE_GROW_NO_FIT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SAFE_REGROW_PASS_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SAFE_REGROW_PASS_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SAFE_REGROW_PASS_START', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SAFE_REGROW_PASS_START', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SCENE_SCAN_DONE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SCENE_SCAN_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SCENE_SCAN_ERROR', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SCENE_SCAN_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_AUTO_ADJUST_SCENE_SCAN_SKIP', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SCENE_SCAN_SKIP', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SCENE_TEXT_ITEM_SCAN', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SCENE_TEXT_ITEM_SCAN', 'description': '텍스트 item별 스캔 상세입니다. 일괄 작업에서 로그가 크게 늘어납니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SKIP', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SKIP', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_SOURCE_READY', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_SOURCE_READY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_TARGET_RECT', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_TARGET_RECT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_VERTICAL_APPLIED', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_VERTICAL_APPLIED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_VERTICAL_FALLBACK_MULTILINE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_VERTICAL_FALLBACK_MULTILINE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_AUTO_ADJUST_VERTICAL_ROUTE', 'group': '자동 텍스트 조정', 'label': 'TEXT_AUTO_ADJUST_VERTICAL_ROUTE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_CTRL_DRAG_DUPLICATE_BEGIN', 'group': '기타', 'label': 'TEXT_CTRL_DRAG_DUPLICATE_BEGIN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_CTRL_DRAG_DUPLICATE_DONE', 'group': '기타', 'label': 'TEXT_CTRL_DRAG_DUPLICATE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_DELETE_APPLY_DEFERRED', 'group': '기타', 'label': 'TEXT_DELETE_APPLY_DEFERRED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_DELETE_LIVE_APPLY', 'group': '기타', 'label': 'TEXT_DELETE_LIVE_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_DELETE_UNDO_RECORD', 'group': '기타', 'label': 'TEXT_DELETE_UNDO_RECORD', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_KEYBOARD_NUDGE', 'group': '기타', 'label': 'TEXT_KEYBOARD_NUDGE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_LAYER_BIND_CHECK', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_LAYER_BIND_CHECK', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_LAYER_BIND_CHECK_ERROR', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_LAYER_BIND_CHECK_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'TEXT_LAYER_BIND_MISMATCH_NO_REPAIR', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_LAYER_BIND_MISMATCH_NO_REPAIR', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_LAYER_LIFECYCLE_SNAPSHOT', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_LAYER_LIFECYCLE_SNAPSHOT', 'description': '텍스트 레이어의 data_rows/scene_rows 상세 스냅샷입니다. 가장 로그가 큽니다.', 'default_enabled': False}, {'event': 'TEXT_LAYER_REBOUND_DATA', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_LAYER_REBOUND_DATA', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_LAYER_REBUILD_NEEDS_FULL_REFRESH', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_LAYER_REBUILD_NEEDS_FULL_REFRESH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_LAYER_REBUILD_RASTER_MODE_MISMATCH', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_LAYER_REBUILD_RASTER_MODE_MISMATCH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_LIVE_ITEMS_ADDED_AFTER_STRUCTURE_CHANGE', 'group': '기타', 'label': 'TEXT_LIVE_ITEMS_ADDED_AFTER_STRUCTURE_CHANGE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_LIVE_ITEM_CREATE_DONE', 'group': '기타', 'label': 'TEXT_LIVE_ITEM_CREATE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_MOVE_DIRTY_FAST_PATH', 'group': '기타', 'label': 'TEXT_MOVE_DIRTY_FAST_PATH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_MOVE_DIRTY_SKIPPED_NO_CHANGE', 'group': '기타', 'label': 'TEXT_MOVE_DIRTY_SKIPPED_NO_CHANGE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_MOVE_FAST_PATH_BEGIN', 'group': '기타', 'label': 'TEXT_MOVE_FAST_PATH_BEGIN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_MOVE_FAST_PATH_END', 'group': '기타', 'label': 'TEXT_MOVE_FAST_PATH_END', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_MOVE_SYNC_SKIPPED_ALREADY_FLUSHED', 'group': '기타', 'label': 'TEXT_MOVE_SYNC_SKIPPED_ALREADY_FLUSHED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_MULTI_SELECT_CANCEL_CLEANUP', 'group': '기타', 'label': 'TEXT_MULTI_SELECT_CANCEL_CLEANUP', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_MULTI_SELECT_CANCEL_CLEAR', 'group': '기타', 'label': 'TEXT_MULTI_SELECT_CANCEL_CLEAR', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_ORPHAN_SCENE_ITEMS_PURGED', 'group': '기타', 'label': 'TEXT_ORPHAN_SCENE_ITEMS_PURGED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_REGION_RESET_APPLIED', 'group': '기타', 'label': 'TEXT_REGION_RESET_APPLIED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_GEOMETRY_FLUSH', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_GEOMETRY_FLUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_ITEMS_REMOVED_BY_IDENTITY', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_ITEMS_REMOVED_BY_IDENTITY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_MUTATION_SAFETY_DONE', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_MUTATION_SAFETY_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_MUTATION_SAFETY_ENTER', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_MUTATION_SAFETY_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_MUTATION_TIMER_GUARD_ENTER', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_MUTATION_TIMER_GUARD_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_MUTATION_TIMER_GUARD_HOLD', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_MUTATION_TIMER_GUARD_HOLD', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_MUTATION_TIMER_GUARD_RELEASE', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_MUTATION_TIMER_GUARD_RELEASE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_RESYNC_BARRIER_DONE', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_RESYNC_BARRIER_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_RESYNC_BARRIER_ENTER', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_RESYNC_BARRIER_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_RESYNC_BARRIER_PURGE', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_RESYNC_BARRIER_PURGE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_RESYNC_BARRIER_QUEUED', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_RESYNC_BARRIER_QUEUED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_RESYNC_BARRIER_STILL_MISMATCH', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_RESYNC_BARRIER_STILL_MISMATCH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_RESYNC_DEFERRED_DURING_TEXT_DRAG', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_RESYNC_DEFERRED_DURING_TEXT_DRAG', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SCENE_RESYNC_RUN_DEFERRED_DURING_TEXT_DRAG', 'group': '텍스트 레이어/렌더링', 'label': 'TEXT_SCENE_RESYNC_RUN_DEFERRED_DURING_TEXT_DRAG', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_SHOW_TOGGLE_CHANGED', 'group': '기타', 'label': 'TEXT_SHOW_TOGGLE_CHANGED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_STYLE_REFRESH_FORCE_REBUILD', 'group': '기타', 'label': 'TEXT_STYLE_REFRESH_FORCE_REBUILD', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_STYLE_REFRESH_IN_PLACE', 'group': '기타', 'label': 'TEXT_STYLE_REFRESH_IN_PLACE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_TABLE_REFRESH_AFTER_RASTER_MODE_RESYNC', 'group': '기타', 'label': 'TEXT_TABLE_REFRESH_AFTER_RASTER_MODE_RESYNC', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_TABLE_REFRESH_AFTER_STRUCTURE_CHANGE', 'group': '기타', 'label': 'TEXT_TABLE_REFRESH_AFTER_STRUCTURE_CHANGE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_UI_TO_DATA_COMMIT_SKIPPED_DURING_AUTO_TEXT_ADJUST', 'group': '기타', 'label': 'TEXT_UI_TO_DATA_COMMIT_SKIPPED_DURING_AUTO_TEXT_ADJUST', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TEXT_UNDO_PUSH', 'group': '기타', 'label': 'TEXT_UNDO_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TRANSLATE_SINGLE_APPLY_BEGIN', 'group': '번역/OCR', 'label': 'TRANSLATE_SINGLE_APPLY_BEGIN', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TRANSLATE_SINGLE_APPLY_DONE', 'group': '번역/OCR', 'label': 'TRANSLATE_SINGLE_APPLY_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TRANSLATE_SINGLE_FINISHED_HANDLER_DONE', 'group': '번역/OCR', 'label': 'TRANSLATE_SINGLE_FINISHED_HANDLER_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TRANSLATE_SINGLE_FINISHED_SIGNAL', 'group': '번역/OCR', 'label': 'TRANSLATE_SINGLE_FINISHED_SIGNAL', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TRANSLATE_SINGLE_PROGRESS', 'group': '번역/OCR', 'label': 'TRANSLATE_SINGLE_PROGRESS', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'TRANSLATE_SINGLE_REQUEST_PREPARED', 'group': '번역/OCR', 'label': 'TRANSLATE_SINGLE_REQUEST_PREPARED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_COMMAND_UNHANDLED_COMPONENT', 'group': 'Undo', 'label': 'UNDO_COMMAND_UNHANDLED_COMPONENT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_CURRENT_PAGE_EMPTY', 'group': 'Undo', 'label': 'UNDO_CURRENT_PAGE_EMPTY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_CURRENT_PAGE_VIEW_POP', 'group': 'Undo', 'label': 'UNDO_CURRENT_PAGE_VIEW_POP', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_MAGIC_WAND_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_MAGIC_WAND_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_MAGIC_WAND_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_MAGIC_WAND_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_MASK_STATE_APPLY', 'group': 'Undo', 'label': 'UNDO_MASK_STATE_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_OCR_REGION_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_OCR_REGION_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_OCR_REGION_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_OCR_REGION_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_OCR_REGION_TEMP_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_OCR_REGION_TEMP_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_PAINT_MASK_LIVE_REFRESH', 'group': 'Undo', 'label': 'UNDO_PAINT_MASK_LIVE_REFRESH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_PAINT_MASK_PATCH_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_PAINT_MASK_PATCH_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_PROJECT_STRUCTURE_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_PROJECT_STRUCTURE_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_PROJECT_STRUCTURE_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_PROJECT_STRUCTURE_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_GEOMETRY_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_TEXT_GEOMETRY_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_GEOMETRY_COMMAND_MARKER_APPLY', 'group': 'Undo', 'label': 'UNDO_TEXT_GEOMETRY_COMMAND_MARKER_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_GEOMETRY_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_TEXT_GEOMETRY_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_GEOMETRY_COMMAND_SKIP_NO_CHANGE', 'group': 'Undo', 'label': 'UNDO_TEXT_GEOMETRY_COMMAND_SKIP_NO_CHANGE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_ITEM_LIFECYCLE_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_TEXT_ITEM_LIFECYCLE_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_ITEM_LIFECYCLE_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_TEXT_ITEM_LIFECYCLE_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_REGION_RESET_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_TEXT_REGION_RESET_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_STYLE_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_TEXT_STYLE_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_STYLE_COMMAND_DEFERRED_DURING_TEXT_DRAG', 'group': 'Undo', 'label': 'UNDO_TEXT_STYLE_COMMAND_DEFERRED_DURING_TEXT_DRAG', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_STYLE_COMMAND_FINISH_ERROR', 'group': 'Undo', 'label': 'UNDO_TEXT_STYLE_COMMAND_FINISH_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'UNDO_TEXT_STYLE_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_TEXT_STYLE_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_STYLE_COMMAND_SKIP_NOOP', 'group': 'Undo', 'label': 'UNDO_TEXT_STYLE_COMMAND_SKIP_NOOP', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_TEXT_STYLE_REFRESH_IN_PLACE', 'group': 'Undo', 'label': 'UNDO_TEXT_STYLE_REFRESH_IN_PLACE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_VIEW_STATE_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_VIEW_STATE_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_VIEW_STATE_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_VIEW_STATE_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_WORK_TAB_COMMAND_APPLY', 'group': 'Undo', 'label': 'UNDO_WORK_TAB_COMMAND_APPLY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'UNDO_WORK_TAB_COMMAND_PUSH', 'group': 'Undo', 'label': 'UNDO_WORK_TAB_COMMAND_PUSH', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'USE_BACKGROUND_AS_SOURCE_BRUSH_CONFIRM_REQUIRED', 'group': '기타', 'label': 'USE_BACKGROUND_AS_SOURCE_BRUSH_CONFIRM_REQUIRED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'USE_BACKGROUND_AS_SOURCE_BRUSH_CONFIRM_RESULT', 'group': '기타', 'label': 'USE_BACKGROUND_AS_SOURCE_BRUSH_CONFIRM_RESULT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'USE_BACKGROUND_AS_SOURCE_FLUSH_FAILED', 'group': '기타', 'label': 'USE_BACKGROUND_AS_SOURCE_FLUSH_FAILED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'USE_BACKGROUND_AS_SOURCE_PAGE_APPLIED', 'group': '기타', 'label': 'USE_BACKGROUND_AS_SOURCE_PAGE_APPLIED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'VIEW_CLEAR_MODE_LAYERS_DONE', 'group': '뷰/페이지 전환', 'label': 'VIEW_CLEAR_MODE_LAYERS_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'VIEW_CLEAR_MODE_LAYERS_ENTER', 'group': '뷰/페이지 전환', 'label': 'VIEW_CLEAR_MODE_LAYERS_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'VIEW_DRAW_MOVABLE_TEXTS_DONE', 'group': '텍스트 레이어/렌더링', 'label': 'VIEW_DRAW_MOVABLE_TEXTS_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'VIEW_DRAW_MOVABLE_TEXTS_ENTER', 'group': '텍스트 레이어/렌더링', 'label': 'VIEW_DRAW_MOVABLE_TEXTS_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'VIEW_DRAW_MOVABLE_TEXTS_SKIPPED_SHOW_OFF', 'group': '텍스트 레이어/렌더링', 'label': 'VIEW_DRAW_MOVABLE_TEXTS_SKIPPED_SHOW_OFF', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'VIEW_DRAW_MOVABLE_TEXT_ITEM_ADDED', 'group': '텍스트 레이어/렌더링', 'label': 'VIEW_DRAW_MOVABLE_TEXT_ITEM_ADDED', 'description': '텍스트 렌더 item별 추가 로그입니다. 페이지마다 많이 찍힙니다.', 'default_enabled': False}, {'event': 'VIEW_LAYER_COMMIT_DEFERRED_DURING_UI_ACTIVITY', 'group': '뷰/페이지 전환', 'label': 'VIEW_LAYER_COMMIT_DEFERRED_DURING_UI_ACTIVITY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORKSPACE_STRUCTURE_LIGHT_SAVE_DONE', 'group': '저장/프로젝트', 'label': 'WORKSPACE_STRUCTURE_LIGHT_SAVE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORKSPACE_STRUCTURE_LIGHT_SAVE_ENTER', 'group': '저장/프로젝트', 'label': 'WORKSPACE_STRUCTURE_LIGHT_SAVE_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORK_CACHE_IMAGE_DELTA_SAVE_DONE', 'group': '저장/프로젝트', 'label': 'WORK_CACHE_IMAGE_DELTA_SAVE_DONE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORK_CACHE_IMAGE_DELTA_SAVE_ENTER', 'group': '저장/프로젝트', 'label': 'WORK_CACHE_IMAGE_DELTA_SAVE_ENTER', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORK_CACHE_SAVE_DEFERRED_DURING_EXPLICIT_SAVE', 'group': '저장/프로젝트', 'label': 'WORK_CACHE_SAVE_DEFERRED_DURING_EXPLICIT_SAVE', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}, {'event': 'WORK_CACHE_SAVE_DEFERRED_DURING_INLINE_TEXT_EDIT', 'group': '저장/프로젝트', 'label': 'WORK_CACHE_SAVE_DEFERRED_DURING_INLINE_TEXT_EDIT', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORK_CACHE_SAVE_DEFERRED_DURING_TEXT_DRAG', 'group': '저장/프로젝트', 'label': 'WORK_CACHE_SAVE_DEFERRED_DURING_TEXT_DRAG', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORK_CACHE_SAVE_DEFERRED_DURING_UI_ACTIVITY', 'group': '저장/프로젝트', 'label': 'WORK_CACHE_SAVE_DEFERRED_DURING_UI_ACTIVITY', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORK_CACHE_TIMER_STOPPED_FOR_SAVE_AS_DIALOG', 'group': '저장/프로젝트', 'label': 'WORK_CACHE_TIMER_STOPPED_FOR_SAVE_AS_DIALOG', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'WORK_TAB_UNDO_PUSH_ERROR', 'group': '기타', 'label': 'WORK_TAB_UNDO_PUSH_ERROR', 'description': '오류/실패/미해결 상황 추적용 로그입니다.', 'default_enabled': True}, {'event': 'WORK_TAB_UNDO_RECORDED', 'group': '기타', 'label': 'WORK_TAB_UNDO_RECORDED', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': False}, {'event': 'YSBT_OPEN_WORKSPACE_REUSE_CHECK', 'group': '저장/프로젝트', 'label': 'YSBT_OPEN_WORKSPACE_REUSE_CHECK', 'description': '엔진 경계/작업 진단 로그입니다.', 'default_enabled': True}]


# Patch-added events. Keep these outside the generated base registry so future
# feature patches can add log switches without rebuilding the entire registry blob.
LOG_EVENT_REGISTRY.extend([
    {
        'event': 'TEXT_AUTO_ADJUST_GLOBAL_OVERLAP_PASS_ERROR',
        'group': '자동 텍스트 조정',
        'label': '전체쌍 겹침 보정 오류',
        'description': '전체쌍 겹침 보정 패스가 실패했을 때 전체 자동조정 파이프라인을 중단하지 않고 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_AUTO_ADJUST_SAFE_REGROW_PASS_ERROR',
        'group': '자동 텍스트 조정',
        'label': '안전 재성장 오류',
        'description': '겹침 보정 후 안전 재성장 패스가 실패했을 때 전체 자동조정 파이프라인을 중단하지 않고 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_PASS_START',
        'group': '자동 텍스트 조정',
        'label': '실제 여유 공간 성장 시작',
        'description': 'OCR 박스가 아니라 실제 텍스트 bounds 기준으로 글자를 다시 키우는 pass 시작 로그입니다.',
        'default_enabled': False,
    },
    {
        'event': 'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_PASS_DONE',
        'group': '자동 텍스트 조정',
        'label': '실제 여유 공간 성장 완료',
        'description': '실제 여유 공간 성장 pass 완료 요약 로그입니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_APPLIED',
        'group': '자동 텍스트 조정',
        'label': '실제 여유 공간 성장 적용',
        'description': '다른 텍스트와 겹치지 않고 이미지 밖으로 나가지 않는 범위에서 font_size를 키운 경우 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_BLOCKED',
        'group': '자동 텍스트 조정',
        'label': '실제 여유 공간 성장 차단',
        'description': '성장 후보가 overlap, boundary, 측정 실패 등으로 막힌 이유를 기록합니다. 많이 찍힐 수 있습니다.',
        'default_enabled': False,
    },
    {
        'event': 'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_FINALIZED',
        'group': '자동 텍스트 조정',
        'label': '실제 여유 공간 성장 최종 재검사',
        'description': '성장 후 최종 겹침/이미지 경계 재검사 결과를 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_SIZE_FAIL',
        'group': '자동 텍스트 조정',
        'label': '실제 여유 공간 성장 크기별 실패 분포',
        'description': '각 font_size에서 boundary/outside_ocr/overlap 중 무엇으로 후보가 실패했는지 분포를 기록합니다. 로그가 커질 수 있습니다.',
        'default_enabled': False,
    },
    {
        'event': 'TEXT_AUTO_ADJUST_AVAILABLE_SPACE_GROW_SAFE_RECT_FIT_DONE',
        'group': '자동 텍스트 조정',
        'label': '안전 사각형 기준 성장 계산',
        'description': '이웃 텍스트 침범 영역을 뺀 안전 사각형의 폭/높이로 font_size를 이분탐색한 결과를 기록합니다.',
        'default_enabled': False,
    },
    {
        'event': 'TOP_LEVEL_WIDGETS',
        'group': 'UI 진단',
        'label': '상위 위젯 덤프',
        'description': '툴팁/팝업/떠 있는 위젯 진단용 대량 로그입니다. 기본은 끕니다.',
        'default_enabled': False,
    },

    {
        'event': 'TEXT_VERTICAL_AUTO_ADJUST_PREPASS_START',
        'group': '자동 텍스트 조정',
        'label': '세로쓰기 자동조정 사전분기 시작',
        'description': '자동 텍스트 조정 시작 시 세로쓰기 후보를 별도 엔진으로 보낼지 검사하는 시작 로그입니다.',
        'default_enabled': False,
    },
    {
        'event': 'TEXT_VERTICAL_AUTO_ADJUST_PREPASS_DONE',
        'group': '자동 텍스트 조정',
        'label': '세로쓰기 자동조정 사전분기 완료',
        'description': '세로쓰기 전용 자동조정으로 분기된 항목 수와 변경 항목 수를 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_VERTICAL_AUTO_ADJUST_ITEM_DONE',
        'group': '자동 텍스트 조정',
        'label': '세로쓰기 자동조정 항목 결과',
        'description': '세로쓰기 한 줄 자동조정 항목별 글자 크기/채움률/자동 전환 여부를 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_VERTICAL_AUTO_ADJUST_ITEM_ERROR',
        'group': '자동 텍스트 조정',
        'label': '세로쓰기 자동조정 항목 오류',
        'description': '세로쓰기 전용 자동조정 항목 처리 중 오류를 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_VERTICAL_AUTO_ADJUST_PREPASS_ERROR',
        'group': '자동 텍스트 조정',
        'label': '세로쓰기 자동조정 사전분기 오류',
        'description': '세로쓰기 전용 자동조정 사전분기 전체가 실패했을 때 기록합니다.',
        'default_enabled': True,
    },



    {
        'event': 'BATCH_EXPORT_PAGE_BEGIN',
        'group': '출력',
        'label': '일괄 출력 페이지 시작',
        'description': '일괄 출력에서 각 페이지 처리를 시작할 때 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'BATCH_EXPORT_PAGE_LOAD_BEGIN',
        'group': '출력',
        'label': '일괄 출력 페이지 로드 시작',
        'description': '일괄 출력 중 최종화면 로드 직전 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'BATCH_EXPORT_PAGE_LOAD_DONE',
        'group': '출력',
        'label': '일괄 출력 페이지 로드 완료',
        'description': '일괄 출력 중 최종화면 로드 완료 후 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'BATCH_EXPORT_RESULT_BEGIN',
        'group': '출력',
        'label': '일괄 출력 저장 시작',
        'description': '일괄 출력에서 현재 scene 저장 직전 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'BATCH_EXPORT_RESULT_DONE',
        'group': '출력',
        'label': '일괄 출력 저장 완료',
        'description': '일괄 출력에서 현재 scene 저장 완료 후 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'BATCH_EXPORT_PAGE_ERROR',
        'group': '출력',
        'label': '일괄 출력 페이지 오류',
        'description': '일괄 출력 중 Python 예외가 발생한 페이지를 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'SINGLE_ANALYZE_DATA_SUMMARY',
        'group': 'OCR/분석',
        'label': '단일 분석 데이터 요약',
        'description': '단일 OCR 분석 완료 후 생성된 분석 박스 수, OCR 조각 수, 주요 키 요약을 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'SINGLE_ANALYZE_BOX_DETAIL',
        'group': 'OCR/분석',
        'label': '단일 분석 박스 상세',
        'description': '단일 OCR 분석 결과의 각 텍스트 박스 rect, text, ocr_items 개수, vertices 개수를 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'SINGLE_ANALYZE_OCR_ITEM_DETAIL',
        'group': 'OCR/분석',
        'label': '단일 분석 OCR 조각 상세',
        'description': '분석 박스 내부에 보존된 OCR 조각의 text, rect, center, vertices, provider 정보를 기록합니다. 로그가 커질 수 있습니다.',
        'default_enabled': True,
    },
])


ESSENTIAL_EVENT_NAMES = {
    'AUDIT_INIT', 'APP_INIT', 'YSBT_OPEN_WORKSPACE_REUSE_CHECK',
}


def log_event_default_map():
    return {str(item.get('event')): bool(item.get('default_enabled')) for item in LOG_EVENT_REGISTRY}


def log_event_group_names():
    return sorted({str(item.get('group') or '기타') for item in LOG_EVENT_REGISTRY})


def log_event_registry_by_name():
    return {str(item.get('event')): dict(item) for item in LOG_EVENT_REGISTRY}


def is_essential_log_event(event_name: str) -> bool:
    name = str(event_name or '')
    if name in ESSENTIAL_EVENT_NAMES:
        return True
    if 'ERROR' in name or 'FATAL' in name or 'CRASH' in name or 'ABORT' in name or 'UNRESOLVED' in name:
        return True
    return False


def is_log_event_enabled(event_name: str, enabled_map=None, *, unregistered_enabled: bool = False) -> bool:
    name = str(event_name or '')
    if not name:
        return False
    if is_essential_log_event(name):
        return True
    defaults = log_event_default_map()
    if enabled_map is None:
        enabled_map = {}
    try:
        if name in enabled_map:
            return bool(enabled_map.get(name))
    except Exception:
        pass
    if name in defaults:
        return bool(defaults.get(name))
    # Support future grouped entries if they are added later.
    try:
        for pat, val in dict(enabled_map or {}).items():
            if '*' in str(pat) and fnmatch(name, str(pat)):
                return bool(val)
    except Exception:
        pass
    return bool(unregistered_enabled)


def make_preset_map(preset: str):
    preset = str(preset or 'default').lower()
    out = log_event_default_map()
    if preset in ('default', '기본값'):
        return out
    if preset in ('minimal', 'minimum', '최소'):
        return {k: is_essential_log_event(k) for k in out}
    if preset in ('all', '전체'):
        return {k: True for k in out}
    if preset in ('auto_text', '자동텍스트', '자동 텍스트 조정 디버그'):
        return {k: (is_essential_log_event(k) or k.startswith('TEXT_AUTO_ADJUST')) for k in out}
    if preset in ('render', '렌더링', '렌더링/레이어 디버그'):
        return {k: (is_essential_log_event(k) or k.startswith('VIEW_') or k.startswith('TEXT_LAYER') or k.startswith('TEXT_SCENE')) for k in out}
    if preset in ('undo', 'undo 디버그'):
        return {k: (is_essential_log_event(k) or k.startswith('UNDO_')) for k in out}
    return out


def log_output_settings_file():
    """Return the separate cache JSON path for log output settings.

    The log-output selection is a setting, not a general app option.
    Keep it in its own cache file so large debug toggles do not pollute
    app_options.json and can be backed up/replaced independently.
    """
    return get_cache_file(LOG_OUTPUT_SETTINGS_FILE_NAME)


def _utc_now_text():
    try:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    except Exception:
        return ''


def build_log_output_settings(enabled_map=None, *, unregistered_enabled: bool = False):
    base = log_event_default_map()
    clean = {}
    incoming = dict(enabled_map or {}) if isinstance(enabled_map, dict) else {}
    for event in sorted(base.keys()):
        enabled = bool(incoming.get(event, base.get(event, False)))
        if is_essential_log_event(event):
            enabled = True
        clean[str(event)] = bool(enabled)
    return {
        'schema_version': LOG_OUTPUT_SETTINGS_SCHEMA_VERSION,
        'cache_kind': LOG_OUTPUT_SETTINGS_CACHE_KIND,
        'updated_at': _utc_now_text(),
        'unregistered_enabled': bool(unregistered_enabled),
        'enabled_events': clean,
    }


def normalize_log_output_settings(data=None, *, migrate_from_app_options=None):
    legacy_map = None
    legacy_unregistered = False
    try:
        if isinstance(migrate_from_app_options, dict):
            raw = migrate_from_app_options.get(LOG_OPTIONS_APP_KEY)
            if isinstance(raw, dict):
                legacy_map = raw
            legacy_unregistered = bool(migrate_from_app_options.get(LOG_UNREGISTERED_APP_KEY, False))
    except Exception:
        pass

    if isinstance(data, dict):
        raw_map = data.get('enabled_events')
        if not isinstance(raw_map, dict):
            raw_map = data.get('events')
        if not isinstance(raw_map, dict):
            raw_map = data.get(LOG_OPTIONS_APP_KEY)
        raw_unregistered = bool(data.get('unregistered_enabled', data.get(LOG_UNREGISTERED_APP_KEY, False)))
        return build_log_output_settings(raw_map if isinstance(raw_map, dict) else legacy_map, unregistered_enabled=raw_unregistered)

    return build_log_output_settings(legacy_map, unregistered_enabled=legacy_unregistered)


def load_log_output_settings(migrate_from_app_options=None):
    path = log_output_settings_file()
    data = None
    existed = False
    try:
        if path.exists():
            existed = True
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
    except Exception:
        data = None
    settings = normalize_log_output_settings(data, migrate_from_app_options=migrate_from_app_options)
    # Ensure the dedicated cache exists, and migrate legacy app_options-based values
    # on first run after this patch.
    if not existed:
        save_log_output_settings(settings)
    return settings


def save_log_output_settings(settings):
    data = normalize_log_output_settings(settings)
    path = log_output_settings_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return data


def log_output_enabled_map_from_settings(settings):
    if isinstance(settings, dict) and isinstance(settings.get('enabled_events'), dict):
        return dict(settings.get('enabled_events') or {})
    return log_event_default_map()


def log_output_unregistered_from_settings(settings):
    try:
        return bool((settings or {}).get('unregistered_enabled', False))
    except Exception:
        return False

# Patch: text creation/options diagnostics
LOG_EVENT_REGISTRY.extend([
    {
        'event': 'TEXT_PLAIN_CLIPBOARD_STYLE_APPLIED',
        'group': '텍스트 생성/붙여넣기',
        'label': '일반 클립보드 텍스트 현재 스타일 적용',
        'description': 'Windows/일반 클립보드 텍스트를 붙여넣기용 item으로 만들 때 현재 UI 텍스트 스타일을 적용했는지 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_CONTEXT_ADD_REQUEST',
        'group': '텍스트 생성/붙여넣기',
        'label': '우클릭 텍스트 추가 요청',
        'description': '최종화면 우클릭 메뉴에서 텍스트 추가를 요청했을 때 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_CONTEXT_ADD_DONE',
        'group': '텍스트 생성/붙여넣기',
        'label': '우클릭 텍스트 추가 완료',
        'description': '최종화면 우클릭 메뉴에서 텍스트 추가 편집기가 열린 뒤 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'TEXT_CONTEXT_ADD_ERROR',
        'group': '텍스트 생성/붙여넣기',
        'label': '우클릭 텍스트 추가 오류',
        'description': '최종화면 우클릭 텍스트 추가가 실패했을 때 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'OPTIONS_DIALOG_OPEN_REQUEST',
        'group': 'UI 진단',
        'label': '설정/옵션 창 열기 요청',
        'description': '설정/옵션 통합창 열기를 요청했을 때 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'OPTIONS_DIALOG_OPEN_DONE',
        'group': 'UI 진단',
        'label': '설정/옵션 창 열기 완료',
        'description': '설정/옵션 통합창 열기 호출이 끝났을 때 기록합니다.',
        'default_enabled': True,
    },
    {
        'event': 'OPTIONS_DIALOG_OPEN_ERROR',
        'group': 'UI 진단',
        'label': '설정/옵션 창 열기 오류',
        'description': '설정/옵션 통합창을 열지 못했을 때 예외를 기록합니다.',
        'default_enabled': True,
    },
])
