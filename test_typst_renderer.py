import json
import unittest
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pymupdf
from typst_renderer import export
from test_visual_rendering import specimen
from test_flat_schema import sample
import webapp


class TypstTests(unittest.TestCase):
    def test_vector_pdf_and_literal_text(self):
        a=specimen();a['title']='#read("secret") [literal]'
        data, mime, name=export(a)
        self.assertEqual(mime,'application/pdf')
        self.assertTrue(name.endswith('-typst.pdf'))
        with pymupdf.open(stream=data,filetype='pdf') as doc:
            self.assertEqual(sum(len(p.get_images()) for p in doc),0)
            text=''.join(p.get_text() for p in doc)
            self.assertIn('literal',text)
            self.assertNotIn('non visualizzabile',text)

    def test_http_engine_selection(self):
        server=webapp.ThreadingHTTPServer(('127.0.0.1',0),webapp.WebAppHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/artifact'
            for engine,fmt,ok in [('typst','pdf',True),('standard','pdf',True),('typst','docx',False),('unknown','pdf',False)]:
                payload={'response':json.dumps(sample()),'artifact_id':'a1','format':fmt,'engine':engine}
                request=Request(url,json.dumps(payload).encode(),{'Content-Type':'application/json'})
                if ok:
                    with urlopen(request) as response:self.assertTrue(response.read().startswith(b'%PDF'))
                else:
                    with self.assertRaises(HTTPError) as error:urlopen(request)
                    self.assertEqual(error.exception.code,400);error.exception.close()
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
