import base64
import contextlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer
import requests
import google_forms_direct as google
from test_google_form import quiz_sample
from validation import validated_artifacts


class FakeClient:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail
        self.uploads = 0
        self.forms = 0

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = Mock(status_code=200, content=b'{}')
        if self.fail and self.fail in url and method != 'PATCH':
            response.status_code = 403
            response.json.return_value = {'error': {'message': 'Denied'}}
            return response
        if '/upload/drive/' in url:
            self.uploads += 1
            self.assert_png(kwargs['data'])
            result = {'id': 'image' + str(self.uploads)}
        elif '/permissions?' in url:
            result = {'id': 'public'}
        elif url.endswith('?unpublished=true'):
            self.forms += 1
            result = {'formId': 'form1'}
        elif method == 'GET':
            result = {'formId': 'form1', 'responderUri': 'https://docs.google.com/forms/d/e/published/viewform'}
        else:
            result = {}
        response.json.return_value = result
        return response

    def assert_png(self, data):
        assert data.startswith(bytes([137]) + b'PNG')

    def close(self):
        pass


class GoogleRequestTests(unittest.TestCase):
    def test_read_timeout_retries_and_recovers(self):
        response = Mock(status_code=200, content=b'{}')
        response.json.return_value = {'id': 'ok'}
        client = Mock()
        client.request.side_effect = [requests.ReadTimeout(), response]
        with patch.object(google.time, 'sleep'):
            self.assertEqual(google.request(client, 'GET', google.DRIVE), {'id': 'ok'})
        self.assertEqual(client.request.call_count, 2)
        self.assertEqual(client.request.call_args.kwargs['timeout'], (10, 90))

    def test_read_timeout_has_bounded_retries(self):
        client = Mock()
        client.request.side_effect = requests.ReadTimeout()
        with patch.object(google.time, 'sleep'), self.assertRaisesRegex(google.GoogleError, 'Google Drive non ha risposto'):
            google.request(client, 'GET', google.DRIVE)
        self.assertEqual(client.request.call_count, 3)

    def test_write_timeout_is_not_replayed(self):
        for method in ('POST', 'PATCH', 'DELETE'):
            with self.subTest(method=method):
                client = Mock()
                client.request.side_effect = requests.ReadTimeout()
                with self.assertRaisesRegex(google.GoogleError, 'potrebbe essere stata completata'):
                    google.request(client, method, google.DRIVE)
                client.request.assert_called_once()


