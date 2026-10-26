/**
 * Agente Docente - collega gli MP4 di Drive ai feedback delle risposte errate.
 * Esegui con l'account scolastico da https://script.google.com (nuovo progetto).
 * Compila i due URL sotto. La cartella deve contenere feedback.json e gli MP4.
 * Esegui verificaCollegamenti, poi collegaVideoFeedback. Non serve un deployment.
 */
const CONFIG_FEEDBACK = {
  moduloUrl: 'INCOLLA_URL_MODULO_SCOLASTICO_EDIT',
  cartellaUrl: 'INCOLLA_URL_CARTELLA_VIDEO'
};

function verificaCollegamenti() {
  const piano = preparaCollegamenti_();
  console.log('Modulo: ' + piano.form.getTitle());
  console.log('Cartella: ' + piano.folder.getName());
  piano.rows.forEach(r => console.log('Domanda ' + r.number + ': ' + r.filename + ' -> ' + r.url));
  console.log('Verifica completata: ' + piano.rows.length + ' video. Esegui collegaVideoFeedback.');
}

function collegaVideoFeedback() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    // Tutti i controlli e la costruzione dei feedback precedono le modifiche.
    const piano = preparaCollegamenti_();
    const aggiornati = [];
    try {
      piano.rows.forEach(r => {
        r.item.setFeedbackForIncorrect(r.feedback);
        aggiornati.push(r);
      });
    } catch (error) {
      const falliti = [];
      aggiornati.reverse().forEach(r => {
        try { r.item.setFeedbackForIncorrect(r.previous); }
        catch (_) { falliti.push(r.number); }
      });
      throw new Error('Collegamento interrotto: ' + error.message +
        (falliti.length ? '. Ripristino non riuscito per le domande: ' + falliti.join(', ') : '. Feedback precedenti ripristinati.'));
    }
    console.log('Completato: ' + piano.rows.length + ' feedback video collegati.');
    console.log('Controlla l\'accesso ai video con un account studente e la pubblicazione dei voti nel quiz.');
  } finally {
    lock.releaseLock();
  }
}

function idGoogle_(value, kind) {
  value = String(value || '').trim();
  if (!value || value.startsWith('INCOLLA_')) throw new Error('Compila ' + kind + ' in CONFIG_FEEDBACK.');
  if (/^[\w-]+$/.test(value)) return value;
  const pattern = kind === 'moduloUrl' ? /\/forms\/d\/([\w-]+)(?:\/|$|\?)/ : /\/folders\/([\w-]+)(?:\/|$|\?)/;
  const match = value.match(pattern);
  if (!match || (kind === 'moduloUrl' && match[1] === 'e')) {
    throw new Error(kind + ': usa il link di modifica del modulo (/forms/d/ID/edit) o il link della cartella Drive.');
  }
  return match[1];
}

function fileUnico_(folder, name) {
  const files = folder.getFilesByName(name);
  if (!files.hasNext()) throw new Error('File mancante nella cartella: ' + name);
  const file = files.next();
  if (files.hasNext()) throw new Error('Nome duplicato nella cartella: ' + name + '. Conserva un solo file con questo nome.');
  return file;
}

function preparaCollegamenti_() {
  const form = FormApp.openById(idGoogle_(CONFIG_FEEDBACK.moduloUrl, 'moduloUrl'));
  if (!form.isQuiz()) throw new Error('Il modulo deve avere attivo Trasforma in un quiz.');
  const folder = DriveApp.getFolderById(idGoogle_(CONFIG_FEEDBACK.cartellaUrl, 'cartellaUrl'));
  const document = JSON.parse(fileUnico_(folder, 'feedback.json').getBlob().getDataAsString('UTF-8').replace(/^\uFEFF/, ''));
  if (document.schema_version !== 1 || !Array.isArray(document.questions) || !document.questions.length) {
    throw new Error('feedback.json non valido o senza domande.');
  }
  if (typeof document.title !== 'string' || !form.getTitle().endsWith(document.title)) {
    throw new Error('Il titolo del modulo non corrisponde al quiz del JSON: ' + document.title + '. Usa la copia corretta e conserva il titolo originale, anche preceduto da Copia di.');
  }
  const items = form.getItems(FormApp.ItemType.MULTIPLE_CHOICE).map(item => item.asMultipleChoiceItem());
  if (items.length !== document.questions.length) {
    throw new Error('Numero di domande a scelta multipla diverso dal JSON. Usa il modulo corrispondente a questa cartella.');
  }
  const used = new Set();
  const rows = document.questions.map((q, index) => {
    if (q.question_number !== index + 1 || typeof q.title !== 'string' ||
        typeof q.video_filename !== 'string' || !/^[\w-]+\.mp4$/.test(q.video_filename)) {
      throw new Error('Dati domanda o nome video non validi nel JSON, posizione ' + (index + 1));
    }
    const titles = [q.question_number + '. ' + q.title,
                    'Domanda ' + q.question_number + ' - Seleziona una risposta'];
    const matches = items.filter(item => titles.includes(item.getTitle()));
    if (matches.length !== 1 || used.has(matches[0].getId())) {
      throw new Error('Domanda ' + q.question_number + ' non identificabile. Non rinominare le domande generate; verifica modulo e cartella.');
    }
    const item = matches[0];
    used.add(item.getId());
    const file = fileUnico_(folder, q.video_filename);
    if (file.getMimeType() !== 'video/mp4') throw new Error('Il file non e un video MP4: ' + q.video_filename);
    const url = file.getUrl();
    const previous = item.getFeedbackForIncorrect();
    const builder = FormApp.createFeedback().setText(previous && previous.getText() || 'Guarda il procedimento corretto nel video.');
    const links = previous ? previous.getLinkUrls() : [];
    // Evita duplicati se lo script viene eseguito di nuovo.
    [...new Set(links)].filter(link => link !== url).forEach(link => builder.addLink(link));
    builder.addLink(url, 'Guarda la soluzione spiegata');
    return {item, previous, feedback: builder.build(), url, filename: q.video_filename, number: q.question_number};
  });
  return {form, folder, rows};
}
