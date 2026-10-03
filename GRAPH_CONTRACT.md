# Aree e rettangoli nel contratto grafico

Ogni grafico function_2d accetta due array opzionali, `areas` e `rectangles`.
Nel contratto attivo questi campi possono essere omessi. Non vengono estratti
parametri da alt_text: una descrizione non basta a costruire le figure.

Esempio di campi da aggiungere a un grafico con expression `x^2`:

```json
{
  "areas": [
    {"expression": "x^2", "x_start": 0, "x_end": 2, "baseline": 0}
  ],
  "rectangles": [
    {"expression": "x^2", "x_start": 0, "x_end": 2, "baseline": 0,
     "count": 4, "sample": "midpoint"}
  ]
}
```

Ogni elemento specifica una sola funzione, estremi finiti crescenti e una
baseline orizzontale. Le aree sono colorate tra baseline e funzione.
I rettangoli hanno larghezza uniforme e campionamento `left`, `right` oppure
`midpoint`; count deve essere compreso tra 1 e 500. Le altezze possono essere
negative. Le funzioni devono essere finite nei punti valutati: non si eseguono
calcoli simbolici di integrali impropri o interpretazioni di codice.

Pydantic valida struttura e parametri; il renderer calcola le coordinate
localmente. Lo schema generato viene passato mediante response_json_schema.
La direttiva server DGS00 descrive i campi; la copia precedente e conservata in
contract_backups/graph-before-overlays.json. Nessuna nuova chiamata Gemini e
stata eseguita per questa estensione: accettazione del nuovo schema da parte
del servizio non verificata dal vivo.

Riavviare il server e ricostruire il prompt per usare la direttiva aggiornata.
Riesportare una vecchia risposta non aggiunge parametri mancanti alle figure.
`nEtichette function_2d: con points presenti, labels etichetta i punti; senza points, labels etichetta le curve nello stesso ordine delle espressioni separate da punto e virgola. In entrambi i casi labels puo essere vuoto.

Funzioni a tratti: usare pieces ed expression vuota. Ogni tratto contiene expression, x_start, x_end, start/end (open, closed, none), holes (ascisse escluse interne). I punti isolati pieni restano in points. I buchi sono marcati con cerchi vuoti. Non ricaviamo questi dati da alt_text.
