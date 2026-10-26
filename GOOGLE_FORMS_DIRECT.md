# Creazione diretta Google Moduli

La configurazione guidata ? in `/google-connect.html`. Le schede dei quiz nel compositore e nella cronologia mostrano Collega Google, Crea modulo Google e Scollega Google.

## Server HTTPS / Cloud Run

- Installa requirements.txt (il Dockerfile lo fa durante la build).
- Nel progetto 684501675906 configura un client OAuth **Applicazione web** con redirect `https://SERVIZIO.run.app/api/google/callback`.
- Conserva il JSON in Secret Manager e montalo come `/secrets/google/oauth.json`; concedi al service account del servizio accesso a quel segreto.
- Imposta `GOOGLE_OAUTH_CLIENT_FILE=/secrets/google/oauth.json` e `GOOGLE_OAUTH_REDIRECT_URI=https://SERVIZIO.run.app/api/google/callback`.
- Per questa versione: massimo 1 istanza e tutto il traffico su una revisione. Sessioni, token e risultati sono in memoria per browser, scadono dopo 12 ore di inattivit? e si perdono a ogni riavvio. Non sono salvati nel codice o inviati al browser. Dopo il riavvio ricollega Google; la deduplicazione vale per il collegamento corrente.
- Aggiungi gli account autorizzati in Utenti di test se l'app ? ancora in Testing.
- Mantieni la protezione di accesso al servizio Cloud Run; il collegamento Google autorizza la creazione dei moduli, non protegge gli altri endpoint della webapp.

## Prova locale

Usa `http://localhost:8000` e registra il redirect `http://localhost:8000/api/google/callback`. Il JSON predefinito ? `~/.agentdocente/google_oauth_client.json`, esterno alla cartella pubblica. Per usare un'altra porta configura il redirect esatto.

## Permessi e comportamento

L'unico scope OAuth richiesto ? `https://www.googleapis.com/auth/drive.file`, accettato dalle API Forms e Drive. Il modulo viene creato non pubblicato, popolato con domande, opzioni e punteggi, poi pubblicato. Le immagini sono prima caricate tramite Drive, condivise tramite link per essere importate, quindi rese private rimuovendo quel permesso e cestinate. Se l'importazione fallisce, viene cestinato solo il nuovo modulo. Se la pulizia fallisce, viene mostrato un avviso. Non sono lette liste di documenti di Drive.

Scollega Google revoca il token OAuth e cancella le credenziali dalla sessione. I cookie sono HttpOnly/SameSite=Lax, Secure su HTTPS. Le richieste di creazione/collegamento/revoca richiedono origine e token CSRF. Il callback controlla lo state, monouso e con durata di 10 minuti. I token e i codici OAuth non vengono registrati nei log dell'app.

## Prestazioni dell'esportazione

Le immagini identiche vengono caricate una sola volta. Caricamento e pulizia usano
al massimo quattro connessioni indipendenti, ciascuna con la propria sessione HTTP
e una copia delle credenziali OAuth. Prima di iniziare l'importazione o la pulizia,
il server attende la conclusione di tutti i caricamenti, anche in caso di errore.
Il link pubblico viene verificato prima di richiedere i metadati di fallback.
Le domande sono importate prima singolarmente, per validare la prima domanda,
e poi in gruppi di cinque. Le scritture non sono ripetute dopo un timeout.

Il risultato API include `timings`: secondi di preparazione, caricamento immagini,
inserimento, pubblicazione, pulizia e totale, oltre al numero di immagini uniche.
L'interfaccia mostra il totale e un dettaglio espandibile delle fasi.
I tempi delle fasi parallele sono tempi trascorsi, non la somma dei tempi dei thread.
Le misure non contengono token o contenuti del quiz.


## Download dei feedback video

Nella preparazione seleziona "Prepara feedback video per le risposte errate".
Ogni domanda deve avere passaggi con testo italiano da narrare e formula LaTeX
(facoltativa) da mostrare durante la narrazione. Il materiale generato e la
cronologia offrono "Scarica JSON feedback" e "Genera video feedback (.zip)".
La generazione locale richiede Windows, una voce italiana System.Speech e FFmpeg
nel PATH. La pagina mostra il nome esatto della cartella di destinazione.

Lo ZIP contiene una cartella Feedback_<titolo>_<codice> con un MP4 per domanda,
feedback.json e LEGGIMI.txt. Il codice dipende dal contenuto del quiz e del feedback:
la stessa esportazione mantiene i nomi; quiz diversi non mescolano i video.
Estrai lo ZIP e carica l'intera cartella nel Drive scolastico, mantenendo i nomi
e concedendo l'accesso agli studenti. Questa operazione non associa ancora i link
al modulo: il collegamento dei feedback e un passaggio successivo.


## Collegamento dei video al modulo scolastico

Ogni ZIP include collega_feedback_video.gs. Carica la cartella estratta (incluso
feedback.json) su Drive scolastico. Nell'account scolastico crea un progetto su
https://script.google.com e incolla lo script in Codice.gs. Compila moduloUrl
con il link /forms/d/ID/edit della copia scolastica e cartellaUrl con il link
della cartella che contiene direttamente JSON e MP4. Esegui verificaCollegamenti,
poi collegaVideoFeedback. Non serve pubblicare il progetto come web app.

Lo script controlla titolo del quiz, domande numerate, nomi e tipo dei video;
blocca il collegamento se mancano file o se esistono duplicati. Conserva testo
e URL del feedback precedente e non duplica il link del video nelle riesecuzioni.
Se una scrittura fallisce tenta di ripristinare i feedback gia aggiornati.
I permessi Drive degli studenti devono essere configurati sulla cartella/video.
