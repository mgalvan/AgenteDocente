import base64
import io
import json
import unittest
from PIL import Image, ImageChops
from pydantic import ValidationError
from google_form_export import google_form_payload
from google_form_geometry import polygon_image, measurement_label
from models_api_flat import RegularPolygonDiagram
from test_google_form import quiz_sample
from validation import validated_artifacts


class PolygonQuizTests(unittest.TestCase):
    def diagram(self, **changes):
        return dict(sides=6, length=6.0, measure='side', unit='cm', show_apothem=True, **changes)

    def test_figure_reaches_google_payload_even_without_math(self):
        data = quiz_sample()
        question = data['artifacts'][0]['quiz_questions'][0]
        question['title'] = 'Calcola l area dell esagono regolare rappresentato.'
        question['diagrams'] = [self.diagram()]
        artifact = validated_artifacts(json.dumps(data))[0]
        payload = google_form_payload(artifact)
        image = Image.open(io.BytesIO(base64.b64decode(payload['questions'][0]['image_base64'])))
        self.assertEqual(image.width, 1480)
        self.assertGreater(image.height, 900)
        # Confirm the bottom contains the figure, rather than just prose.
        figure = image.crop((140, image.height-900, 1340, image.height))
        box = ImageChops.difference(figure, Image.new('RGB', figure.size, 'white')).getbbox()
        self.assertGreater(box[2]-box[0], 500)
        self.assertGreater(box[3]-box[1], 500)

    def test_apothem_and_all_supported_side_counts_render(self):
        for sides in (3, 4, 5, 6, 8, 20):
            for measure in ('side', 'apothem'):
                spec = self.diagram()
                spec.update(sides=sides, measure=measure, show_apothem=False)
                self.assertEqual(polygon_image(spec).size, (1200, 900))

    def test_invalid_or_nonfinite_geometry_rejected(self):
        for change in ({'sides': 2}, {'sides': 21}, {'length': 0.0}, {'length': float('inf')}, {'measure': 'height'}):
            spec = self.diagram()
            spec.update(change)
            with self.assertRaises(ValidationError):
                RegularPolygonDiagram.model_validate(spec)

    def test_existing_text_only_questions_remain_text(self):
        artifact = validated_artifacts(json.dumps(quiz_sample()))[0]
        self.assertNotIn('image_base64', google_form_payload(artifact)['questions'][0])


class AlgebraicMeasurementTests(unittest.TestCase):
    def test_legacy_factors_keep_parentheses(self):
        for coefficient, factor in [(2.0, 'x+y'), (5.0, 'x-1'), (4.0, 'a+b')]:
            spec = RegularPolygonDiagram(sides=6, length=coefficient, measure='side', unit=factor, show_apothem=False)
            label, symbolic = measurement_label(spec)
            self.assertTrue(symbolic)
            self.assertEqual(label, f'{coefficient:g}' + r'\left(' + factor + r'\right)')

    def test_complete_formula_preserved_and_rendered(self):
        spec = RegularPolygonDiagram(sides=4, length=1.0, measurement_latex='5(x-1)', measure='side', unit='', show_apothem=False)
        self.assertEqual(measurement_label(spec), ('5(x-1)', True))
        self.assertEqual(polygon_image(spec.model_dump()).size, (1200, 900))

    def test_numeric_units_do_not_become_algebra(self):
        spec = RegularPolygonDiagram(sides=6, length=6.0, measure='side', unit='cm', show_apothem=False)
        self.assertEqual(measurement_label(spec), ('6 cm', False))

    def test_old_saved_quiz_recovers_with_same_measurements(self):
        from response_recovery import inspect_response
        data = quiz_sample()
        data['artifacts'][0]['quiz_questions'][0].update(title='Il lato misura 2(x+y).', diagrams=[dict(sides=6, length=2.0, measure='side', unit='x+y', show_apothem=False)])
        raw = json.dumps(data)
        artifact = validated_artifacts(raw)[0]
        recovered, warnings = inspect_response(raw)
        self.assertEqual(recovered, [artifact])
        self.assertEqual(warnings, [])
