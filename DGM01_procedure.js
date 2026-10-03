/* DGM01: dynamic exercise rows, independent of the ordinary exercise form. */
window.DGM01Procedure = {
  mount(host, parameter, catalogs, changed, topicParameter) {
    host.replaceChildren();
    if (!parameter) return;
    const title = document.createElement('h3'); title.textContent = 'Esercizi del gioco';
    const heading = document.createElement('div'); heading.className = 'exercise-heading';
    const info = document.createElement('button'); info.type = 'button'; info.className = 'secondary'; info.textContent = 'INFO';
    info.dataset.matrixInfo = ''; info.setAttribute('aria-haspopup', 'dialog'); info.setAttribute('aria-controls', 'matrixInfo');
    heading.append(title, info);
    const wrap = document.createElement('div'); wrap.className = 'table-wrap';
    const table = document.createElement('table');
    table.innerHTML = '<thead><tr><th>#</th><th>Tipo esercizio</th><th>Difficoltà</th><th>Livello cognitivo</th><th>Soluzioni</th><th>Grafico (opzionale)</th></tr></thead><tbody></tbody>';
    wrap.append(table); host.append(heading, wrap);
    const body = table.tBodies[0];
    const sync = () => {
      const count = Number(parameter.value);
      if (!Number.isSafeInteger(count) || count < 1) { changed(); return; }
      while (body.rows.length > count) body.deleteRow(-1);
      while (body.rows.length < count) {
        const row = body.insertRow(); row.insertCell().textContent = body.rows.length;
        for (const [key, group] of [['det','DET'],['ded','DED'],['dbl','DBL'],['des','DES'],['dgt','DGT']]) {
          const el = document.createElement(group ? 'select' : 'input'); el.dataset.key = key;
          el.setAttribute('aria-label', key+' esercizio '+body.rows.length);
          if (group) { el.add(new Option('Seleziona','')); (catalogs[group] || []).forEach(([code,title]) => el.add(new Option(code+' - '+title,code))); }
          else el.type = 'text';
          el.required = key !== 'dgt'; el.addEventListener('input',changed); el.addEventListener('change',changed);
          row.insertCell().append(el);
        }
      }
      changed();
    };
    parameter.addEventListener('input',sync); sync();
  },
  rows() { return [...document.querySelectorAll('#gameExercises tbody tr')].map(row => Object.fromEntries([...row.querySelectorAll('[data-key]')].map(el => [el.dataset.key,el.value.trim()]))); },
  valid() { return this.rows().length > 0 && [...document.querySelectorAll('#gameExercises input, #gameExercises select')].every(el => el.checkValidity()); }
};