class ImportPerformanceTests(unittest.TestCase):
    def payload(self, count):
        encoded = base64.b64encode(bytes([137]) + b'PNG-test').decode()
        question = {'title': 'Calcola', 'option_labels': ['A', 'B', 'C', 'D'],
                    'options': ['A', 'B', 'C', 'D'], 'option_images_base64': [encoded, None, None, None],
                    'option_image_widths': [100, None, None, None],
                    'points': 1, 'correct_index': 0, 'image_base64': encoded}
        return {'title': 'Quiz', 'questions': [question] * count}

    def test_twenty_questions_keep_order_grading_and_cleanup(self):
        client = FakeClient()
        _, item = google.session()
        with patch.object(google, 'image_source', return_value='https://example.com/image.png'):
            result = google._create(client, self.payload(20), item, 'key', base64)
        batches = [kwargs['json']['requests'] for _, url, kwargs in client.calls if url.endswith(':batchUpdate')]
        self.assertEqual(len(batches), 5)
        questions = [r['createItem'] for batch in batches for r in batch if 'createItem' in r]
        self.assertEqual([q['location']['index'] for q in questions], list(range(20)))
        self.assertTrue(all(q['item']['questionItem']['question']['grading']['correctAnswers']['answers'] == [{'value': 'A'}] for q in questions))
        self.assertEqual(client.uploads, 1)
        self.assertFalse(any('name' in kwargs.get('json', {}) for _, _, kwargs in client.calls))
        self.assertEqual(sum(method == 'DELETE' for method, _, _ in client.calls), 1)
        self.assertEqual(result['timings']['unique_images'], 1)
        self.assertIn('cleanup_seconds', item['results']['key']['timings'])

    def test_last_partial_batch_is_imported(self):
        for count in (1, 2, 5, 6, 7, 20, 21):
            with self.subTest(count=count):
                client = FakeClient()
                _, item = google.session()
                with patch.object(google, 'image_source', return_value='https://example.com/image.png'):
                    google._create(client, self.payload(count), item, 'key', base64)
                questions = [r for _, url, kwargs in client.calls if url.endswith(':batchUpdate') for r in kwargs['json']['requests'] if 'createItem' in r]
                self.assertEqual(len(questions), count)

    def test_failed_second_batch_cleans_up_without_publishing(self):
        client = FakeClient()
        original = client.request
        batches = 0
        def send(method, url, **kwargs):
            nonlocal batches
            if url.endswith(':batchUpdate'):
                batches += 1
                if batches == 2:
                    raise requests.ReadTimeout()
            return original(method, url, **kwargs)
        client.request = send
        _, item = google.session()
        with patch.object(google, 'image_source', return_value='https://example.com/image.png'), self.assertRaises(google.GoogleError):
            google._create(client, self.payload(20), item, 'key', base64)
        self.assertEqual(batches, 2)
        self.assertFalse(any(url.endswith(':setPublishSettings') for _, url, _ in client.calls))
        self.assertTrue(any(url == google.DRIVE + '/form1' and kwargs.get('json', {}).get('trashed') for _, url, kwargs in client.calls))
        self.assertEqual(item['results'], {})


class ParallelImageTests(unittest.TestCase):
    def payload(self):
        payload = ImportPerformanceTests().payload(1)
        question = payload['questions'][0]
        question['image_base64'] = None
        question['option_images_base64'] = [base64.b64encode(bytes([137]) + b'PNG' + str(i).encode()).decode() for i in range(4)]
        question['option_image_widths'] = [100] * 4
        return payload

    def run_creation(self, fail_source=False, fail_cleanup=False):
        shared = FakeClient()
        guard = threading.Lock()
        barrier = threading.Barrier(4, timeout=5)
        clients = []
        observed = []
        sources_finished = []

        class WorkerClient:
            def __init__(self):
                self.thread = threading.get_ident()
                self.closed = False
                with guard:
                    clients.append(self)

            def request(worker, method, url, **kwargs):
                self.assertEqual(worker.thread, threading.get_ident())
                with guard:
                    if method in ('DELETE', 'PATCH'):
                        self.assertEqual(len(sources_finished), 4)
                        if fail_cleanup and method == 'DELETE':
                            raise requests.ReadTimeout()
                    return shared.request(method, url, **kwargs)

            def close(worker):
                self.assertEqual(worker.thread, threading.get_ident())
                worker.closed = True

        def source(client, file_id):
            with guard:
                observed.append(threading.get_ident())
            barrier.wait()
            with guard:
                sources_finished.append(file_id)
            if fail_source and file_id == 'image1':
                raise google.GoogleError('Immagine non accessibile')
            return 'https://example.com/' + file_id

        _, item = google.session()
        with patch.object(google, 'image_source', side_effect=source):
            if fail_source:
                with self.assertRaisesRegex(google.GoogleError, 'Immagine non accessibile'):
                    google._create(shared, self.payload(), item, 'key', base64, client_factory=WorkerClient)
                result = None
            else:
                result = google._create(shared, self.payload(), item, 'key', base64, client_factory=WorkerClient)
        self.assertEqual(len(set(observed)), 4)
        self.assertEqual(shared.uploads, 4)
        self.assertTrue(all(worker.closed for worker in clients))
        self.assertEqual(len(clients), 8)  # Four upload sessions and four cleanup sessions.
        trashed = [url for _, url, kwargs in shared.calls if kwargs.get('json', {}).get('trashed')]
        self.assertEqual(len(trashed), 4)
        return shared, item, result

    def test_uploads_and_cleanup_use_four_separate_sessions(self):
        client, item, result = self.run_creation()
        self.assertEqual(client.forms, 1)
        self.assertEqual(result['timings']['unique_images'], 4)
        self.assertEqual(result['warnings'], [])

    def test_failed_upload_waits_for_workers_then_cleans_all_files(self):
        client, item, result = self.run_creation(fail_source=True)
        self.assertEqual(client.forms, 0)
        self.assertEqual(item['results'], {})

    def test_cleanup_failure_keeps_form_and_reports_warnings(self):
        client, item, result = self.run_creation(fail_cleanup=True)
        self.assertEqual(client.forms, 1)
        self.assertEqual(len(result['warnings']), 4)

    def test_no_image_quiz_needs_no_worker_sessions(self):
        payload = ImportPerformanceTests().payload(20)
        for question in payload['questions']:
            question['image_base64'] = None
            question['option_images_base64'] = [None] * 4
        factory = Mock()
        _, item = google.session()
        result = google._create(FakeClient(), payload, item, 'key', base64, client_factory=factory)
        factory.assert_not_called()
        self.assertEqual(result['timings']['unique_images'], 0)


