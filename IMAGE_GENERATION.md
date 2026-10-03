# Immagini AI opzionali

Attivare Genera immagini AI prima di inviare a Gemini. Default disattivato.
Il limite predefinito e 3 immagini nuove, impostabile tra 1 e 10. Ogni immagine
richiede una chiamata aggiuntiva a pagamento; nessun retry automatico.
Il limite riguarda il numero di chiamate, non un budget monetario.

Si usa GEMINI_API_KEY e il modello gemini-2.5-flash-image, modificabile tramite
GEMINI_IMAGE_MODEL. Servono accesso e fatturazione abilitati per quel modello.
Si generano solo generated_images richiamate dagli artefatti. provided_images
richiede ancora risorse fornite dall utente e non viene generato automaticamente.

PNG salvati in generated_assets, chiave derivata da modello e descrizione.
Descrizioni identiche riutilizzano lo stesso file tra documenti e richieste.
Esportazione e cronologia non avviano chiamate AI. Con flag disattivato nessuna
nuova generazione; i file gia salvati restano disponibili. Gli errori immagini
vengono segnalati senza scartare la lezione. Non viene modificato il JSON Gemini.

Verifiche locali con provider simulato: cache, limite, fallimento senza retry,
PDF standard e Typst, DOCX e PPTX. Nessuna prova API a pagamento eseguita.
