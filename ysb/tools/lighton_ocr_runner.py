# -*- coding: utf-8 -*-
"""Batch runner for LOCAL LightOnOCR OCR crops.

Executed from the separate .venv_lightocr environment so the heavy VLM/OCR
runtime does not pollute the main YSB runtime venv.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _clean_text(text):
    text = str(text or "")
    text = re.sub(r"<\|[^|]+\|>", " ", text)
    text = text.replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        low = line.lower()
        if low in ("text", "ocr", "assistant"):
            continue
        if low.startswith("the visible text") or low.startswith("here is"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--prompt", default="Extract all visible text from this image. Return only the text. Do not translate.")
    ap.add_argument("--max-new-tokens", type=int, default=160)
    args = ap.parse_args()

    model_dir = str(Path(args.model_dir).resolve())
    manifest_path = Path(args.manifest)
    output_path = Path(args.output)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = data.get("items", []) if isinstance(data, dict) else []

    # LightOnOCR-2 is supported by the Transformers v5 LightOnOcr classes.
    # Keep imports inside the runner process so YSB's main venv stays light.
    import torch
    from PIL import Image
    try:
        from transformers import LightOnOcrForConditionalGeneration, LightOnOcrProcessor
    except Exception as e:
        raise RuntimeError(
            "LightOnOCR requires Transformers v5 with LightOnOcr classes. "
            "Run install_local_lightocr_v2.1.0.bat again. Original error: " + str(e)
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    processor = LightOnOcrProcessor.from_pretrained(model_dir, local_files_only=True)
    model = LightOnOcrForConditionalGeneration.from_pretrained(
        model_dir,
        torch_dtype=dtype,
        local_files_only=True,
    ).to(device)
    model.eval()

    results = []
    for item in items:
        item_id = item.get("id")
        image_path = str(item.get("path") or "")
        try:
            image = Image.open(image_path).convert("RGB")
            conversation = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": args.prompt},
                    ],
                }
            ]
            try:
                inputs = processor.apply_chat_template(
                    conversation,
                    add_generation_prompt=True,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt",
                )
            except Exception:
                # Some processor builds follow the model card's URL-style schema.
                conversation = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "url": image_path},
                            {"type": "text", "text": args.prompt},
                        ],
                    }
                ]
                inputs = processor.apply_chat_template(
                    conversation,
                    add_generation_prompt=True,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt",
                )
            inputs = {
                k: (v.to(device=device, dtype=dtype) if hasattr(v, "is_floating_point") and v.is_floating_point() else v.to(device))
                for k, v in inputs.items()
            }
            with torch.no_grad():
                output_ids = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
            start = inputs["input_ids"].shape[1]
            generated_ids = output_ids[0, start:]
            text = processor.decode(generated_ids, skip_special_tokens=True)
            results.append({"id": item_id, "text": _clean_text(text), "error": ""})
        except Exception as e:
            results.append({"id": item_id, "text": "", "error": str(e)})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"LightOnOCR completed: {len(results)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
