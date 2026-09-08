"""Explicit source-to-sRGB normalization; original files are always read-only."""
import io,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageCms,ImageOps

MAX_PIXELS=64_000_000

def check_size(width,height):
    if width<1 or height<1 or width*height>MAX_PIXELS:raise ValueError('색상 정규화는 최대 6,400만 픽셀까지 지원합니다.')

def high_precision(path):
    suffix=Path(path).suffix.lower()
    if suffix=='.exr':return True
    if suffix=='.png':
        with open(path,'rb') as stream:header=stream.read(29)
        return len(header)>=29 and header[:8]==b'\x89PNG\r\n\x1a\n' and header[24]==16
    if suffix in ('.tif','.tiff'):
        import tifffile
        with tifffile.TiffFile(path) as image:return image.pages[0].dtype.itemsize>1
    return False

def native_pixels(path):
    path=Path(path);suffix=path.suffix.lower();metadata={}
    if suffix=='.exr':
        import OpenEXR
        with OpenEXR.File(str(path),header_only=True) as header:
            if len(header.parts)!=1:raise ValueError('다중 파트 EXR은 지원하지 않습니다.')
            info=header.header();lo,hi=info['dataWindow'];check_size(int(hi[0]-lo[0]+1),int(hi[1]-lo[1]+1))
            if info['type'] not in (OpenEXR.scanlineimage,OpenEXR.tiledimage):raise ValueError('Deep EXR은 지원하지 않습니다.')
            metadata={key:str(value) for key,value in info.items() if key!='channels'}
        with OpenEXR.File(str(path),separate_channels=True) as file:
            channels=file.channels()
            if not {'R','G','B'}.issubset(channels):raise ValueError('EXR에 R/G/B 채널이 필요합니다.')
            pixels=np.stack([channels[key].pixels for key in ('R','G','B')+ (('A',) if 'A' in channels else ())],axis=-1)
    elif suffix in ('.tif','.tiff'):
        import tifffile
        with tifffile.TiffFile(path) as image:
            if len(image.pages)!=1:raise ValueError('고정밀 다중 페이지 TIFF는 지원하지 않습니다.')
            page=image.pages[0];check_size(page.imagewidth,page.imagelength);pixels=page.asarray()
            if page.planarconfig==2:pixels=np.moveaxis(pixels,0,-1)
            if int(page.photometric) not in (0,1,2):raise ValueError('고정밀 TIFF는 RGB/회색조만 지원합니다.')
            if int(page.photometric)==0:
                if pixels.dtype.kind=='u':pixels=np.iinfo(pixels.dtype).max-pixels
                else:pixels=1-pixels
            metadata={'photometric':str(page.photometric),'extrasamples':str(page.extrasamples)}
            orientation=page.tags.get('Orientation');orientation=int(orientation.value) if orientation else 1
            transforms={2:lambda a:np.fliplr(a),3:lambda a:np.flipud(np.fliplr(a)),4:lambda a:np.flipud(a),5:lambda a:np.swapaxes(a,0,1),6:lambda a:np.rot90(a,3),7:lambda a:np.flipud(np.fliplr(np.swapaxes(a,0,1))),8:lambda a:np.rot90(a)}
            if orientation in transforms:pixels=transforms[orientation](pixels)
    elif suffix=='.png':
        import png
        with path.open('rb') as stream:
            reader=png.Reader(file=stream);reader.preamble();check_size(reader.width,reader.height)
            width,height,rows,info=reader.asDirect()
            pixels=np.vstack([np.asarray(row,dtype=np.uint16 if info['bitdepth']>8 else np.uint8) for row in rows]).reshape(height,width,info['planes']);metadata={'bitdepth':info['bitdepth']}
    else:
        with Image.open(path) as image:
            check_size(*image.size);pixels=np.asarray(ImageOps.exif_transpose(image).convert('RGBA'))
    if pixels.ndim==2:pixels=pixels[...,None]
    if pixels.ndim!=3 or pixels.shape[2] not in (1,2,3,4) or pixels.dtype.kind not in ('u','f'):raise ValueError('지원하지 않는 고정밀 픽셀 형식입니다.')
    check_size(pixels.shape[1],pixels.shape[0])
    return pixels,metadata

