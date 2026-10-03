import io,unittest,hashlib
from docx import Document
from verification_template import FILE, compile_test

class TemplateTests(unittest.TestCase):
    def test_fills_and_preserves_original(self):
        original=FILE.read_bytes()
        cell=lambda s:{'segments':[{'type':'text','content':s}]}
        artifact={'title':'Prova','sections':[{'title':'Esercizio 1','blocks':[{'block_type':'text','content':'Risolvi x+1=2.'},{'block_type':'table','headers':[cell('Esercizio'),cell('Punteggio massimo')],'rows':[[cell('1'),cell('100')],[cell('TOTALE'),cell('100')]]}]}]}
        content,_,_=compile_test(artifact)
        self.assertEqual(FILE.read_bytes(),original)
        doc=Document(io.BytesIO(content));xml=doc._element.xml
        self.assertNotIn('{{PUNTI',xml);self.assertNotIn('{{INIZIO',xml)
        self.assertIn('Risolvi x+1=2.',xml);self.assertIn('w:type="page"',xml)
        artifact['sections'][0]['blocks'][1]['rows'][0][1]=cell('90')
        with self.assertRaises(ValueError):compile_test(artifact)
