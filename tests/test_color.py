import unittest,tempfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageCms
from bmk_studio.color import normalize_pixels,native_pixels,normalize_source,high_precision,srgb_profile
from bmk_studio.core import load_image,inspect_image,fingerprint,save_derived

class ColorTests(unittest.TestCase):
    def test_hdr_mapping_alpha_and_invalid_values(self):
        values=np.array([[[0.,0.,0.,0.],[4.,4.,4.,.5]]],dtype=np.float32)
        image=normalize_pixels(values);self.assertEqual(image.getpixel((0,0)),(0,0,0,0));self.assertEqual(image.getpixel((1,0))[3],128)
        self.assertTrue(225<image.getpixel((1,0))[0]<240)
        values[0,0,0]=np.inf
        with self.assertRaises(ValueError):normalize_pixels(values)
    def test_uint16_png_and_tiff_preserve_native_values(self):
        import png,tifffile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pixels=np.array([[[0,32768,65535],[10000,20000,30000]]],dtype=np.uint16)
            path=root/'rgb16.png'
            with path.open('wb') as stream:png.Writer(2,1,greyscale=False,bitdepth=16).write(stream,pixels.reshape(1,-1))
            self.assertTrue(high_precision(path));self.assertTrue(np.array_equal(native_pixels(path)[0],pixels));self.assertEqual(load_image(path).getpixel((0,0)),(0,128,255,255))
            tifffile.imwrite(root/'rgb16.tif',pixels,photometric='rgb');self.assertTrue(np.array_equal(native_pixels(root/'rgb16.tif')[0],pixels))
            for codec in ('lzw','deflate','zstd'):
                compressed=root/(codec+'.tif');tifffile.imwrite(compressed,pixels,photometric='rgb',compression=codec)
                self.assertTrue(np.array_equal(native_pixels(compressed)[0],pixels),codec)
    def test_float_exr_read_and_no_fabricated_prompt(self):
        import OpenEXR
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.exr';pixels=np.full((3,4,3),4.,dtype=np.float32)
            with OpenEXR.File({}, {'RGB':pixels}) as file:file.write(str(path))
            before=fingerprint(path);self.assertTrue(np.array_equal(native_pixels(path)[0],pixels))
            self.assertEqual(load_image(path).size,(4,3));self.assertEqual(inspect_image(path)['positive'],'');self.assertEqual(fingerprint(path),before)
    def test_icc_conversion_and_export_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profile.png';Image.new('RGB',(8,8),(40,90,160)).save(path,icc_profile=srgb_profile());before=fingerprint(path)
            image,record=normalize_source(path);self.assertEqual(image.getpixel((0,0)),(40,90,160,255));self.assertEqual(record['output'],'sRGB')
            target=save_derived(image,Path(folder)/'out.png',record)
            with Image.open(target) as exported:self.assertTrue(exported.info['icc_profile'])
            self.assertEqual(fingerprint(path),before)
            missing=Path(folder)/'missing.png';Image.new('RGB',(2,2)).save(missing)
            with self.assertRaises(ValueError):normalize_source(missing)
    def test_lab_profile_converts_neutral_to_srgb(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lab.tif';profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('LAB')).tobytes()
            Image.new('LAB',(2,2),(128,128,128)).save(path,icc_profile=profile)
            image,record=normalize_source(path);r,g,b,_=image.getpixel((0,0))
            self.assertLessEqual(max(r,g,b)-min(r,g,b),2);self.assertTrue(116<=r<=122)

if __name__=='__main__':unittest.main()
