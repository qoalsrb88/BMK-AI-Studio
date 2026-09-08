import unittest
import numpy as np
from PIL import Image
from bmk_studio.core import stitch_image

class StitchAlignmentTests(unittest.TestCase):
    def test_offset_and_outside(self):
        base=Image.new('RGB',(40,40),'red');patch=Image.new('RGB',(10,10),'blue')
        out=stitch_image(base,patch,(10,10,10,10),feather=0,offset=(5,-5))
        self.assertEqual(out.getpixel((15,5)),(0,0,255,255));self.assertEqual(out.getpixel((10,10)),(255,0,0,255))
        out=stitch_image(base,patch,(10,10,10,10),feather=0,offset=(-100,0))
        np.testing.assert_array_equal(np.asarray(out.convert('RGB')),np.asarray(base))
    def test_rotation_and_scale(self):
        base=Image.new('RGB',(40,40),'red');patch=Image.new('RGB',(10,20),'blue')
        out=stitch_image(base,patch,(15,10,10,20),feather=0,angle=90)
        self.assertEqual(out.getpixel((10,15)),(0,0,255,255));self.assertEqual(out.getpixel((15,10)),(255,0,0,255))
        out=stitch_image(base,patch,(15,10,10,20),feather=0,scale=.5)
        self.assertEqual(out.getpixel((20,20)),(0,0,255,255));self.assertEqual(out.getpixel((15,10)),(255,0,0,255))
    def test_mask_transforms_with_patch(self):
        base=Image.new('RGB',(40,40),'red');patch=Image.new('RGB',(10,10),'blue');mask=Image.new('L',(10,10),0)
        for x in range(5):
            for y in range(10):mask.putpixel((x,y),255)
        out=stitch_image(base,patch,(10,10,10,10),feather=0,mask=mask,offset=(5,0),angle=90)
        self.assertEqual(out.getpixel((17,12)),(0,0,255,255));self.assertEqual(out.getpixel((17,18)),(255,0,0,255))
    def test_invalid_alignment(self):
        for settings in ({'scale':0},{'angle':float('nan')},{'offset':(float('inf'),0)}):
            with self.assertRaises(ValueError):stitch_image(Image.new('RGB',(20,20)),Image.new('RGB',(5,5)),(1,1,5,5),**settings)

if __name__=='__main__':unittest.main()
