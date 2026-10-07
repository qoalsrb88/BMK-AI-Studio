import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from bmk_studio import update_assets,update_install
from bmk_studio.core import Store
from bmk_studio.update_transfer import download_installer
from bmk_studio.update_download import DownloadCancelled


PAYLOAD=b'synthetic installer bytes'
DIGEST=hashlib.sha256(PAYLOAD).hexdigest()


def asset():
    return {'id':7,'name':'BMK-AI-Studio-99.0.0-Windows-x64-CPU-Setup.exe','size':len(PAYLOAD),
            'digest':'sha256:'+DIGEST,'state':'uploaded'}


class Response(io.BytesIO):
    def __init__(self,body=b'',status=200,headers=None):
        super().__init__(body);self.status=status;self.headers=headers or {}


class AssetTests(unittest.TestCase):
    def test_select_flavor_and_reject_unverifiable_or_ambiguous_assets(self):
        item=asset();release={'assets':[item]}
        self.assertEqual(update_assets.installer_asset(release,'99.0.0','CPU')['sha256'],DIGEST)
        self.assertIsNone(update_assets.installer_asset(release,'99.0.0','NVIDIA'))
        for change in ({'digest':None},{'size':True},{'size':2*1024**3},{'id':True},{'state':'new'},
                       {'name':'../setup.exe'},{'digest':'sha256:'+'x'*64}):
            self.assertIsNone(update_assets.installer_asset({'assets':[dict(item,**change)]},'99.0.0','CPU'))
        self.assertIsNone(update_assets.installer_asset({'assets':[item,item]},'99.0.0','CPU'))

    def test_redirect_credentials_are_not_forwarded_and_download_is_verified(self):
        requests=[];responses=[Response(status=302,headers={'Location':'https://release-assets.githubusercontent.com/file?signature=fixture'}),Response(PAYLOAD)]
        def open_request(request,timeout):requests.append(request);return responses.pop(0)
        with tempfile.TemporaryDirectory() as root:
            chosen=update_assets.installer_asset({'assets':[asset()]},'99.0.0','CPU')
            path=download_installer(chosen,'synthetic-access',root,opener=SimpleNamespace(open=open_request))
            self.assertEqual(path.read_bytes(),PAYLOAD)
        self.assertEqual(requests[0].get_header('Authorization'),'Bearer synthetic-access')
        self.assertIsNone(requests[1].get_header('Authorization'))

    def test_unsafe_redirect_truncation_and_cancel_leave_no_installer(self):
        chosen=update_assets.installer_asset({'assets':[asset()]},'99.0.0','CPU')
        with tempfile.TemporaryDirectory() as root:
            for url in ('http://release-assets.githubusercontent.com/a','https://evil.invalid/a',
                        'https://release-assets.githubusercontent.com@evil.invalid/a',
                        'https://release-assets.githubusercontent.com:444/a','https://api.github.com/user'):
                response=Response(status=302,headers={'Location':url})
                with self.assertRaises(ValueError):download_installer(chosen,'synthetic',root,opener=SimpleNamespace(open=lambda *a,**k:response))
                self.assertTrue(response.closed)
            response=Response(PAYLOAD[:-1])
            with self.assertRaises(ValueError):download_installer(chosen,None,root,opener=SimpleNamespace(open=lambda *a,**k:response))
            with self.assertRaises(DownloadCancelled):download_installer(chosen,None,root,cancelled=lambda:True)
            self.assertEqual(list(Path(root).iterdir()),[])


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.folder=self.root/'updates'/'session';self.folder.mkdir(parents=True)
        self.data=self.root/'user';store=Store(self.data);store.save_note('preserve',{'prompt':'original','unknown':{'keep':True}});store.db.close()
        (self.data/'original.txt').write_text('never overwrite')
        self.previous=self.root/'previous.exe';self.previous.write_bytes(b'previous')
        self.installer=self.folder/'setup.exe';self.installer.write_bytes(PAYLOAD)
        self.plan={'schema':1,'installer':str(self.installer),'size':len(PAYLOAD),'sha256':DIGEST,'publisher':'1'*40,
                   'version':'99.0.0','flavor':'CPU','previous':str(self.previous),'parent_pid':1,
                   'data_directory':str(self.data),'created':time.time()}
        self.plan_path=self.folder/'install.json';self.plan_path.write_text(json.dumps(self.plan))

    def apply(self,installer_exit=0,startup_exit=False,bad_protocol=False,bad_signature=False):
        started=[]
        def run(args,**kwargs):
            if args[0]==str(self.installer):
                target=Path(next(arg[5:] for arg in args if arg.startswith('/DIR=')));target.mkdir(parents=True)
                (target/'BMK-AI-Studio.exe').write_bytes(b'new application')
                (target/'build-info.json').write_text(json.dumps({'version':'99.0.0','cuda':None,'update_protocol':2 if bad_protocol else 1}))
                return SimpleNamespace(returncode=installer_exit)
            Path(args[2]).write_text(json.dumps({'passed':True,'version':'99.0.0'}))
            return SimpleNamespace(returncode=0)
        def popen(args,**kwargs):
            started.append(args)
            if '--update-ready' in args and not startup_exit:
                Path(args[-1]).write_text(json.dumps({'version':'99.0.0','protocol':1,'data_directory':str(self.data)}))
            return SimpleNamespace(poll=lambda:0 if startup_exit else None)
        with patch.object(update_install,'read_plan',return_value=(self.plan_path,self.plan)),patch.object(update_install,'wait_parent'),\
             patch.object(update_install,'verify_installable',side_effect=ValueError('untrusted') if bad_signature else None),\
             patch.object(update_install,'verify_publisher'),patch.object(update_install.subprocess,'run',side_effect=run),\
             patch.object(update_install.subprocess,'Popen',side_effect=popen),patch.dict(os.environ,{'LOCALAPPDATA':str(self.root)}):
            result=update_install.apply_update(self.plan_path)
        self.assertEqual(self.previous.read_bytes(),b'previous')
        self.assertEqual((self.data/'original.txt').read_text(),'never overwrite')
        return result,started

    def test_install_verifies_and_backs_up_before_new_app_starts(self):
        result,started=self.apply()
        self.assertTrue(result['installed']);self.assertEqual(len(started),1)
        backup=Path(result['backup']);self.assertEqual((backup/'original.txt').read_text(),'never overwrite')
        store=Store(backup);note=store.notes()[0];self.assertIn('preserve',str(note));store.db.close()

    def test_failed_installer_restarts_original_without_replacing_data(self):
        result,started=self.apply(installer_exit=1)
        self.assertFalse(result['installed']);self.assertEqual(started,[[str(self.previous),'--user-directory',str(self.data)]])

    def test_concurrent_or_replayed_worker_cannot_run_installer_twice(self):
        self.apply()
        with self.assertRaises(FileExistsError):self.apply()

    def test_untrusted_installer_is_not_executed(self):
        result,started=self.apply(bad_signature=True)
        self.assertFalse(result['installed']);self.assertNotIn('backup',result)
        self.assertEqual(started[0][0],str(self.previous));self.assertFalse((self.root/'Programs').exists())

    def test_incompatible_data_protocol_never_launches_new_app(self):
        result,started=self.apply(bad_protocol=True)
        self.assertFalse(result['installed']);self.assertEqual(len(started),1);self.assertEqual(started[0][0],str(self.previous))

    def test_failed_start_recovers_on_copy_and_keeps_attempted_profile(self):
        result,started=self.apply(startup_exit=True)
        self.assertFalse(result['installed']);self.assertEqual(len(started),2)
        self.assertEqual(started[1],[str(self.previous),'--user-directory',str(self.folder/'data-backup')])

    def test_plan_rejects_wrong_publisher_expiry_outside_installer_and_replay(self):
        with patch.object(update_install,'update_root',return_value=self.root/'updates'),\
             patch.object(update_install.update_config,'SIGNING_THUMBPRINT','1'*40),\
             patch.object(update_install.sys,'executable',str(self.previous)):
            self.assertEqual(update_install.read_plan(self.plan_path)[1]['version'],'99.0.0')
            for change in ({'publisher':'2'*40},{'created':time.time()-601},{'installer':str(self.root/'evil.exe')},{'version':'0.0.1'},{'parent_pid':os.getpid()}):
                self.plan_path.write_text(json.dumps(dict(self.plan,**change)))
                with self.assertRaises(ValueError):update_install.read_plan(self.plan_path)
            self.plan_path.write_text(json.dumps(self.plan));(self.folder/'installation-result.json').write_text('{}')
            with self.assertRaises(ValueError):update_install.read_plan(self.plan_path)
