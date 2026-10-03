"""Resolve explicit flat-contract IDs into renderer objects, without inference."""
import re


def materialize(manifest):
    warnings = []
    def collection(name):
        rows = manifest.get(name, [])
        return {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)} if isinstance(rows, list) else {}
    texts, formulas, graphs = collection("texts"), collection("formulas"), collection("graphs")
    images = {**collection("generated_images"), **collection("provided_images")}
    lists, tables = collection("lists"), collection("tables")
    def missing(kind, ref):
        warnings.append(f"Riferimento {kind} non disponibile: {ref}.")
        return {"type": "text", "content": f"[Contenuto {kind} non disponibile: {ref}]"}
    def rich(ref):
        resource = texts.get(ref)
        if resource is None:
            return {"segments": [missing("text", ref)]}
        segments = []
        for segment in resource.get("segments", []):
            if not isinstance(segment, dict):
                continue
            value = segment.get("value", "")
            if segment.get("kind") == "formula":
                segments.append({"type":"formula", "display":"inline", "latex":str(value), "alt_text":""})
            else:
                segments.append({"type":"text", "content":str(value)})
        return {"segments": segments}
    def cell(value):
        if not isinstance(value, dict) or not isinstance(value.get("segments"), list):
            warnings.append("Voce/cella non conforme: richiesti contenuti diretti.")
            return {"segments": [{"type": "text", "content": "[Cella non valida]"}]}
        return {"segments": [
            {"type": "formula", "display": "inline", "latex": str(s.get("value", "")), "alt_text": ""}
            if s.get("kind") == "formula" else {"type": "text", "content": str(s.get("value", ""))}
            for s in value["segments"] if isinstance(s, dict)]}
    artifacts = []
    for index, artifact in enumerate(manifest.get("artifacts", [])):
        if not isinstance(artifact, dict):
            continue
        identifier = artifact.get("id") or f"export_{index}"
        converted = {"artifact_id":identifier, "artifact_type":artifact.get("kind", "exercise_sheet"), "audience":artifact.get("audience", "teacher"),
                     "format":artifact.get("format", "pdf"), "title":artifact.get("title", "Artefatto"), "references":[],
                     "filename_hint": re.sub(r"[^a-zA-Z0-9_-]", "_", str(identifier))+"."+str(artifact.get("format", "pdf"))}
        containers = []
        for container in artifact.get("containers", []):
            if not isinstance(container, dict):
                continue
            blocks = []
            for link in container.get("blocks", []):
                if not isinstance(link, dict):
                    continue
                kind, ref = link.get("kind", "text"), link.get("ref", "")
                base = {"block_id":link.get("id", ""), "block_type":kind, "audience":"teacher" if kind == "speaker_note" else converted["audience"]}
                if kind in {"text", "speaker_note"}:
                    base.update(rich(ref))
                elif kind == "formula" and ref in formulas:
                    base.update({k:v for k,v in formulas[ref].items() if k != "id"}, display="block")
                elif kind == "list" and ref in lists:
                    base["items"] = [cell(item) for item in lists[ref].get("items", [])]
                elif kind == "table" and ref in tables:
                    base["headers"] = [cell(item) for item in tables[ref].get("headers", [])]
                    base["rows"] = [[cell(item) for item in row] for row in tables[ref].get("rows", [])]
                elif kind == "graph" and ref in graphs:
                    base.update({k:v for k,v in graphs[ref].items() if k != "id"})
                elif kind == "image" and ref in images:
                    base.update({k:v for k,v in images[ref].items() if k != "id"})
                    from generated_assets import cached_image
                    if not cached_image(base):
                        warnings.append(f"{ref}: immagine non disponibile; generazione disattivata, non riuscita o risorsa non caricata.")
                else:
                    base.update(block_type="text", segments=[missing(kind, ref)])
                blocks.append(base)
            containers.append({"section_id" if converted["format"] != "pptx" else "slide_id":container.get("id", ""), "title":container.get("title", ""), "blocks":blocks})
        converted["slides" if converted["format"] == "pptx" else "sections"] = containers
        artifacts.append(converted)
    return artifacts, list(dict.fromkeys(warnings))
