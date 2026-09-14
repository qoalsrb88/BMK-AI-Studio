import hashlib,json,os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bmk_studio.update_download import stage_download,verify_installable,DownloadCancelled
from bmk_studio.authenticode import verify_publisher
from bmk_studio.update_credentials import LoginStore
from sign_release import sign_bundle,Signer
from package_release import REQUIRED

class DownloadSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.payload=b'controlled installer fixture';self.sha=hashlib.sha256(self.payload).hexdigest()
    def tearDown(self):self.temp.cleanup()
    def test_complete_download_and_existing_file_preserved(self):
        target=self.root/'setup.exe'
        stage_download([self.payload[:5],self.payload[5:]],target,len(self.payload),self.sha)
        with self.assertRaises(FileExistsError):stage_download([b'evil'],target,4,'0'*64)
        self.assertEqual(target.read_bytes(),self.payload)
    def test_corruption_truncation_oversize_and_cancel_leave_no_file(self):
        target=self.root/'setup.exe'
        for blocks in ([b'x'*len(self.payload)],[self.payload[:-1]],[self.payload+b'x']):
            with self.assertRaises(ValueError):stage_download(blocks,target,len(self.payload),self.sha)
            self.assertEqual(list(self.root.iterdir()),[])
        with self.assertRaises(DownloadCancelled):stage_download([self.payload],target,len(self.payload),self.sha,lambda:True)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_changed_download_rejected_before_publisher_check(self):
        target=self.root/'setup.exe';target.write_bytes(self.payload)
        with patch('bmk_studio.update_download.verify_publisher',return_value={'status':'Valid'}) as verify:
            verify_installable(target,len(self.payload),self.sha,'1'*40);verify.assert_called_once()
            target.write_bytes(b'x'*len(self.payload));verify.reset_mock()
            with self.assertRaises(ValueError):verify_installable(target,len(self.payload),self.sha,'1'*40)
            verify.assert_not_called()

class PublisherTests(unittest.TestCase):
    def test_untrusted_wrong_publisher_and_no_timestamp_rejected(self):
        for data in ({'status':'NotSigned'},{'status':'Valid','thumbprint':'2'*40,'timestamped':True},
                     {'status':'Valid','thumbprint':'1'*40,'timestamped':False}):
            with patch('bmk_studio.authenticode.inspect_signature',return_value=data):
                with self.assertRaises(ValueError):verify_publisher('fixture.exe','1'*40)
    def test_valid_pinned_publisher_and_timestamp(self):
        value={'status':'Valid','thumbprint':'A'*40,'timestamped':True}
        with patch('bmk_studio.authenticode.inspect_signature',return_value=value):
            self.assertEqual(verify_publisher('fixture.exe','a'*40),value)

@unittest.skipUnless(os.name=='nt','Windows DPAPI')
class LoginStorageTests(unittest.TestCase):
    def test_encrypted_roundtrip_binding_expiry_and_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            store=LoginStore(Path(folder)/'login.bin')
            token='synthetic-access-value';store.save('client',token,time.time()+600)
            self.assertNotIn(token.encode(),store.path.read_bytes())
            self.assertEqual(store.load('client')[0],token);self.assertIsNone(store.load('different-client'))
            store.save('client',token,time.time()-1);self.assertIsNone(store.load('client'))
            store.path.write_bytes(b'corrupt');self.assertIsNone(store.load('client'))
            store.clear();self.assertFalse(store.path.exists())

class SigningCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        for name in REQUIRED:(self.source/name).write_text('fixture',encoding='utf-8')
        (self.source/'_internal').mkdir();(self.source/'licenses').mkdir()
        (self.source/'build-info.json').write_text(json.dumps({'source_dirty':False,'source_commit':'1'*40,'version':'0.9.9','signed':False}))
    def tearDown(self):self.temp.cleanup()
    def test_only_copy_signed_and_hashes_recomputed(self):
        class SyntheticSigner:
            def sign_generated_file(self,path):
                path.write_bytes(path.read_bytes()+b'-synthetic-signature')
                return {'status':'Valid','thumbprint':'1'*40,'timestamped':True}
        before=(self.source/'BMK-AI-Studio.exe').read_bytes();target=self.root/'signed'
        report=sign_bundle(self.source,target,SyntheticSigner())
        self.assertEqual((self.source/'BMK-AI-Studio.exe').read_bytes(),before)
        self.assertTrue(report['build']['signed'])
        entry=next(v for v in report['files'] if v['path']=='BMK-AI-Studio.exe')
        self.assertEqual(entry['sha256'],hashlib.sha256((target/'BMK-AI-Studio.exe').read_bytes()).hexdigest())
        with self.assertRaises(FileExistsError):sign_bundle(self.source,target,SyntheticSigner())
    def test_failed_signing_does_not_claim_success(self):
        class FailingSigner:
            def sign_generated_file(self,path):raise RuntimeError('Signing unavailable')
        with self.assertRaises(RuntimeError):sign_bundle(self.source,self.root/'failed',FailingSigner())
        self.assertFalse(json.loads((self.root/'failed/build-info.json').read_text())['signed'])
        self.assertEqual((self.source/'BMK-AI-Studio.exe').read_text(),'fixture')
    def test_signer_configuration_rejects_unsafe_timestamp_and_password(self):
        config=self.root/'signing.private.json'
        value={'signtool':sys.executable,'certificate_thumbprint':'1'*40,'timestamp_url':'http://timestamp.invalid'}
        config.write_text(json.dumps(value))
        with self.assertRaises(ValueError):Signer(config)
        value['timestamp_url']='https://timestamp.invalid';value['password']='not-supported';config.write_text(json.dumps(value))
        with self.assertRaises(ValueError):Signer(config)

