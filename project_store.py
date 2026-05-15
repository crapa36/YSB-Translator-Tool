import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Any

import cv2
import numpy as np


PROJECT_VERSION = 1
PROJECT_FILENAME = "project.json"


def imread_unicode(path: str):
    arr = np.fromfile(path, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def relpath(path: str, root: str) -> str:
    return os.path.relpath(path, root).replace("\\", "/")


def abs_from_rel(root: str, rel: str) -> str:
    return os.path.join(root, rel.replace("/", os.sep))


def json_safe(value: Any):
    """numpy 값이 섞여도 project.json에 들어갈 수 있게 변환."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


class ProjectStore:
    """
    프로젝트 폴더 저장/불러오기 담당.

    폴더 구조:
    project_dir/
      project.json
      images/
      masks/
      clean/
      scripts/
    """

    def __init__(self, project_dir: str | None = None):
        self.project_dir = project_dir

    @property
    def project_file(self) -> str | None:
        if not self.project_dir:
            return None
        return os.path.join(self.project_dir, PROJECT_FILENAME)

    def init_dirs(self):
        if not self.project_dir:
            raise ValueError("project_dir이 비어 있습니다.")
        ensure_dir(self.project_dir)
        ensure_dir(os.path.join(self.project_dir, "images"))
        ensure_dir(os.path.join(self.project_dir, "masks"))
        ensure_dir(os.path.join(self.project_dir, "clean"))
        ensure_dir(os.path.join(self.project_dir, "scripts"))
        ensure_dir(os.path.join(self.project_dir, "Result"))
        ensure_dir(os.path.join(self.project_dir, "Txt"))

    def create_from_images(self, project_dir: str, source_paths: List[str]) -> Tuple[List[str], Dict[int, dict]]:
        self.project_dir = project_dir
        self.init_dirs()

        paths: List[str] = []
        data: Dict[int, dict] = {}

        for i, src in enumerate(source_paths):
            src_path = Path(src)
            ext = src_path.suffix.lower() or ".png"
            dst_name = f"{i + 1:04d}{ext}"
            dst = os.path.join(self.project_dir, "images", dst_name)
            shutil.copy2(src, dst)

            img = imread_unicode(dst)
            paths.append(dst)
            data[i] = {
                "ori": img,
                "data": [],
                "mask_merge": None,
                "mask_inpaint": None,
                "mask_merge_off": None,
                "mask_inpaint_off": None,
                "mask_toggle_enabled": False,
                "use_inpainted_as_source": False,
                "bg_clean": None,
                "working_source": None,
                "final_paint": None,
                "final_paint_above": None,
                "original_name": src_path.name,
            }

        self.save(paths, data, current_index=0)
        return paths, data

    def save(self, paths: List[str], data: Dict[int, dict], current_index: int = 0):
        if not self.project_dir:
            return

        self.init_dirs()

        pages = []
        for i, image_path in enumerate(paths):
            curr = data.get(i, {})

            # 이미지가 프로젝트 images 밖에 있으면 복사해서 프로젝트 내부로 고정
            abs_image = os.path.abspath(image_path)
            project_abs = os.path.abspath(self.project_dir)
            if not abs_image.startswith(project_abs):
                ext = Path(image_path).suffix.lower() or ".png"
                dst = os.path.join(self.project_dir, "images", f"{i + 1:04d}{ext}")
                if os.path.abspath(image_path) != os.path.abspath(dst):
                    shutil.copy2(image_path, dst)
                image_path = dst
                paths[i] = dst

            page = {
                "image": relpath(image_path, self.project_dir),
                "original_name": curr.get("original_name", os.path.basename(image_path)),
                "data": json_safe(curr.get("data", [])),
            }

            mask_merge = curr.get("mask_merge")
            if mask_merge is not None:
                mask_path = os.path.join(self.project_dir, "masks", f"mask_merge_{i + 1:04d}.npy")
                np.save(mask_path, np.array(mask_merge, dtype=np.uint8).copy())
                page["mask_merge"] = relpath(mask_path, self.project_dir)

            mask_inpaint = curr.get("mask_inpaint")
            if mask_inpaint is not None:
                mask_path = os.path.join(self.project_dir, "masks", f"mask_inpaint_{i + 1:04d}.npy")
                np.save(mask_path, np.array(mask_inpaint, dtype=np.uint8).copy())
                page["mask_inpaint"] = relpath(mask_path, self.project_dir)

            mask_merge_off = curr.get("mask_merge_off")
            if mask_merge_off is not None:
                mask_path = os.path.join(self.project_dir, "masks", f"mask_merge_off_{i + 1:04d}.npy")
                np.save(mask_path, np.array(mask_merge_off, dtype=np.uint8).copy())
                page["mask_merge_off"] = relpath(mask_path, self.project_dir)

            mask_inpaint_off = curr.get("mask_inpaint_off")
            if mask_inpaint_off is not None:
                mask_path = os.path.join(self.project_dir, "masks", f"mask_inpaint_off_{i + 1:04d}.npy")
                np.save(mask_path, np.array(mask_inpaint_off, dtype=np.uint8).copy())
                page["mask_inpaint_off"] = relpath(mask_path, self.project_dir)

            page["mask_toggle_enabled"] = bool(curr.get("mask_toggle_enabled", False))
            page["use_inpainted_as_source"] = bool(curr.get("use_inpainted_as_source", False))

            working_source = curr.get("working_source")
            if working_source is not None:
                source_path = os.path.join(self.project_dir, "clean", f"working_source_{i + 1:04d}.png")
                if isinstance(working_source, (bytes, bytearray)):
                    with open(source_path, "wb") as f:
                        f.write(working_source)
                    page["working_source"] = relpath(source_path, self.project_dir)
                elif isinstance(working_source, np.ndarray):
                    cv2.imwrite(source_path, working_source)
                    page["working_source"] = relpath(source_path, self.project_dir)

            bg_clean = curr.get("bg_clean")
            if bg_clean is not None:
                clean_path = os.path.join(self.project_dir, "clean", f"clean_{i + 1:04d}.png")
                if isinstance(bg_clean, (bytes, bytearray)):
                    with open(clean_path, "wb") as f:
                        f.write(bg_clean)
                    page["clean"] = relpath(clean_path, self.project_dir)
                elif isinstance(bg_clean, np.ndarray):
                    cv2.imwrite(clean_path, bg_clean)
                    page["clean"] = relpath(clean_path, self.project_dir)

            final_paint = curr.get("final_paint")
            if final_paint is not None:
                paint_path = os.path.join(self.project_dir, "clean", f"final_paint_{i + 1:04d}.png")
                if isinstance(final_paint, (bytes, bytearray)):
                    with open(paint_path, "wb") as f:
                        f.write(final_paint)
                    page["final_paint"] = relpath(paint_path, self.project_dir)
                elif isinstance(final_paint, np.ndarray):
                    cv2.imwrite(paint_path, final_paint)
                    page["final_paint"] = relpath(paint_path, self.project_dir)

            final_paint_above = curr.get("final_paint_above")
            if final_paint_above is not None:
                paint_path = os.path.join(self.project_dir, "clean", f"final_paint_above_{i + 1:04d}.png")
                if isinstance(final_paint_above, (bytes, bytearray)):
                    with open(paint_path, "wb") as f:
                        f.write(final_paint_above)
                    page["final_paint_above"] = relpath(paint_path, self.project_dir)
                elif isinstance(final_paint_above, np.ndarray):
                    cv2.imwrite(paint_path, final_paint_above)
                    page["final_paint_above"] = relpath(paint_path, self.project_dir)

            pages.append(page)

        payload = {
            "version": PROJECT_VERSION,
            "current_index": int(current_index),
            "pages": pages,
        }

        with open(self.project_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load(self, project_json_path: str) -> Tuple[List[str], Dict[int, dict], int]:
        project_json_path = os.path.abspath(project_json_path)
        self.project_dir = os.path.dirname(project_json_path)

        with open(project_json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        paths: List[str] = []
        data: Dict[int, dict] = {}

        for i, page in enumerate(payload.get("pages", [])):
            image_path = abs_from_rel(self.project_dir, page["image"])
            paths.append(image_path)

            ori = imread_unicode(image_path) if os.path.exists(image_path) else None

            mask_merge = None
            if page.get("mask_merge"):
                p = abs_from_rel(self.project_dir, page["mask_merge"])
                if os.path.exists(p):
                    mask_merge = np.load(p).copy()

            mask_inpaint = None
            if page.get("mask_inpaint"):
                p = abs_from_rel(self.project_dir, page["mask_inpaint"])
                if os.path.exists(p):
                    mask_inpaint = np.load(p).copy()

            mask_merge_off = None
            if page.get("mask_merge_off"):
                p = abs_from_rel(self.project_dir, page["mask_merge_off"])
                if os.path.exists(p):
                    mask_merge_off = np.load(p).copy()

            mask_inpaint_off = None
            if page.get("mask_inpaint_off"):
                p = abs_from_rel(self.project_dir, page["mask_inpaint_off"])
                if os.path.exists(p):
                    mask_inpaint_off = np.load(p).copy()

            working_source = None
            if page.get("working_source"):
                p = abs_from_rel(self.project_dir, page["working_source"])
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        working_source = f.read()

            bg_clean = None
            if page.get("clean"):
                p = abs_from_rel(self.project_dir, page["clean"])
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        bg_clean = f.read()

            final_paint = None
            if page.get("final_paint"):
                p = abs_from_rel(self.project_dir, page["final_paint"])
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        final_paint = f.read()

            final_paint_above = None
            if page.get("final_paint_above"):
                p = abs_from_rel(self.project_dir, page["final_paint_above"])
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        final_paint_above = f.read()

            data[i] = {
                "ori": ori,
                "data": page.get("data", []),
                "mask_merge": mask_merge,
                "mask_inpaint": mask_inpaint,
                "mask_merge_off": mask_merge_off,
                "mask_inpaint_off": mask_inpaint_off,
                "mask_toggle_enabled": bool(page.get("mask_toggle_enabled", False)),
                "use_inpainted_as_source": bool(page.get("use_inpainted_as_source", False)),
                "bg_clean": bg_clean,
                "working_source": working_source,
                "final_paint": final_paint,
                "final_paint_above": final_paint_above,
                "original_name": page.get("original_name", os.path.basename(image_path)),
            }

        current_index = int(payload.get("current_index", 0))
        if paths:
            current_index = max(0, min(current_index, len(paths) - 1))
        else:
            current_index = 0

        return paths, data, current_index
