from __future__ import annotations

import json
import os
import re
import uuid
import urllib.error
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote
from game_catalog import games_from_directives, validate_game
import sqlite3
from directives_store import load_directives, replace_directives
from gemini_client import ask_gemini, gemini_schema
from models_api_flat import response_json_schema
from validation import validate_response, validated_artifacts, ResponseValidationError
from renderers import artifact_file
from response_recovery import inspect_response


BASE_DIR = Path(__file__).resolve().parent
SOFTWARE_VERSION = "1.0.8"
SCHOOLS_FILE = BASE_DIR / "scuola.json"
ROUTING_FILE = BASE_DIR / "routing_table.json"
REQUEST_TYPES_FILE = BASE_DIR / "Codici tipo_richiesta.json"
CHATBOT_FILE = BASE_DIR / "chatbot.json"
HISTORY_FILE = BASE_DIR / "history.json"
CATALOG_GROUPS = ("DET", "DED", "DBL", "DES", "DGT")
DEFAULT_REQUEST_TYPES = ["*", "lezione", "esercizio", "verifica", "lezione L1", "lezione L2", "lezione L3", "lezione L4"]
CHATBOTS = ["Gemini", "Chat Gpt", "Meta", "Perplexity", "Copilot"]


def load_catalogs() -> dict[str, list[dict[str, str]]]:
    directives = load_directives()
    catalogs = {group: [] for group in CATALOG_GROUPS}
    for directive in directives:
        group = directive.get("Gruppo")
        code = directive.get("Codice", "")
        if group in catalogs and not (group == "DBL" and code == "DBL01"):
            catalogs[group].append({"code": code, "title": directive.get("Titolo", "")})
    numbers = sorted({int(d["Gruppo"][2:]) for d in directives if re.fullmatch(r"DT[1-9][0-9]*", d.get("Gruppo", ""))})
    catalogs["lesson_types"] = [{"code": f"L{n}", "title": f"L{n}"} for n in numbers]
    catalogs["games"] = games_from_directives(directives)
    return catalogs


