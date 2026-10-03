"""One explicit, bounded API call. Run manually; never imported by the server."""
import json
import os
from pathlib import Path
from google import genai
from google.genai import types, errors
from pydantic import ValidationError
from models_api_flat import FlatResponse, serving_schema


def main():
    destination = Path(__file__).resolve().parent / "flat_schema_probe"
    destination.mkdir(exist_ok=True)
    schema = serving_schema()
    (destination / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_json_schema=schema,
        system_instruction="Test tecnico: rispetta il contratto. ID univoci e riferimenti esistenti. Campi non usati: stringhe vuote o array vuoti. Non produrre immagini reali, solo descrizioni.",
        temperature=0, max_output_tokens=1400,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    prompt = "Risposta complete minima: un exercise_sheet teacher pdf, un container, quattro riferimenti: text, formula, graph, image. Un testo brevissimo, formula x+1, grafico function_2d expression x (viewport da -1 a 1), immagine generated con prompt di tre parole. Una risorsa per ciascuna raccolta usata. lists, tables, questions vuoti. Nessun altro contenuto. request_type esercizio."
    report = {"model": "gemini-2.5-flash", "max_output_tokens": 1400, "attempts": 1}
    try:
        with genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=60000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
            response = client.models.generate_content(model=report["model"], contents=prompt, config=config)
        report["schema_accepted"] = True
        report["usage"] = response.usage_metadata.model_dump(exclude_none=True) if response.usage_metadata else {}
        raw = response.text or ""
        (destination / "response.json").write_text(raw, encoding="utf-8")
        try:
            model = FlatResponse.model_validate_json(raw)
            report["valid"] = True
            report["counts"] = {name: len(getattr(model, name)) for name in ("artifacts", "texts", "formulas", "graphs", "generated_images", "provided_images")}
        except ValidationError as error:
            report["valid"] = False
            report["errors"] = error.errors(include_input=False, include_url=False, include_context=False)
    except errors.APIError as error:
        report.update(schema_accepted=False, http_status=error.code, error=error.message)
    (destination / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
