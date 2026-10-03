"""User DOCX template and immutable generated game handouts."""
import io
import json
import re
import uuid
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from docx import Document

ROOT = Path(__file__).resolve().parent
FILE = ROOT / 'DGM01_template.docx'
STORE = ROOT / 'game_documents'
MAX_SIZE = 10*1024*1024
MARKERS = ('TITOLO_GIOCO', 'Regolamento', 'PAR02', 'PAR01')


def document(content):
    if not content or len(content)>MAX_SIZE: raise ValueError('Modello DOCX: massimo 10 MB.')
    try:
        with ZipFile(io.BytesIO(content)) as z:
            if sum(x.file_size for x in z.infolist())>50*1024*1024: raise ValueError('Modello troppo grande.')
        doc=Document(io.BytesIO(content))
    except (BadZipFile, KeyError) as e: raise ValueError('Documento DOCX non valido.') from e
    text='\n'.join(''.join(p.itertext()) for p in doc._element.body.xpath('.//w:p'))
    for marker in MARKERS:
        if marker not in text: raise ValueError('Marcatore mancante: '+marker)
    return doc


def save(content, name):
    document(content)
    temp=FILE.with_suffix('.tmp');temp.write_bytes(content);temp.replace(FILE)
    FILE.with_suffix('.json').write_text(json.dumps({'name':name},ensure_ascii=False),encoding='utf8')
    return status()


def status():
    if not FILE.exists(): return {'configured':False}
    try: name=json.loads(FILE.with_suffix('.json').read_text(encoding='utf8'))['name']
    except (OSError,ValueError,KeyError): name=FILE.name
    return {'configured':True,'name':name}


def create(parameters, directives):
    if not FILE.exists(): raise ValueError('Caricare il modello Word del gioco G01.')
    first=next(d for d in directives if d['Gruppo']=='DGM01' and d['Codice']=='DGM0101')
    values={'TITOLO_GIOCO':first['Titolo'],'Regolamento':first['Direttiva completa'],'PAR01':parameters['PAR01'],'PAR02':parameters['PAR02']}
    doc=document(FILE.read_bytes())
    template_text='\n'.join(''.join(n.text or '' for n in p.xpath('.//w:t')) for p in doc._element.body.xpath('.//w:p'))
    # Prefer explicit placeholders so labels such as "Regolamento:" stay intact.
    bare_markers=[marker for marker in MARKERS if '{{'+marker+'}}' not in template_text]
    pattern=re.compile(r'\{\{(?:'+'|'.join(MARKERS)+r')\}\}' + (r'|\b(?:'+'|'.join(bare_markers)+r')\b' if bare_markers else ''))
    for p in doc._element.body.xpath('.//w:p'):
        nodes=p.xpath('.//w:t');text=''.join(n.text or '' for n in nodes)
        for match in reversed(list(pattern.finditer(text))):
            value=values[match[0].strip('{}')];offset=0
            for node in nodes:
                old=node.text or '';lo=max(0,match.start()-offset);hi=min(len(old),match.end()-offset)
                if lo<hi:node.text=old[:lo]+(value if offset<=match.start()<offset+len(old) else '')+old[hi:]
                offset+=len(old)
    STORE.mkdir(exist_ok=True);identifier=uuid.uuid4().hex
    doc.save(STORE/(identifier+'.docx'))
    return {'artifact_id':'game-template-'+identifier,'title':first['Titolo']+' - Regolamento','formats':['docx']}


def download(identifier):
    if not re.fullmatch(r'game-template-[0-9a-f]{32}',identifier): raise ValueError('Documento non valido.')
    path=STORE/(identifier.removeprefix('game-template-')+'.docx')
    if not path.exists(): raise ValueError('Documento del gioco non disponibile.')
    return path.read_bytes(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'G01-Regolamento.docx'
