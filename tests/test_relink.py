import unittest,tempfile,shutil,json
from pathlib import Path
from PIL import Image
from bmk_studio.core import Store,fingerprint,file_stamp
from bmk_studio.sessions import Sessions
from bmk_studio.relink import relink_source

class RelinkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.data=self.root/'data'
        self.old=self.root/'old.png';self.new=self.root/'new.png';Image.new('RGB',(32,32),'red').save(self.old);shutil.copy2(self.old,self.new)
        self.store=Store(self.data);self.digest=fingerprint(self.old);self.store.remember_source(self.old,self.digest)
        self.store.save_asset(self.old,{'unknown':{'origin':'preserve'}},'draft','negative','memo')
        self.repo=Sessions(self.data);self.state={'schema':1,'source':str(self.old),'source_hash':self.digest,'operations':[{'crop':[1,1,10,10]}]}
        self.repo.save(Image.new('RGBA',(10,10),(1,2,3,44)),self.state)
    def tearDown(self):self.store.db.close();self.temp.cleanup()
    def test_moved_original_keeps_both_records_and_independent_snapshots(self):
        self.old.unlink();relink_source(self.data,self.old,self.new)
        image,state=self.repo.load(self.new);self.assertEqual(image.getpixel((0,0)),(1,2,3,44));self.assertEqual(state['source'],str(self.new))
        self.assertEqual(self.store.asset(self.new),self.store.asset(self.old));self.assertTrue(self.repo.contains(self.old))
        self.repo.save(image,state);shutil.copy2(self.new,self.old)
        self.assertIsNotNone(self.repo.load(self.old));self.assertEqual(fingerprint(self.new),self.digest)
    def test_mismatched_candidate_rejected_without_partial_copy(self):
        Image.new('RGB',(32,32),'blue').save(self.new)
        with self.assertRaises(ValueError):relink_source(self.data,self.old,self.new)
        self.assertIsNone(self.store.asset(self.new));self.assertFalse(self.repo.contains(self.new))
    def test_existing_destination_not_overwritten(self):
        self.store.save_asset(self.new,{},'own draft','','')
        with self.assertRaises(ValueError):relink_source(self.data,self.old,self.new)
        self.assertEqual(self.store.asset(self.new)[0],'own draft')
    def test_corrupt_snapshot_rejected(self):
        next(self.repo.folder.glob('*.png')).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):relink_source(self.data,self.old,self.new)
        self.assertIsNone(self.store.asset(self.new))

if __name__=='__main__':unittest.main()
