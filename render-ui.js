// Shared download feedback for composer and history.
let renderInProgress = false;
let lastRenderUrl = null;
async function downloadArtifact(artifact, responseText, format, button) {
  if (renderInProgress) return;
  renderInProgress = true;
  const engineSelect = document.getElementById('pdfEngine');
  const engine = format === 'pdf' ? engineSelect?.value || 'standard' : 'standard';
  const engineName = engine === 'typst' ? 'Typst/Lilaq' : 'motore attuale';
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
  status.textContent = `Generazione ${format.toUpperCase()} in corso: ${engineName} sta lavorando. Attendi il download.`;
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
    status.textContent = `${format.toUpperCase()} generato con ${engineName}. Download avviato.`;
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
