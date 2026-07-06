import os
import sys
from pathlib import Path
import torch
from PIL import Image
import numpy as np
import cv2

def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()

class LocalInpaintEngine:
    def __init__(self, model_path: str):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if not os.path.isabs(model_path):
            model_path = os.path.abspath(os.path.join(_app_root(), model_path))

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"로컬 모델 파일을 찾을 수 없습니다: {model_path}")

        print(f">>> [Local Inpaint] Loading JIT model from: {model_path} on {self.device}")
        
        try:
            # Load the TorchScript JIT model
            self.model = torch.jit.load(model_path, map_location=self.device)
            self.model.eval()
        except Exception as e:
            err_str = str(e)
            if "PytorchStreamReader" in err_str or "constants.pkl" in err_str or "archive" in err_str:
                raise ValueError(
                    f"모델 로딩 실패: '{os.path.basename(model_path)}' 파일은 일반 PyTorch state_dict 가중치 파일이며, TorchScript(JIT) 형식의 모델이 아닙니다.\n\n"
                    "이 로컬 인페인팅 엔진은 네트워크 구조와 가중치가 하나로 컴파일된 TorchScript JIT 모델(.jit 또는 JIT로 변환된 .pt/.pth)만 직접 로드하여 실행할 수 있습니다.\n"
                    "만약 manga_inpaintor.jit 등의 JIT 전용 모델이 폴더에 있다면 설정창에서 해당 모델을 선택하여 다시 시작해 주세요."
                )
            raise ValueError(f"로컬 모델 로드 중 오류가 발생했습니다: {e}")
        
        self.model_path = model_path
        # Get parameter names from the schema (excluding 'self')
        self.arg_names = [arg.name for arg in self.model.forward.schema.arguments if arg.name != 'self']
        self.is_manga_inpaintor = (len(self.arg_names) == 5 and 'lines' in self.arg_names)
        self.is_mat = "mat" in os.path.basename(model_path).lower()

    @torch.inference_mode()
    def inpaint(self, image_np: np.ndarray, mask_np: np.ndarray) -> np.ndarray:
        # numpy image shape: (H, W, C) [RGB], mask shape: (H, W) [L]
        h, w, c = image_np.shape

        if self.is_manga_inpaintor:
            # 1. Specialized Manga Inpainter signature: (images, lines, masks, noise, ones)
            # Manga inpainter expects grayscale (1 channel) inputs resized to 512x512
            img_gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
            img_resized = cv2.resize(img_gray, (512, 512), interpolation=cv2.INTER_LANCZOS4)
            mask_resized = cv2.resize(mask_np, (512, 512), interpolation=cv2.INTER_NEAREST)

            # Build tensors [1, 1, 512, 512]
            img_tensor = torch.from_numpy(img_resized).float().unsqueeze(0).unsqueeze(0) / 255.0
            # Image normalization range: [-1, 1]
            img_tensor = (img_tensor - 0.5) / 0.5
            mask_tensor = torch.from_numpy(mask_resized).float().unsqueeze(0).unsqueeze(0) / 255.0

            # Helper tensors
            lines_tensor = torch.zeros((1, 1, 512, 512), dtype=torch.float32, device=self.device)
            noise_tensor = torch.randn((1, 1, 512, 512), dtype=torch.float32, device=self.device)
            ones_tensor = torch.ones((1, 1, 512, 512), dtype=torch.float32, device=self.device)

            # Move to device
            img_tensor = img_tensor.to(self.device)
            mask_tensor = mask_tensor.to(self.device)

            # Run inference
            output = self.model(img_tensor, lines_tensor, mask_tensor, noise_tensor, ones_tensor)

            # De-normalize output from [-1, 1] back to [0, 1]
            output = output * 0.5 + 0.5
            output = torch.clamp(output, 0.0, 1.0)

            # Convert 1-channel output tensor back to numpy
            output_np = (output.squeeze(0).squeeze(0).cpu().numpy() * 255.0).astype(np.uint8)
            output_rgb = cv2.cvtColor(output_np, cv2.COLOR_GRAY2RGB)

            # Resize back to original size
            if (512, 512) != (w, h):
                output_resized = cv2.resize(output_rgb, (w, h), interpolation=cv2.INTER_LANCZOS4)
            else:
                output_resized = output_rgb

            # Re-composite only the masked region
            final_img = image_np.copy()
            mask_bool = (mask_np > 10)
            final_img[mask_bool] = output_resized[mask_bool]
            return final_img

        else:
            # 2. Standard (LaMa / MAT) signature: (images, masks)
            if self.is_mat:
                # MAT typically expects 512x512
                target_w = 512
                target_h = 512
            else:
                # LaMa expects multiples of 8
                target_w = (w + 7) // 8 * 8
                target_h = (h + 7) // 8 * 8

            img_resized = cv2.resize(image_np, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
            mask_resized = cv2.resize(mask_np, (target_w, target_h), interpolation=cv2.INTER_NEAREST)

            # Build tensors [1, C, H, W]
            img_tensor = torch.from_numpy(img_resized).float().permute(2, 0, 1).unsqueeze(0) / 255.0
            mask_tensor = torch.from_numpy(mask_resized).float().unsqueeze(0).unsqueeze(0) / 255.0

            if self.is_mat:
                # MAT normalization range is [-1, 1]
                img_tensor = (img_tensor - 0.5) / 0.5

            # Move to device
            img_tensor = img_tensor.to(self.device)
            mask_tensor = mask_tensor.to(self.device)

            # Run inference
            output = self.model(img_tensor, mask_tensor)

            # Handle outputs (tuples or dicts)
            if isinstance(output, tuple):
                output = output[0]
            elif isinstance(output, dict):
                for key in ("image", "output", "prediction"):
                    if key in output:
                        output = output[key]
                        break

            if self.is_mat:
                # De-normalize MAT output from [-1, 1] back to [0, 1]
                output = output * 0.5 + 0.5

            # Clamp and convert back to numpy
            output = torch.clamp(output, 0.0, 1.0)
            output_np = (output.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).astype(np.uint8)

            # Resize back to original size
            if (target_w, target_h) != (w, h):
                output_np = cv2.resize(output_np, (w, h), interpolation=cv2.INTER_LANCZOS4)

            # Re-composite only the masked region to preserve clean original background pixels
            final_img = image_np.copy()
            mask_bool = (mask_np > 10)
            final_img[mask_bool] = output_np[mask_bool]

            return final_img
