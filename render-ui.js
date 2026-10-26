// Shared download feedback for composer and history.
let renderInProgress = false;
let lastRenderUrl = null;
async function downloadArtifact(artifact, responseText, format, button) {
  if (renderInProgress) return;
  renderInProgress = true;
  const engineSelect = document.getElementById('pdfEngine');
  const engine = format === 'pdf' ? engineSelect?.value || 'standard' : 'standard';
  const engineName = engine === 'typst' ? 'Typst/Lilaq' : 'motore attuale';
  const feedbackExport = ['json', 'zip'].includes(format) && artifact.artifact_type === 'modulogoogle';
  const controls = [...document.querySelectorAll('.artifact-card button, #pdfEngine')];
  const states = controls.map(control => [control, control.disabled]);
  const oldText = button.textContent;
  let status = document.getElementById('renderStatus');
  if (!status) {
    status = document.createElement('div'); status.id = 'renderStatus';
    status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    status.style.cssText = 'position:fixed;bottom:20px;left:20px;right:20px;z-index:1000;padding:16px;background:#e6f5f2;color:#05645f;border:1px solid #087f78;border-radius:8px;box-shadow:0 4px 16px #0002';
    document.body.appendChild(status);
  }
  states.forEach(([control]) => { control.disabled = true; });
  button.textContent = 'Generazione in corso...';
  status.textContent = feedbackExport ? (format === 'zip' ? 'Generazione dei video con voce italiana e preparazione ZIP: attendi, puo richiedere alcuni minuti.' : 'Preparazione JSON feedback...') : format === 'gs' ? 'Preparazione del modulo Google in corso...' : `Generazione ${format.toUpperCase()} in corso: ${engineName} sta lavorando. Attendi il download.`;
  status.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch('/api/artifact', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({response:responseText, artifact_id:artifact.artifact_id, format, engine})});
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.error || 'Rendering non riuscito.');
    }
    const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url;
    link.download = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1] || `artefatto.${format}`;
    document.body.appendChild(link); link.click(); link.remove();
    if (lastRenderUrl) URL.revokeObjectURL(lastRenderUrl);
    lastRenderUrl = url;
    status.textContent = feedbackExport ? (format === 'zip' ? `ZIP pronto. Estrai e carica su Drive scolastico la cartella ${artifact.feedback_folder || 'contenuta nello ZIP'}, senza rinominare i video.` : 'JSON feedback pronto. Download avviato.') : format === 'gs' ? 'Modulo Google scaricato: incolla il file in Google Apps Script ed esegui creaModuloGoogle.' : `${format.toUpperCase()} generato con ${engineName}. Download avviato.`;
    const manual = document.createElement('a');manual.href=url;manual.download=link.download;manual.textContent=' Scarica '+link.download;manual.style.fontWeight='bold';status.appendChild(manual);
  } catch (error) {
    status.textContent = `Generazione non riuscita: ${error.message}. Puoi riprovare.`;
  } finally {
    states.forEach(([control, disabled]) => { control.disabled = disabled; });
    button.textContent = oldText;
    status.setAttribute('aria-busy', 'false');
    renderInProgress = false;
  }
}


