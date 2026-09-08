import unittest,tempfile
from pathlib import Path
from datetime import datetime
from bmk_studio.prompt_tools import expand_wildcards,wildcard_path,export_stem,clean_filename
from bmk_studio.core import save_derived
from PIL import Image

class PromptToolsTests(unittest.TestCase):
    def test_sidecar_collision_never_overwrites_or_leaves_partial_png(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'image.png';sidecar=Path(str(target)+'.bmk.json');sidecar.write_text('preserve')
            result=save_derived(Image.new('RGB',(2,2)),target,{'work':'new'})
            self.assertEqual(sidecar.read_text(),'preserve');self.assertFalse(target.exists());self.assertEqual(result.name,'image_2.png')
    def test_seeded_nested_expansion_and_original_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'color.txt').write_text('# comment\nred\nblue\n',encoding='utf-8');(root/'outfit.txt').write_text('__color__ dress',encoding='utf-8')
            text='__outfit__, __color__'
            first=expand_wildcards(text,root,42);self.assertEqual(first,expand_wildcards(text,root,42));self.assertNotIn('__',first[0]);self.assertEqual(text,'__outfit__, __color__')
            (root/'color.txt').write_text('__outfit__',encoding='utf-8')
            with self.assertRaises(ValueError):expand_wildcards(text,root,42)
    def test_missing_and_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):expand_wildcards('__missing__',folder)
            for key in ('../secret','/absolute','x//y','C:/path'):
                with self.assertRaises(ValueError):wildcard_path(folder,key)
    def test_names_reserved_paths_and_format(self):
        self.assertEqual(clean_filename('CON'),'_CON');self.assertEqual(clean_filename(' foo / bar. '),'foo _ bar')
        self.assertEqual(export_stem('{date}_{source}_{width}x{height}','cat.png',(32,40),now=datetime(2026,9,8)),'20260908_cat_32x40')
        for pattern in ('{source.__class__}','{unknown}','{source!r}','{date:100000}'):
            with self.assertRaises(ValueError):export_stem(pattern,'x',(1,1))
        self.assertLessEqual(len(clean_filename('😀'*300).encode('utf-16-le')),300)

if __name__=='__main__':unittest.main()
