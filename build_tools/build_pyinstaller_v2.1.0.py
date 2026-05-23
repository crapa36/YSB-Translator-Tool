# -*- coding: utf-8 -*-
"""Deprecated combined build entry.

The Lite and Local packages are intentionally built from separate files now so
compression time and bundled contents can be checked per edition.

Use one of these instead:
- build_tools/build_pyinstaller_lite_v2.1.0.py
- build_tools/build_pyinstaller_local_v2.1.0.py
"""
from __future__ import annotations

import sys


def main() -> int:
    print("This combined Lite+Local build driver is deprecated.")
    print("Use one of these single-edition drivers instead:")
    print("  build_tools\\build_lite_exe_v2.1.0.bat")
    print("  build_tools\\build_local_exe_v2.1.0.bat")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
