# Prototipo di contratto piatto

Il prototipo ? in models_api_flat.py e non sostituisce il contratto operativo.
artifacts resta alla radice. Ogni artefatto contiene containers (sezioni per
PDF/DOCX, slide per PPTX) e riferimenti ordinati ai contenuti.
Le raccolte texts, formulas, graphs, images, lists e tables contengono le
risorse identificate. Liste e celle richiamano texts; i segmenti formula
richiamano formulas. Le note del relatore sono riferimenti a texts.

Tutti gli oggetti sono chiusi (extra=forbid), con campi tipizzati e Literal.
Non ci sono union annidate. I model_validator controllano dati per tipo di
grafico, sorgenti immagini, riferimenti esistenti, ID univoci e tabelle rettangolari.
I grafici del prototipo sono limitati a function_2d, scatter e bar_chart.
Le immagini sono descrizioni da generare oppure risorse fornite: nessuna immagine
? stata effettivamente generata dal test.

## Prova reale autorizzata

Una chiamata, Gemini 2.5 Flash, retry disabilitati, thinking_budget=0,
max_output_tokens=1400. Schema accettato: nessun errore di complessit?.
Uso dichiarato dall'API: 135 token prompt, 682 output, 817 totali.
JSON e report originali in flat_schema_probe/response.json e report.json.

La risposta NON supera tutta la validazione: per un'immagine generated Gemini
ha compilato resource_id, che deve essere vuoto. Il JSON ? leggibile; il
problema ? il vincolo fra campi della sorgente immagine. Non sono state fatte
chiamate di correzione. Nel prossimo progetto di contratto occorre eliminare
questa alternativa impropria (ad esempio separando immagini da generare e
risorse fornite), non ignorare l'errore.

Cinque test locali superati: esempio completo, riferimenti/ID, lista/tabella
con matematica, schema senza union e rifiuto dei campi aggiuntivi.
Questo esito dimostra la fattibilit? del formato piatto sul servizio, non la
correttezza universale dei contenuti o la disponibilit? dei renderer.
