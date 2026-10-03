# Contratto attivo setupgemma_flat_2.1

Schema generato da models_api_flat.py e passato a Gemini come response_json_schema,
separatamente da prompt e system instruction. artifacts resta alla radice.
Gemini produce due documenti separati; il programma non duplica contenuti.

Liste: items contiene oggetti con segments. Tabelle: headers e ogni elemento
in rows contengono gli stessi oggetti. Ogni segmento ha kind text/formula e value:
testo diretto oppure LaTeX diretto, senza delimitatori e senza ID.
Esempio: {"segments":[{"kind":"text","value":"Area: "},{"kind":"formula","value":"A=4"}]}.
Tutti i segmenti formula, anche in texts, contengono LaTeX diretto. La raccolta
formulas serve ai blocchi formula autonomi. I riferimenti dei blocks restano invariati.

La versione 1 e i formati annidati precedenti non sono piu accettati.
La cronologia precedente e stata svuotata su richiesta. Non ci sono migrazioni
ne recuperi di contenuti mancanti dai vecchi formati. Gli errori del contratto
attivo vengono mostrati; gli artefatti ancora renderizzabili sono esportabili.

Moduli: models_api_flat.py (struttura), validation.py (contenuto),
response_recovery.py (diagnostica del contratto attivo), flat_adapter.py
(materializzazione), image_renderers.py e typst_renderer.py (esportazione).
renderers.py e soltanto il punto di accesso al motore standard.

Direttive server DAR00 e DAF10 allineate. Non reimportare direttive strutturali
precedenti. Riavviare il server e ricostruire il prompt dopo l'aggiornamento.
Nessuna chiamata di correzione automatica a Gemini.

Verifica: python -m unittest discover
Rigenerazione schema: python models_api_flat.py
Dettagli dei renderer in RENDER_ENGINES.md, grafici in GRAPH_CONTRACT.md.

geometry_2d: polygons contiene label e vertices ordinati x/y, almeno tre distinti
e finiti; chiusura automatica. expression e gli altri array grafici vuoti.
I renderer mantengono la scala geometrica. Nessuna migrazione dei vecchi JSON.
