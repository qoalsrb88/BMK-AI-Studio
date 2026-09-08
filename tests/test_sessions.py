import tempfile,unittest,sqlite3,json
from pathlib import Path
from PIL import Image
from bmk_studio.sessions import Sessions
from bmk_studio.core import fingerprint

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'source.png'
        Image.new('RGB',(32,32),'red').save(self.source);self.repo=Sessions(self.root/'data')
        self.state={'schema':1,'source':str(self.source),'source_hash':fingerprint(self.source),'operations':[{'crop':[0,0,10,10]}],'crop_context':None}
    def tearDown(self):self.temp.cleanup()
    def test_roundtrip_and_replace(self):
        before=fingerprint(self.source);first=self.repo.save(Image.new('RGBA',(10,10),(1,2,3,44)),self.state)
        im,state=Sessions(self.root/'data').load(self.source);self.assertEqual(im.getpixel((0,0)),(1,2,3,44));self.assertEqual(state,self.state)
        self.repo.save(Image.new('RGB',(20,20),'blue'),self.state);self.assertFalse(Path(first).exists());self.assertEqual(len(self.repo.entries()),1)
        self.assertEqual(fingerprint(self.source),before)
    def test_changed_source_preserves_checkpoint(self):
        self.repo.save(Image.new('RGB',(10,10)),self.state);Image.new('RGB',(32,32),'blue').save(self.source)
        with self.assertRaises(ValueError):self.repo.load(self.source)
        with self.assertRaises(ValueError):self.repo.save(Image.new('RGB',(8,8)),self.state)
        self.assertEqual(len(self.repo.entries()),1)
    def test_missing_mask(self):
        self.state['crop_context']={'mask':str(self.root/'missing.png'),'mask_hash':'x'}
        with self.assertRaises(ValueError):self.repo.save(Image.new('RGB',(10,10)),self.state)
    def test_corrupt_snapshot(self):
        saved=Path(self.repo.save(Image.new('RGB',(10,10)),self.state));saved.write_bytes(b'broken')
        with self.assertRaises(ValueError):self.repo.load(self.source)
    def test_malformed_state(self):
        self.repo.save(Image.new('RGB',(10,10)),self.state)
        with sqlite3.connect(self.repo.db_path) as db:db.execute('UPDATE checkpoints SET state=?',('{"schema":999}',))
        db.close()
        with self.assertRaises(ValueError):self.repo.load(self.source)

if __name__=='__main__':unittest.main()
