# Confronto motori PDF

Nel compositore e nella cronologia, scegliere **Motore PDF** prima di premere
Render PDF. La selezione non richiama Gemini. I due motori ricevono lo stesso
artefatto prodotto da inspect_response, dopo validazione e recupero.

- Attuale: ReportLab, Matplotlib e formule PNG.
- Typst/Lilaq (sperimentale): impaginazione Typst 0.15.0, grafici vettoriali
  Lilaq 0.6.0, formule MathJax SVG. Non converte LaTeX in sintassi Typst.

DOCX e PPTX continuano a usare il motore attuale. Nessun cambio di schema,
direttive o contenuto generato. Typst conserva due documenti separati e non
aggiunge grafici mancanti. I PDF Typst hanno suffisso -typst.pdf.

Installazione: pip install -r requirements.txt e npm ci --prefix renderer_tools.
Il primo utilizzo di Typst richiede rete per scaricare Lilaq e le dipendenze
nella cartella renderer_tools/typst-packages; poi riutilizza i pacchetti locali.
Ogni compilazione usa una directory temporanea separata. I testi sono passati
come stringhe, non interpretati come codice Typst; le espressioni grafiche sono
valutate dal parser AST esistente. Un errore di compilazione e mostrato al client,
senza retry LLM, senza cambio automatico di motore e senza eliminare il grafico.
Singoli dati non renderizzabili conservano il segnaposto esplicito.

Il PDF e vettoriale nei campioni verificati, ma non viene certificato PDF/A.
Il font del testo e Libertinus Serif; la matematica usa i glifi MathJax.
La qualita editoriale va confrontata sui propri contenuti: questa e una seconda
implementazione sperimentale, non una garanzia di resa editoriale universale.

Test: python -m unittest test_typst_renderer
