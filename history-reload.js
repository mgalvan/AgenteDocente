/* Old history entries contain only composed text; new entries retain form data. */
function historyRequest(entry) {
  if (entry.request_data) return entry.request_data;
  const prompt = entry.prompt || '';
  const field = label => prompt.match(new RegExp('^' + label + ': (.*)\\.$', 'm'))?.[1] || '';
  const school = prompt.match(/^Scuola: (.*); indirizzo: (.*)\.$/m);
  const rows = [...prompt.matchAll(/^Esercizio \d+: tipo (.*?); numero (.*?); argomento (.*?); difficoltà (.*?); livello cognitivo (.*?); soluzione (.*?)(?:; grafico (.*?))?\.$/gm)]
    .map(m => Object.fromEntries(['det','count','topic','ded','dbl','des','dgt'].map((key,i) => [key,m[i+1] || ''])));
  const gameCode = prompt.match(/^Tipo di gioco: G(\d+)\b/m)?.[1];
  const parameters = Object.fromEntries([...prompt.matchAll(/^(PAR\d+) \([^\n]*?\): ([^\n]*)/gm)].map(m => [m[1],m[2]]));
  if (field('Artefatto richiesto') === 'Giochi') {
    for (const m of prompt.matchAll(/^Esercizio \d+: tipo (.*?); argomento (.*?); difficoltà (.*?); livello cognitivo (.*?); soluzioni (DES\d+)(?:; grafico (DGT\d+))?\.?$/gm)) {
      rows.push({det:m[1],topic:m[2],ded:m[3],dbl:m[4],des:m[5],dgt:m[6] || ''});
    }
  }
  return {artifact: field('Artefatto richiesto'), classe: field('Classe'),
    lesson_type: field('Tipo di lezione'), lesson_topic: field('Argomento'),
    ai_role: prompt.split('\n')[0], school_type: school?.[1] || '', school_address: school?.[2] || '',
    bes_dsa: prompt.includes('Sono presenti studenti BES/DSA.'), rows,
    game_type: entry.game_type || (gameCode ? 'DGM'+gameCode : ''), game_parameters: entry.game_parameters || parameters};
}

async function restoreHistoryPrompt() {
  const id = new URLSearchParams(location.search).get('reload');
  if (!id) return;
  try {
    const response = await fetch('/api/history', {cache:'no-store'});
    if (!response.ok) throw Error('Cronologia non disponibile.');
    const entry = (await response.json()).find(item => item.id === id);
    if (!entry) throw Error('La richiesta non è più presente nella cronologia.');
    const data = historyRequest(entry);
    const set = (id, value) => { if (value !== undefined) $(id).value = value; };
    set('artifact',data.artifact); set('classe',data.classe);
    set('lessonType',data.lesson_type); set('lessonTopic',data.lesson_topic);
    set('aiRole',data.ai_role); set('schoolType',data.school_type);
    updateSchoolAddresses(); set('schoolAddress',data.school_address);
    for (const [id,key] of [['besDsa','bes_dsa'],['useCache','use_cache'],['generateImages','generate_images']]) {
      if (data[key] !== undefined) $(id).checked = data[key] === true;
    }
    set('cacheMinutes',data.cache_minutes); set('imageLimit',data.image_limit);
    if (data.artifact === 'Giochi') {
      set('gameType',data.game_type); showGame();
      for (const control of document.querySelectorAll('#gameParameters [data-parameter]')) {
        control.value = data.game_parameters?.[control.dataset.parameter] || '';
        control.dispatchEvent(new Event('input'));
      }
      document.querySelectorAll('#gameExercises tbody tr').forEach((row,i) => {
        row.querySelectorAll('[data-key]').forEach(el => el.value = data.rows?.[i]?.[el.dataset.key] || '');
      });
    } else {
      document.querySelectorAll('#exerciseRows tr').forEach((row,i) => {
        for (const key of ['det','count','topic','ded','dbl','des','dgt']) row.querySelector('.'+key).value = data.rows?.[i]?.[key] || '';
      });
    }
    updateVisibility();
    const notice = document.createElement('p');
    notice.className = 'helper'; notice.setAttribute('role','status');
    notice.textContent = $('prepare').disabled
      ? 'Prompt ricaricato. Controlla e completa i campi mancanti prima di prepararlo.'
      : 'Prompt ricaricato dalla cronologia. Puoi modificare i campi e premere Prepara prompt AI.';
    $('prepare').closest('.actions').before(notice);
    history.replaceState(null,'',location.pathname);
  } catch (error) { alert('Impossibile ricaricare il prompt: '+error.message); }
}
