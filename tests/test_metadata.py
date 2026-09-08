import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from bmk_studio.core import inspect_image
from bmk_studio.metadata import details, parameter_settings, comfy_branches


def graph():
    return {'1':{'class_type':'CLIPTextEncode','inputs':{'text':'bird'}},
            '2':{'class_type':'CLIPTextEncode','inputs':{'text':'blur'}},
            '3':{'class_type':'KSampler','inputs':{'positive':['1',0],'negative':['2',0],'steps':20,'seed':42}},
            '4':{'class_type':'KSampler','inputs':{'positive':['2',0],'negative':['1',0],'steps':10,'seed':99}}}


class MetadataTests(unittest.TestCase):
    def test_quoted_settings(self):
        result=parameter_settings('bird\nSteps: 20, Seed: 42, Lora hashes: "a: 123, b: 456", Size: 832x1216')
        self.assertEqual(result['Lora hashes'],'"a: 123, b: 456"');self.assertEqual(result['Size'],'832x1216')
        self.assertEqual(parameter_settings('A painting with Steps: 20'),{})

    def test_graph_choices_are_independent(self):
        branches=comfy_branches({'prompt':json.dumps(graph())})
        self.assertEqual(len(branches),2)
        self.assertEqual(branches[0]['positive'][0]['text'],'bird')
        self.assertEqual(branches[1]['positive'][0]['text'],'blur')
        self.assertEqual(branches[0]['settings']['seed'],42)

    def test_dynamic_and_cycle_reported(self):
        g=graph();g['1']['inputs']['text']=['9',0]
        self.assertTrue(comfy_branches({'prompt':g})[0]['warnings'])
        g['1']['inputs']['conditioning']=['1',0]
        self.assertTrue(comfy_branches({'prompt':g})[0]['warnings'])

    def test_xmp_png_jpeg_webp(self):
        packet=b'<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><dc:description><rdf:Alt><rdf:li xml:lang="x-default">sea --ar 16:9</rdf:li></rdf:Alt></dc:description></x:xmpmeta>'
        with tempfile.TemporaryDirectory() as folder:
            for ext in ('png','jpg','webp'):
                with self.subTest(ext=ext):
                    p=Path(folder)/('image.'+ext);im=Image.new('RGB',(16,16),'red')
                    if ext=='png':
                        png=PngInfo();png.add_itxt('XML:com.adobe.xmp',packet.decode());im.save(p,pnginfo=png)
                    else:im.save(p,xmp=packet)
                    info=inspect_image(p)
                    self.assertEqual(info['positive'],'sea --ar 16:9')
                    self.assertIn('XMP',info['source'])

    def test_exif_user_comment(self):
        with tempfile.TemporaryDirectory() as folder:
            for ext in ('jpg','webp'):
                p=Path(folder)/('image.'+ext)
                exif=Image.Exif();exif[37510]=b'ASCII\0\0\0bird\nNegative prompt: blur\nSteps: 20, Seed: 42'
                Image.new('RGB',(16,16)).save(p,exif=exif)
                info=inspect_image(p)
                self.assertEqual(info['positive'],'bird');self.assertEqual(info['negative'],'blur')

    def test_bad_xmp_does_not_break(self):
        for packet in ('<broken', '<!DOCTYPE a [<!ENTITY b "x">]><a>&b;</a>'):
            result=details({'xmp':packet});self.assertEqual(result['xmp'],{});self.assertTrue(result['warnings'])

    def test_parameters_priority_and_unknown_settings(self):
        result=details({'parameters':'bird\nSteps: 20, Seed: 2, Novel setting: unknown','Comment':'{"steps":99}'})
        self.assertEqual(result['settings']['Seed'],'2');self.assertEqual(result['settings']['Novel setting'],'unknown')

    def test_nai_settings_no_prompt_inference(self):
        result=details({'Comment':{'steps':28,'sampler':'k_euler','prompt':'bird','future_flag':True}})
        self.assertEqual(result['settings']['steps'],28);self.assertNotIn('prompt',result['settings'])

if __name__=='__main__':unittest.main()
