# -*- coding: utf-8 -*-
"""Optional developer-tool loader for YSB Tool.

This module is safe to keep in the main body.  It never imports devtools directly;
external development tools are discovered by module name and ignored when absent.
"""

from __future__ import annotations

import importlib
import importlib.util
import traceback


DEVTOOLS_PANEL_MODULE = "ysb_devtools.simulation_panel"


def _safe_log(main_window, message: str) -> None:
    try:
        main_window.log(message)
    except Exception:
        try:
            print(message)
        except Exception:
            pass


def _safe_audit(main_window, event: str, **fields) -> None:
    try:
        if hasattr(main_window, "audit_boundary_event"):
            main_window.audit_boundary_event(event, **fields)
    except Exception:
        pass


def try_register_simulation_tools(main_window) -> bool:
    """Register optional in-app real-run test tools when ysb_devtools exists.

    Contract:
    - If ysb_devtools is absent, do nothing and return False.
    - If ysb_devtools fails while loading/registering, log only and keep the main app alive.
    - The main body must not import ysb_devtools with a normal direct import.
    """
    try:
        spec = importlib.util.find_spec(DEVTOOLS_PANEL_MODULE)
    except ModuleNotFoundError as e:
        # Parent package absent is the normal production/build case.  Stay silent.
        if str(getattr(e, "name", "") or "").startswith("ysb_devtools"):
            _safe_audit(main_window, "DEVTOOLS_NOT_FOUND", module=DEVTOOLS_PANEL_MODULE)
            return False
        _safe_audit(main_window, "DEVTOOLS_FIND_SPEC_ERROR", module=DEVTOOLS_PANEL_MODULE, error=str(e))
        _safe_log(main_window, f"⚠️ 실전 테스트 도구 탐색 실패: {e}")
        return False
    except Exception as e:
        _safe_audit(main_window, "DEVTOOLS_FIND_SPEC_ERROR", module=DEVTOOLS_PANEL_MODULE, error=str(e))
        _safe_log(main_window, f"⚠️ 실전 테스트 도구 탐색 실패: {e}")
        return False

    if spec is None:
        _safe_audit(main_window, "DEVTOOLS_NOT_FOUND", module=DEVTOOLS_PANEL_MODULE)
        return False

    try:
        module = importlib.import_module(DEVTOOLS_PANEL_MODULE)
        register = getattr(module, "register_simulation_panel", None)
        if not callable(register):
            _safe_audit(main_window, "DEVTOOLS_REGISTER_MISSING", module=DEVTOOLS_PANEL_MODULE)
            _safe_log(main_window, "⚠️ 실전 테스트 도구 등록 함수가 없습니다.")
            return False
        ok = bool(register(main_window))
        _safe_audit(main_window, "DEVTOOLS_REGISTERED", module=DEVTOOLS_PANEL_MODULE, ok=ok)
        return ok
    except Exception as e:
        _safe_audit(main_window, "DEVTOOLS_REGISTER_ERROR", module=DEVTOOLS_PANEL_MODULE, error=str(e))
        _safe_log(main_window, f"⚠️ 실전 테스트 도구 로드 실패: {e}")
        try:
            traceback.print_exc()
        except Exception:
            pass
        return False
