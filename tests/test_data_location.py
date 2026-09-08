import json,os,sqlite3,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from PIL import Image
from bmk_studio.core import Store,fingerprint
from bmk_studio.sessions import Sessions
from bmk_studio import data_location as location

class DataLocationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'old';self.target=self.root/'new';self.config=self.root/'startup.json'
        self.store=Store(self.source);self.store.save_note('keep',{'prompt':str(self.source/'literal-in-prompt'),'future':{'x':[1,False]}})
    def tearDown(self):self.store.db.close();self.temp.cleanup()
    def test_copy_rebases_dependencies_but_preserves_unknown_notes_and_originals(self):
        clipboard=self.source/'clipboard';clipboard.mkdir();source=clipboard/'source.png';Image.new('RGBA',(20,30),(120,40,50,90)).save(source)
        base=self.source/'crop_sources';base.mkdir();image=base/'base.png';Image.new('RGBA',(20,30),(20,40,50,90)).save(image)
        self.store.save_asset(source,{'raw':{'literal':str(source)}},'work','negative','memo');self.store.remember_source(source,fingerprint(source))
        self.store.state('window',{'path':str(source),'reference':str(image),'model':'D:/external/model'})
        self.store.state('tag_queue',{'active':[],'pending':[str(source)]})
        sessions=Sessions(self.source);state={'schema':1,'source':str(source),'source_hash':fingerprint(source),'operations':[{'crop':{'base':str(image),'base_hash':fingerprint(image)}}],'crop_context':{'base':str(image),'base_hash':fingerprint(image)},'box':[0,0,10,10],'rotation':0}
        sessions.save(Image.new('RGBA',(10,10)),state)
        before=fingerprint(self.source/'library.sqlite3');original_hash=fingerprint(source)
        result=location.activate_directory(self.source,self.target,True,self.config);self.assertGreater(result['copied'],2)
        self.assertEqual(fingerprint(self.source/'library.sqlite3'),before);self.assertEqual(fingerprint(source),original_hash)
        self.store.db.close();self.source.rename(self.root/'old-hidden')
        restored=Sessions(self.target).load(self.target/'clipboard/source.png');self.assertEqual(restored[0].size,(10,10));self.assertEqual(restored[1]['crop_context']['base'],str(self.target/'crop_sources/base.png'))
        migrated=Store(self.target)
        try:
            self.assertEqual(migrated.asset(self.target/'clipboard/source.png')[0],'work')
            body=json.loads(migrated.notes()[0][2]);self.assertEqual(body['future'],{'x':[1,False]});self.assertEqual(body['prompt'],str(self.source/'literal-in-prompt'))
            self.assertEqual(migrated.state('window')['model'],'D:/external/model')
        finally:migrated.db.close()
    def test_wal_backup_includes_committed_rows(self):
        self.store.db.execute('PRAGMA journal_mode=WAL');self.store.save_note('WAL',{'prompt':'committed'})
        location.activate_directory(self.source,self.target,True,self.config)
        with closing(sqlite3.connect(self.target/'library.sqlite3')) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM notes').fetchone()[0],2)
    def test_nonempty_nested_and_locked_targets_rejected(self):
        self.target.mkdir();(self.target/'keep.txt').write_text('keep')
        with self.assertRaises(ValueError):location.activate_directory(self.source,self.target,True,self.config)
        self.assertEqual((self.target/'keep.txt').read_text(),'keep');self.assertFalse(self.config.exists())
        with self.assertRaises(ValueError):location.activate_directory(self.source,self.source/'nested',True,self.config)
        lock=location.lock_directory(self.target)
        try:
            with self.assertRaises(ValueError):location.activate_directory(self.source,self.target,False,self.config)
        finally:lock.unlock()
    def test_config_failure_keeps_previous_choice_and_source(self):
        location.save_choice(self.source,self.config)
        with patch.object(location,'save_choice',side_effect=OSError('read only')):
            with self.assertRaises(OSError):location.activate_directory(self.source,self.target,True,self.config)
        self.assertEqual(json.loads(self.config.read_text())['directory'],str(self.source));self.assertTrue((self.target/'library.sqlite3').exists())
    def test_incomplete_copy_cannot_be_selected(self):
        (self.source/'unknown.txt').write_text('preserve')
        with patch.object(location,'rewrite_database',side_effect=RuntimeError('simulated copy interruption')):
            with self.assertRaises(RuntimeError):location.activate_directory(self.source,self.target,True,self.config)
        self.assertTrue((self.target/location.INCOMPLETE).exists());self.assertFalse(self.config.exists())
        with self.assertRaises(ValueError):location.activate_directory(self.source,self.target,False,self.config)
    def test_precedence_missing_choice_and_existing_folder(self):
        self.target.mkdir();location.save_choice(self.target,self.config)
        with patch.dict(os.environ,{'BMK_STUDIO_DATA':''}),patch.object(location,'session_directory',None):
            self.assertEqual(location.resolve_directory(self.config),self.target)
            with patch.dict(os.environ,{'BMK_STUDIO_DATA':str(self.source)}):
                self.assertEqual(location.resolve_directory(self.config),self.source)
                with patch.object(location,'session_directory',str(self.root/'cli')):self.assertEqual(location.resolve_directory(self.config),self.root/'cli')
            self.target.rmdir()
            with self.assertRaises(ValueError):location.resolve_directory(self.config)
        location.activate_directory(self.target,self.source,False,self.config)
        self.assertEqual(json.loads(self.config.read_text())['directory'],str(self.source))

if __name__=='__main__':unittest.main()
