import unittest,tempfile,hashlib,io
from pathlib import Path
from bmk_studio.model_download import download_file,verify_file,DownloadCancelled

class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {}

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'model.safetensors';self.data=b'a'*(1024*1024)+b'b'*77
        self.entry={'name':self.path.name,'size':len(self.data),'algorithm':'sha256','digest':hashlib.sha256(self.data).hexdigest(),'url':'https://example.invalid/file'}
    def tearDown(self):self.temp.cleanup()
    def test_cancel_resume_with_range_and_hash(self):
        progress=[]
        with self.assertRaises(DownloadCancelled):download_file(self.entry,self.path,lambda:bool(progress and progress[-1]>0),progress.append,lambda *args,**kw:Response(self.data))
        partial=self.path.with_name(self.path.name+'.part');offset=partial.stat().st_size
        self.assertEqual(offset,1024*1024);self.assertFalse(self.path.exists())
        def resume(request,**kwargs):
            self.assertEqual(request.get_header('Range'),f'bytes={offset}-')
            return Response(self.data[offset:],206,{'Content-Range':f'bytes {offset}-{len(self.data)-1}/{len(self.data)}'})
        download_file(self.entry,self.path,opener=resume);self.assertTrue(verify_file(self.path,self.entry));self.assertFalse(partial.exists())
    def test_server_ignoring_range_restarts_without_duplicate_bytes(self):
        self.path.with_name(self.path.name+'.part').write_bytes(b'partial')
        download_file(self.entry,self.path,opener=lambda *args,**kw:Response(self.data));self.assertEqual(self.path.read_bytes(),self.data)
    def test_wrong_hash_not_installed(self):
        with self.assertRaises(ValueError):download_file(self.entry,self.path,opener=lambda *args,**kw:Response(b'c'*len(self.data)))
        self.assertFalse(self.path.exists())
    def test_wrong_range_not_appended(self):
        part=self.path.with_name(self.path.name+'.part');part.write_bytes(b'abc')
        with self.assertRaises(ValueError):download_file(self.entry,self.path,opener=lambda *args,**kw:Response(self.data,206,{'Content-Range':f'bytes 0-{len(self.data)-1}/{len(self.data)}'}))
        self.assertEqual(part.read_bytes(),b'abc')
    def test_git_blob_hash(self):
        self.path.write_bytes(self.data);entry={**self.entry,'algorithm':'git-sha1','digest':hashlib.sha1(b'blob '+str(len(self.data)).encode()+b'\0'+self.data).hexdigest()}
        self.assertTrue(verify_file(self.path,entry))

if __name__=='__main__':unittest.main()
