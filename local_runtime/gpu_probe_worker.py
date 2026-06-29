# -*- coding: utf-8 -*-
"""Standalone YSB Local GPU/CUDA probe worker.

This file is copied next to packaged Local runtimes.  It lets support/debug
workflows run the same diagnosis without depending on a user-installed Python.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap_project_root() -> Path:
    here = Path(__file__).resolve()
    # Source/package layout: <root>/local_runtime/gpu_probe_worker.py
    root = here.parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def main() -> int:
    _bootstrap_project_root()
    from ysb.editions.local.cuda_runtime_probe import run_full_probe
    report = run_full_probe(write_report=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
