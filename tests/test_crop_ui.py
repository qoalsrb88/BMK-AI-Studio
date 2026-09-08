import unittest
from bmk_studio.crop_ui import anchored_box,bounded_box,snap_value

class CropGeometryTests(unittest.TestCase):
    def test_snap_and_move_boundary_preserve_size(self):
        self.assertEqual(snap_value(23,16),16);self.assertEqual(snap_value(24,16),32)
        self.assertEqual(bounded_box((999,-20,128,96),(513,400)),(385,0,128,96))
    def test_opposite_anchor_and_crossing_all_directions(self):
        for px,py in ((96,96),(304,96),(96,304),(304,304)):
            x,y,w,h=anchored_box((200,200),(px,py),(400,400))
            self.assertEqual((w,h),(104,104));self.assertIn(200,(x,x+w));self.assertIn(200,(y,y+h))
    def test_ratio_wins_over_snap_at_bounds(self):
        for ratio in (1,2/3,3/2,9/16,16/9):
            for point in ((-100,-100),(999,-100),(-100,999),(999,999)):
                x,y,w,h=anchored_box((200,150),point,(513,401),ratio,64)
                self.assertGreater(w,0);self.assertGreater(h,0)
                self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
                self.assertLessEqual(x+w,513);self.assertLessEqual(y+h,401)
                self.assertLessEqual(abs(w-h*ratio),max(1,ratio))

if __name__=='__main__':unittest.main()
