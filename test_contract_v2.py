import copy
import json
import unittest
import pymupdf
from models_api_flat import FlatResponse
from response_recovery import inspect_response
from test_flat_schema import sample
from renderers import artifact_file
from typst_renderer import export


def example():
    data=sample()
    cell={'segments':[{'kind':'text','value':'Area rettangolo: '},{'kind':'formula','value':'A_1=1\\cdot 1=1'}]}
    data['lists']=[{'id':'l1','items':[cell]}]
    data['tables']=[{'id':'tab1','headers':[{'segments':[{'kind':'text','value':'Risultato'}]}],'rows':[[cell]]}]
    data['artifacts'][0]['containers'][0]['blocks']=[{'id':'b1','kind':'list','ref':'l1'},{'id':'b2','kind':'table','ref':'tab1'}]
    return data


class ContractV2Tests(unittest.TestCase):
    def test_direct_content_and_reject_ids(self):
        data=example();FlatResponse.model_validate(data)
        for target in ('items','rows'):
            bad=copy.deepcopy(data)
            if target=='items':bad['lists'][0]['items']=['missing_id']
            else:bad['tables'][0]['rows']=[['missing_id']]
            with self.assertRaises(ValueError):FlatResponse.model_validate(bad)

    def test_old_contract_rejected(self):
        data=example();data['contract_version']='setupgemma_flat_1.0'
        artifacts,warnings=inspect_response(json.dumps(data))
        self.assertEqual(artifacts,[]);self.assertTrue(warnings)

    def test_same_content_both_pdf_backends(self):
        data=example();snapshot=copy.deepcopy(data)
        artifacts,warnings=inspect_response(json.dumps(data))
        self.assertFalse(warnings);self.assertEqual(data,snapshot)
        for result in (artifact_file(artifacts[0],'pdf'),export(artifacts[0])):
            with pymupdf.open(stream=result[0],filetype='pdf') as doc:
                text=''.join(p.get_text() for p in doc)
                self.assertIn('Area rettangolo:',text)
                self.assertNotIn('non disponibile',text)
                self.assertNotIn('non visualizzabile',text)


if __name__=='__main__':unittest.main()
