import tempfile,unittest,json
from pathlib import Path
from bmk_studio.core import Store
from bmk_studio.organize import field,set_rating,set_favorites
from bmk_studio.data_location import copy_data

class OrganizeTests(unittest.TestCase):
    def test_missing_metadata_is_unknown(self):
        self.assertEqual(field('file\nnot json','aspect'),'unknown')
        self.assertEqual(field('file\n{}','positive'),'')
        self.assertEqual(field('file\n{"size":[20,30]}','aspect'),'portrait')
    def test_copy_rebases_classification_without_rewriting_note_literals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();store=Store(root/'old');path=str(store.root/'clipboard/image.png')
            set_favorites(store.db,[path],True);set_rating(store.db,[path],4)
            with store.db:
                store.db.execute('INSERT INTO collections VALUES(?)',('keep',));store.db.execute('INSERT INTO collection_items VALUES(?,?)',('keep',path))
            store.save_note('raw',{'prompt':path});copy_data(store.root,root/'new');copied=Store(root/'new')
            self.assertEqual(copied.db.execute('SELECT path,rating FROM favorites').fetchone(),(str(root/'new/clipboard/image.png'),4))
            self.assertEqual(copied.db.execute('SELECT path FROM collection_items').fetchone()[0],str(root/'new/clipboard/image.png'))
            self.assertEqual(json.loads(copied.notes()[0][2])['prompt'],path)
            copied.db.close();store.db.close()
