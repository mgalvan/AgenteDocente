const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
vm.runInThisContext(fs.readFileSync('history-reload.js','utf8'));

const old = historyRequest({prompt: `Agisci come docente di matematica.
Scuola: Liceo; indirizzo: Scientifico.
Classe: 2.
Artefatto richiesto: Verifica sommativa.
Sono presenti studenti BES/DSA.
Esercizio 1: tipo DET02; numero 2; argomento Monomi; prodotti e potenze; difficoltà DED02; livello cognitivo DBL03; soluzione DES04; grafico DGT01.
Esercizio 2: tipo DET01; numero 1; argomento Equazioni; difficoltà DED01; livello cognitivo DBL02; soluzione DES01.`});
assert.equal(old.classe,'2');
assert.equal(old.school_address,'Scientifico');
assert.equal(old.bes_dsa,true);
assert.equal(old.rows.length,2);
assert.equal(old.rows[0].topic,'Monomi; prodotti e potenze');
assert.equal(old.rows[0].dgt,'DGT01');
assert.equal(old.rows[1].des,'DES01');
assert.equal(old.rows[1].dgt,'');
const lesson = historyRequest({prompt:'Classe: 3.\nArtefatto richiesto: Lezione.\nTipo di lezione: L2.\nArgomento: Derivate.'});
assert.equal(lesson.lesson_type,'L2');
assert.equal(lesson.lesson_topic,'Derivate');
const game = historyRequest({prompt:'Artefatto richiesto: Giochi.\nTipo di gioco: G01 - Gioco\nPAR01 (argomento): Equazioni\nPAR02 (numero esercizi): 1\nEsercizio 1: tipo DET02; argomento Equazioni; difficoltà DED02; livello cognitivo DBL03; soluzioni DES04.'});
assert.equal(game.game_type,'DGM01');
assert.equal(game.game_parameters.PAR02,'1');
assert.equal(game.rows[0].des,'DES04');
const saved = {...old, use_cache:true, cache_minutes:20, generate_images:true, image_limit:2};
assert.deepEqual(historyRequest({request_data:saved}),saved);

// Check that the actual saved requests can recover their exercise rows.
for (const entry of JSON.parse(fs.readFileSync('history.json','utf8'))) {
  const count = (entry.prompt || '').match(/^Esercizio \d+: tipo .*; numero /gm)?.length || 0;
  if (count && !entry.request_data) assert.equal(historyRequest(entry).rows.length,count);
}
console.log('Recupero cronologia: verifica, lezione, gioco, parametri salvati e richieste esistenti OK.');
