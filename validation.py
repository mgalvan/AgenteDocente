"""Strict parsing and application checks, independent of Gemini and renderers."""
from __future__ import annotations
import re
import json
from models_api_flat import FlatResponse
from flat_adapter import materialize
from pydantic import ValidationError


LATEX_MARKERS = ("$", r"\(", r"\)", r"\[", r"\]", r"\begin{", r"\end{", r"\frac", r"\Delta", r"\cdot", r"\sqrt", r"\pmatrix", r"\cases")


class ResponseValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def readable_errors(error: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, item['loc'])) or 'root'}: {item['msg']}" for item in error.errors(include_input=False, include_url=False)]


def artifact_content_errors(artifact) -> list[str]:
    errors = []
    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"content", "title", "alt_text"} and isinstance(child, str):
                    if any(marker in child for marker in LATEX_MARKERS):
                        errors.append(f"{path}.{key}: LaTeX nel testo; usare formula o segments (DMA00).")
                if key == "latex" and isinstance(child, str):
                    if any(marker in child for marker in ("$", r"\(", r"\)", r"\[", r"\]")):
                        errors.append(f"{path}.latex: rimuovere i delimitatori matematici esterni.")
                    starts = re.findall(r"\\begin\{([^}]+)\}", child)
                    ends = re.findall(r"\\end\{([^}]+)\}", child)
                    if starts != list(reversed(ends)) and sorted(starts) != sorted(ends):
                        errors.append(f"{path}.latex: ambiente LaTeX non chiuso.")
                if key in {"items", "headers", "rows"}:
                    def check_cells(cells):
                        for cell in cells:
                            if isinstance(cell, str) and any(marker in cell for marker in LATEX_MARKERS):
                                errors.append(f"{path}.{key}: formula nel testo di una lista/tabella: esportazione consentita, impaginazione da verificare.")
                            elif isinstance(cell, list):
                                check_cells(cell)
                    check_cells(child)
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}.{index}")
    visit(artifact.model_dump(exclude_none=True), artifact.artifact_id)
    if not re.fullmatch(r"[\w .-]+", artifact.filename_hint) or artifact.filename_hint in {".", ".."}:
        errors.append(f"{artifact.artifact_id}.filename_hint: usare un nome sicuro senza directory.")
    for container in artifact.sections or artifact.slides or []:
        for block in container.blocks:
            if block.block_type != "speaker_note" and block.audience != artifact.audience:
                errors.append(f"{block.block_id}: audience incompatibile con l'artefatto.")
    return list(dict.fromkeys(errors))


def validate_response(raw: str) -> FlatResponse:
    try:
        response = FlatResponse.model_validate_json(raw)
    except ValidationError as error:
        raise ResponseValidationError(readable_errors(error)) from error
    converted, _ = materialize(response.model_dump())
    from types import SimpleNamespace
    problems = []
    for item in converted:
        proxy = SimpleNamespace(artifact_id=item["artifact_id"], filename_hint=item["filename_hint"], sections=[], slides=[], model_dump=lambda **kwargs: item)
        problems.extend(artifact_content_errors(proxy))
    if problems:
        raise ResponseValidationError(list(dict.fromkeys(problems)))
    return response


def validated_artifacts(raw: str) -> list[dict]:
    return materialize(validate_response(raw).model_dump())[0]
