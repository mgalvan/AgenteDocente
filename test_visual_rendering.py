import io
import unittest
import zipfile
from pathlib import Path
from visual_assets import formula,graph,evaluate_expression,Asset
from image_renderers import parts
from renderers import artifact_file
import numpy as np


def specimen():
    return {'artifact_id':'visual_test','artifact_type':'exercise_sheet','audience':'teacher','format':'pdf','filename_hint':'visual_test.pdf','title':'Formule e grafici',
    'sections':[{'title':'Notazioni matematiche','blocks':[
      {'block_type':'text','segments':[{'type':'text','content':'Una frazione inline: '},{'type':'formula','latex':r'\frac{a}{b}','alt_text':'a su b'},{'type':'text','content':'. Il testo rimane modificabile.'}]},
      {'block_type':'formula','latex':r'\begin{cases}2x+y=3\\x-y=0\end{cases}','alt_text':'Sistema'},
      {'block_type':'formula','latex':r'\begin{pmatrix}1&2&3\\4&5&6\\7&8&9\end{pmatrix}','alt_text':'Matrice'},
      {'block_type':'formula','latex':r'\begin{vmatrix}a&b\\c&d\end{vmatrix}=ad-bc','alt_text':'Determinante'},
      {'block_type':'list','items':[{'segments':[{'type':'text','content':'Integrale: '},{'type':'formula','latex':r'\int_0^1 x^2\,dx','alt_text':'Integrale'}]},r'Limite: $\lim_{x\to0}\frac{\sin x}{x}=1$']},
      {'block_type':'table','headers':['Tipo','Formula'],'rows':[['Somma',{'segments':[{'type':'formula','latex':r'\sum_{k=1}^n k=\frac{n(n+1)}{2}','alt_text':'Somma'}]}],['Radicale',{'segments':[{'type':'formula','latex':r'\sqrt{x^2+1}','alt_text':'Radicale'}]}]]}
    ]},{'title':'Grafico cartesiano','blocks':[{'block_type':'graph','kind':'function_2d','expression':'sin(x)','viewport':{'x_min':-6.3,'x_max':6.3,'y_min':-1.2,'y_max':1.2},'x_label':'x','y_label':'sin(x)','alt_text':'Seno'}]}]}


class VisualTests(unittest.TestCase):
    def test_common_notations(self):
        for source in [r'\frac{a}{b}',r'\begin{cases}x+y=1\\x-y=0\end{cases}',r'\begin{vmatrix}a&b\\c&d\end{vmatrix}',r'\int_0^1 x\,dx']:
            asset=formula(source)
            self.assertTrue(asset.path.read_bytes().startswith(b'\x89PNG'))
            self.assertGreater(asset.height,0)

    def test_typed_and_legacy_inline(self):
        self.assertTrue(any(isinstance(p,Asset) for p in parts(r'Calcola $x^2$ ora')))
        self.assertTrue(any(isinstance(p,Asset) for p in parts({'segments':[{'type':'formula','latex':'x^2'}]})))

    def test_expression_is_not_python_execution(self):
        x=np.array([0.,1.])
        np.testing.assert_allclose(evaluate_expression('x^2+1',x),[1,2])
        for bad in ["__import__('os').system('x')",'x.__class__','[x for x in x]','2**10000']:
            with self.assertRaises((ValueError,SyntaxError)):evaluate_expression(bad,x)

    def test_all_exports_contain_raster_images(self):
        for fmt in ('pdf','pptx','docx'):
            data,_,_=artifact_file(specimen(),fmt,best_effort=True)
            if fmt=='pdf':
                import fitz
                doc=fitz.open(stream=data,filetype='pdf')
                self.assertGreater(sum(len(p.get_images()) for p in doc),5)
                self.assertNotIn('Formula non visualizzabile',''.join(p.get_text() for p in doc))
                doc.close()
            else:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    self.assertGreater(len([n for n in archive.namelist() if '/media/' in n]),5)


if __name__=='__main__':unittest.main()
