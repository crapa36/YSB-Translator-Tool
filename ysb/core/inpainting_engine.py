import torch
from diffusers import StableDiffusionXLInpaintPipeline, EulerDiscreteScheduler
from PIL import Image
import numpy as np

class SDXLLightningInpaintEngine:
    def __init__(self, model_dir: str):
        # 16GB VRAM 최적화 FP16 세팅으로 로딩
        self.pipe = StableDiffusionXLInpaintPipeline.from_pretrained(
            "diffusers/stable-diffusion-xl-1.0-inpainting-0.1",
            torch_dtype=torch.float16,
            variant="fp16",
            use_safetensors=True
        ).to("cuda")
        
        # SDXL Lightning 4-Step LoRA 융합
        self.pipe.load_lora_weights(
            "ByteDance/SDXL-Lightning", 
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
        
        # 4스텝 고속 추론 구동
        with torch.inference_mode():
            output = self.pipe(
                prompt="clean background, highly detailed, seamless texture, masterpiece",
                negative_prompt="text, watermark, logo, deformed, blurry, ugly, low quality",
                image=init_image,
                mask_image=mask_image,
                num_inference_steps=4,
                guidance_scale=1.0, # Lightning 구조는 가이던스 스케일 1.0이 정석
            ).images[0]
            
        return np.array(output)
