"""Deterministic Google Apps Script export; generated answers are data, never code."""
import json
import base64
import io
from PIL import Image
from models_api_flat import Artifact


def validate_requested_quiz(raw, request):
    from validation import validate_response
    response = validate_response(raw)
    if response.status == "needs_clarification":
        return
    if len(response.artifacts) != 1 or response.artifacts[0].kind != "modulogoogle":
        raise ValueError("La risposta deve contenere un unico artefatto modulogoogle.")
    quiz = response.artifacts[0].quiz_questions
    if request.get("google_form_feedback") is True and any(not q.feedback_steps for q in quiz):
        raise ValueError("Feedback richiesto: mancano i passaggi di risoluzione per una o piu domande.")
    if len(quiz) != int(request["google_form_questions"]) or any(len(q.options) != int(request["google_form_answers"]) for q in quiz):
        raise ValueError("Il modulo generato non rispetta il numero di domande o risposte richiesto. Nessun modulo pronto disponibile.")


def google_form_payload(artifact):
    quiz = Artifact.model_validate({"id": artifact["artifact_id"], "kind": "modulogoogle",
        "audience": artifact.get("audience", "teacher"), "format": "gs", "title": artifact["title"],
        "containers": [], "quiz_questions": artifact.get("quiz_questions", [])})
    questions = [q.model_dump() for q in quiz.quiz_questions]
    from google_form_math import question_image, option_text, text_image
    for question in questions:
        image = question_image(question)
        if image:
            question["image_base64"] = base64.b64encode(image).decode('ascii')
        question['option_images_base64'] = []
        question['option_image_widths'] = []
        labels = []
        for index, option in enumerate(question['options']):
            label = option_text(option)
            option_image = text_image(option, width=740, margin=24, tight=True) if label is None else None
            question['option_images_base64'].append(base64.b64encode(option_image).decode('ascii') if option_image else None)
            if option_image:
                with Image.open(io.BytesIO(option_image)) as rendered:
                    question['option_image_widths'].append(min(600, round(rendered.width * 0.85)))
            else:
                question['option_image_widths'].append(None)
            # The API requires distinct option values. Invisible separators keep
            # image-only choices free of visible placeholder labels.
            labels.append(label if label is not None else '\u2063' * (index + 1))
        if len(set(labels)) != len(labels):
            raise ValueError('Risposte equivalenti dopo la rimozione dei delimitatori matematici: correggere le opzioni.')
        question['option_labels'] = labels
    return {'title': quiz.title, 'questions': questions}