def resolve_directives(codes: list[str], directives_by_code: dict[str, dict[str, str]], groups: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    resolved = []
    seen = set()
    for code in codes:
        token = code.strip().upper()
        matches = [directives_by_code[token]] if token in directives_by_code else groups.get(token, [])
        for directive in matches:
            directive_code = directive["Codice"]
            if directive_code not in seen:
                seen.add(directive_code)
                resolved.append(directive)
    return resolved


def compose_request(data: dict[str, object]) -> dict[str, str]:
    if data.get("artifact") in ("Esercizi", "Verifica sommativa"):
        rows = data.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError("Righe esercizi non valide.")
        used = 0
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise ValueError(f"Riga {index}: dati non validi.")
            if not any(str(row.get(key, "")).strip() for key in ("det", "count", "topic", "ded", "dbl", "des", "dgt")):
                continue
            used += 1
            for key, label in (("det","Tipo esercizio"),("count","Numero"),("topic","Argomento"),("ded","Difficolta"),("dbl","Livello cognitivo"),("des","Soluzione")):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f"Riga {index}: compilare {label}; solo Grafico e opzionale.")
            try:
                count = float(row["count"])
            except ValueError:
                count = 0
            if not 1 <= count <= 9 or not count.is_integer():
                raise ValueError(f"Riga {index}: numero intero tra 1 e 9.")
        if not used:
            raise ValueError("Compilare almeno una riga di esercizi.")
    directives = load_directives()
    directives_by_code = {item["Codice"].upper(): item for item in directives}
    groups: dict[str, list[dict[str, str]]] = {}
    for item in directives:
        groups.setdefault(item["Gruppo"].upper(), []).append(item)
    routing = load_routing()
    artifact = str(data.get("artifact", ""))
    lesson_type = str(data.get("lesson_type", ""))
    routing_type = {"Lezione": f"lezione {lesson_type}", "Esercizi": "esercizio", "Verifica sommativa": "verifica"}.get(artifact, "")
    selected_types = ["*"]
    if artifact == "Lezione":
        selected_types.extend(["lezione", routing_type])
    elif artifact == "Esercizi":
        selected_types.append("esercizio")
    elif artifact == "Verifica sommativa":
        selected_types.extend(["verifica", "esercizio"])
    route_codes = [code for row in routing if row.get("TipoRichiesta") in selected_types for code in row.get("Direttive", "").split(",")]
    if artifact == "Lezione" and re.fullmatch(r"L[1-9][0-9]*", lesson_type):
        route_codes.append("DT" + lesson_type[1:])
    game_text = ""
    if artifact == "Giochi":
        game_group = str(data.get("game_type", ""))
        game_route = "gioco G" + game_group[3:]
        route_codes.extend(code for row in routing if row.get("TipoRichiesta") == game_route for code in row.get("Direttive", "").split(","))
        game_codes, game_text = validate_game(directives, data.get("game_type"), data.get("game_parameters", {}))
        route_codes.extend(game_codes)
        if data.get("game_type") == "DGM01":
            from DGM01_procedure import compose_exercises
            codes, text = compose_exercises(data.get("rows", []), data.get("game_parameters", {}), directives)
            route_codes.extend(codes)
            game_text += "\n" + text
    exercise_codes = []
    for row in data.get("rows", []):
        if isinstance(row, dict):
            exercise_codes.extend(row.get(key, "") for key in ("det", "ded", "dbl", "des", "dgt"))
    bes_codes = [item["Codice"] for item in groups.get("DBES", [])] if data.get("bes_dsa") is True else []
    resolved = resolve_directives(route_codes + exercise_codes + bes_codes, directives_by_code, groups)
    system_instruction = "\n\n".join(f"[{item['Codice']}] {item['Titolo']}\n{item['Direttiva completa']}" for item in resolved)
    prompt = str(data.get("prompt", "")).strip()
    school_type = str(data.get("school_type", "")).strip()
    school_address = str(data.get("school_address", "")).strip()
    ai_role = str(data.get("ai_role", "")).strip() or "Agisci come docente di matematica."
    if game_text:
        prompt += "\n" + game_text
    if artifact == "Esercizi" or (artifact == "Giochi" and data.get("game_type") == "DGM01"):
        title_lines = [
            "Titoli degli esercizi: aggiungi al titolo di ogni esercizio la coppia di codici DED e DBL "
            "selezionata per la sua riga, nel formato [DEDxx / DBLxx]. "
            "La coppia deve comparire nel titolo visibile dell'esercizio negli artefatti, "
            "anche nelle eventuali soluzioni, una sola volta. Mantieni l'ordine delle righe "
            "e applica la stessa coppia a tutti gli esercizi richiesti da una riga."
        ]
        exercise_number = 1
        for row_index, row in enumerate(data.get("rows", []), 1):
            if not isinstance(row, dict) or not row.get("ded") or not row.get("dbl"):
                continue
            count = int(float(row["count"])) if artifact == "Esercizi" else 1
            pair = f"[{row['ded'].strip()} / {row['dbl'].strip()}]"
            for _ in range(count):
                title_lines.append(f"Esercizio {exercise_number} (riga {row_index}): titolo con {pair}.")
                exercise_number += 1
        prompt += "\n" + "\n".join(title_lines)
    lines = prompt.splitlines()
    if ai_role in lines:
        lines.remove(ai_role)
    if school_type and school_address:
        school_line = f"Scuola: {school_type}; indirizzo: {school_address}."
        lines = [line for line in lines if line != school_line]
        lines.insert(0, school_line)
    prompt = "\n".join([ai_role, *lines])
    return {"system_instruction": system_instruction, "prompt": prompt}


def load_schools() -> list[dict[str, str]]:
    if not SCHOOLS_FILE.exists():
        save_schools([{"TipoScuola": "Istituto professionale", "Indirizzo": "Manutenzione e assistenza tecnica"}])
    with SCHOOLS_FILE.open(encoding="utf-8-sig") as file:
        value = json.load(file)
    return value if isinstance(value, list) else []


def save_schools(rows: list[dict[str, str]]) -> None:
    with SCHOOLS_FILE.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)


def validate_schools(rows: object) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        raise ValueError("La tabella Scuola deve essere una lista di righe.")
    cleaned = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Ogni riga Scuola deve essere un oggetto.")
        school = {"TipoScuola": str(row.get("TipoScuola", "")).strip(), "Indirizzo": str(row.get("Indirizzo", "")).strip()}
        if not school["TipoScuola"] or not school["Indirizzo"]:
            raise ValueError("Tipo scuola e indirizzo sono obbligatori.")
        if school not in cleaned:
            cleaned.append(school)
    return cleaned


def extract_artifacts(response: str) -> list[dict[str, object]]:
    try:
        return validated_artifacts(response)
    except ResponseValidationError:
        return []


def generate_original_response(system_instruction: str, prompt: str, **options) -> tuple[str, list[dict[str, object]], list[str]]:
    response = ask_gemini(system_instruction, prompt, **options)
    artifacts, warnings = inspect_response(response)
    return response, artifacts, warnings


