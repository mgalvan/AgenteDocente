import json
import unittest
from unittest.mock import MagicMock, patch
from test_flat_schema import sample
from gemini_client import ask_gemini, generate_config

class TransportTests(unittest.TestCase):
    def test_sdk_structured_config(self):
        config=generate_config("SEMANTICHE")
        self.assertEqual(config.response_mime_type,"application/json")
        self.assertIn("artifacts", config.response_json_schema["properties"])
        self.assertEqual(config.system_instruction,"SEMANTICHE")
        def required_exist(node):
            if isinstance(node, dict):
                if "properties" in node:
                    self.assertTrue(set(node.get("required", [])) <= set(node["properties"]))
                for child in node.values(): required_exist(child)
            elif isinstance(node, list):
                for child in node: required_exist(child)
        required_exist(config.response_json_schema)
        client=MagicMock(); client.models.generate_content.return_value.text=json.dumps(sample())
        with patch("gemini_client.genai.Client") as factory,patch.dict("os.environ",{"GEMINI_API_KEY":"test"}):
            factory.return_value.__enter__.return_value=client
            ask_gemini("SEMANTICHE","PROMPT")
            args=client.models.generate_content.call_args.kwargs
            self.assertEqual(args["contents"],"PROMPT")
            self.assertIsNotNone(args["config"].response_json_schema)


if __name__ == "__main__": unittest.main()
