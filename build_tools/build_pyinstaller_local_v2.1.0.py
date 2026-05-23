# -*- coding: utf-8 -*-
from __future__ import annotations

from build_pyinstaller_v2_1_0_core import build_edition, log


if __name__ == "__main__":
    try:
        raise SystemExit(build_edition("local"))
    except Exception as exc:
        log("")
        log(f"ERROR: {exc}")
        raise SystemExit(1)
