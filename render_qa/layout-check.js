
    let catalogs = {};
    const $ = id => document.getElementById(id);
    const artifact = $('artifact');
    const chatbot = $('chatbot');
    const schoolType = $('schoolType');
    const schoolAddress = $('schoolAddress');
    let schools = [];
    const utilityButton = $('utilityButton');
    utilityButton.addEventListener('click', () => utilityButton.parentElement.classList.toggle('open'));

    function escapeOption(value) { return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }
    function options(group) { return '<option value="">Seleziona</option>' + catalogs[group].map(item => `<option value="${escapeOption(item[0])}">${escapeOption(item[0])} · ${escapeOption(item[1])}</option>`).join(''); }
    function buildRows() {
      $('exerciseRows').innerHTML = Array.from({ length: 10 }, (_, index) => `<tr data-row="${index + 1}"><td>${index + 1}</td><td><select class="det">${options('DET')}</select></td><td><input class="count" type="number" min="1" max="9" placeholder="1-9"></td><td><input class="topic" type="text" placeholder="Argomento"></td><td><select class="ded">${options('DED')}</select></td><td><select class="dbl">${options('DBL')}</select></td><td><select class="des">${options('DES')}</select></td><td><select class="dgt">${options('DGT')}</select></td></tr>`).join('');
    }
    function updateVisibility() {
      const value = artifact.value;
      $('lessonPanel').classList.toggle('visible', value === 'Lezione');
      $('exercisePanel').classList.toggle('visible', value === 'Esercizi' || value === 'Verifica sommativa');
      $('tableTitle').textContent = value === 'Verifica sommativa' ? 'Configurazione della verifica' : 'Configurazione degli esercizi';
      updateActionState();
    }
    function rowValues(row) { const value = selector => row.querySelector(selector).value; return { det: value('.det'), count: value('.count'), topic: value('.topic'), ded: value('.ded'), dbl: value('.dbl'), des: value('.des'), dgt: value('.dgt') }; }
    function updateActionState() {
      const type = artifact.value;
      const commonFieldsReady = Boolean($('classe').value && type);
      let requestReady = false;
      if (type === 'Lezione') {
        requestReady = Boolean($('lessonType').value && $('lessonTopic').value.trim());
      } else if (type === 'Esercizi' || type === 'Verifica sommativa') {
        requestReady = [...document.querySelectorAll('#exerciseRows tr')].some(row => {
          const values = rowValues(row);
          return Boolean(values.det && values.count && values.topic.trim());
        });
      }
      const enabled = commonFieldsReady && requestReady;
      $('prepare').disabled = !enabled;
      $('sendGemini').disabled = !enabled;
    }
    function requestPayload(prompt) { return { artifact: artifact.value, lesson_type: $('lessonType').value, school_type: schoolType.value, school_address: schoolAddress.value, ai_role: $('aiRole').value.trim(), bes_dsa: $('besDsa').checked, use_cache: $('useCache').checked, cache_minutes: Number($('cacheMinutes').value), generate_images: $('generateImages').checked, image_limit: Number($('imageLimit').value), prompt, rows: [...document.querySelectorAll('#exerciseRows tr')].map(rowValues).filter(row => Object.values(row).some(Boolean)) }; }
    function updateSchoolAddresses() {
      const addresses = schools.filter(school => school.TipoScuola === schoolType.value).map(school => school.Indirizzo);
      schoolAddress.innerHTML = '<option value="">Seleziona indirizzo</option>' + addresses.map(address => `<option value="${address}">${address}</option>`).join('');
      schoolAddress.disabled = !addresses.length;
    }
    function parseGeminiJson(text) {
      const cleaned = text.trim().replace(/^```json\s*/i, '').replace(/\s*```$/, '');
      try { return JSON.parse(cleaned); } catch (error) {
        const start = cleaned.indexOf('{');
        if (start < 0) return null;
        try { return JSON.parse(cleaned.slice(start)); } catch (ignored) { return null; }
      }
    }
    function showArtifacts(responseText, serverArtifacts = null) {
      const manifest = parseGeminiJson(responseText);
      const artifacts = Array.isArray(serverArtifacts) ? serverArtifacts : (manifest && Array.isArray(manifest.artifacts) ? manifest.artifacts : []);
      $('artifacts').innerHTML = '';
      if (!artifacts.length) return;
      const heading = document.createElement('strong');
      heading.textContent = `Artefatti separati (${artifacts.length})`;
      $('artifacts').appendChild(heading);
      const engineLabel=document.createElement('div'); engineLabel.innerHTML='<label>Motore PDF <select id="pdfEngine"><option value="standard">Attuale (ReportLab/Matplotlib)</option><option value="typst">Typst/Lilaq (sperimentale)</option></select></label>'; $('artifacts').appendChild(engineLabel);
      artifacts.forEach((artifact, index) => {
        const card = document.createElement('div');
        card.className = 'artifact-card';
        card.innerHTML = `<strong>${artifact.title || artifact.artifact_type || `Artefatto ${index + 1}`}</strong>`;
        ['pdf', 'pptx', 'docx'].forEach(format => {
          const button = document.createElement('button'); button.className = 'secondary'; button.textContent = `Render ${format.toUpperCase()}`;
          button.addEventListener('click', () => downloadArtifact(artifact, responseText, format, button));
          card.appendChild(button);
        });
        $('artifacts').appendChild(card);
      });
    }
    function buildPrompt() {
      const type = artifact.value;
      const lines = [$('aiRole').value.trim() || 'Agisci come docente di matematica.', `Classe: ${$('classe').value || '[da specificare]'}.`, `Artefatto richiesto: ${type || '[da specificare]'}.`];
      if ($('besDsa').checked) lines.push('Sono presenti studenti BES/DSA.');
      if (type === 'Lezione') { lines.push(`Tipo di lezione: ${$('lessonType').value || '[da specificare]'}.`, `Argomento: ${$('lessonTopic').value || '[da specificare]'}.`); }
      if (type === 'Esercizi' || type === 'Verifica sommativa') { lines.push(type === 'Verifica sommativa' ? 'Genera una verifica sommativa coerente come unico oggetto valutativo.' : 'Genera gli esercizi richiesti come unità autonome.'); document.querySelectorAll('#exerciseRows tr').forEach(row => { const v = rowValues(row); if (v.topic || v.det || v.count) lines.push(`Esercizio ${row.dataset.row}: tipo ${v.det || '[da scegliere]'}; numero ${v.count || '[da scegliere]'}; argomento ${v.topic || '[da specificare]'}; difficoltà ${v.ded || '[da scegliere]'}; livello cognitivo ${v.dbl || '[da scegliere]'}; soluzione ${v.des || '[da scegliere]'}; grafico ${v.dgt || '[da scegliere]'}.`); }); }
      lines.push('Rispetta le direttive che sono state inviate con il prompt');
      return lines.join('\n');
    }
    async function init() {
      try {
        const [catalogResponse, chatbotResponse, schoolResponse] = await Promise.all([fetch('/api/catalogs'), fetch('/api/chatbot', { cache: 'no-store' }), fetch('/api/schools', { cache: 'no-store' })]);
        if (!catalogResponse.ok || !chatbotResponse.ok || !schoolResponse.ok) throw new Error('impostazioni non disponibili');
        const apiCatalogs = await catalogResponse.json();
        const chatbotSettings = await chatbotResponse.json();
        schools = await schoolResponse.json();
        const schoolTypes = [...new Set(schools.map(school => school.TipoScuola))];
        schoolType.innerHTML = '<option value="">Seleziona tipo scuola</option>' + schoolTypes.map(type => `<option value="${type}">${type}</option>`).join('');
        schoolType.disabled = !schoolTypes.length;
        schoolType.addEventListener('change', updateSchoolAddresses);
        chatbot.innerHTML = chatbotSettings.options.map(value => `<option value="${value}">${value}</option>`).join('');
        chatbot.value = chatbotSettings.chatbot;
        chatbot.disabled = false;
        chatbot.addEventListener('change', async () => {
          const previous = chatbotSettings.chatbot;
          const selected = chatbot.value;
          if (!confirm(`Confermi l'utilizzo di ${selected}?`)) { chatbot.value = previous; return; }
          const response = await fetch('/api/chatbot', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ chatbot: selected }) });
          if (!response.ok) { chatbot.value = previous; alert('Impossibile salvare il chatbot selezionato.'); return; }
          chatbotSettings.chatbot = selected;
        });
        catalogs = Object.fromEntries(Object.entries(apiCatalogs).map(([group, items]) => [group, items.map(item => [item.code, item.title])]));
        buildRows();
        updateActionState();
        artifact.addEventListener('change', updateVisibility);
        document.querySelectorAll('input, select').forEach(element => {
          element.addEventListener('input', updateActionState);
          element.addEventListener('change', updateActionState);
        });
        $('besDsa').addEventListener('change', () => {
          if (!$('promptText').value) return;
          const lines = $('promptText').value.split('\n').filter(line => line !== 'Sono presenti studenti BES/DSA.');
          if ($('besDsa').checked) lines.push('Sono presenti studenti BES/DSA.');
          $('promptText').value = lines.join('\n');
          $('prepare').click();
        });
        $('prepare').addEventListener('click', async () => {
          const prompt = buildPrompt();
          const response = await fetch('/api/compose', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(requestPayload(prompt)) });
          if (!response.ok) { alert('Impossibile preparare la richiesta.'); return; }
          const composed = await response.json();
          $('promptText').value = composed.prompt;
          $('systemText').value = composed.system_instruction;
          $('promptOutput').classList.add('visible');
          $('promptText').focus();
        });
        $('sendGemini').addEventListener('click', async () => {
          $('sendGemini').disabled = true;
          const prompt = $('promptText').value || buildPrompt();
          $('cacheStatus').textContent=$('useCache').checked ? 'Preparazione o riuso cache in corso...' : 'Cache esplicita disattivata.';
          $('geminiResponse').value = $('generateImages').checked ? 'Generazione lezione e immagini in corso; attendere...' : 'Invio in corso...';
          $('validationProblems').classList.remove('visible');
          $('validationProblems').textContent = '';
          try {
            const response = await fetch('/api/gemini', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(requestPayload(prompt)) });
            const result = await response.json();
            const cache=result.cache_info;
            $('cacheStatus').textContent=cache?.state==='created'||cache?.state==='reused'
              ? `Cache ${cache.state==='created'?'creata':'riutilizzata'}, scadenza ${new Date(cache.expires).toLocaleString('it-IT')}. Token da cache: ${cache.cached_tokens ?? 'non riportati'}.`
              : ($('useCache').checked ? 'Cache/generazione non completata. Nessun tentativo automatico senza cache.' : 'Cache esplicita disattivata.');
            $('geminiResponse').value = result.response || result.error || 'Nessuna risposta ricevuta.';
            const problems = result.validation_problems || [];
            if (problems.length || !response.ok) {
              $('validationProblems').textContent = 'Avvisi: puoi comunque esportare gli artefatti disponibili.\n- ' + (problems.length ? problems.join('\n- ') : (result.error || 'Errore HTTP ' + response.status));
              $('validationProblems').classList.add('visible');
            }
            if (result.response || result.artifacts) showArtifacts(result.response || '', result.artifacts || []);
          } catch (error) {
            $('cacheStatus').textContent='Richiesta non completata; verificare il messaggio di errore.';
            $('geminiResponse').value = 'Risposta tecnica non disponibile: ' + error.message;
            $('validationProblems').textContent = 'Problema di comunicazione con il server locale o Gemini:\n- ' + error.message;
            $('validationProblems').classList.add('visible');
          } finally {
            $('sendGemini').disabled = false;
          }
        });
        $('copyPrompt').addEventListener('click', async () => { await navigator.clipboard.writeText($('promptText').value); $('copied').classList.add('show'); setTimeout(() => $('copied').classList.remove('show'), 1600); });
        $('exit').addEventListener('click', async () => {
          if (!confirm('Vuoi uscire dal programma?')) return;
          await fetch('/api/shutdown', { method: 'POST' });
          window.close();
          document.body.innerHTML = '<main class="shell"><h1>Programma chiuso</h1><p class="intro">Il server locale e stato arrestato.</p></main>';
        });
      } catch (error) {
        document.querySelector('.status').textContent = 'Errore caricamento direttive';
        console.error(error);
      }
    }
    init();
  