class DirectFormsTests(unittest.TestCase):
    def setUp(self):
        source_patch = patch.object(google, 'image_source', side_effect=lambda client, file_id: 'https://lh3.googleusercontent.com/' + file_id + '=s2048')
        source_patch.start()
        self.addCleanup(source_patch.stop)
        google.SESSIONS.clear()
        self.identifier, self.item = google.session()
        self.item['credentials'] = object()
        data = quiz_sample()
        question = data['artifacts'][0]['quiz_questions'][0]
        question['title'] = 'Calcola $$2^5$$'
        question['options'] = ['$$32$$', '$$2^5$$', '4', '8']
        question['correct_index'] = 0
        self.artifact = validated_artifacts(json.dumps(data))[0]

    def test_only_per_file_scope_and_browser_isolation(self):
        self.assertEqual(google.SCOPES, ['https://www.googleapis.com/auth/drive.file'])
        _, other = google.session()
        self.assertIsNone(other['credentials'])
        self.assertNotEqual(other['csrf'], self.item['csrf'])
        self.assertNotIn('credentials', google.status(self.item))
        self.item['seen'] = time.time() - 43201
        _, fresh = google.session(self.identifier)
        self.assertIsNone(fresh['credentials'])

    def test_creates_images_grading_publishes_and_reuses(self):
        client = FakeClient()
        with patch('google.auth.transport.requests.AuthorizedSession', return_value=client):
            result = google.create_form(self.item, self.artifact)
            reused = google.create_form(self.item, self.artifact)
        self.assertEqual(client.forms, 1)
        self.assertTrue(reused['reused'])
        self.assertEqual(result['form_id'], 'form1')
        self.assertEqual(client.uploads, 2)
        batch = next(kwargs['json'] for method, url, kwargs in client.calls if url.endswith(':batchUpdate'))
        question = batch['requests'][2]['createItem']['item']['questionItem']
        self.assertIn('image', question)
        options = question['question']['choiceQuestion']['options']
        self.assertEqual(options[0], {'value': '32'})
        self.assertIn('image', options[1])
        self.assertTrue(options[1]['image']['sourceUri'].startswith('https://lh3.googleusercontent.com/'))
        self.assertLess(options[1]['image']['properties']['width'], 200)
        self.assertEqual(question['question']['grading']['correctAnswers']['answers'], [{'value': '32'}])
        self.assertEqual(sum(method == 'DELETE' for method, _, _ in client.calls), 2)
        self.assertEqual(sum(kwargs.get('json', {}).get('trashed', False) for _, _, kwargs in client.calls), 2)

    def test_repeated_images_are_reused_and_questions_imported_in_groups(self):
        artifact = dict(self.artifact)
        artifact['quiz_questions'] = [self.artifact['quiz_questions'][0]] * 20
        client = FakeClient()
        with patch('google.auth.transport.requests.AuthorizedSession', return_value=client):
            google.create_form(self.item, artifact)
        self.assertEqual(client.uploads, 2)
        batches = [kwargs['json']['requests'] for _, url, kwargs in client.calls if url.endswith(':batchUpdate')]
        self.assertEqual(len(batches), 5)
        self.assertEqual(batches[-1][-1]['createItem']['location']['index'], 19)
        first_import = next(index for index, (_, url, _) in enumerate(client.calls) if url.endswith(':batchUpdate'))
        self.assertLess(first_import, 10)

    def test_failed_import_trashes_new_form_and_support_files(self):
        client = FakeClient(fail=':batchUpdate')
        with patch('google.auth.transport.requests.AuthorizedSession', return_value=client):
            with self.assertRaises(google.GoogleError):
                google.create_form(self.item, self.artifact)
        trashed = [url for _, url, kwargs in client.calls if kwargs.get('json', {}).get('trashed')]
        self.assertIn(google.DRIVE + '/form1', trashed)
        self.assertEqual(len(trashed), 3)
        self.assertEqual(self.item['results'], {})

    def test_failed_drive_sharing_does_not_create_form(self):
        client = FakeClient(fail='/permissions?')
        with patch('google.auth.transport.requests.AuthorizedSession', return_value=client):
            with self.assertRaises(google.GoogleError):
                google.create_form(self.item, self.artifact)
        self.assertEqual(client.forms, 0)
        self.assertTrue(any(kwargs.get('json', {}).get('trashed') for _, _, kwargs in client.calls))

    def test_local_alias_uses_the_same_origin_as_oauth(self):
        with patch.dict(os.environ, {'GOOGLE_OAUTH_REDIRECT_URI': 'http://localhost:8000/api/google/callback'}):
            self.assertEqual(google.local_origin_redirect('127.0.0.1:8000'), 'http://localhost:8000')
            self.assertIsNone(google.local_origin_redirect('localhost:8000'))
            self.assertIsNone(google.local_origin_redirect('127.0.0.1:9000'))
            self.assertIsNone(google.local_origin_redirect('example.com:8000'))
        with patch.dict(os.environ, {'GOOGLE_OAUTH_REDIRECT_URI': 'https://example.run.app/api/google/callback'}):
            self.assertIsNone(google.local_origin_redirect('127.0.0.1:8000'))

    def test_real_oauth_start_uses_only_drive_file_and_configured_callback(self):
        from urllib.parse import urlparse, parse_qs
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'oauth.json'
            config.write_text(json.dumps({'web': {'client_id': 'test.apps.googleusercontent.com', 'client_secret': 'not-a-real-secret',
                                                 'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                                                 'token_uri': 'https://oauth2.googleapis.com/token'}}))
            with patch.dict(os.environ, {'GOOGLE_OAUTH_CLIENT_FILE': str(config),
                                        'GOOGLE_OAUTH_REDIRECT_URI': 'https://example.run.app/api/google/callback'}):
                url = google.start(self.item)
            query = parse_qs(urlparse(url).query)
            self.assertEqual(query['scope'], google.SCOPES)
            self.assertEqual(query['redirect_uri'], ['https://example.run.app/api/google/callback'])
            self.assertEqual(query['state'], [self.item['pending']['state']])
            self.assertNotIn('not-a-real-secret', url)

    def test_state_validation_expiry_and_one_use(self):
        self.item['pending'] = {'flow': Mock(), 'state': 'expected', 'time': time.time()}
        with self.assertRaises(ValueError):
            google.finish(self.item, 'wrong', 'code')
        self.assertNotIn('pending', self.item)
        self.item['pending'] = {'flow': Mock(), 'state': 'expected', 'time': time.time() - 601}
        with self.assertRaises(ValueError):
            google.finish(self.item, 'expected', 'code')
        with self.assertRaises(ValueError):
            google.finish(self.item, 'expected', 'code')

    def test_callback_checks_granted_scopes(self):
        flow = Mock()
        flow.credentials.granted_scopes = []
        flow.oauth2session.token = {'scope': 'openid'}
        self.item['pending'] = {'flow': flow, 'state': 'expected', 'time': time.time()}
        self.item['credentials'] = None
        with self.assertRaises(ValueError):
            google.finish(self.item, 'expected', 'code')
        self.assertIsNone(self.item['credentials'])
        flow.credentials.granted_scopes = google.SCOPES
        self.item['pending'] = {'flow': flow, 'state': 'expected', 'time': time.time()}
        google.finish(self.item, 'expected', 'code')
        self.assertIs(self.item['credentials'], flow.credentials)

    def test_disconnect_revokes_and_forgets_credentials(self):
        self.item['credentials'] = Mock(refresh_token='refresh', token='token')
        with patch('requests.post', return_value=Mock(status_code=200)) as revoke:
            google.disconnect(self.item)
        self.assertEqual(revoke.call_args.kwargs['data'], {'token': 'refresh'})
        self.assertIsNone(self.item['credentials'])
        self.assertEqual(self.item['results'], {})


class ImageSourceTests(unittest.TestCase):
    def test_public_thumbnail_is_verified_without_authentication(self):
        from PIL import Image
        output = io.BytesIO()
        Image.new('RGB', (80, 40), 'white').save(output, 'PNG')
        response = Mock(status_code=200, headers={'Content-Type': 'image/png'}, content=output.getvalue())
        with patch.object(google, 'request', return_value={'thumbnailLink': 'https://lh3.googleusercontent.com/picture=s220'}) as metadata, patch('requests.get', return_value=response) as get:
            source = google.image_source(Mock(), 'created-image')
        self.assertEqual(source, 'https://drive.google.com/thumbnail?id=created-image&sz=w2048')
        self.assertNotIn('headers', get.call_args.kwargs)
        metadata.assert_not_called()

    def test_unready_images_are_rechecked_and_fail_before_import(self):
        with patch.object(google, 'request') as metadata, patch('requests.get', return_value=Mock(status_code=404)) as get, patch.object(google.time, 'sleep'):
            with self.assertRaises(google.GoogleError):
                google.image_source(Mock(), 'created-image')
        metadata.assert_not_called()
        self.assertEqual(get.call_count, 8)

    def test_original_file_replaces_temporary_signed_thumbnail(self):
        from PIL import Image
        output = io.BytesIO()
        Image.new('RGB', (80, 40), 'white').save(output, 'PNG')
        ready = Mock(status_code=200, headers={'Content-Type': 'image/png'}, content=output.getvalue())
        with patch.object(google, 'request') as metadata, patch('requests.get', side_effect=[Mock(status_code=404), ready]):
            source = google.image_source(Mock(), 'created-image')
        self.assertEqual(source, 'https://drive.google.com/uc?export=download&id=created-image')
        metadata.assert_not_called()

    def test_waits_for_public_access_to_propagate(self):
        from PIL import Image
        output = io.BytesIO()
        Image.new('RGB', (80, 40), 'white').save(output, 'PNG')
        ready = Mock(status_code=200, headers={'Content-Type': 'image/png'}, content=output.getvalue())
        with patch('requests.get', side_effect=[Mock(status_code=403), Mock(status_code=403), ready]), patch.object(google.time, 'sleep') as sleep:
            source = google.image_source(Mock(), 'created-image')
        self.assertEqual(source, 'https://drive.google.com/thumbnail?id=created-image&sz=w2048')
        sleep.assert_called_once_with(1)

    def test_html_download_page_is_not_accepted_as_an_image(self):
        response = Mock(status_code=200, headers={'Content-Type': 'text/html'}, content=b'<html>Sign in</html>')
        with patch.object(google, 'request', return_value={'thumbnailLink': 'https://lh3.googleusercontent.com/picture=s220'}), patch('requests.get', return_value=response), patch.object(google.time, 'sleep'):
            with self.assertRaises(google.GoogleError):
                google.image_source(Mock(), 'created-image')


class GoogleRoutesTests(unittest.TestCase):
    def test_status_cookie_csrf_secret_blocking_and_account_isolation(self):
        import webapp
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / 'google_oauth_client.json'
            secret.write_text('{"web":{"client_secret":"DO-NOT-SERVE"}}')
            with patch.object(webapp, 'BASE_DIR', Path(directory)):
                server = ThreadingHTTPServer(('127.0.0.1', 0), webapp.WebAppHandler)
                base = f'http://127.0.0.1:{server.server_port}'
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                with patch.dict(os.environ, {'GOOGLE_OAUTH_REDIRECT_URI': base + '/api/google/callback', 'GOOGLE_OAUTH_CLIENT_FILE': str(secret)}):
                    thread.start()
                    try:
                        redirected = requests.get(base + '/history', headers={'Host': f'localhost:{server.server_port}'}, allow_redirects=False, timeout=5)
                        self.assertEqual(redirected.status_code, 302)
                        self.assertEqual(redirected.headers['Location'], base + '/history')
                        browser = requests.Session()
                        response = browser.get(base + '/api/google/status', timeout=5)
                        self.assertEqual(response.status_code, 200)
                        data = response.json()
                        self.assertTrue(data['configured'])
                        self.assertFalse(data['connected'])
                        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
                        self.assertNotIn('DO-NOT-SERVE', response.text)
                        response = browser.post(base + '/api/google/create', json={}, timeout=5)
                        self.assertEqual(response.status_code, 403)
                        response = browser.post(base + '/api/google/create', json={}, headers={'Origin': base, 'X-CSRF-Token': data['csrf']}, timeout=5)
                        self.assertEqual(response.status_code, 400)
                        # Use the real materialized artifact contract through HTTP.
                        sid = browser.cookies.get(google.COOKIE)
                        google.SESSIONS[sid]['credentials'] = object()
                        with patch.object(google, 'create_form', return_value={'form_id': 'created', 'edit_url': 'https://docs.google.com/forms/d/created/edit'}) as create:
                            response = browser.post(base + '/api/google/create', json={'response': json.dumps(quiz_sample()), 'artifact_id': 'modulogoogle'}, headers={'Origin': base, 'X-CSRF-Token': data['csrf']}, timeout=5)
                            self.assertEqual(response.status_code, 200, response.text)
                            self.assertEqual(response.json()['form_id'], 'created')
                            self.assertEqual(create.call_args.args[1]['artifact_type'], 'modulogoogle')
                            from test_flat_schema import sample
                            invalid = sample()
                            response = browser.post(base + '/api/google/create', json={'response': json.dumps(invalid), 'artifact_id': invalid['artifacts'][0]['id']}, headers={'Origin': base, 'X-CSRF-Token': data['csrf']}, timeout=5)
                            self.assertEqual(response.status_code, 400)
                            self.assertEqual(create.call_count, 1)
                        for method in (browser.get, browser.head):
                            response = method(base + '/google_oauth_client.json', timeout=5)
                            self.assertEqual(response.status_code, 404)
                            self.assertNotIn('DO-NOT-SERVE', response.text)
                        other = requests.get(base + '/api/google/status', timeout=5).json()
                        self.assertNotEqual(data['csrf'], other['csrf'])
                        response = browser.get(base + '/api/google/callback?state=bad&code=secret-code', timeout=5)
                        self.assertIn('non valido', response.text)
                        self.assertNotIn('secret-code', response.text)
                    finally:
                        server.shutdown(); server.server_close(); thread.join(timeout=5)
