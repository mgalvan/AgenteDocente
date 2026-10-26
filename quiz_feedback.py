"""Export ordered feedback data and synchronized, per-question MP4 videos."""
import io
import hashlib
import re
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def feedback_document(artifact):
    from models_api_flat import GoogleFormQuestion
    questions = [GoogleFormQuestion.model_validate(q) for q in artifact.get("quiz_questions", [])]
    if not questions or any(not q.feedback_steps for q in questions):
        raise ValueError("Rigenera il modulo attivando il feedback: servono passaggi per ogni domanda.")
    identity = json.dumps({"title": artifact["title"], "questions": [q.model_dump() for q in questions]},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    quiz_code = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    title_slug = re.sub(r"[^a-zA-Z0-9]+", "_", artifact["title"]).strip("_")[:48] or "quiz"
    folder_name = f"Feedback_{title_slug}_{quiz_code}"
    return {"schema_version": 1, "quiz_code": quiz_code, "folder_name": folder_name, "artifact_id": artifact["artifact_id"], "title": artifact["title"],
            "language": "it-IT", "trigger": "incorrect_answer", "questions": [
                {"question_id": f"question_{i}", "question_number": i, "title": q.title,
                 "video_filename": f"{quiz_code}_domanda_{i:03d}.mp4",
                 "steps": [s.model_dump() for s in q.feedback_steps]}
                for i, q in enumerate(questions, 1)]}


def run(command, env=None):
    result = subprocess.run(command, capture_output=True, timeout=300, env=env,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-1500:]
        raise ValueError("Generazione video non riuscita: " + detail)


def narrate(text, target):
    # Fixed script: user text is read as UTF-8 data, never interpolated into code.
    source = target.with_suffix(".txt")
    source.write_text(text, encoding="utf-8")
    script = target.with_suffix(".ps1")
    script.write_text("""param([string]$source, [string]$target)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $voices = @($speaker.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'it-IT' })
  if ($voices.Count -eq 0) { throw 'Installa una voce di sintesi vocale italiana in Windows.' }
  $speaker.SelectVoice($voices[0].VoiceInfo.Name)
  $speaker.SetOutputToWaveFile($target)
  $speaker.Speak([System.IO.File]::ReadAllText($source, [System.Text.Encoding]::UTF8))
} finally { $speaker.Dispose() }
""", encoding="utf-8-sig")
    command = script.read_text(encoding="utf-8-sig").replace(
        "param([string]$source, [string]$target)",
        "$source = $env:QUIZ_FEEDBACK_SOURCE; $target = $env:QUIZ_FEEDBACK_TARGET")
    run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**os.environ, "QUIZ_FEEDBACK_SOURCE": str(source), "QUIZ_FEEDBACK_TARGET": str(target)})



