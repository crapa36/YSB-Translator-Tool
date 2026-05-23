# -*- coding: utf-8 -*-
"""Deprecated combined build entry.

The Lite and Local packages are intentionally built from separate files now so
compression time and bundled contents can be checked per edition.

Use one of these instead:
- build_tools/build_pyinstaller_lite.py
- build_tools/build_pyinstaller_local.py
"""
from __future__ import annotations

import sys


def main() -> int:
    print("This combined Lite+Local build driver is deprecated.")
    print("Use one of these single-edition drivers instead:")
    print("  build_tools\\build_lite_exe.bat")
    print("  build_tools\\build_local_exe.bat")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
