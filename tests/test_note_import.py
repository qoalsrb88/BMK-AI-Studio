import json,tempfile,unittest
from pathlib import Path
from bmk_studio.core import Store

class NoteImportTests(unittest.TestCase):
    def test_folder_partial_failure_unknown_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'inputs';(folder/'character').mkdir(parents=True)
            valid=folder/'character'/'one.json';valid.write_text(json.dumps({'prompt':'bird','schema':7,'params':{'seed':9}}))
            invalid=folder/'bad.json';invalid.write_text('{broken')
            wrong=folder/'wrong.json';wrong.write_text('{"prompt":42}')
            store=Store(root/'data');report=store.import_note_files([invalid,valid,wrong],folder)
            self.assertEqual(len(report['imported']),1);self.assertEqual(len(report['failed']),2)
            record=store.note(report['imported'][0]['id']);self.assertEqual(record[3],'character')
            self.assertEqual(json.loads(record[2])['params'],{'seed':9});self.assertEqual(json.loads(record[2])['schema'],7)
            store.db.close()
    def test_state_roundtrip_and_corrupt(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp);store.state('documents',{'ids':['one'],'active':'one'});store.db.close()
            store=Store(temp);self.assertEqual(store.state('documents')['ids'],['one'])
            with store.db:store.db.execute('UPDATE app_state SET value=?',('{broken',))
            self.assertIsNone(store.state('documents'));store.db.close()

if __name__=='__main__':unittest.main()
