"""Diagnostics and nonblocking export for the sole active contract. No LLM retry."""
import json
from validation import validate_response, ResponseValidationError
from flat_adapter import materialize


def inspect_response(raw):
    try:
        candidate = json.loads(raw)
    except (ValueError, TypeError):
        return [], ["Risposta JSON non valida."]
    if not isinstance(candidate, dict) or candidate.get("contract_version") != "setupgemma_flat_2.1":
        return [], ["Contratto non supportato: richiesto setupgemma_flat_2.1."]
    warnings = []
    try:
        validate_response(raw)
    except ResponseValidationError as error:
        warnings = error.errors
    try:
        artifacts, messages = materialize(candidate)
        return artifacts, list(dict.fromkeys(warnings + messages))
    except (TypeError, AttributeError, KeyError):
        return [], warnings + ["Struttura non renderizzabile."]
