import json
import unittest
from bmk_studio.updates import available_release, MAX_RESPONSE, RELEASES_URL

def release(tag, beta=False, draft=False):
    return dict(tag_name=tag, prerelease=beta, draft=draft, html_url='https://untrusted.invalid/')

class UpdateTests(unittest.TestCase):
    def test_numeric_order_and_beta_channel(self):
        data=json.dumps([release('v0.9.9'),release('v0.10.0',True),release('v9.0.0',draft=True)]).encode()
        self.assertEqual(available_release(data,'0.9.8')['version'],'0.10.0')
        self.assertEqual(available_release(data,'0.9.8',False)['version'],'0.9.9')
        self.assertIsNone(available_release(data,'0.10.0'))
    def test_rejects_malformed_and_never_uses_remote_url(self):
        data=json.dumps([release('../../evil'),release('v0.10.0-rc1'),release('v0.9.9')]).encode()
        self.assertEqual(available_release(data,'0.9.8')['url'],RELEASES_URL+'/tag/v0.9.9')
        for data in (b'{}',b'not json',b' '* (MAX_RESPONSE+1)):
            with self.assertRaises(ValueError):available_release(data,'0.9.8')

