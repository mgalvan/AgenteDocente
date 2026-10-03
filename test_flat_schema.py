import copy
import unittest
from pydantic import ValidationError
from models_api_flat import FlatResponse, serving_schema


def sample():
    return {
        "contract_version":"setupgemma_flat_2.1", "status":"complete", "request_type":"esercizio",
        "artifacts":[{"id":"a1","kind":"exercise_sheet","audience":"teacher","format":"pdf","title":"Prova",
          "containers":[{"id":"s1","title":"Esempio","blocks":[{"id":"b1","kind":"text","ref":"t1"},{"id":"b2","kind":"formula","ref":"f1"},{"id":"b3","kind":"graph","ref":"g1"},{"id":"b4","kind":"image","ref":"i1"}]}]}],
        "texts":[{"id":"t1","segments":[{"kind":"text","value":"Calcola "},{"kind":"formula","value":"x+1"}]}],
        "formulas":[{"id":"f1","latex":"x+1","alt_text":"x piu uno","expression":""}],
        "graphs":[{"id":"g1","kind":"function_2d","expression":"x","points":[],"labels":[],"values":[],"viewport":{"x_min":-1.,"x_max":1.,"y_min":-1.,"y_max":1.},"x_label":"x","y_label":"y","alt_text":"Retta"}],
        "generated_images":[{"id":"i1","generation_prompt":"Un piano cartesiano","alt_text":"Piano"}], "provided_images":[],
        "lists":[],"tables":[],"questions":[],"validation_summary":{"complete":True,"audience_checked":True,"math_checked":True}}


class FlatTests(unittest.TestCase):
    def test_example(self):
        FlatResponse.model_validate(sample())

    def test_links_and_ids(self):
        for change in ("missing", "duplicate"):
            data=sample()
            if change == "missing": data["artifacts"][0]["containers"][0]["blocks"][0]["ref"]="not_found"
            else: data["generated_images"][0]["id"]="f1"
            with self.assertRaises(ValidationError): FlatResponse.model_validate(data)

    def test_table_and_list_can_reference_math_text(self):
        data=sample()
        cell={"segments":[{"kind":"text","value":"Calcola "},{"kind":"formula","value":"x+1"}]}
        data["lists"]=[{"id":"l1","items":[cell]}]
        data["tables"]=[{"id":"tab1","headers":[cell],"rows":[[cell]]}]
        FlatResponse.model_validate(data)
        data["tables"][0]["rows"]=[[cell,cell]]
        with self.assertRaises(ValidationError): FlatResponse.model_validate(data)

    def test_no_unions_or_open_objects(self):
        def visit(node):
            if isinstance(node,dict):
                self.assertFalse({"anyOf","oneOf"} & node.keys())
                if node.get("type")=="object":self.assertIs(node.get("additionalProperties"),False)
                for item in node.values():visit(item)
            elif isinstance(node,list):
                for item in node:visit(item)
        visit(serving_schema())

    def test_generated_image_cannot_invent_resource_id(self):
        data=sample();data["generated_images"][0]["resource_id"]="invented"
        with self.assertRaises(ValidationError):FlatResponse.model_validate(data)

    def test_application_dispatch_and_export(self):
        import json
        from response_recovery import inspect_response
        from renderers import artifact_file
        artifacts,warnings=inspect_response(json.dumps(sample()))
        self.assertEqual(artifacts[0]["artifact_id"],"a1")
        self.assertEqual(artifacts[0]["sections"][0]["blocks"][1]["latex"],"x+1")
        for fmt,signature in (("pdf",b"%PDF"),("pptx",b"PK"),("docx",b"PK")):
            content,_,_=artifact_file(artifacts[0],fmt,best_effort=True,warnings=warnings)
            self.assertTrue(content.startswith(signature))

    def test_unknown_fields_rejected(self):
        data=sample();data["formulas"][0]["python"]="x"
        with self.assertRaises(ValidationError):FlatResponse.model_validate(data)


if __name__ == "__main__": unittest.main()