def feedback_latex(value):
    """Accept raw LaTeX and AI output already wrapped in math delimiters."""
    value = value.strip()
    wrappers = (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$"))
    while value:
        for start, end in wrappers:
            if len(value) >= len(start) + len(end) and value.startswith(start) and value.endswith(end):
                value = value[len(start):-len(end)].strip()
                break
        else:
            break
    # Repair over-escaped commands observed in generated feedback; leave row breaks intact.
    value = re.sub(r"\\{2,}(?=(?:cdot|text|ne|frac|times|sqrt|ldots|leq|geq)\b)", lambda _: "\\", value)
    return value


def render_question(question, directory, ffmpeg):
    from PIL import Image, ImageDraw, ImageFont
    from visual_assets import formula
    import textwrap
    clips = []
    for i, step in enumerate(question["steps"], 1):
        audio, image, clip = (directory / f"step_{i}.{ext}" for ext in ("wav", "png", "mp4"))
        narrate(step["text"], audio)
        canvas = Image.new("RGB", (1280, 720), "white")
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 30)
        draw.text((50, 30), f"Domanda {question['question_number']} - Passaggio {i}", font=font, fill="black")
        latex = feedback_latex(step["formula"])
        if latex:
            try:
                asset = formula(latex)
                with Image.open(asset.path) as original:
                    rgba = original.convert("RGBA")
                    picture = Image.new("RGB", rgba.size, "white")
                    picture.paste(rgba, mask=rgba.getchannel("A"))
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                raise ValueError(f"Domanda {question['question_number']}, passaggio {i}: {error}") from error
            picture.thumbnail((1180, 570))
            canvas.paste(picture, ((1280-picture.width)//2, (720-picture.height)//2))
        else:
            lines = textwrap.wrap(step["text"], width=66)
            if len(lines) > 13:
                raise ValueError("Passaggio troppo lungo per il video: suddividere la narrazione in piu record.")
            draw.multiline_text((50, 130), chr(10).join(lines), font=font, fill="black", spacing=12)
        canvas.save(image)
        run([ffmpeg, "-y", "-loop", "1", "-framerate", "25", "-i", str(image), "-i", str(audio),
             "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-af", "apad=pad_dur=0.15", "-shortest", str(clip)])
        clips.append(clip)
    listing = directory / "clips.txt"
    listing.write_text(chr(10).join("file '" + p.name + "'" for p in clips), encoding="utf-8")
    target = directory / (question["question_id"] + ".mp4")
    run([ffmpeg, "-y", "-f", "concat", "-safe", "1", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(target)])
    return target


def export_feedback(artifact, fmt):
    if fmt not in ("json", "zip"):
        raise ValueError("Formato feedback non supportato.")
    document = feedback_document(artifact)
    content = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    if fmt == "json":
        return content, "application/json; charset=utf-8", "feedback.json"
    ffmpeg = shutil.which("ffmpeg")
    if os.name != "nt" or not ffmpeg:
        raise ValueError("I video feedback richiedono Windows con una voce italiana e FFmpeg nel PATH. Il JSON resta scaricabile.")
    output = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="quiz_feedback_") as temporary:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            root = document["folder_name"] + "/"
            archive.writestr(root + "feedback.json", content)
            archive.writestr(root + "collega_feedback_video.gs", Path(__file__).with_name("collega_feedback_video.gs").read_bytes())
            archive.writestr(root + "LEGGIMI.txt", feedback_instructions(document).encode("utf-8"))
            for question in document["questions"]:
                directory = Path(temporary) / question["question_id"]
                directory.mkdir()
                target = render_question(question, directory, ffmpeg)
                archive.write(target, root + question["video_filename"])
    return output.getvalue(), "application/zip", document["folder_name"] + ".zip"


def feedback_instructions(document):
    rows = ["FEEDBACK VIDEO - " + document["title"], "",
            "1. Estrai questo archivio ZIP.",
            "2. Nell'account scolastico carica su Drive la cartella:",
            document["folder_name"],
            "3. Mantieni invariati i nomi dei video e conserva feedback.json.",
            "4. Consenti agli studenti interessati di visualizzare i video.",
            "", "ASSOCIAZIONE DOMANDE / VIDEO"]
    rows.extend(f"Domanda {q['question_number']}: {q['video_filename']}" for q in document["questions"])
    rows.extend(["", "Ogni MP4 contiene i passaggi della soluzione con voce italiana e immagini sincronizzate.",
                 "Il caricamento della cartella non inserisce automaticamente i link nel modulo.",
                 "5. Con l'account scolastico apri https://script.google.com e crea un nuovo progetto.",
                 "6. Incolla il contenuto di collega_feedback_video.gs nel file Codice.gs.",
                 "7. In CONFIG_FEEDBACK inserisci il link di modifica del modulo scolastico e il link di questa cartella.",
                 "8. Salva, seleziona verificaCollegamenti ed esegui autorizzando l'accesso richiesto.",
                 "9. Se la verifica riesce, esegui collegaVideoFeedback.",
                 "10. Controlla una risposta errata e l'accesso al relativo video con un account studente.",
                 "Lo script inserisce link ai video, non video incorporati. Non richiede un deployment.",
                 "La condivisione dei video con gli studenti deve essere configurata su Drive.",
                 "Non rinominare le domande generate prima del collegamento."])
    return "\n".join(rows) + "\n"
