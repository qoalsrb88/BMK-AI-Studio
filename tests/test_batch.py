import tempfile
import unittest
from pathlib import Path
from PIL import Image
from bmk_studio.batch import BatchTagJob
from bmk_studio.core import Store, file_stamp
from bmk_studio.tagger import model_signature
from bmk_studio.library import StableFiles, folder_snapshot, IndexJob

class FakeTagger:
    def __init__(self):self.calls=[];self.hook=None
    def run_many(self,paths,model_dir):
        self.calls.append(paths)
        if self.hook:self.hook(paths)
        if any(Path(p).name=='broken.png' for p in paths):raise ValueError('bad image')
        return [{'device':'fake','model':'test','scores':[{'tag':Path(p).stem,'category':0,'score':.9}]} for p in paths]

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.model=self.root/'model';self.model.mkdir()
        for name in ('config.json','model.safetensors','selected_tags.csv'):(self.model/name).write_text('fake')
        self.paths=[]
        for i in range(5):
            path=self.root/f'{i}.png';Image.new('RGB',(20+i,30+i),(i*30,50,120)).save(path);self.paths.append(str(path))
    def tearDown(self):self.temp.cleanup()
    def job(self,paths,tagger):return BatchTagJob(paths,str(self.model),tagger,self.root/'data',2)
    def test_batch_sizes_and_persistent_cache(self):
        tagger=FakeTagger();job=self.job(self.paths,tagger);job.run()
        self.assertEqual([len(x) for x in tagger.calls],[2,2,1]);self.assertEqual(job.stats['completed'],5)
        again=self.job(self.paths,tagger);again.run();self.assertEqual(again.stats['cached'],5);self.assertEqual(len(tagger.calls),3)
        store=Store(self.root/'data');self.assertIsNotNone(store.saved_tags(self.paths[0],model_signature(self.model),file_stamp(self.paths[0])));store.db.close()
    def test_failed_file_does_not_discard_neighbours(self):
        bad=self.root/'broken.png';bad.write_bytes(b'bad')
        tagger=FakeTagger();job=self.job([self.paths[0],str(bad),self.paths[1]],tagger);job.run()
        self.assertEqual(job.stats['failed'],1);self.assertEqual(job.stats['completed'],2)
    def test_cancellation_retains_completed_batch(self):
        tagger=FakeTagger();job=self.job(self.paths,tagger)
        # Deterministic cancellation predicate also works when run() is called without starting a QThread.
        stopped=[False];job.isInterruptionRequested=lambda:stopped[0]
        tagger.hook=lambda paths:stopped.__setitem__(0,True)
        job.run();self.assertTrue(job.stats['cancelled']);self.assertEqual(job.stats['completed'],2)
        tagger.hook=None;again=self.job(self.paths,tagger);again.run();self.assertEqual(again.stats['cached'],2)
    def test_changed_image_invalidates_cache(self):
        tagger=FakeTagger();self.job(self.paths[:1],tagger).run()
        Image.new('RGB',(32,48),'orange').save(self.paths[0])
        job=self.job(self.paths[:1],tagger);job.run();self.assertEqual(job.stats['cached'],0)
    def test_changed_during_inference_not_saved(self):
        tagger=FakeTagger();tagger.hook=lambda paths:Image.new('RGB',(60,60),'green').save(paths[0])
        job=self.job(self.paths[:1],tagger);job.run();self.assertEqual(job.stats['completed'],0);self.assertEqual(job.stats['failed'],1)
    def test_model_labels_change_invalidates_cache(self):
        tagger=FakeTagger();self.job(self.paths[:1],tagger).run();(self.model/'selected_tags.csv').write_text('different tags')
        job=self.job(self.paths[:1],tagger);job.run();self.assertEqual(job.stats['cached'],0)
    def test_model_changed_during_inference_not_cached(self):
        tagger=FakeTagger();tagger.hook=lambda paths:(self.model/'selected_tags.csv').write_text('changed during inference')
        job=self.job(self.paths[:1],tagger);job.run();self.assertEqual(job.stats['completed'],0);self.assertEqual(job.stats['failed'],1)
    def test_index_is_searchable_and_original_unchanged(self):
        before=Path(self.paths[0]).read_bytes();job=IndexJob(self.paths,self.root/'data');job.run()
        store=Store(self.root/'data');rows=store.indexed_images();self.assertEqual(len(rows),5);self.assertGreater(len(rows[0][3]),10);store.db.close()
        self.assertEqual(before,Path(self.paths[0]).read_bytes())

class StableFileTests(unittest.TestCase):
    def test_waits_for_stability(self):
        state=StableFiles(settle_seconds=2)
        self.assertEqual(state.update({'a':'1'},0),[])
        self.assertEqual(state.update({'a':'2'},1),[])
        self.assertEqual(state.update({'a':'2'},2),[])
        self.assertEqual(state.update({'a':'2'},3),['a'])
        self.assertEqual(state.update({'a':'2'},5),[])
    def test_delete_recreate_and_changed_file(self):
        state=StableFiles({'a':'1'},1)
        self.assertEqual(state.update({'a':'2'},0),[]);self.assertEqual(state.update({'a':'2'},1),['a'])
        state.update({},2);self.assertEqual(state.update({'a':'2'},3),[]);self.assertEqual(state.update({'a':'2'},4),['a'])
    def test_scan_ignores_download_partials_and_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'file.png.crdownload').write_text('partial');(root/'folder.png').mkdir();(root/'ok.png').write_text('candidate')
            self.assertEqual([Path(p).name for p in folder_snapshot(root)],['ok.png'])

if __name__=='__main__':unittest.main()