// Quiz preview and guided Apps Script creation, shared by composer and history.
function appendGoogleFormControls(card, artifact, responseText) {
  appendDirectGoogleControls(card, artifact, responseText);
  if (artifact.feedback_folder) {
    const instructions = document.createElement('p');
    instructions.textContent = `Dopo aver generato lo ZIP, estrailo e carica nel Drive scolastico la cartella ${artifact.feedback_folder}. Mantieni i nomi dei video e consenti agli studenti di visualizzarli. Poi segui LEGGIMI.txt per eseguire lo script collega_feedback_video.gs incluso nello ZIP e collegare i video al modulo.`;
    card.appendChild(instructions);
  }
  const preview = document.createElement('details');
  preview.open = true;
  const summary = document.createElement('summary');
  summary.textContent = 'Anteprima delle domande';
  preview.appendChild(summary);
  const quiz = artifact.quiz_questions || (() => {
    try { return JSON.parse(responseText).artifacts.find(item => item.id === artifact.artifact_id)?.quiz_questions || []; }
    catch (_) { return []; }
  })();
  quiz.forEach((question, index) => {
    const group = document.createElement('fieldset');
    const legend = document.createElement('legend');
    legend.textContent = `${index + 1}. ${question.title}`;
    group.appendChild(legend);
    question.options.forEach(option => {
      const line = document.createElement('div');
      line.textContent = `? ${option}`;
      group.appendChild(line);
    });
    preview.appendChild(group);
  });
  if (!quiz.length) {
    const message = document.createElement('p');
    message.textContent = 'Anteprima non disponibile: ricarica la richiesta dalla cronologia.';
    preview.appendChild(message);
  }
  card.appendChild(preview);
  const hasMath = text => text.includes('$') || text.includes('\\(') || text.includes('\\[');
  if (quiz.some(question => hasMath(question.title) || question.options.some(option => hasMath(option)))) {
    const mathStatus = document.createElement('p');
    mathStatus.setAttribute('role', 'status');
    mathStatus.textContent = 'Preparazione delle formule impaginate...';
    preview.appendChild(mathStatus);
    fetch('/api/artifact', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({response:responseText, artifact_id:artifact.artifact_id, format:'gs', engine:'standard'})})
      .then(async response => {
        if (!response.ok) { const error = await response.json(); throw Error(error.error || 'Rendering matematico non riuscito.'); }
        const script = await response.text();
        const match = script.match(/const MODULO_GOOGLE = ([^\n]+);/);
        if (!match) throw Error('Dati delle immagini non disponibili.');
        const data = JSON.parse(match[1]);
        const groups = preview.querySelectorAll('fieldset');
        data.questions.forEach((question, index) => {
          if (!groups[index]) return;
          const group = groups[index];
          group.replaceChildren();
          const legend = document.createElement('legend');
          legend.textContent = question.image_base64 ? `Domanda ${index + 1}` : `${index + 1}. ${question.title}`;
          group.appendChild(legend);
          const addImage = (parent, encoded, alt) => {
            const image = document.createElement('img');
            image.src = 'data:image/png;base64,' + encoded;
            image.alt = alt;
            image.style.maxWidth = '100%'; image.style.height = 'auto';
            parent.appendChild(image);
          };
          if (question.image_base64) addImage(group, question.image_base64, question.title);
          question.options.forEach((option, optionIndex) => {
            const line = document.createElement('div');
            line.style.cssText = 'display:flex;align-items:center;gap:8px;margin:8px 0';
            const radio = document.createElement('input');
            radio.type = 'radio'; radio.disabled = true;
            radio.setAttribute('aria-label', `Opzione ${optionIndex + 1}`);
            line.appendChild(radio);
            const encoded = question.option_images_base64?.[optionIndex];
            if (encoded) addImage(line, encoded, option);
            else line.appendChild(document.createTextNode(question.option_labels?.[optionIndex] ?? option));
            group.appendChild(line);
          });
        });
        mathStatus.textContent = 'Ogni risposta ? mostrata nella propria opzione.';
      }).catch(error => { mathStatus.textContent = error.message; });
  }
  const scriptCard = document.createElement('details');
  const scriptSummary = document.createElement('summary');
  scriptSummary.textContent = 'Esportazione Apps Script (alternativa)';
  scriptCard.appendChild(scriptSummary); card.appendChild(scriptCard);
  const help = document.createElement('p');
  help.textContent = 'Per creare il quiz nel tuo account Google: copia lo script, apri Google Apps Script, crea un Nuovo progetto e incolla il codice in Codice.gs sostituendo quello iniziale. Salva, seleziona creaModuloGoogle e premi Esegui. Autorizza Google e apri il link Compilazione nel Registro di esecuzione. Per risposte con immagini, abilita Google Forms API e Google Drive API. Copia anche il manifest appsscript.json mostrato sotto: usa drive.file per i soli file creati dal programma. Se avevi autorizzato la versione precedente, revoca il vecchio accesso e autorizza nuovamente. Il download o caricamento del file .gs da solo non esegue lo script.';
  scriptCard.appendChild(help);
  const link = document.createElement('a');
  link.href = 'https://script.google.com/home/start';
  link.target = '_blank'; link.rel = 'noopener';
  link.textContent = 'Apri Google Apps Script';
  scriptCard.appendChild(link);
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'secondary';
  button.textContent = 'Mostra e copia script Google';
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  const code = document.createElement('textarea');
  code.readOnly = true; code.hidden = true; code.rows = 12;
  code.style.width = '100%'; code.setAttribute('aria-label', 'Script da incollare in Google Apps Script');
  const manifestCode = document.createElement('textarea');
  manifestCode.readOnly = true; manifestCode.hidden = true; manifestCode.rows = 12;
  manifestCode.style.width = '100%';
  manifestCode.setAttribute('aria-label', 'Configurazione appsscript.json con accesso limitato ai file del programma');
  const manifestButton = document.createElement('button');
  manifestButton.type = 'button'; manifestButton.className = 'secondary'; manifestButton.hidden = true;
  manifestButton.textContent = 'Copia configurazione appsscript.json';
  manifestButton.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(manifestCode.value); status.textContent = 'Configurazione copiata: incollala in appsscript.json. Rimuovi il vecchio permesso drive e conserva eventuali altri campi del progetto.'; }
    catch (_) { manifestCode.focus(); manifestCode.select(); status.textContent = 'Premi Ctrl+C e incolla la configurazione in appsscript.json.'; }
  });
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      if (!code.value) {
        const response = await fetch('/api/artifact', {method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({response:responseText, artifact_id:artifact.artifact_id, format:'gs', engine:'standard'})});
        if (!response.ok) { const error = await response.json(); throw Error(error.error || 'Script non disponibile.'); }
        code.value = await response.text();
      }
      const manifestMatch = code.value.match(/const MANIFEST_GOOGLE = ([^\n]+);/);
      if (manifestMatch) {
        manifestCode.value = JSON.stringify(JSON.parse(manifestMatch[1]), null, 2);
        manifestCode.hidden = false; manifestButton.hidden = false;
      }
      code.hidden = false;
      try {
        await navigator.clipboard.writeText(code.value);
        status.textContent = 'Script copiato. Apri Google Apps Script e incollalo in Codice.gs.';
      } catch (_) {
        code.focus(); code.select();
        status.textContent = 'Premi Ctrl+C per copiare lo script selezionato, poi incollalo in Google Apps Script.';
      }
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
  scriptCard.append(button, status, code, manifestButton, manifestCode);
}
