// Direct Google Forms creation, shared by composer and history.
function appendDirectGoogleControls(card, artifact, responseText) {
  const panel = document.createElement('div');
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  const connect = document.createElement('button'); connect.className = 'secondary'; connect.textContent = 'Collega Google';
  const create = document.createElement('button'); create.textContent = 'Crea modulo Google'; create.disabled = true;
  const disconnect = document.createElement('button'); disconnect.className = 'secondary'; disconnect.textContent = 'Scollega Google'; disconnect.hidden = true;
  const links = document.createElement('div');
  const help = document.createElement('a'); help.href = '/google-connect.html'; help.target = '_blank'; help.rel = 'noopener'; help.textContent = 'Configurazione iniziale del collegamento Google';
  panel.append(connect, create, disconnect, status, links, help); card.appendChild(panel);
  let csrf = '', connected = false, busy = false, popup = null, poll = null;
  async function refresh() {
    try {
      const response = await fetch('/api/google/status', {cache: 'no-store'});
      const data = await response.json();
      if (!response.ok) throw Error(data.error || 'Collegamento Google non disponibile.');
      csrf = data.csrf; connected = data.connected;
      create.disabled = busy || !connected; disconnect.hidden = !connected;
      connect.hidden = connected; connect.disabled = busy || !data.configured;
      if (busy && data.progress) status.textContent = data.progress;
      if (!busy) status.textContent = connected ? 'Google collegato. Accesso limitato ai file creati dal programma.' : data.configured ? 'Collega il tuo account per creare il modulo.' : `Credenziale Google non trovata. Salva google_oauth_client.json in: ${data.client_file}`;
      if (connected && poll) {clearInterval(poll); poll = null;}
    } catch (error) {status.textContent = error.message; create.disabled = true;}
  }
  async function post(path, body = {}) {
    // Several quiz cards share one cookie: get its current CSRF token.
    const sessionResponse = await fetch('/api/google/status', {cache: 'no-store'});
    const sessionData = await sessionResponse.json();
    if (!sessionResponse.ok) throw Error(sessionData.error || 'Sessione Google non disponibile.');
    csrf = sessionData.csrf;
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Operazione Google non riuscita.');
    return data;
  }
  connect.addEventListener('click', async () => {
    popup = window.open('about:blank', 'agente-google-auth', 'width=620,height=740');
    if (!popup) {status.textContent = 'Consenti le finestre popup per collegare Google.'; return;}
    try {
      const result = await post('/api/google/connect');
      popup.location.href = result.authorization_url;
      if (poll) clearInterval(poll);
      let attempts = 0;
      poll = setInterval(() => {
        if (++attempts > 300 || !panel.isConnected) {clearInterval(poll); poll = null; return;}
        refresh();
      }, 2000);
    } catch (error) {popup.close(); status.textContent = error.message;}
  });
  create.addEventListener('click', async () => {
    busy = true; create.disabled = true; disconnect.disabled = true; links.replaceChildren();
    status.textContent = 'Creazione del modulo Google in corso...';
    const progressTimer = setInterval(refresh, 2000);
    try {
      const result = await post('/api/google/create', {response: responseText, artifact_id: artifact.artifact_id});
      status.textContent = result.reused ? 'Modulo gia creato: puoi aprirlo dai link.' : 'Modulo Google creato.';
      if (!result.reused && result.timings?.total_seconds != null) status.textContent += ` Tempo: ${Math.round(result.timings.total_seconds)} secondi.`;
      if (!result.reused && result.timings) {
        const details = document.createElement('details');
        const summary = document.createElement('summary'); summary.textContent = 'Dettaglio dei tempi';
        const breakdown = document.createElement('p');
        const phases = [['Preparazione', 'preparation_seconds'], ['Caricamento immagini', 'images_seconds'], ['Inserimento domande', 'import_seconds'], ['Pubblicazione', 'publish_seconds'], ['Pulizia immagini', 'cleanup_seconds']];
        breakdown.textContent = phases.filter(([, key]) => result.timings[key] != null).map(([label, key]) => `${label}: ${Math.round(result.timings[key])} s`).join(' ? ');
        if (result.timings.unique_images != null) breakdown.textContent += ` ? Immagini: ${result.timings.unique_images}`;
        details.append(summary, breakdown); links.appendChild(details);
      }
      if (result.warnings?.length) status.textContent += ' ' + result.warnings.join(' ');
      for (const [label, url] of [['Apri il modulo da modificare', result.edit_url], ['Apri il modulo da compilare', result.response_url]]) {
        const link = document.createElement('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener'; link.textContent = label; link.style.marginRight = '18px'; links.appendChild(link);
      }
    } catch (error) {status.textContent = error.message;}
    finally {clearInterval(progressTimer); busy = false; create.disabled = !connected; disconnect.disabled = false;}
  });
  disconnect.addEventListener('click', async () => {
    try {await post('/api/google/disconnect'); links.replaceChildren(); await refresh();}
    catch (error) {status.textContent = error.message;}
  });
  const listener = event => {
    if (!panel.isConnected) {window.removeEventListener('message', listener); return;}
    if (event.origin === location.origin && event.source === popup && event.data?.type === 'google-connected') refresh();
  };
  window.addEventListener('message', listener);
  refresh();
}
