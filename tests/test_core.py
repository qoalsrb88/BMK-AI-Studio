import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from bmk_studio.core import Store, inspect_image, crop_image, stitch_image, tone_restore, save_derived, fingerprint
from bmk_studio.vendor.prompt_converter import BMKPromptSyntaxConverter

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def png(self,fields):
        path=self.root/'input.png';meta=PngInfo()
        for k,v in fields.items():meta.add_text(k,v if isinstance(v,str) else json.dumps(v))
        Image.new('RGB',(64,48),'red').save(path,pnginfo=meta);return path
    def test_a1111(self):
        info=inspect_image(self.png({'parameters':'red bird\nNegative prompt: blur\nSteps: 20, Sampler: Euler, CFG scale: 7, Seed: 42, Size: 64x48'}))
        self.assertEqual(info['positive'],'red bird');self.assertEqual(info['negative'],'blur')
    def test_nai_characters_preserved(self):
        info=inspect_image(self.png({'Software':'NovelAI','Description':'old prompt','Comment':{'v4_prompt':{'caption':{'base_caption':'two people','char_captions':[{'char_caption':'red hair','centers':[{'x':.2,'y':.5}]}]}},'v4_negative_prompt':{'caption':{'base_caption':'blur','char_captions':[]}}}}))
        self.assertEqual(info['positive'],'two people');self.assertNotIn('red hair',info['positive'])
        self.assertEqual(info['characters'][0]['characters'][0]['char_caption'],'red hair')
    def test_image_saver_prefers_parameters(self):
        info=inspect_image(self.png({'parameters':'actual output\nNegative prompt: bad\nSteps: 10, Seed: 2','prompt':{'1':{'class_type':'CLIPTextEncode','inputs':{'text':'unused candidate'}}}}))
        self.assertEqual(info['positive'],'actual output');self.assertEqual(info['candidates'][0]['text'],'unused candidate')
    def test_description_xmp(self):
        info=inspect_image(self.png({'Description':'sea --ar 16:9 Job ID: abc','XML:com.adobe.xmp':'<x:xmpmeta xmlns:x="adobe:ns:meta/" />'}))
        self.assertIn('sea',info['positive']);self.assertIn('XML:com.adobe.xmp',info['raw'])
    def test_empty_metadata_not_inferred(self):
        info=inspect_image(self.png({}));self.assertEqual(info['positive'],'');self.assertEqual(info['negative'],'')
    def test_corrupt_file(self):
        p=self.root/'bad.png';p.write_bytes(b'not an image')
        with self.assertRaises(Exception):inspect_image(p)
    def test_notes_reopen_and_history(self):
        store=Store(self.root);nid=store.save_note('인물',{'prompt':'first'});store.save_note('인물',{'prompt':'second'},nid);store.db.close()
        store=Store(self.root);self.assertEqual(len(store.notes()),1);self.assertIn('second',store.notes()[0][2]);self.assertEqual(store.db.execute('select count(*) from history').fetchone()[0],2);store.db.close()
    def test_asset_and_score_separation(self):
        store=Store(self.root);store.save_asset('a',{'positive':'original'},'edited','bad','memo');store.cache('key',{'scores':[1]})
        self.assertEqual(store.asset('a')[0],'edited');self.assertEqual(store.cache('key')['scores'],[1]);store.db.close()
    def test_crop_stitch_rotation_roundtrip(self):
        rng=np.random.default_rng(2);im=Image.fromarray(rng.integers(0,256,(48,64,3),dtype=np.uint8))
        for angle in (0,90,180,270):
            box=(5,6,20,25);crop=crop_image(im,box,angle);out=stitch_image(im,crop,box,angle,0)
            np.testing.assert_array_equal(np.asarray(im),np.asarray(out.convert('RGB')))
    def test_invalid_crop(self):
        with self.assertRaises(ValueError):crop_image(Image.new('RGB',(10,10)),(8,8,10,10))
    def test_stitch_keeps_outside(self):
        im=Image.new('RGB',(40,40),'red');out=stitch_image(im,Image.new('RGB',(8,8),'blue'),(10,10,8,8),0,0)
        self.assertEqual(out.getpixel((0,0)),(255,0,0,255));self.assertEqual(out.getpixel((12,12)),(0,0,255,255))
    def test_tone_strength_zero_identity(self):
        im=Image.new('RGBA',(20,30),(100,120,180,77));out=tone_restore(im,Image.new('RGB',(50,50),'white'),0)
        np.testing.assert_array_equal(np.asarray(im),np.asarray(out))
    def test_tone_constant_reference(self):
        out=tone_restore(Image.new('RGB',(20,30),(80,100,120)),Image.new('RGB',(20,30),(120,140,160)),1,3)
        self.assertEqual(out.getpixel((5,5)),(120,140,160,255))
    def test_safe_export_sidecar_no_overwrite(self):
        p=self.png({'Description':'preserve'});before=fingerprint(p)
        saved=save_derived(Image.new('RGB',(10,10),'blue'),p,{'source':str(p)})
        self.assertNotEqual(saved,p);self.assertEqual(fingerprint(p),before);self.assertTrue(Path(str(saved)+'.bmk.json').is_file())
    def test_weight_conversion(self):
        conv=BMKPromptSyntaxConverter();self.assertIn('(red hair:1.2)',conv.convert('1.2::red hair::','NovelAI → ComfyUI',1.5,False)[0])

if __name__=='__main__':unittest.main()
