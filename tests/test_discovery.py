import unittest,tempfile,json,io
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from bmk_studio.core import Store,file_stamp,fingerprint
from bmk_studio.discovery import generated_date,date_value,completions,timeline,similar_groups
from bmk_studio.semantic import search
from bmk_studio.data_location import copy_data

class FakeEncoder:
    key='test-encoder'
    calls=0
    def __init__(self,folder):pass
    def encode(self,texts):
        type(self).calls+=len(texts)
        return np.asarray([[1,0] if 'forest' in text else [0,1] for text in texts],dtype=np.float32)

class DiscoveryTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.store=Store(self.root/'user')
    def tearDown(self):self.store.db.close();self.temp.cleanup()
    def add(self,name,positive,raw=None):
        path=self.root/name;Image.new('RGB',(64,80),'blue').save(path);record={'positive':positive,'negative':'blur','raw':raw or {},'size':[64,80]}
        self.store.index_image(path,file_stamp(path),name+'\n'+json.dumps(record).casefold(),b'');return str(path)
    def test_explicit_dates_no_filename_or_filetime_guessing(self):
        self.assertEqual(generated_date('2026-09-08.png\n{}'),'')
        self.assertEqual(generated_date('file\n{"raw":{"exif":{"datetimeoriginal":"2026:09:08 12:00:00"}}}'),'2026-09-08')
        self.assertEqual(generated_date('file\n{"raw":{},"xmp":{"createdate":"2026-09-08t12:00:00z"}}'),'2026-09-08')
        self.assertEqual(generated_date('file\n{"raw":{"creation time":"2026-02-30"}}'),'')
        self.assertEqual(date_value('',None,'modified'),'')
    def test_completion_and_timeline_exclude_hidden(self):
        a=self.add('a.png','forest flowers',{'Creation Time':'2026-09-08'});b=self.add('b.png','forest fog')
        self.assertEqual(completions(self.store.root/'library.sqlite3','fo','positive')[0],'forest')
        self.store.hide_paths([a]);self.assertNotIn('flowers',completions(self.store.root/'library.sqlite3','fl'))
        months,missing=timeline(self.store.root/'library.sqlite3','generated');self.assertEqual((months,missing),([],1))
        self.store.reveal_paths([a]);months,missing=timeline(self.store.root/'library.sqlite3','generated');self.assertEqual(months,[('2026-09',1)])
    def test_semantic_cache_tracks_text_source_and_content(self):
        a=self.add('a.png','forest trees');b=self.add('b.png','ocean');c=self.add('missing.png','')
        args=(self.store.root/'library.sqlite3',[a,b,c],'forest','unused')
        FakeEncoder.calls=0;first=search(*args,encoder_factory=FakeEncoder);self.assertEqual(first['matches'][0][1],a);self.assertEqual(first['skipped'],1);self.assertEqual(FakeEncoder.calls,3)
        search(*args,encoder_factory=FakeEncoder);self.assertEqual(FakeEncoder.calls,4)
        self.store.save_asset(a,{},'ocean','','');self.store.save_asset(b,{},'forest','','')
        work=search(*args,source='work',encoder_factory=FakeEncoder);self.assertEqual(work['matches'][0][1],b)
        self.store.save_asset(a,{},'forest updated','','');search(*args,source='work',encoder_factory=FakeEncoder)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0],4)
        before=FakeEncoder.calls;result=search(*args,cancelled=lambda:True,encoder_factory=FakeEncoder);self.assertTrue(result['cancelled']);self.assertEqual(result['matches'],[])
    def test_visual_groups_cache_and_original_preservation(self):
        paths=[]
        for name,color in [('a.png','white'),('b.png','white'),('c.png','red')]:
            path=self.root/name;image=Image.new('RGB',(200,240),color);ImageDraw.Draw(image).ellipse((10,30,160,170),fill='black');image.save(path);paths.append(str(path))
        hashes=[fingerprint(p) for p in paths];result=similar_groups(self.store.root/'library.sqlite3',paths)
        self.assertEqual(result['groups'],[paths[:2]]);self.assertFalse(result['failed']);self.assertEqual(hashes,[fingerprint(p) for p in paths])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM visual_signatures').fetchone()[0],3)
    def test_discovery_paths_rebased_on_data_copy(self):
        path=str(self.store.root/'clipboard/image.png');self.store.state('semantic_settings',{'model':str(self.store.root/'models/example')});self.store.state('last_deleted_collection',{'name':'keep','paths':[path]})
        with self.store.db:
            self.store.db.execute('INSERT INTO visual_signatures VALUES(?,?,?,?,?)',(path,'stamp','0xff',1,'[0,0,0]'))
            self.store.db.execute('INSERT INTO semantic_vectors VALUES(?,?,?,?,?)',(path,'positive','hash','model',b'123'))
            self.store.db.execute('INSERT INTO large_thumbnails VALUES(?,?,?,?)',(path,'stamp',b'png',1))
        self.store.state('disk_browser',{'folder':str(self.store.root/'clipboard'),'favorites':[str(self.store.root/'clipboard'),str(self.root/'external')]})
        target=self.root/'copied';copy_data(self.store.root,target);copied=Store(target)
        try:
            self.assertEqual(copied.state('disk_browser'),{'folder':str(target/'clipboard'),'favorites':[str(target/'clipboard'),str(self.root/'external')]})
            for table in ('visual_signatures','semantic_vectors','large_thumbnails'):self.assertEqual(copied.db.execute(f'SELECT path FROM {table}').fetchone()[0],str(target/'clipboard/image.png'))
            self.assertEqual(copied.state('semantic_settings')['model'],str(target/'models/example'));self.assertEqual(copied.state('last_deleted_collection')['paths'],[str(target/'clipboard/image.png')])
        finally:copied.db.close()
