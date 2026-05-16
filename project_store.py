import os
import json
import shutil
import zipfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any

import cv2
import numpy as np


PROJECT_VERSION = 1
PROJECT_FILENAME = "project.json"
MANIFEST_FILENAME = "manifest.json"
YSB_EXTENSION = ".ysbt"
YSBT_SIGNATURE = b"YSBT-PROJECT\x00\r\n\x1a\n"
SIGNATURE_FILENAME = ".ysbt_signature"


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
      manifest.json
      images/
      masks/text_mask/
      masks/paint_mask/
      clean/
      working_source/
      final_paint/
      final_paint_above/
      scripts/
      Result/
      Txt/
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
        ensure_dir(os.path.join(self.project_dir, "masks", "text_mask"))
        ensure_dir(os.path.join(self.project_dir, "masks", "paint_mask"))
        ensure_dir(os.path.join(self.project_dir, "masks", "text_mask_off"))
        ensure_dir(os.path.join(self.project_dir, "masks", "paint_mask_off"))
        ensure_dir(os.path.join(self.project_dir, "clean"))
        ensure_dir(os.path.join(self.project_dir, "working_source"))
        ensure_dir(os.path.join(self.project_dir, "final_paint"))
        ensure_dir(os.path.join(self.project_dir, "final_paint_above"))
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


    def project_uuid(self) -> str:
        if not self.project_dir:
            return uuid.uuid4().hex
        manifest_path = os.path.join(self.project_dir, MANIFEST_FILENAME)
        try:
            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("project_uuid"):
                    return str(data["project_uuid"])
        except Exception:
            pass
        return uuid.uuid4().hex

    def write_manifest(self, package_source: str | None = None, project_name: str | None = None, project_uuid: str | None = None):
        if not self.project_dir:
            return
        manifest_path = os.path.join(self.project_dir, MANIFEST_FILENAME)
        old = {}
        try:
            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    old = loaded
        except Exception:
            old = {}
        now = datetime.now().isoformat(timespec="seconds")

        folder_name = clean_workspace_name(Path(self.project_dir).name)
        old_name = str(old.get("project_name") or "")
        if project_name:
            final_name = clean_workspace_name(project_name)
        elif old_name.startswith("unsaved_") or not old_name:
            final_name = folder_name
        else:
            final_name = clean_workspace_name(old_name)

        final_uuid = str(project_uuid or old.get("project_uuid") or uuid.uuid4().hex)
        payload = {
            "format": "YSBT_PROJECT",
            "signature": "YSBT-PROJECT",
            "format_version": "1.0",
            "project_uuid": final_uuid,
            "project_name": final_name,
            "project_version": PROJECT_VERSION,
            "created_at": old.get("created_at") or now,
            "last_saved_at": now,
        }
        if package_source:
            payload["package_source"] = package_source
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

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
                mask_path = os.path.join(self.project_dir, "masks", "text_mask", f"mask_merge_{i + 1:04d}.npy")
                np.save(mask_path, np.array(mask_merge, dtype=np.uint8).copy())
                page["mask_merge"] = relpath(mask_path, self.project_dir)

            mask_inpaint = curr.get("mask_inpaint")
            if mask_inpaint is not None:
                mask_path = os.path.join(self.project_dir, "masks", "paint_mask", f"mask_inpaint_{i + 1:04d}.npy")
                np.save(mask_path, np.array(mask_inpaint, dtype=np.uint8).copy())
                page["mask_inpaint"] = relpath(mask_path, self.project_dir)

            mask_merge_off = curr.get("mask_merge_off")
            if mask_merge_off is not None:
                mask_path = os.path.join(self.project_dir, "masks", "text_mask_off", f"mask_merge_off_{i + 1:04d}.npy")
                np.save(mask_path, np.array(mask_merge_off, dtype=np.uint8).copy())
                page["mask_merge_off"] = relpath(mask_path, self.project_dir)

            mask_inpaint_off = curr.get("mask_inpaint_off")
            if mask_inpaint_off is not None:
                mask_path = os.path.join(self.project_dir, "masks", "paint_mask_off", f"mask_inpaint_off_{i + 1:04d}.npy")
                np.save(mask_path, np.array(mask_inpaint_off, dtype=np.uint8).copy())
                page["mask_inpaint_off"] = relpath(mask_path, self.project_dir)

            page["mask_toggle_enabled"] = bool(curr.get("mask_toggle_enabled", False))
            page["use_inpainted_as_source"] = bool(curr.get("use_inpainted_as_source", False))

            working_source = curr.get("working_source")
            if working_source is not None:
                source_path = os.path.join(self.project_dir, "working_source", f"working_source_{i + 1:04d}.png")
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
                paint_path = os.path.join(self.project_dir, "final_paint", f"final_paint_{i + 1:04d}.png")
                if isinstance(final_paint, (bytes, bytearray)):
                    with open(paint_path, "wb") as f:
                        f.write(final_paint)
                    page["final_paint"] = relpath(paint_path, self.project_dir)
                elif isinstance(final_paint, np.ndarray):
                    cv2.imwrite(paint_path, final_paint)
                    page["final_paint"] = relpath(paint_path, self.project_dir)

            final_paint_above = curr.get("final_paint_above")
            if final_paint_above is not None:
                paint_path = os.path.join(self.project_dir, "final_paint_above", f"final_paint_above_{i + 1:04d}.png")
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

        self.write_manifest()
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



