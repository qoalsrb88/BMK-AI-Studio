import unittest
from bmk_studio.metadata import details,comfy_branches
from bmk_studio.core import searchable_tags

class ExtendedMetadataTests(unittest.TestCase):
    def test_custom_sampler_zero_negative(self):
        g={'1':{'class_type':'CLIPTextEncode','inputs':{'text':'bird'}},'2':{'class_type':'ConditioningZeroOut','inputs':{'conditioning':['1',0]}},
           '3':{'class_type':'DualModelGuider','inputs':{'positive':['1',0],'negative':['2',0],'cfg':7}},
           '4':{'class_type':'RandomNoise','inputs':{'noise_seed':8}},'5':{'class_type':'SamplerCustomAdvanced','inputs':{'guider':['3',0],'noise':['4',0]}}}
        branches=comfy_branches({'prompt':g});self.assertEqual(len(branches),1)
        self.assertEqual(branches[0]['positive'][0]['text'],'bird');self.assertEqual(branches[0]['negative'],[])
        self.assertEqual(branches[0]['settings']['noise.noise_seed'],8);self.assertFalse(branches[0]['warnings'])
    def test_wrapper_settings_without_inventing_prompt(self):
        result=details({'forge':'{"checkpoint":"gpt_image_2","quality":"high","prompt_type":"none"}'})
        self.assertEqual(result['settings']['quality'],'high');self.assertNotIn('positive',result)
    def test_search_thresholds_and_rating(self):
        result={'scores':[{'tag':'red_hair','score':.4,'category':0},{'tag':'character','score':.7,'category':4},{'tag':'rating','score':1,'category':9}]}
        text=searchable_tags(result);self.assertIn('red hair',text);self.assertNotIn('character',text);self.assertNotIn('rating',text)

if __name__=='__main__':unittest.main()
