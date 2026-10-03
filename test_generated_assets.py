import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import generated_assets as ga
from test_flat_schema import sample

class ImageTests(unittest.TestCase):
    def test_cache_and_limit(self):
        m=sample();out=io.BytesIO();Image.new('RGB',(20,20)).save(out,format='PNG')
        with tempfile.TemporaryDirectory() as folder,patch.object(ga,'ROOT',Path(folder)),patch.object(ga,'request_image',return_value=out.getvalue()) as call:
            self.assertFalse(ga.generate_images(json.dumps(m),1))
            self.assertFalse(ga.generate_images(json.dumps(m),1))
            self.assertEqual(call.call_count,1)
            self.assertIsNotNone(ga.cached_image(m['generated_images'][0]))
    def test_failure_no_retry(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(ga,'ROOT',Path(folder)),patch.object(ga,'request_image',side_effect=ValueError('failed')) as call:
            self.assertTrue(ga.generate_images(json.dumps(sample()),1))
            self.assertEqual(call.call_count,1)
    def test_zero_budget_no_calls(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(ga,'ROOT',Path(folder)),patch.object(ga,'request_image') as call:
            self.assertTrue(ga.generate_images(json.dumps(sample()),0));call.assert_not_called()
