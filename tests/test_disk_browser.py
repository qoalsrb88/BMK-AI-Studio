import tempfile,unittest
from pathlib import Path
from bmk_studio.disk_browser import scan_folder

class DiskScanTests(unittest.TestCase):
    def test_only_direct_supported_images_and_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'child').mkdir();(root/'child/deep.png').write_bytes(b'');(root/'A.PNG').write_bytes(b'png');(root/'skip.txt').write_text('preserve')
            rows,skipped=scan_folder(root);self.assertEqual(skipped,0);self.assertEqual({r[1] for r in rows},{'child','A.PNG'});self.assertTrue(next(r for r in rows if r[1]=='child')[2]);self.assertEqual(next(r for r in rows if r[1]=='A.PNG')[3],3)
    def test_cancel_and_missing_directory_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'a.png').write_bytes(b'')
            self.assertIsNone(scan_folder(root,lambda:True))
            with self.assertRaises(OSError):scan_folder(root/'missing')
