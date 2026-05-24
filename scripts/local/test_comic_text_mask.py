# -*- coding: utf-8 -*-
"""Visual mask test for Local comic_text_detector.

This script does not run OCR. It checks the most important Local detector part:
"Does the detector produce a mask that can actually be used for text removal?"

Usage:
    python scripts/local/test_comic_text_mask.py path/to/page.png
    python scripts/local/test_comic_text_mask.py path/to/page.png --out tmp_mask_test
    python scripts/local/test_comic_text_mask.py path/to/page.png --dilate 2 --device cpu

Outputs:
    *.comic_detector_report.json
    *.mask_used.png
    *.mask_overlay.png
    *.mask_whiteout_preview.png
    *.mask_cv2_inpaint_preview.png
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
from ysb.engines.text_detection.mask_preview import write_mask_preview_set


def _line_to_json(line):
    return {
        "polygon": [[int(x), int(y)] for x, y in line.polygon],
        "confidence": line.confidence,
    }


def _block_to_json(block):
    return {
        "bbox": [int(v) for v in block.bbox],
        "language": block.language,
        "vertical": block.vertical,
        "font_size": block.font_size,
        "angle": block.angle,
        "confidence": block.confidence,
        "line_count": len(block.lines),
        "lines": [_line_to_json(line) for line in block.lines],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Test comic_text_detector mask outputs visually.")
    parser.add_argument("image", help="Image path to test")
    parser.add_argument("--out", default="", help="Output directory. Default: <image>_mask_test")
    parser.add_argument("--device", default="auto", help="auto/cpu/cuda")
    parser.add_argument("--input-size", type=int, default=1024, help="Detector input size")
    parser.add_argument("--dilate", type=int, default=0, help="Expand final preview mask by N pixels")
    parser.add_argument("--inpaint-radius", type=int, default=3, help="OpenCV preview inpaint radius")
    parser.add_argument(
        "--no-undetected-mask",
        action="store_true",
        help="Disable comic_text_detector keep_undetected_mask option",
    )
    args = parser.parse_args()

    set_current_edition("local")

    image = Path(args.image).resolve()
    if not image.exists():
        print(f"Image not found: {image}")
        return 2

    out_dir = Path(args.out).resolve() if args.out else image.parent / f"{image.stem}_mask_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = detect_with_default_engine(
        TextDetectionRequest(
            image_path=str(image),
            options={
                "save_masks": True,
                "output_dir": str(out_dir),
                "device": args.device,
                "input_size": args.input_size,
                "keep_undetected_mask": not args.no_undetected_mask,
            },
        )
    )

    preview_paths: dict[str, str] = {}
    if result.ok:
        raw = result.raw or {}
        mask = raw.get("mask_refined") or raw.get("mask")
        if mask is not None:
            preview_paths = write_mask_preview_set(
                image_path=image,
                mask=mask,
                output_dir=out_dir,
                stem=image.stem,
                dilate_px=args.dilate,
                inpaint_radius=args.inpaint_radius,
            )

    report = {
        "ok": result.ok,
        "engine": result.engine,
        "error": result.error,
        "input_image": str(image),
        "output_dir": str(out_dir),
        "block_count": len(result.blocks),
        "detector_mask_path": result.mask_path,
        "detector_refined_mask_path": result.refined_mask_path,
        "preview_paths": preview_paths,
        "options": {
            "device": args.device,
            "input_size": args.input_size,
            "dilate": args.dilate,
            "inpaint_radius": args.inpaint_radius,
            "keep_undetected_mask": not args.no_undetected_mask,
        },
        "blocks": [_block_to_json(block) for block in result.blocks],
    }
    report_path = out_dir / f"{image.stem}.comic_mask_test_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ok={result.ok} engine={result.engine} blocks={len(result.blocks)}")
    if result.error:
        print(f"error={result.error}")
    print(f"report={report_path}")
    for label, path in preview_paths.items():
        print(f"{label}={path}")
    if result.ok and not preview_paths:
        print("Detector ran, but no mask was returned for preview.")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
