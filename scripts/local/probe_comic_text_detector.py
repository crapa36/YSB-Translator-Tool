# -*- coding: utf-8 -*-
"""Run Local comic_text_detector on one image and write a small JSON report.

Usage:
    python scripts/local/probe_comic_text_detector.py path/to/image.png
    python scripts/local/probe_comic_text_detector.py path/to/image.png --out tmp_detector
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ysb.editions.current import set_current_edition
from ysb.engines.text_detection.base import TextDetectionRequest
from ysb.engines.text_detection.manager import detect_with_default_engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="Image path to inspect")
    parser.add_argument("--out", default="", help="Output directory for masks/report")
    parser.add_argument("--device", default="auto", help="auto/cpu/cuda")
    parser.add_argument("--input-size", type=int, default=1024)
    args = parser.parse_args()

    set_current_edition("local")
    image = Path(args.image).resolve()
    out_dir = Path(args.out).resolve() if args.out else image.parent / f"{image.stem}_comic_detector_probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = detect_with_default_engine(TextDetectionRequest(
        image_path=str(image),
        options={
            "save_masks": True,
            "output_dir": str(out_dir),
            "device": args.device,
            "input_size": args.input_size,
        },
    ))

    report = {
        "ok": result.ok,
        "engine": result.engine,
        "error": result.error,
        "mask_path": result.mask_path,
        "refined_mask_path": result.refined_mask_path,
        "blocks": [
            {
                "bbox": list(block.bbox),
                "language": block.language,
                "vertical": block.vertical,
                "font_size": block.font_size,
                "angle": block.angle,
                "line_count": len(block.lines),
                "lines": [[list(pt) for pt in line.polygon] for line in block.lines],
            }
            for block in result.blocks
        ],
    }
    report_path = out_dir / f"{image.stem}.comic_detector_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ok={result.ok} engine={result.engine} blocks={len(result.blocks)}")
    if result.error:
        print(f"error={result.error}")
    print(f"report={report_path}")
    if result.refined_mask_path:
        print(f"mask={result.refined_mask_path}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