def srgb_profile():return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()

def normalize_pixels(pixels,encoding='linear',exposure=0.0,tone_map='reinhard',premultiplied=False):
    if encoding not in ('linear','srgb') or tone_map not in ('reinhard','clip'):raise ValueError('지원하지 않는 색상 처리입니다.')
    if not np.isfinite(exposure) or not -16<=exposure<=16:raise ValueError('노출은 -16~16 EV 범위입니다.')
    a=pixels.astype(np.float32)
    if pixels.dtype.kind=='u':a/=np.iinfo(pixels.dtype).max
    if not np.isfinite(a).all():raise ValueError('HDR 픽셀에 NaN/무한대가 있어 변환하지 않았습니다.')
    if a.shape[2] in (1,2):rgb=np.repeat(a[:,:,:1],3,axis=2)
    else:rgb=a[:,:,:3]
    alpha=a[:,:,-1] if a.shape[2] in (2,4) else np.ones(a.shape[:2],np.float32)
    if premultiplied:rgb=np.divide(rgb,alpha[...,None],out=np.zeros_like(rgb),where=alpha[...,None]>0)
    if encoding=='srgb':rgb=np.where(rgb<=.04045,rgb/12.92,((np.maximum(rgb,0)+.055)/1.055)**2.4)
    rgb=np.maximum(rgb*2**exposure,0)
    if tone_map=='reinhard':
        luminance=rgb@np.array([.2126,.7152,.0722],dtype=np.float32)
        rgb=rgb/(1+luminance[...,None])
    rgb=np.clip(rgb,0,1);rgb=np.where(rgb<=.0031308,12.92*rgb,1.055*rgb**(1/2.4)-.055)
    rgba=np.concatenate((rgb,np.clip(alpha,0,1)[...,None]),axis=2)
    result=Image.fromarray(np.uint8(np.rint(np.clip(rgba,0,1)*255)))
    result.info['icc_profile']=srgb_profile();return result

def normalize_source(path,mode='icc',encoding='linear',exposure=0.0,tone_map='reinhard',premultiplied=False):
    if mode not in ('icc','hdr'):raise ValueError('지원하지 않는 정규화 모드입니다.')
    if mode=='icc':
        with Image.open(path) as source:
            check_size(*source.size);profile=source.info.get('icc_profile')
            if not profile:raise ValueError('원본에 ICC 프로파일이 없습니다. 입력 색상 해석을 직접 선택하세요.')
            source=ImageOps.exif_transpose(source);alpha=source.getchannel('A') if 'A' in source.getbands() else None
            # Feed the original CMYK/LAB/RGB values to LittleCMS before any RGBA conversion.
            converted=ImageCms.profileToProfile(source,ImageCms.ImageCmsProfile(io.BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGB').convert('RGBA')
            if alpha is not None:converted.putalpha(alpha)
            converted.info['icc_profile']=srgb_profile()
            return converted,{'mode':'icc','input_profile_sha256':hashlib.sha256(profile).hexdigest(),'output':'sRGB'}
    pixels,metadata=native_pixels(path)
    result=normalize_pixels(pixels,encoding,exposure,tone_map,premultiplied)
    return result,{'mode':'hdr','input_encoding':encoding,'exposure':exposure,'tone_map':tone_map,'premultiplied':premultiplied,'native_dtype':str(pixels.dtype),'metadata':metadata,'output':'8-bit sRGB'}

def display_high_precision(path):
    pixels,metadata=native_pixels(path);floating=pixels.dtype.kind=='f'
    return normalize_pixels(pixels,'linear' if floating else 'srgb',tone_map='reinhard' if floating else 'clip')
