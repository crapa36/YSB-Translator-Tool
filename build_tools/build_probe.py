# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_module_spec(name: str, label: str | None = None) -> None:
    label = label or name
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise ModuleNotFoundError(f"No module named '{name}'")
    origin = spec.origin or "(namespace/package)"
    print(f"{label} FOUND: {origin}")


def check_import(name: str, label: str | None = None) -> None:
    label = label or name
    mod = importlib.import_module(name)
    path = getattr(mod, "__file__", "")
    print(f"{label} OK" + (f": {path}" if path else ""))


def main() -> int:
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python: {sys.version}")

    # Local package checks only. Do not import the actual UI modules here.
    check_module_spec("ysb", "Local package ysb")
    check_module_spec("ysb.ui.main_window", "Local module ysb.ui.main_window")
    check_module_spec("ysb.core.ysb_launcher", "Local module ysb.core.ysb_launcher")

    # Keep external checks short. Heavy optional API packages are checked at runtime.
    for name in [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "cv2",
        "numpy",
        "requests",
        "PIL._imaging",
    ]:
        check_import(name)

    print("Build environment check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
