import unittest
from visual_assets import resolved_curves
from models_api_flat import CurvePiece
from typst_renderer import finite_runs

class PiecewiseTests(unittest.TestCase):
    def test_hole_splits_same_curve(self):
        p=dict(expression='x+1',x_start=-2.,x_end=4.,start='none',end='none',holes=[1.])
        curves,markers=resolved_curves({'pieces':[p]},[-2,4,-1,5])
        self.assertEqual(len(curves),1)
        self.assertEqual(len(finite_runs(curves[0][1],curves[0][2])),2)
        self.assertEqual(markers,[(1.,2.,'open')])
    def test_jump_endpoints(self):
        pieces=[dict(expression='x+1',x_start=-2.,x_end=0.,start='none',end='closed',holes=[]),dict(expression='x-1',x_start=0.,x_end=2.,start='open',end='none',holes=[])]
        curves,markers=resolved_curves({'pieces':pieces},[-2,2,-2,2])
        self.assertEqual(markers,[(0.,1.,'closed'),(0.,-1.,'open')])
        self.assertEqual(len(curves),2)
    def test_invalid_hole(self):
        with self.assertRaises(ValueError):CurvePiece.model_validate(dict(expression='x',x_start=0.,x_end=1.,start='none',end='none',holes=[2.]))
