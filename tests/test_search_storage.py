import unittest,tempfile,json
from bmk_studio.core import Store

class SearchStorageTests(unittest.TestCase):
    def test_legacy_tags_migrate_once(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            with store.db:
                store.db.execute('INSERT INTO tags VALUES(?,?)',('old',json.dumps({'scores':[{'tag':'blue_eyes','category':0,'score':.8}]})))
                store.db.execute('INSERT INTO tag_runs VALUES(?,?,?,?)',('image','model','stamp','old'))
            self.assertTrue(store.needs_tag_search());store.backfill_tag_search();self.assertFalse(store.needs_tag_search())
            self.assertIn('blue eyes',store.search_extras()['image']['tags']);store.db.close()
    def test_hide_preserves_all_data(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);store.index_image('a','stamp','text',b'');store.save_asset('a',{},'draft','','')
            store.hide_paths(['a']);self.assertEqual(store.indexed_images(),[]);self.assertEqual(store.asset('a')[0],'draft')
            store.index_image('a','new','changed',b'');self.assertEqual(store.indexed_images(),[])
            store.reveal_paths(['a']);self.assertEqual(len(store.indexed_images()),1);store.db.close()

if __name__=='__main__':unittest.main()
