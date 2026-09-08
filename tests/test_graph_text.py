import unittest
from bmk_studio.metadata import comfy_branches

class GraphTextTests(unittest.TestCase):
    def branches(self,nodes,positive):
        return comfy_branches({'prompt':{**nodes,'sampler':{'class_type':'KSampler','inputs':{'positive':positive,'seed':1}}}})[0]
    def test_boolean_switch_skips_unselected_cycle_and_joins_text(self):
        branch=self.branches({'s':{'class_type':'ComfySwitchNode','inputs':{'switch':['bool',0],'on_true':['join',0],'on_false':['s',0]}},'bool':{'class_type':'PrimitiveBoolean','inputs':{'value':True}},'a':{'class_type':'PrimitiveStringMultiline','inputs':{'value':'red'}},'join':{'class_type':'StringConcatenate','inputs':{'string_a':['a',0],'string_b':'dress','delimiter':' '}},'clip':{'class_type':'CLIPTextEncode','inputs':{'text':['s',0]}}},['clip',0])
        self.assertEqual(branch['positive'][0]['text'],'red dress');self.assertFalse(branch['warnings']);self.assertEqual(branch['resolved_choices'][0]['selected'],'on_true')
    def test_context_inheritance_and_override(self):
        nodes={'base':{'class_type':'BMKContextAnima','inputs':{'positive':['clip',0]}},'next':{'class_type':'BMKContextAnima','inputs':{'base_ctx':['base',0]}},'clip':{'class_type':'CLIPTextEncode','inputs':{'text':'known'}}}
        self.assertEqual(self.branches(nodes,['next',6])['positive'][0]['text'],'known')
        nodes['next']['inputs']['positive']=['zero',0];nodes['zero']={'class_type':'ConditioningZeroOut','inputs':{}}
        self.assertFalse(self.branches(nodes,['next',6])['positive'])
    def test_unknown_selector_is_not_guessed(self):
        branch=self.branches({'s':{'class_type':'LazySwitchKJ','inputs':{'switch':['unknown',0],'on_true':['clip',0]}},'clip':{'class_type':'CLIPTextEncode','inputs':{'text':'must not guess'}}},['s',0])
        self.assertFalse(branch['positive']);self.assertTrue(branch['warnings'])
    def test_artist_blend_keeps_inputs_separate_and_warns(self):
        branch=self.branches({'m':{'class_type':'AnimaArtistMixerTextBlend','inputs':{'base_prompt':'subject','artist_text':'artist','blend_mode':'exact'}}},['m',0])
        self.assertEqual([p['text'] for p in branch['positive']],['subject','artist']);self.assertTrue(branch['warnings'])

if __name__=='__main__':unittest.main()