def load_routing() -> list[dict[str, str]]:
    if not ROUTING_FILE.exists():
        return []
    with ROUTING_FILE.open(encoding="utf-8-sig") as file:
        value = json.load(file)
    return value if isinstance(value, list) else []


def load_request_types() -> list[str]:
    if not REQUEST_TYPES_FILE.exists():
        save_request_types(DEFAULT_REQUEST_TYPES)
    with REQUEST_TYPES_FILE.open(encoding="utf-8-sig") as file:
        value = json.load(file)
    return value if isinstance(value, list) else []


def save_request_types(values: list[str]) -> None:
    with REQUEST_TYPES_FILE.open("w", encoding="utf-8") as file:
        json.dump(values, file, ensure_ascii=False, indent=2)


def load_chatbot() -> str:
    if not CHATBOT_FILE.exists():
        save_chatbot("Gemini")
    with CHATBOT_FILE.open(encoding="utf-8-sig") as file:
        value = json.load(file)
    return value if value in CHATBOTS else "Gemini"


def save_chatbot(value: str) -> None:
    with CHATBOT_FILE.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def history_game_parameters(entry):
    if entry.get("game_type") == "DGM01":
        return entry.get("game_parameters")
    prompt = str(entry.get("prompt", ""))
    if not re.search(r"^Tipo di gioco: G01\b", prompt, re.M):
        return None
    # Older requests only stored these values in the composed prompt.
    parameters = dict(re.findall(r"^(PAR01|PAR02) \([^\n]*?\): ([^\n]*)", prompt, re.M))
    return parameters if all(parameters.get(key, "").strip() for key in ("PAR01", "PAR02")) else None


def regenerate_history_game(entry_id):
    import DGM01_template
    entry = next((item for item in load_history() if item.get("id") == entry_id), None)
    parameters = history_game_parameters(entry) if entry else None
    if not parameters:
        raise ValueError("Parametri del gioco G01 non disponibili nella richiesta salvata.")
    artifact = DGM01_template.create(parameters, load_directives())
    return DGM01_template.download(artifact["artifact_id"])


def load_history() -> list[dict[str, object]]:
    if not HISTORY_FILE.exists():
        return []
    with HISTORY_FILE.open(encoding="utf-8-sig") as file:
        value = json.load(file)
    entries = value if isinstance(value, list) else []
    for entry in entries:
        local_artifacts = [a for a in entry.get("artifacts", []) if str(a.get("artifact_id", "")).startswith("game-template-")]
        entry["artifacts"], entry["validation_problems"] = inspect_response(str(entry.get("response", "")))
        if history_game_parameters(entry):
            entry["artifacts"].insert(0, {"artifact_id": "history-game-" + entry["id"], "history_id": entry["id"], "title": "G01 - Regolamento", "formats": ["docx"]})
        else:
            entry["artifacts"] = local_artifacts + entry["artifacts"]
    return entries


def save_history(entries: list[dict[str, object]]) -> None:
    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(entries, file, ensure_ascii=False, indent=2)


def save_prompt_history(prompt: str, chatbot: str, response: str, artifacts: list[dict[str, object]], validation_problems: list[str], game_parameters=None) -> dict[str, object]:
    entries = load_history()
    entry = {
        "id": uuid.uuid4().hex,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "chatbot": chatbot,
        "prompt": prompt,
        "response": response,
        "artifacts": artifacts,
        "validation_problems": validation_problems,
    }
    if game_parameters is not None:
        entry.update(game_type="DGM01", game_parameters=dict(game_parameters))
    entries.append(entry)
    entries.sort(key=lambda item: str(item.get("requested_at", "")))
    save_history(entries)
    return entry


def save_routing(rows: list[dict[str, str]]) -> None:
    with ROUTING_FILE.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)


def validate_routing(rows: object) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        raise ValueError("Il routing deve essere una lista di righe.")
    fields = ("TipoRichiesta", "Direttive")
    clean_rows = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Ogni riga deve essere un oggetto.")
        clean_row = {field: str(row.get(field, "")).strip() for field in fields}
        if clean_row["TipoRichiesta"] not in set(load_request_types()):
            raise ValueError(f"Tipo richiesta non valido: {clean_row['TipoRichiesta']}")
        if not clean_row["Direttive"]:
            raise ValueError("Il campo Direttive non puo essere vuoto.")
        clean_row["Direttive"] = ",".join(
            directive.strip().upper()
            for directive in clean_row["Direttive"].split(",")
            if directive.strip()
        )
        clean_rows.append(clean_row)
    return clean_rows


