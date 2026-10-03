import json
import unittest
from pathlib import Path
import pymupdf
from test_flat_schema import sample
from models_api_flat import FlatResponse
from response_recovery import inspect_response
from renderers import artifact_file
from typst_renderer import export


def example():
    data=sample();data['texts'][0]['segments']=[{'kind':'text','value':'Volume: '},{'kind':'formula','value':'V'}]
    g=data['graphs'][0];g.update(kind='geometry_2d',expression='',viewport={'x_min':-1.,'x_max':12.,'y_min':-1.,'y_max':12.},polygons=[{'label':str(side),'vertices':[{'x':0.,'y':0.},{'x':side,'y':0.},{'x':side,'y':side},{'x':0.,'y':side}]} for side in (10.,10.5)])
    data['artifacts'][0]['containers'][0]['blocks']=data['artifacts'][0]['containers'][0]['blocks'][:1]+[{'id':'bg','kind':'graph','ref':'g1'}]
    return data


class GeometryTests(unittest.TestCase):
    def test_curve_labels_without_points(self):
        data=sample();g=data['graphs'][0]
        g.update(expression='2^x; (1/2)^x', labels=['Crescente','Decrescente'])
        FlatResponse.model_validate(data)
        g['labels']=['Una sola']
        with self.assertRaises(ValueError):FlatResponse.model_validate(data)

    def test_inline_and_geometry(self):
        data=example();FlatResponse.model_validate(data)
        artifacts,warnings=inspect_response(json.dumps(data));self.assertFalse(warnings)
        self.assertEqual(artifacts[0]['sections'][0]['blocks'][0]['segments'][1]['latex'],'V')
        for index,result in enumerate((artifact_file(artifacts[0],'pdf'),export(artifacts[0]))):
            with pymupdf.open(stream=result[0],filetype='pdf') as doc:
                text=''.join(p.get_text() for p in doc)
                self.assertNotIn('non disponibile',text)
                if index==1:self.assertIn('10.5',text)
                else:self.assertGreater(sum(len(p.get_images()) for p in doc),0)
    def test_invalid_polygon(self):
        data=example();data['graphs'][0]['polygons'][0]['vertices']=[]
        with self.assertRaises(ValueError):FlatResponse.model_validate(data)
    def test_polygon_requires_geometry(self):
        data=example();data['graphs'][0]['kind']='function_2d';data['graphs'][0]['expression']='x'
        with self.assertRaises(ValueError):FlatResponse.model_validate(data)

if __name__=='__main__':unittest.main()
