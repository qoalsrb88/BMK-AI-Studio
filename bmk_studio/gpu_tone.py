"""CUDA counterpart of the CPU edge-clamped wavelet tone filter."""
import numpy as np
from PIL import Image

def low_frequency_tensor(value,levels):
    import torch
    for level in range(levels):
        radius=2**level
        for axis in (0,1):
            indices=torch.arange(value.shape[axis],device=value.device)
            left=value.index_select(axis,(indices-radius).clamp(0,value.shape[axis]-1))
            right=value.index_select(axis,(indices+radius).clamp(0,value.shape[axis]-1))
            value=(left+2*value+right)*.25
    return value

def tone_restore_cuda(content,reference,strength=.8,levels=5,luminance=False):
    import torch
    if not torch.cuda.is_available():raise ValueError('CUDA GPU를 사용할 수 없습니다. CPU 톤 처리를 선택하세요.')
    if not 1<=levels<=8 or not np.isfinite(strength):raise ValueError('톤 설정이 유효하지 않습니다.')
    with torch.inference_mode():
        a=torch.from_numpy(np.asarray(content.convert('RGB'),dtype=np.float32)/255).to('cuda')
        b=torch.from_numpy(np.asarray(reference.convert('RGB').resize(content.size,Image.Resampling.BICUBIC),dtype=np.float32)/255).to('cuda')
        if luminance:
            weights=torch.tensor([.2126,.7152,.0722],device='cuda');low_a=(a@weights)[...,None];low_b=(b@weights)[...,None]
        else:low_a=a;low_b=b
        delta=low_frequency_tensor(low_b,levels)-low_frequency_tensor(low_a,levels)
        pixels=((a+strength*delta).clamp(0,1)*255).round().to(torch.uint8).cpu().numpy()
    image=Image.fromarray(pixels).convert('RGBA');image.putalpha(content.convert('RGBA').getchannel('A'))
    if content.info.get('icc_profile'):image.info['icc_profile']=content.info['icc_profile']
    return image
