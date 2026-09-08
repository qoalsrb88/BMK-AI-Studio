"""Standalone WD v3 inference. No ComfyUI imports or node runtime.

Preprocessing follows WD timm model configuration (white padding, BGR).
Only SmilingWolf WD v3 models are currently supported.
"""
from pathlib import Path
import csv
import numpy as np
from .core import load_image

def model_signature(model_dir):
    parts=[]
    for name in ('config.json','model.safetensors','selected_tags.csv'):
        path=Path(model_dir)/name
        st=path.stat()
        parts.append(f'{path.resolve()}:{st.st_mtime_ns}:{st.st_size}')
    return '|'.join(parts)

def inference_signature(model_dir,precision='fp32'):
    if precision not in ('fp32','fp16','bf16'):raise ValueError('지원하지 않는 추론 정밀도입니다.')
    signature=model_signature(model_dir)
    return signature if precision=='fp32' else signature+'|precision='+precision

class Tagger:
    def __init__(self,precision='fp32'):
        self.loaded = None
        self.precision=precision

    def _load_model(self, model_dir):
        import torch
        import timm
        from safetensors.torch import load_file
        model_dir = Path(model_dir)
        for name in ('config.json', 'model.safetensors', 'selected_tags.csv'):
            if not (model_dir/name).is_file():
                raise ValueError(f'WD v3 모델 폴더에 {name} 파일이 필요합니다.')
        signature = inference_signature(model_dir,self.precision)
        if self.loaded != signature:
            self.loaded = None
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            if self.precision!='fp32' and self.device.type!='cuda':raise ValueError('FP16/BF16은 CUDA에서 지원합니다. CPU에서는 FP32를 선택하세요.')
            if self.precision=='bf16' and not torch.cuda.is_bf16_supported():raise ValueError('이 GPU는 BF16 추론을 지원하지 않습니다.')
            self.model = timm.create_model(f'local-dir:{model_dir}', pretrained=False).eval()
            self.model.load_state_dict(load_file(str(model_dir/'model.safetensors')))
            self.model.to(self.device, dtype=torch.float32)
            self.config = timm.data.resolve_data_config(self.model.pretrained_cfg, model=self.model)
            with (model_dir/'selected_tags.csv').open(encoding='utf-8') as f:
                self.labels = list(csv.DictReader(f))
            if len(self.labels)!=self.model.num_classes:
                raise ValueError('태그 목록과 모델 출력 개수가 일치하지 않습니다. 같은 모델의 파일을 사용하세요.')
            self.loaded = signature
        return signature

    def _prepare(self, path):
        import torch
        import torch.nn.functional as F
        pil = load_image(path)
        # White composite prevents transparent RGB from influencing tags.
        from PIL import Image
        white = Image.new('RGBA', pil.size, 'white')
        white.alpha_composite(pil)
        a = np.array(white.convert('RGB'), dtype=np.float32)/255
        t = torch.from_numpy(a).permute(2,0,1).unsqueeze(0)
        _, h, w = self.config['input_size']
        ratio = min(w/pil.width, h/pil.height, 1)
        nh,nw = max(1,int(pil.height*ratio)), max(1,int(pil.width*ratio))
        resized = F.interpolate(t, size=(nh,nw), mode=self.config.get('interpolation','bicubic'), align_corners=False)
        inputs = torch.ones((1,3,h,w))
        y,x = (h-nh)//2, (w-nw)//2
        inputs[:,:,y:y+nh,x:x+nw] = resized
        mean = torch.tensor(self.config['mean']).view(1,3,1,1)
        std = torch.tensor(self.config['std']).view(1,3,1,1)
        return ((inputs-mean)/std)[:,[2,1,0]]

    def run_many(self, paths, model_dir):
        import torch
        self._load_model(model_dir)
        inputs=torch.cat([self._prepare(p) for p in paths],dim=0).to(self.device)
        with torch.inference_mode(),torch.autocast(device_type=self.device.type,dtype=torch.bfloat16 if self.precision=='bf16' else torch.float16,enabled=self.precision!='fp32'):
            logits = self.model(inputs)
            if not torch.isfinite(logits).all():
                raise ValueError('모델 출력이 유효하지 않습니다.')
            batches = logits.sigmoid().float().cpu().tolist()
        return [{'device': str(self.device), 'model': Path(model_dir).name, 'precision':self.precision, 'scores': [
            {'tag': row['name'], 'category': int(row['category']), 'score': score}
            for row,score in zip(self.labels,scores)]} for scores in batches]

    def run(self,path,model_dir):
        return self.run_many([path],model_dir)[0]
