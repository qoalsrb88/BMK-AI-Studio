import tempfile
import unittest
import sqlite3
import json
from pathlib import Path
import numpy as np
from PIL import Image
from bmk_studio.core import Store,normalize_category,resize_image,stitch_image,tone_delta,apply_tone_delta,tone_restore

class NoteTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
    def tearDown(self):self.store.db.close();self.temp.cleanup()
    def test_category_and_unknown_fields_roundtrip(self):
        body={'prompt':'hero','loras':[{'name':'local'}],'params':[{'widget':'seed','value':123}],'ui':{'md':{'notes':True}}}
        nid=self.store.save_note('Hero',body,category='Characters / outfits')
        self.assertEqual(self.store.note(nid)[3],'Characters/outfits');self.assertEqual(json.loads(self.store.note(nid)[2]),body)
        self.assertEqual(len(self.store.note_entries('outfits')),1)
    def test_restore_is_new_revision_and_retains_both_versions(self):
        nid=self.store.save_note('Original',{'prompt':'first'},category='old')
        first=self.store.revisions(nid)[0][0]
        self.store.save_note('Changed',{'prompt':'second'},nid,'new')
        result=self.store.restore_revision(nid,first)
        self.assertEqual(result[1],'Original');self.assertEqual(result[3],'old');self.assertEqual(len(self.store.revisions(nid)),3)
        self.assertEqual(json.loads(self.store.revisions(nid)[1][2])['prompt'],'second')
    def test_foreign_revision_rejected(self):
        a=self.store.save_note('a',{});b=self.store.save_note('b',{})
        with self.assertRaises(ValueError):self.store.restore_revision(a,self.store.revisions(b)[0][0])
    def test_archive_is_reversible_and_does_not_remove_history(self):
        nid=self.store.save_note('note',{'prompt':'safe'});self.store.archive_note(nid)
        self.assertEqual(self.store.notes(),[]);self.assertEqual(len(self.store.note_entries(archived=True)),1)
        self.store.save_note('edited',{'prompt':'still archived'},nid)
        self.assertEqual(self.store.notes(),[]);self.store.archive_note(nid,False)
        self.assertEqual(len(self.store.notes()),1);self.assertEqual(len(self.store.revisions(nid)),2)
    def test_legacy_schema_is_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            db=sqlite3.connect(Path(folder)/'library.sqlite3')
            db.executescript("CREATE TABLE notes(id TEXT PRIMARY KEY,title TEXT,body TEXT,updated TEXT); CREATE TABLE history(id INTEGER PRIMARY KEY,note_id TEXT,body TEXT,updated TEXT); INSERT INTO notes VALUES('old','legacy','{\"prompt\":\"retained\"}','2026'); INSERT INTO history(note_id,body,updated) VALUES('old','{\"prompt\":\"retained\"}','2026');")
            db.close();store=Store(folder)
            self.assertEqual(store.note('old')[3],'');store.restore_revision('old',1)
            self.assertEqual(json.loads(store.note('old')[2])['prompt'],'retained');store.db.close()
    def test_category_normalization(self):self.assertEqual(normalize_category(' / characters \\ outfit /../ blue /'),'characters/outfit/blue')

class EditingTests(unittest.TestCase):
    def test_contain_preserves_aspect_and_padding(self):
        out=resize_image(Image.new('RGBA',(200,100),'red'),100,100,'contain','transparent')
        self.assertEqual(out.getpixel((50,0))[3],0);self.assertEqual(out.getpixel((50,50)),(255,0,0,255))
    def test_cover_and_stretch_sizes(self):
        im=Image.new('RGB',(100,300),'blue')
        for mode in ('cover','stretch'):self.assertEqual(resize_image(im,80,40,mode).size,(80,40))
    def test_extreme_ratio_and_output_limit(self):
        self.assertEqual(resize_image(Image.new('RGB',(400,1)),1,720).size,(1,720))
        with self.assertRaises(ValueError):resize_image(Image.new('RGB',(1,1)),10000,10000)
    def test_zero_mask_preserves_original(self):
        original=Image.new('RGBA',(40,40),'red');out=stitch_image(original,Image.new('RGB',(20,20),'blue'),(10,10,20,20),mask=Image.new('L',(20,20),0))
        np.testing.assert_array_equal(np.asarray(original),np.asarray(out))
    def test_mask_selection_and_alpha_multiply(self):
        original=Image.new('RGBA',(20,20),'red');mask=Image.new('L',(10,10),0);mask.paste(255,(0,0,5,10))
        out=stitch_image(original,Image.new('RGBA',(10,10),(0,0,255,128)),(5,5,10,10),feather=0,mask=mask)
        self.assertEqual(out.getpixel((11,10)),(255,0,0,255));self.assertEqual(out.getpixel((6,10)),(127,0,128,255))
    def test_reusable_tone_delta_matches_full_calculation(self):
        content=Image.new('RGBA',(32,40),(80,130,200,99));ref=Image.new('RGB',(20,20),(160,100,80))
        for lum in (False,True):
            delta=tone_delta(content,ref,3,lum)
            for strength in (0,.3,1,2):
                np.testing.assert_array_equal(np.asarray(apply_tone_delta(content,delta,strength)),np.asarray(tone_restore(content,ref,strength,3,lum)))

if __name__=='__main__':unittest.main()
