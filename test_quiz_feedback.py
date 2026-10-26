import json
import io
import zipfile
from unittest.mock import patch
import unittest
from pydantic import ValidationError
from models_api_flat import GoogleFormQuestion
from quiz_feedback import export_feedback

class FeedbackTests(unittest.TestCase):
    def test_json_order_and_optional_formula(self):
        q = dict(title="Equazione", options=["1", "2"], correct_index=1, points=1,
                 feedback_steps=[dict(text="Sottrai uno.", formula="x=2"), dict(text="La risposta e due.", formula="")])
        data, mime, name = export_feedback(dict(artifact_id="quiz", title="Quiz", quiz_questions=[q]), "json")
        result = json.loads(data)
        self.assertEqual(result["trigger"], "incorrect_answer")
        self.assertEqual(result["questions"][0]["steps"], q["feedback_steps"])
        self.assertEqual(name, "feedback.json")
        q["feedback_steps"][0]["text"] = " "
        with self.assertRaises(ValidationError): GoogleFormQuestion.model_validate(q)

    def test_old_quiz_requires_regeneration(self):
        with self.assertRaises(ValueError):
            export_feedback(dict(artifact_id="quiz", title="Quiz", quiz_questions=[]), "json")

    def test_zip_has_unique_folder_manifest_and_videos(self):
        artifact = dict(artifact_id="quiz", title="Equazioni / prova", quiz_questions=[
            dict(title="Trova x", options=["1", "2"], correct_index=1, points=1,
                 feedback_steps=[dict(text="La soluzione e due.", formula="x=2")])])
        def fake_render(question, directory, ffmpeg):
            target = directory / "video.mp4"
            target.write_bytes(b"test-video")
            return target
        with patch("quiz_feedback.shutil.which", return_value="ffmpeg"), patch("quiz_feedback.render_question", side_effect=fake_render):
            content, mime, name = export_feedback(artifact, "zip")
        from quiz_feedback import feedback_document
        document = feedback_document(artifact)
        root = document["folder_name"] + "/"
        self.assertEqual(name, document["folder_name"] + ".zip")
        self.assertEqual(mime, "application/zip")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(set(archive.namelist()), {root+"feedback.json", root+"LEGGIMI.txt", root+"collega_feedback_video.gs", root+document["questions"][0]["video_filename"]})
            self.assertEqual(json.loads(archive.read(root+"feedback.json")), document)
        self.assertEqual(feedback_document(artifact)["folder_name"], document["folder_name"])
        artifact["quiz_questions"][0]["feedback_steps"][0]["text"] = "Una spiegazione diversa."
        self.assertNotEqual(feedback_document(artifact)["folder_name"], document["folder_name"])

    def test_materialized_feedback_downloads(self):
        from test_google_form import quiz_sample
        from validation import validated_artifacts
        data = quiz_sample()
        data["artifacts"][0]["quiz_questions"][0]["feedback_steps"] = [dict(text="La risposta e due.", formula="x=2")]
        artifact = validated_artifacts(json.dumps(data))[0]
        self.assertIn("zip", artifact["formats"])
        self.assertTrue(artifact["feedback_folder"].startswith("Feedback_"))


    def test_feedback_latex_accepts_existing_delimiters(self):
        from quiz_feedback import feedback_latex
        for value in ("x=2", "$$x=2$$", "$x=2$", r"\[x=2\]", r"\(x=2\)", "  $$ x=2 $$  "):
            self.assertEqual(feedback_latex(value), "x=2")
        self.assertEqual(feedback_latex("$$ $$"), "")
        self.assertEqual(feedback_latex(r"$$2 \\cdot x$$"), r"2 \cdot x")
        self.assertEqual(feedback_latex(r"\begin{aligned}x&=1\\y&=2\end{aligned}"),
                         r"\begin{aligned}x&=1\\y&=2\end{aligned}")