def export_google_form(artifact):
    payload = google_form_payload(artifact)
    manifest = {'timeZone': 'Europe/Rome', 'runtimeVersion': 'V8', 'dependencies': {},
                'oauthScopes': ['https://www.googleapis.com/auth/forms',
                                'https://www.googleapis.com/auth/forms.body',
                                'https://www.googleapis.com/auth/drive.file',
                                'https://www.googleapis.com/auth/script.external_request']}
    data = json.dumps(payload, ensure_ascii=True)
    source = """// Agente Docente - modulo Google pronto alla creazione.
// 1. Apri https://script.google.com e crea un nuovo progetto.
// 2. Incolla tutto questo file in Codice.gs.
// 3. Salva anche il manifest appsscript.json indicato sotto.
// Esegui creaModuloGoogle e seleziona TUTTE le autorizzazioni richieste per autorizzare l'accesso a Google Moduli.
// Se ci sono immagini nelle risposte, configura prima la Google Forms API:
// https://developers.google.com/workspace/forms/api/guides/apps-script-setup
// Collega un progetto Google Cloud con Google Forms API e Google Drive API abilitate.
// Nel manifest appsscript.json aggiungi oauthScopes: forms, forms.body, drive.file,
// script.external_request (tutti con prefisso https://www.googleapis.com/auth/).
// Manifest completo per un progetto nuovo (per uno esistente conserva gli altri campi):
// {"timeZone":"Europe/Rome","runtimeVersion":"V8","dependencies":{},"oauthScopes":[
// "https://www.googleapis.com/auth/forms",
// "https://www.googleapis.com/auth/forms.body",
// "https://www.googleapis.com/auth/drive.file",
// "https://www.googleapis.com/auth/script.external_request"]}
// Le immagini delle opzioni sono condivise temporaneamente tramite Drive,
// importate nel modulo e poi rese private e cestinate.
// Rimuovi il precedente ambito drive dal manifest. Se era gia autorizzato,
// revoca il vecchio accesso nelle connessioni del tuo account e autorizza di nuovo.
// 4. Nel registro trovi i link di modifica e compilazione.
// Le esecuzioni successive riaprono lo stesso modulo senza duplicarlo.
const MANIFEST_GOOGLE = """ + json.dumps(manifest) + ";\n" + """const MODULO_GOOGLE = """ + data + ";\n" + """
function creaModuloGoogle() {
  // Stop before creating any file if a required scope was not granted.
  ScriptApp.requireScopes(ScriptApp.AuthMode.FULL, MANIFEST_GOOGLE.oauthScopes);
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const properties = PropertiesService.getScriptProperties();
    const key = 'agenteDocente:drive-file-v4:' + Utilities.base64EncodeWebSafe(
      Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, JSON.stringify(MODULO_GOOGLE)));
    const existing = properties.getProperty(key);
    if (existing) {
      const form = FormApp.openById(existing);
      console.log('Modifica: ' + form.getEditUrl());
      console.log('Compilazione: ' + form.getPublishedUrl());
      return form.getEditUrl();
    }
    const form = FormApp.create(MODULO_GOOGLE.title, true);
    try {
      form.setIsQuiz(true);
      form.setDescription('Quiz a risposta multipla. Seleziona una risposta per domanda.');
      MODULO_GOOGLE.questions.forEach((question, index) => {
        if (question.image_base64) {
          const image = Utilities.newBlob(Utilities.base64Decode(question.image_base64), 'image/png', 'domanda-' + (index + 1) + '.png');
          form.addImageItem().setTitle('Domanda ' + (index + 1))
            .setImage(image).setWidth(740);
        }
        const item = form.addMultipleChoiceItem();
        item.setTitle(question.image_base64 ? 'Domanda ' + (index + 1) + ' - Seleziona una risposta' : (index + 1) + '. ' + question.title);
        item.setRequired(true);
        item.setPoints(question.points);
        item.setChoices(question.options.map((value, i) => item.createChoice(question.option_labels[i], i === question.correct_index)));
        item.showOtherOption(false);
      });
      inserisciImmaginiRisposte(form.getId());
      properties.setProperty(key, form.getId());
    } catch (error) {
      console.warn('Modulo incompleto, da controllare o cestinare manualmente: ' + form.getEditUrl());
      throw error;
    }
    console.log('Modifica: ' + form.getEditUrl());
    console.log('Compilazione: ' + form.getPublishedUrl());
    return form.getEditUrl();
  } finally {
    lock.releaseLock();
  }
}

function richiestaForms(formId, suffix, payload) {
  const options = {
    method: payload ? 'post' : 'get',
    headers: {Authorization: 'Bearer ' + ScriptApp.getOAuthToken()},
    muteHttpExceptions: true
  };
  if (payload) {
    options.contentType = 'application/json';
    options.payload = JSON.stringify(payload);
  }
  const response = UrlFetchApp.fetch('https://forms.googleapis.com/v1/forms/' + formId + suffix, options);
  if (response.getResponseCode() >= 300) {
    throw Error('Immagini nelle risposte: configura Google Forms API e gli ambiti OAuth come indicato all\\'inizio dello script. Dettaglio: ' + response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

function richiestaDrive(url, method, payload, contentType) {
  const options = {method, headers: {Authorization: 'Bearer ' + ScriptApp.getOAuthToken()}, muteHttpExceptions: true};
  if (payload !== undefined) {
    options.contentType = contentType || 'application/json';
    options.payload = contentType ? payload : JSON.stringify(payload);
  }
  const response = UrlFetchApp.fetch(url, options);
  if (response.getResponseCode() >= 300) {
    throw Error('File di appoggio: abilita Google Drive API e configura drive.file nel manifest. Dettaglio: ' + response.getContentText());
  }
  const body = response.getContentText();
  return body ? JSON.parse(body) : {};
}

function inserisciImmaginiRisposte(formId) {
  if (!MODULO_GOOGLE.questions.some(q => q.option_images_base64.some(Boolean))) return;
  const document = richiestaForms(formId, '', null);
  const questions = document.items.map((item, index) => ({item, index})).filter(entry => entry.item.questionItem);
  if (questions.length !== MODULO_GOOGLE.questions.length) throw Error('Numero delle domande nel modulo non coerente.');
  const files = [];
  try {
    const requests = [];
    MODULO_GOOGLE.questions.forEach((question, questionIndex) => {
      if (!question.option_images_base64.some(Boolean)) return;
      const options = question.option_labels.map((value, optionIndex) => {
        const option = {value};
        const encoded = question.option_images_base64[optionIndex];
        if (encoded) {
          const blob = Utilities.newBlob(Utilities.base64Decode(encoded), 'image/png', 'opzione-' + (questionIndex + 1) + '-' + (optionIndex + 1) + '.png');
          const file = richiestaDrive('https://www.googleapis.com/upload/drive/v3/files?uploadType=media&fields=id&ignoreDefaultVisibility=true', 'post', blob.getBytes(), 'image/png');
          // Register immediately, so metadata/sharing failures also clean up.
          files.push(file);
          richiestaDrive('https://www.googleapis.com/drive/v3/files/' + file.id, 'patch', {name: blob.getName()});
          const permission = richiestaDrive('https://www.googleapis.com/drive/v3/files/' + file.id + '/permissions?fields=id', 'post', {type: 'anyone', role: 'reader', allowFileDiscovery: false});
          file.permissionId = permission.id;
          option.image = {
            sourceUri: 'https://drive.google.com/uc?export=download&id=' + file.id,
            altText: question.options[optionIndex],
            properties: {width: question.option_image_widths[optionIndex]}
          };
        }
        return option;
      });
      const entry = questions[questionIndex];
      requests.push({updateItem: {
        item: {itemId: entry.item.itemId, questionItem: {question: {
          choiceQuestion: {type: 'RADIO', options, shuffle: false},
          grading: {pointValue: question.points, correctAnswers: {answers: [{value: question.option_labels[question.correct_index]}]}}
        }}},
        location: {index: entry.index},
        updateMask: 'questionItem.question.choiceQuestion,questionItem.question.grading'
      }});
    });
    richiestaForms(formId, ':batchUpdate', {requests});
  } finally {
    files.forEach(file => {
      if (file.permissionId) {
        try {
          richiestaDrive('https://www.googleapis.com/drive/v3/files/' + file.id + '/permissions/' + file.permissionId, 'delete');
        } catch (error) { console.warn('Revoca condivisione immagine non riuscita: ' + file.id); }
      }
      // Trash independently even if revoking sharing fails.
      try {
        richiestaDrive('https://www.googleapis.com/drive/v3/files/' + file.id, 'patch', {trashed: true});
      } catch (error) { console.warn('Pulizia immagine temporanea non riuscita: ' + file.id); }
    });
  }
}

"""
    return source.encode('utf-8'), 'text/plain; charset=utf-8', 'modulogoogle.gs'


def google_form_document(artifact):
    """Printable questions plus a separate teacher answer key from the same quiz data."""
    from google_form_math import rich_block
    sections = []
    questions = artifact.get("quiz_questions", [])
    for index, question in enumerate(questions, 1):
        blocks = [rich_block(question.get("title", ""))]
        blocks.extend(rich_block(f"{option_index + 1}. {option}")
                      for option_index, option in enumerate(question.get("options", [])))
        sections.append({"section_id": f"quiz_question_{index}", "title": f"Domanda {index}", "blocks": blocks})
    if questions:
        key_blocks = []
        for index, question in enumerate(questions, 1):
            options = question.get("options", [])
            correct = question.get("correct_index")
            if isinstance(correct, int) and not isinstance(correct, bool) and 0 <= correct < len(options):
                answer = f"Risposta {correct + 1}: {options[correct]}"
            else:
                answer = "Risposta corretta non valida"
            key_blocks.append(rich_block(f"Domanda {index} - {answer} (punti: {question.get('points', 1)})."))
        sections.append({"section_id": "quiz_answer_key", "title": "Soluzioni per il docente", "blocks": key_blocks})
    return {**artifact, "sections": sections, "filename_hint": "modulogoogle.gs"}
