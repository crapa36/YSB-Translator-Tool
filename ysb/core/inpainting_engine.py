import os
import sys
from pathlib import Path
import torch
from diffusers import StableDiffusionXLInpaintPipeline, EulerDiscreteScheduler
from PIL import Image
import numpy as np

def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()

class SDXLLightningInpaintEngine:
    def __init__(self, model_dir: str):
        if not os.path.isabs(model_dir):
            model_dir = os.path.abspath(os.path.join(_app_root(), model_dir))

        # 모델 가중치 파일 존재 여부 검증 (Git LFS pull 누락 방지)
        unet_dir = os.path.join(model_dir, "unet")
        if os.path.isdir(unet_dir):
            weight_files = [f for f in os.listdir(unet_dir)
                           if f.endswith((".safetensors", ".bin"))]
            if not weight_files:
                raise FileNotFoundError(
                    f"모델 가중치 파일이 없습니다: {unet_dir}\n"
                    f"Git LFS 파일이 다운로드되지 않은 것 같습니다.\n"
                    f"모델 디렉토리에서 'git lfs pull'을 실행하거나, "
                    f"Hugging Face에서 직접 다운로드하세요."
                )

        # fp16 variant 파일 존재 여부 확인 후 fallback
        has_fp16 = any(
            f.startswith("diffusion_pytorch_model.fp16.")
            for f in os.listdir(unet_dir)
        ) if os.path.isdir(unet_dir) else False

        load_kwargs = dict(
            torch_dtype=torch.float16,
            use_safetensors=True,
        )
        if has_fp16:
            load_kwargs["variant"] = "fp16"

        self.pipe = StableDiffusionXLInpaintPipeline.from_pretrained(
            model_dir, **load_kwargs
        ).to("cuda")
        
        # 로컬 폴더에 위치한 SDXL Lightning 4-Step LoRA 가중치 파일 로드 및 병합
        lora_dir = os.path.abspath(os.path.join(_app_root(), "local_models", "sdxl_lightning"))
        self.pipe.load_lora_weights(
            lora_dir, 
            weight_name="sdxl_lightning_4step_lora.safetensors"
        )
        self.pipe.fuse_lora()
        
        # 스케줄러를 트레일링 타임스텝 방식으로 설정하여 4스텝만으로 완벽한 품질 유도
        self.pipe.scheduler = EulerDiscreteScheduler.from_config(
            self.pipe.scheduler.config, 
            timestep_spacing="trailing"
        )
        
        # 메모리 효율성 최대화 (xformers 혹은 SDPA 강제 적용)
        self.pipe.enable_attention_slicing()

    def inpaint(self, image_np: np.ndarray, mask_np: np.ndarray) -> np.ndarray:
        # NumPy 배열을 PIL 이미지로 변환
        init_image = Image.fromarray(image_np).convert("RGB")
        mask_image = Image.fromarray(mask_np).convert("L")

        # 원본 크기 보존 (파이프라인 출력 후 복원용)
        orig_w, orig_h = init_image.size

        # SDXL VAE는 8의 배수 크기를 요구한다. 맞지 않으면 shape mismatch로 실패하거나
        # 품질이 저하된다. 8의 배수로 올림하고, 결과를 원본 크기로 복원한다.
        target_w = (orig_w + 7) // 8 * 8
        target_h = (orig_h + 7) // 8 * 8

        if (target_w, target_h) != (orig_w, orig_h):
            init_image = init_image.resize((target_w, target_h), Image.LANCZOS)
            mask_image = mask_image.resize((target_w, target_h), Image.NEAREST)

        # 4스텝 고속 추론 구동
        # - strength=0.9999: 마스크 영역을 거의 완전히 재생성한다.
        #   이 값이 없으면 기본값(~0.6)이 적용되어 actual_steps = floor(4 * 0.6) = 2가 되고,
        #   마스크 영역의 원본 텍스트가 거의 그대로 보존되어 글씨가 지워지지 않는다.
        # - guidance_scale=0.0: Lightning 4-Step은 CFG 없이 학습되었다.
        #   CFG ≤ 1.0이면 negative_prompt는 무시되므로 전달하지 않는다.
        with torch.inference_mode():
            output = self.pipe(
                prompt="clean background, highly detailed, seamless texture",
                image=init_image,
                mask_image=mask_image,
                num_inference_steps=4,
                guidance_scale=0.0,
                strength=0.9999,
            ).images[0]

        # 8의 배수 정규화로 크기가 바뀌었으면 원본 크기로 복원
        if (target_w, target_h) != (orig_w, orig_h):
            output = output.resize((orig_w, orig_h), Image.LANCZOS)

        return np.array(output)

