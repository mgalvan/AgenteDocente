import unittest
import numpy as np
from flat_adapter import materialize
from test_flat_schema import sample
from visual_assets import graph_curves


class GraphRecoveryTests(unittest.TestCase):
    def test_function_graph_accepts_labelled_points(self):
        from models_api_flat import FlatResponse
        data = sample()
        data['graphs'][0]['points'] = [{'x': 0, 'y': 1}]
        data['graphs'][0]['labels'] = ['A']
        FlatResponse.model_validate(data)
        data['graphs'][0]['labels'].append('B')
        with self.assertRaises(ValueError):
            FlatResponse.model_validate(data)

    def test_function_labels_on_each_curve(self):
        curves = graph_curves('y=2^x; y=(1/2)^x; f(x) = x+1', [-2, 2, -1, 10])
        self.assertEqual(len(curves), 3)
        np.testing.assert_allclose(curves[0][2], 2.0**curves[0][1])
        np.testing.assert_allclose(curves[1][2], 0.5**curves[1][1])
        np.testing.assert_allclose(curves[2][2], curves[2][1]+1)

    def test_arbitrary_assignments_are_rejected(self):
        for source in ('z=x', 'y==x', 'y=x=2', 'y=__import__("os")'):
            with self.assertRaises((ValueError, SyntaxError)):
                graph_curves(source, [-2, 2, -1, 10])

    def test_multiple_curves_and_constant(self):
        curves = graph_curves('x^2; -3x-2.25; 0', [-2, 2, -5, 5])
        self.assertEqual(len(curves), 3)
        np.testing.assert_allclose(curves[1][2], -3*curves[1][1]-2.25)
        np.testing.assert_allclose(curves[2][2], 0)

    def test_explicit_intervals(self):
        curves = graph_curves('x for x in [0,2]; 2 for x in [2,4]', [-1, 5, -1, 5])
        self.assertEqual((curves[0][1][0], curves[0][1][-1]), (0, 2))
        self.assertEqual((curves[1][1][0], curves[1][1][-1]), (2, 4))
        np.testing.assert_allclose(curves[1][2], 2)

    def test_input_is_never_python_code(self):
        for source in ('x; __import__("os").getcwd()', 'x for x in range(3)', 'x for x in [3,1]'):
            with self.assertRaises((ValueError, SyntaxError)):
                graph_curves(source, [-1, 5, -1, 5])



if __name__ == '__main__':
    unittest.main()