def has_ysbt_signature(path: str) -> bool:
    """YSBT 전용 파일인지 파일 앞쪽 고유 바이트로 확인한다."""
    try:
        with open(path, "rb") as f:
            return f.read(len(YSBT_SIGNATURE)) == YSBT_SIGNATURE
    except Exception:
        return False


def assert_ysbt_signature(path: str):
    """확장자만 바꾼 일반 ZIP/다른 파일을 잘못 여는 것을 막는다."""
    if not has_ysbt_signature(path):
        raise ValueError("YSBT 전용 시그니처가 없습니다. 올바른 .ysbt 프로젝트 파일이 아닙니다.")


def read_ysb_manifest(ysb_path: str) -> dict:
    """.ysbt 패키지의 manifest.json을 읽는다.

    파일 앞쪽의 YSBT_SIGNATURE를 먼저 확인해, 확장자만 바뀐 ZIP/다른 파일을
    프로젝트로 잘못 여는 것을 막는다.
    """
    assert_ysbt_signature(ysb_path)
    with zipfile.ZipFile(ysb_path, "r") as zf:
        with zf.open(MANIFEST_FILENAME) as f:
            data = json.loads(f.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("manifest.json 형식이 올바르지 않습니다.")
        if data.get("format") != "YSBT_PROJECT" and data.get("signature") != "YSBT-PROJECT":
            raise ValueError("YSBT 프로젝트 manifest가 아닙니다.")
        return data

def safe_project_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    out = "".join("_" if ch in bad else ch for ch in str(name or "ysb_project")).strip()
    return out or "ysb_project"


def clean_workspace_name(name: str) -> str:
    """임시 프로젝트명/패키지명에서 사람이 읽을 기본 이름을 정리한다.

    .ysbt 파일명에는 UUID를 붙이지 않는다.
    UUID는 manifest.json 내부에 저장하고, 작업 폴더를 만들 때만 이름 뒤에 짧게 붙인다.
    예: unsaved_리우1_5c03f97b -> 리우1
    """
    safe = safe_project_name(name or "ysb_project")
    if safe.startswith("unsaved_"):
        rest = safe[len("unsaved_"):]
        parts = rest.rsplit("_", 1)
        if len(parts) == 2 and len(parts[1]) >= 6 and all(ch in "0123456789abcdefABCDEF" for ch in parts[1]):
            safe = parts[0] or "ysb_project"
        else:
            safe = rest or "ysb_project"
    return safe_project_name(safe)


def _read_manifest_from_dir(project_dir: str | Path) -> dict:
    try:
        manifest_path = Path(project_dir) / MANIFEST_FILENAME
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def unique_dir(parent: str | Path, base_name: str) -> str:
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    safe = safe_project_name(base_name)
    cand = parent / safe
    if not cand.exists():
        return str(cand)
    for n in range(2, 10000):
        cand = parent / f"{safe}_{n}"
        if not cand.exists():
            return str(cand)
    return str(parent / f"{safe}_{uuid.uuid4().hex[:8]}")


def unique_dir_with_code_suffix(parent: str | Path, base_name: str, code: str | None = None, *, append_code: bool = True) -> str:
    """base_name 뒤에 고유 코드를 붙여 충돌 없는 작업 폴더를 만든다.

    예: 작품명_a1b2c3d4, 작품명_a1b2c3d4_2
    앞쪽에 코드를 붙이지 않아 정렬/가독성이 유지된다.
    append_code=False이면 base_name 자체에 이미 고유 코드가 들어간 것으로 보고
    충돌 시 _2, _3만 붙인다.
    """
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    safe = safe_project_name(base_name)
    if append_code:
        code = str(code or uuid.uuid4().hex[:8])[:12]
        first = parent / f"{safe}_{code}"
    else:
        first = parent / safe
    if not first.exists():
        return str(first)
    for n in range(2, 10000):
        cand = parent / f"{first.name}_{n}"
        if not cand.exists():
            return str(cand)
    return str(parent / f"{first.name}_{uuid.uuid4().hex[:8]}")


def package_project(project_dir: str, ysb_path: str, project_name: str | None = None, project_uuid: str | None = None) -> str:
    """프로젝트 폴더 전체를 .ysbt 전용 패키지 파일로 묶는다."""
    project_dir = os.path.abspath(project_dir)
    ysb_path = os.path.abspath(ysb_path)
    if not ysb_path.lower().endswith(YSB_EXTENSION):
        ysb_path += YSB_EXTENSION
    if not os.path.exists(os.path.join(project_dir, PROJECT_FILENAME)):
        raise FileNotFoundError(f"{PROJECT_FILENAME}이 없는 프로젝트 폴더입니다: {project_dir}")

    store = ProjectStore(project_dir)
    store.init_dirs()
    store.write_manifest(package_source=ysb_path, project_name=project_name, project_uuid=project_uuid)

    os.makedirs(os.path.dirname(ysb_path), exist_ok=True)
    tmp_path = ysb_path + ".tmp"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    with open(tmp_path, "wb") as raw:
        # ZIP 앞에 전용 고유 바이트를 남긴다. Python zipfile은 앞쪽에 데이터가
        # 붙은 ZIP도 읽을 수 있으므로, 일반 ZIP과 구분하는 안전장치로 사용한다.
        raw.write(YSBT_SIGNATURE)
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.writestr(SIGNATURE_FILENAME, "YSBT-PROJECT\n")
            for root, dirs, files in os.walk(project_dir):
                # __pycache__ 같은 실행 부산물은 제외
                dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".venv", "venv", "build", "dist"}]
                for file in files:
                    if file.endswith((".pyc", ".pyo")):
                        continue
                    abs_path = os.path.join(root, file)
                    rel = os.path.relpath(abs_path, project_dir).replace("\\", "/")
                    zf.write(abs_path, rel)
    os.replace(tmp_path, ysb_path)
    return ysb_path


