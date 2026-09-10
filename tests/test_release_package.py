import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('package_release',Path(__file__).resolve().parents[1]/'scripts/package_release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
class ReleasePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.bundle=self.root/'bundle';self.bundle.mkdir()
        for name in release.REQUIRED:(self.bundle/name).write_text('fixture',encoding='utf-8')
        (self.bundle/'_internal').mkdir();(self.bundle/'_internal/runtime.dll').write_bytes(b'synthetic runtime')
        (self.bundle/'licenses').mkdir();(self.bundle/'licenses/notice.txt').write_text('notice')
        (self.bundle/'build-info.json').write_text(json.dumps({'source_dirty':False,'source_commit':'1'*40,'version':'test'}))
    def tearDown(self):self.temp.cleanup()
    def test_rejects_user_data_weights_and_dirty_source(self):
        for name in ('local-settings.json','private.sqlite3','model.onnx'):
            path=self.bundle/name;path.write_text('private')
            with self.assertRaises(ValueError):release.inspect_bundle(self.bundle)
            path.unlink()
        (self.bundle/'build-info.json').write_text(json.dumps({'source_dirty':True,'source_commit':'1'*40}))
        with self.assertRaises(ValueError):release.inspect_bundle(self.bundle)
    def test_archive_manifest_matches_and_existing_outputs_survive(self):
        output=self.root/'release.zip';report=release.package(self.bundle,output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()),{'release/'+entry['path'] for entry in report['files']})
        before=release.digest(output)
        with self.assertRaises(FileExistsError):release.package(self.bundle,output)
        self.assertEqual(before,release.digest(output));self.assertEqual(report['archive_sha256'],before)
