import unittest
from bmk_studio.note_transfer import append_transfer
class TransferTests(unittest.TestCase):
 def test_source_types_and_unknown_fields_are_preserved(self):
  original={'prompt':'existing','future':{'list':[1]},'notes':'memo'}
  result=append_transfer(original,[('원본 프롬프트','prompt','raw'),('추정 태그','prompt','inferred'),('작업 네거티브','negative','bad')],'H:/original.png')
  self.assertEqual(original,{'prompt':'existing','future':{'list':[1]},'notes':'memo'});self.assertEqual(result['future'],original['future']);self.assertIn('[원본 프롬프트]\nraw',result['prompt']);self.assertIn('[추정 태그]\ninferred',result['prompt']);self.assertEqual(len(result['_studio_image_transfers'][0]['sections']),3)
 def test_empty_and_incompatible_history_do_not_mutate(self):
  for body,sections in [({'future':2},[]),({'_studio_image_transfers':{'unknown':1}},[('원본','prompt','text')])]:
   import copy
   before=copy.deepcopy(body)
   with self.assertRaises(ValueError):append_transfer(body,sections,'image')
   self.assertEqual(body,before)