def _safe_extract_zip(zf: zipfile.ZipFile, target_dir: str):
    target_abs = os.path.abspath(target_dir)
    for member in zf.infolist():
        name = member.filename.replace("\\", "/")
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"안전하지 않은 패키지 경로입니다: {member.filename}")
        dest = os.path.abspath(os.path.join(target_dir, name))
        if not dest.startswith(target_abs):
            raise ValueError(f"패키지 경로가 작업 폴더 밖을 가리킵니다: {member.filename}")
    zf.extractall(target_dir)


def _same_package_source(a: str | None, b: str | None) -> bool:
    try:
        if not a or not b:
            return False
        return os.path.abspath(str(a)).lower() == os.path.abspath(str(b)).lower()
    except Exception:
        return False


def _find_existing_workspace_by_uuid_and_source(workspaces_root: str | Path, project_uuid: str, package_source: str) -> str | None:
    """workspaces 안에서 같은 project_uuid + 같은 .ysbt 경로를 가진 작업 폴더를 찾는다.

    .ysbt 파일명이 기준이고, UUID는 내부 manifest/meta에만 저장된다.
    이미 같은 YSBT를 가져온 상태라면 사용자에게 다시 물어보지 않고 해당 폴더를 조용히 재사용한다.
    """
    try:
        root = Path(workspaces_root)
        if not root.exists():
            return None
        package_source_abs = os.path.abspath(str(package_source)).lower()
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if not (child / PROJECT_FILENAME).exists():
                continue
            m = _read_manifest_from_dir(child)
            if str(m.get("project_uuid") or "") != str(project_uuid):
                continue
            src = str(m.get("package_source") or "")
            if src and os.path.abspath(src).lower() == package_source_abs:
                return str(child)
    except Exception:
        pass
    return None


