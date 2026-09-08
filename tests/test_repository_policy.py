import contextlib,importlib.util,io,subprocess,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('repository_policy',Path(__file__).resolve().parents[1]/'scripts/check_repository.py');policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
class RepositoryPolicyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.old=policy.ROOT;policy.ROOT=self.root
  subprocess.run(['git','init','-q',str(self.root)],check=True)
 def tearDown(self):policy.ROOT=self.old;self.temp.cleanup()
 def test_staged_secret_is_checked_even_if_working_file_is_clean(self):
  secret='gh'+'p_'+'x'*40;(self.root/'README.md').write_text(secret,encoding='utf-8');policy.git('add','README.md');(self.root/'README.md').write_text('clean',encoding='utf-8')
  output=io.StringIO()
  with contextlib.redirect_stdout(output):self.assertTrue(policy.check());self.assertFalse(policy.check(True))
  self.assertNotIn(secret,output.getvalue());self.assertIn('token at line',output.getvalue())
 def test_forced_data_file_is_rejected(self):
  (self.root/'data').mkdir();(self.root/'data/user.json').write_text('{}');policy.git('add','data/user.json')
  with contextlib.redirect_stdout(io.StringIO()):self.assertFalse(policy.check(True))
