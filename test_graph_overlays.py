import unittest
import numpy as np
from matplotlib.figure import Figure
from models_api_flat import Graph, serving_schema
from visual_assets import draw_overlays, graph
from test_flat_schema import sample
from flat_adapter import materialize
from renderers import artifact_file


def example():
    spec = sample()['graphs'][0]
    spec.update(expression='x^2', viewport={'x_min': -.2, 'x_max': 2.2, 'y_min': -.2, 'y_max': 4.5},
                areas=[{'expression': 'x^2', 'x_start': 0., 'x_end': 2., 'baseline': 0.}],
                rectangles=[{'expression': 'x^2', 'x_start': 0., 'x_end': 2., 'baseline': 0., 'count': 4, 'sample': 'midpoint'}])
    return spec


class OverlayTests(unittest.TestCase):
    def test_schema_and_legacy(self):
        Graph.model_validate(example())
        self.assertEqual(Graph.model_validate(sample()['graphs'][0]).areas, [])
        self.assertIn('areas', serving_schema()['$defs']['Graph']['properties'])

    def test_rectangle_geometry(self):
        for mode, offset in [('left', 0), ('right', 1), ('midpoint', .5)]:
            spec = example(); spec['rectangles'][0]['sample'] = mode
            ax = Figure().subplots(); draw_overlays(ax, spec)
            self.assertEqual(len(ax.collections), 1)
            self.assertEqual(len(ax.patches), 4)
            np.testing.assert_allclose([p.get_height() for p in ax.patches], ((np.arange(4)+offset)*.5)**2)
            np.testing.assert_allclose([p.get_width() for p in ax.patches], .5)

    def test_invalid_parameters(self):
        for field, value in [('count', 0), ('count', 501), ('x_end', -1.), ('baseline', float('nan')), ('sample', 'guess')]:
            spec = example(); spec['rectangles'][0][field] = value
            with self.assertRaises(ValueError): Graph.model_validate(spec)
        spec = example(); spec['kind'] = 'scatter'
        with self.assertRaises(ValueError): Graph.model_validate(spec)

    def test_nonfinite_function_rejected(self):
        spec = example(); spec['areas'][0]['expression'] = 'sqrt(-1)'
        with self.assertRaises(ValueError): draw_overlays(Figure().subplots(), spec)

    def test_exports(self):
        spec = example(); self.assertTrue(graph(spec).path.exists())
        data = sample(); data['graphs'] = [spec]
        data['artifacts'][0]['containers'][0]['blocks'] = [{'id':'b1', 'kind':'graph', 'ref':'g1'}]
        artifacts, _ = materialize(data)
        for fmt in ('pdf', 'docx', 'pptx'):
            content, _, _ = artifact_file(artifacts[0], fmt, best_effort=True)
            self.assertGreater(len(content), 1000)


if __name__ == '__main__': unittest.main()
