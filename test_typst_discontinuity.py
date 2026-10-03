import unittest
import numpy as np
from typst_renderer import finite_runs, nums, export
from visual_assets import graph_curves
from test_flat_schema import sample
from flat_adapter import materialize
import pymupdf

class DiscontinuityTests(unittest.TestCase):
    def test_runs_do_not_bridge_gap(self):
        runs=finite_runs(np.arange(5.),np.array([1.,2.,np.nan,4.,5.]))
        self.assertEqual([x.tolist() for x,y in runs],[[0.,1.],[3.,4.]])
        with self.assertRaises(ValueError):nums([np.nan])
    def test_pdf_with_poles(self):
        data=sample();data['artifacts'][0]['containers'][0]['blocks']=[{'id':'b1','kind':'graph','ref':'g1'}]
        g=data['graphs'][0];g.update(expression='1/x; 1/(x-3)',viewport={'x_min':-4.,'x_max':4.,'y_min':-5.,'y_max':5.})
        for label,x,y in graph_curves(g['expression'],[-4,4,-5,5]):
            self.assertGreater(len(finite_runs(x,y)),1)
        artifacts,_=materialize(data)
        pdf=export(artifacts[0])[0]
        with pymupdf.open(stream=pdf,filetype='pdf') as doc:
            self.assertNotIn('non disponibile',''.join(p.get_text() for p in doc))
            self.assertGreater(len(doc[0].get_drawings()),0)
if __name__=='__main__':unittest.main()
