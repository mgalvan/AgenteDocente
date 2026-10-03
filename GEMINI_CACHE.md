# Cache opzionale delle direttive

Nel compositore attivare Riutilizza direttive con cache Gemini. Default spento.
Durata nuove cache: 5, 15, 30 o 60 minuti. Si conserva l'intera system instruction
selezionata dal routing: per L1 include comuni, lezioni, DT1 e opzioni applicabili.
Il prompt specifico rimane fuori dalla cache; lo schema strutturato viene inviato
in ogni generazione. Non e una memoria delle lezioni precedenti.

La firma include direttive esatte, modello, schema, account e durata. Se cambia
uno di questi elementi viene creata una cache diversa. Le vecchie cache non si
riusano ma restano su Google fino alla scadenza: non vengono cancellate subito.
La durata non viene prolungata dal riuso. Disattivare evita creazione e riuso,
ma non cancella cache esistenti. L'indice locale salva hash, nome e scadenza in
gemini_cache_index.json, non la chiave API o il testo delle direttive.

Costi: creazione, utilizzo e conservazione secondo le tariffe Google; il risparmio
netto dipende dal volume di richieste. Google impone una soglia minima di token e
la disponibilita dipende dal modello. Se rifiuta la cache o una cache remota e
stata rimossa, la richiesta mostra l'errore senza rigenerazione automatica.

Interfaccia: cache creata/riutilizzata, scadenza e cached_content_token_count se
riportato dal servizio. Test con provider simulato, nessuna cache a pagamento
creata durante l'implementazione. La prova reale rimane da eseguire dall'utente.
