import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import gemini_cache
from gemini_client import ask_gemini

class CacheTests(unittest.TestCase):
    def test_reuse_and_changed_directives(self):
        client=MagicMock();client.caches.create.return_value=SimpleNamespace(name='cachedContents/test',expire_time=datetime.now(timezone.utc)+timedelta(minutes=15))
        with tempfile.TemporaryDirectory() as folder,patch.object(gemini_cache,'FILE',Path(folder)/'index.json'):
            args=(client,'model','directives',{},'key',15)
            self.assertEqual(gemini_cache.acquire(*args)['state'],'created')
            self.assertEqual(gemini_cache.acquire(*args)['state'],'reused')
            gemini_cache.acquire(client,'model','changed',{},'key',15)
            self.assertEqual(client.caches.create.call_count,2)
    def test_cached_request_omits_system_instruction(self):
        client=MagicMock();client.models.generate_content.return_value=SimpleNamespace(text='{}',usage_metadata=SimpleNamespace(cached_content_token_count=100))
        with patch.dict('os.environ',{'GEMINI_API_KEY':'test'}),patch('gemini_client.genai.Client') as factory,patch('gemini_cache.acquire',return_value={'name':'cachedContents/test','state':'reused','expires':'later'}) as acquire:
            factory.return_value.__enter__.return_value=client
            report={};ask_gemini('directives','prompt',use_cache=True,cache_report=report)
            config=client.models.generate_content.call_args.kwargs['config']
            self.assertIsNone(config.system_instruction)
            self.assertEqual(config.cached_content,'cachedContents/test')
            self.assertIsNotNone(config.response_json_schema)
            self.assertEqual(report['cached_tokens'],100)
            client.reset_mock();acquire.reset_mock()
            ask_gemini('directives','prompt')
            acquire.assert_not_called()
            self.assertEqual(client.models.generate_content.call_args.kwargs['config'].system_instruction,'directives')
    def test_cache_failure_does_not_generate(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'test'}),patch('gemini_client.genai.Client') as factory,patch('gemini_cache.acquire',side_effect=ValueError('cache rejected')):
            with self.assertRaises(ValueError):ask_gemini('directives','prompt',use_cache=True)
            factory.return_value.__enter__.return_value.models.generate_content.assert_not_called()