def validate_request_types(values: object) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("I codici devono essere una lista.")
    clean_values = []
    for index, value in enumerate(values, 1):
        if not isinstance(value, str):
            raise ValueError(f"Riga {index}: il codice deve essere un testo.")
        item = value.strip()
        if not item or not item.isprintable():
            raise ValueError(f"Riga {index}: inserire un codice non vuoto su una sola riga.")
        if item not in clean_values:
            clean_values.append(item)
    return clean_values


class WebAppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/game-template":
            import DGM01_template
            self.send_json(DGM01_template.status())
            return
        if path == "/api/directives/export":
            content = json.dumps(load_directives(), ensure_ascii=False, indent=2).encode("utf-8")
            filename = "TabellaDirettive-" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".json"
            self.send_file(content, "application/json; charset=utf-8", filename)
            return
        if path in ("/api/verification-template", "/api/verification-template/download"):
            import verification_template as template
            if path.endswith("/download"):
                if not template.FILE.exists():
                    self.send_error(404, "Nessun modello caricato"); return
                self.send_file(template.FILE.read_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "ModelloVerifica.docx")
            else:
                self.send_json(template.status())
            return
        if path == "/api/gemini-schema":
            self.send_json(gemini_schema())
            return
        if path == "/api/response-schema":
            self.send_json(response_json_schema())
            return
        if path == "/api/directives":
            self.send_json(load_directives())
            return
        if path == "/api/catalogs":
            self.send_catalogs()
            return
        if path == "/api/schools":
            self.send_json(load_schools())
            return
        if path == "/api/routing":
            self.send_json(load_routing())
            return
        if path == "/api/request-types":
            self.send_json(load_request_types())
            return
        if path == "/api/chatbot":
            self.send_json({"chatbot": load_chatbot(), "options": CHATBOTS})
            return
        if path == "/api/version":
            self.send_json({"version": SOFTWARE_VERSION})
            return
        if path == "/api/history":
            self.send_json(load_history())
            return
        if path == "/api/compose":
            self.send_json(compose_request({}))
            return
        if path in ("/", "/index.html"):
            self.path = "/index.html"
        if path == "/routing":
            self.path = "/routing.html"
        if path == "/request-types":
            self.path = "/request_types.html"
        if path == "/history":
            self.path = "/history.html"
        if path == "/schools":
            self.path = "/schools.html"
        if path == "/directives":
            self.path = "/directives.html"
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path in ("/api/verification-template", "/api/game-template"):
            import verification_template as template
            if urlparse(self.path).path == "/api/game-template":
                import DGM01_template as template
            try:
                length=int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= template.MAX_SIZE:
                    raise ValueError("Caricare un DOCX non vuoto, massimo 10 MB.")
                info=template.save(self.rfile.read(length), unquote(self.headers.get("X-Template-Filename", "verification_template.docx")))
                self.send_json({"ok":True, **info})
            except (ValueError, OSError) as error:
                self.send_json({"ok":False,"error":str(error)},status=400)
            return

        if urlparse(self.path).path == "/api/shutdown":
            self.send_json({"ok": True})
            ThreadingHTTPServer.shutdown(self.server)
            return
        if urlparse(self.path).path not in ("/api/directives/import", "/api/routing", "/api/request-types", "/api/chatbot", "/api/compose", "/api/gemini", "/api/artifact", "/api/history/delete", "/api/schools"):
                self.send_error(404)
                return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            if urlparse(self.path).path == "/api/directives/import":
                rows = replace_directives(body)
                self.send_json({"ok": True, "rows": rows})
            elif urlparse(self.path).path == "/api/request-types":
                values = validate_request_types(body)
                save_request_types(values)
                self.send_json({"ok": True, "values": values})
            elif urlparse(self.path).path == "/api/schools":
                schools = validate_schools(body)
                save_schools(schools)
                self.send_json({"ok": True, "rows": schools})
            elif urlparse(self.path).path == "/api/chatbot":
                value = str(body.get("chatbot", "")).strip() if isinstance(body, dict) else ""
                if value not in CHATBOTS:
                    raise ValueError("Chatbot non valido.")
                save_chatbot(value)
                self.send_json({"ok": True, "chatbot": value})
            elif urlparse(self.path).path in ("/api/compose", "/api/gemini"):
                image_limit = body.get("image_limit", 3)
                if body.get("generate_images") is True and (type(image_limit) is not int or not 1 <= image_limit <= 10):
                    raise ValueError("Limite immagini: inserire un intero tra 1 e 10.")
                composed = compose_request(body)
                local_artifact = None
                if body.get("artifact") == "Giochi" and body.get("game_type") == "DGM01":
                    import DGM01_template
                    local_artifact = DGM01_template.create(body.get("game_parameters", {}), load_directives())
                    composed["artifacts"] = [local_artifact]
                if urlparse(self.path).path == "/api/gemini":
                    cache_report={}
                    composed["response"], composed["artifacts"], composed["validation_problems"] = generate_original_response(composed["system_instruction"], composed["prompt"], use_cache=body.get("use_cache") is True, cache_minutes=body.get("cache_minutes",15), cache_report=cache_report)
                    composed["cache_info"]=cache_report
                    if body.get("generate_images") is True:
                        from generated_assets import generate_images
                        image_messages = generate_images(composed["response"], image_limit)
                        composed["artifacts"], composed["validation_problems"] = inspect_response(composed["response"])
                        composed["validation_problems"].extend(image_messages)
                    if local_artifact:
                        composed["artifacts"].insert(0, local_artifact)
                    entry = save_prompt_history(composed["prompt"], load_chatbot(), composed["response"], composed["artifacts"], composed["validation_problems"], game_parameters=body.get("game_parameters") if local_artifact else None)
                    composed["history_id"] = entry["id"]
                self.send_json({"ok": True, **composed})
            elif urlparse(self.path).path == "/api/artifact":
                if isinstance(body, dict) and str(body.get("artifact_id", "")).startswith("history-game-"):
                    if body.get("format") != "docx": raise ValueError("Il regolamento si genera in DOCX.")
                    self.send_file(*regenerate_history_game(body["artifact_id"].removeprefix("history-game-")))
                    return
                if isinstance(body, dict) and str(body.get("artifact_id", "")).startswith("game-template-"):
                    import DGM01_template
                    if body.get("format") != "docx": raise ValueError("Il modello Word si scarica in DOCX.")
                    self.send_file(*DGM01_template.download(body["artifact_id"]))
                    return
                if not isinstance(body, dict) or not isinstance(body.get("response"), str):
                    raise ValueError("La generazione richiede la risposta JSON completa da validare.")
                artifacts, warnings = inspect_response(body["response"])
                artifact = next((item for item in artifacts if item.get("artifact_id") == body.get("artifact_id")), None)
                if artifact is None:
                    raise ValueError("Nessun artefatto recuperabile con questo identificatore.")
                engine = body.get("engine", "standard")
                if engine not in ("standard", "typst"):
                    raise ValueError("Motore di rendering sconosciuto.")
                if engine == "typst":
                    if body.get("format") != "pdf":
                        raise ValueError("Typst/Lilaq e disponibile solo per PDF.")
                    from typst_renderer import export
                    content, content_type, filename = export(artifact)
                else:
                    content, content_type, filename = artifact_file(artifact, str(body.get("format", "")), best_effort=True, warnings=warnings)
                self.send_file(content, content_type, filename)
            elif urlparse(self.path).path == "/api/history/delete":
                old_entries = load_history()
                entry_id = str(body.get("id", ""))
                entries = [] if body.get("all") else [entry for entry in old_entries if entry.get("id") != entry_id]
                save_history(entries)
                self.send_json({"ok": True, "deleted": len(old_entries) - len(entries)})
            else:
                rows = validate_routing(body)
                save_routing(rows)
                self.send_json({"ok": True, "rows": rows})
        except sqlite3.Error:
            self.send_json({"ok": False, "error": "Errore nel database: importazione annullata, dati precedenti conservati."}, status=500)
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json({"ok": False, "error": str(error)}, status=400)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                message = "Quota Gemini esaurita (limite free tier). Attendi il ripristino della quota oppure configura un progetto Google AI con billing/quota disponibile."
                self.send_json({"ok": False, "error": message, "code": "GEMINI_QUOTA_EXHAUSTED"}, status=429)
            else:
                self.send_json({"ok": False, "error": f"Gemini non disponibile: {error}"}, status=error.code or 502)
        except (urllib.error.URLError, TimeoutError) as error:
            self.send_json({"ok": False, "error": f"Comunicazione Gemini non riuscita: {error}"}, status=502)

    def send_catalogs(self) -> None:
        self.send_json(load_catalogs())

    def send_json(self, value: object, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_file(self, content: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def end_headers(self) -> None:
        if self.path.endswith((".html", "/")):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def run() -> None:
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8000"))    
    server = ThreadingHTTPServer((host, port), WebAppHandler)
    print(f"Webapp disponibile su http://{host}:{port}")
    print("Premi CTRL+C per arrestare il server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer arrestato.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
