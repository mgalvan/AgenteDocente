"""Official Google GenAI structured output transport; no schema in prompt text."""
from __future__ import annotations
import os
import urllib.error
import httpx
from google import genai
from google.genai import types, errors
from models_api_flat import serving_schema

GEMINI_MODEL = "gemini-2.5-flash"


def gemini_schema() -> dict:
    return serving_schema()


def generate_config(system_instruction: str, max_output_tokens: int | None = None):
    return types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_json_schema=gemini_schema(),
        max_output_tokens=max_output_tokens,
    )


def ask_gemini(system_instruction: str, prompt: str, cached_content=None,
               operation: str = "generazione", timeout_seconds: int = 180,
               max_output_tokens: int | None = None, use_cache: bool = False,
               cache_minutes: int = 15, cache_report: dict | None = None) -> str:
    if use_cache and (type(cache_minutes) is not int or not 5 <= cache_minutes <= 60):
        raise ValueError("Durata cache: intero tra 5 e 60 minuti.")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY non configurata sul server.")
    config = generate_config(system_instruction, max_output_tokens)
    options = types.HttpOptions(timeout=timeout_seconds * 1000, retry_options=types.HttpRetryOptions(attempts=1))
    try:
        with genai.Client(api_key=api_key, http_options=options) as client:
            try:
                if use_cache:
                    from gemini_cache import acquire
                    entry=acquire(client,GEMINI_MODEL,system_instruction,gemini_schema(),api_key,cache_minutes)
                    config.system_instruction=None
                    config.cached_content=entry['name']
                    if cache_report is not None:cache_report.update(entry)
                elif cache_report is not None:cache_report.update(state='disabled')
                response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
                if cache_report is not None:
                    usage=response.usage_metadata
                    cache_report['cached_tokens']=getattr(usage,'cached_content_token_count',None)
                if not response.text:
                    raise ValueError("Gemini non ha restituito contenuto testuale (risposta vuota o bloccata).")
                return response.text
            except errors.APIError as error:
                raise urllib.error.HTTPError(None, error.code or 502, f"{operation}: {error.message}", None, None) from error
    except httpx.HTTPError as error:
        raise urllib.error.URLError(f"{operation}: {type(error).__name__}: connessione a Gemini non riuscita") from error
    raise ValueError("Gemini non disponibile.")