def extract_ysb_package(ysb_path: str, workspaces_root: str, reuse_existing: bool = True) -> tuple[str, dict, bool]:
    """.ysbt를 workspaces_root 안의 작업 폴더로 푼다.

    반환: (project_dir, manifest, reused_existing)

    v1.6 보정:
    - .ysbt 파일명에는 고유번호를 붙이지 않는다.
    - project_uuid는 .ysbt 내부 manifest.json에 저장한다.
    - 작업 폴더를 만들 때만 파일 제목 뒤에 uuid 짧은값을 붙인다.
      예: 테스트 파일1.ysbt -> workspaces/테스트 파일1_a1b2c3d4
    - 같은 project_uuid + 같은 .ysbt 파일이면 재가져오기 질문 없이 기존 작업 폴더를 재사용한다.
    """
    ysb_path = os.path.abspath(ysb_path)
    manifest = read_ysb_manifest(ysb_path)
    file_title = clean_workspace_name(Path(ysb_path).stem)
    project_uuid = str(manifest.get("project_uuid") or uuid.uuid4().hex)
    code = project_uuid[:8]

    if reuse_existing:
        existing = _find_existing_workspace_by_uuid_and_source(workspaces_root, project_uuid, ysb_path)
        if existing:
            return existing, manifest, True

    # 사용자가 직접 보는 .ysbt 파일명은 깔끔하게 유지하고,
    # 내부 관리용 작업 폴더에만 uuid 짧은값을 뒤에 붙인다.
    base = f"{file_title}_{code}"
    target = os.path.join(str(workspaces_root), base)

    if os.path.exists(os.path.join(target, PROJECT_FILENAME)):
        existing_manifest = _read_manifest_from_dir(target)
        existing_uuid = str(existing_manifest.get("project_uuid") or "")
        existing_source = str(existing_manifest.get("package_source") or "")
        if reuse_existing and existing_uuid and existing_uuid == project_uuid and _same_package_source(existing_source, ysb_path):
            return target, manifest, True
        # 같은 제목/uuid 앞자리 폴더가 이미 다른 파일에 쓰이고 있으면 뒤에 _2, _3만 붙인다.
        target = unique_dir_with_code_suffix(workspaces_root, base, None, append_code=False)
    else:
        os.makedirs(target, exist_ok=True)

    # target이 새로 정해졌다면 안전하게 생성한다.
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(ysb_path, "r") as zf:
        _safe_extract_zip(zf, target)

    if not os.path.exists(os.path.join(target, PROJECT_FILENAME)):
        raise FileNotFoundError(f"패키지 안에 {PROJECT_FILENAME}이 없습니다: {ysb_path}")

    # 압축 해제 후 작업 폴더 manifest에는 실제 패키지 경로와 사람이 읽을 프로젝트명을 기록한다.
    try:
        ProjectStore(target).write_manifest(package_source=ysb_path, project_name=file_title, project_uuid=project_uuid)
    except Exception:
        pass
    return target, manifest, False
