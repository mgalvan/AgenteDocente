"""Browser-scoped Google OAuth and direct Forms creation. Secrets never enter the UI."""
from __future__ import annotations
import hashlib
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

SCOPES = ['https://www.googleapis.com/auth/drive.file']
FORMS = 'https://forms.googleapis.com/v1/forms'
DRIVE = 'https://www.googleapis.com/drive/v3/files'
SESSIONS = {}
LOCK = threading.RLock()
COOKIE = 'agente_google_session'


def configuration():
    configured_file = os.environ.get('GOOGLE_OAUTH_CLIENT_FILE')
    if configured_file:
        filename = Path(configured_file)
    else:
        roots = [Path.home(), Path(__file__).resolve().parent.parent]
        candidates = [root / directory / 'google_oauth_client.json'
                      for root in roots for directory in ('.agentdocente', '.agentedocente')]
        filename = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    redirect = os.environ.get('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:8000/api/google/callback')
    parsed = urlparse(redirect)
    if parsed.path != '/api/google/callback' or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('GOOGLE_OAUTH_REDIRECT_URI deve terminare con /api/google/callback, senza query o frammenti.')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('Il ritorno OAuth deve usare HTTPS oppure localhost.')
    return filename, redirect


def local_origin_redirect(host):
    """Keep local pages and the OAuth callback on the same cookie origin."""
    try:
        _, redirect = configuration()
        expected = urlparse(redirect)
        incoming = urlparse('http://' + host)
        loopbacks = ('localhost', '127.0.0.1')
        if (expected.scheme == 'http' and expected.hostname in loopbacks
                and incoming.hostname in loopbacks
                and (incoming.port or 80) == (expected.port or 80)
                and incoming.netloc.lower() != expected.netloc.lower()):
            return expected.scheme + '://' + expected.netloc
    except ValueError:
        pass
    return None


def session(identifier=None):
    with LOCK:
        now = time.time()
        for key in list(SESSIONS):
            if now - SESSIONS[key]['seen'] > 43200:
                del SESSIONS[key]
        if identifier not in SESSIONS:
            identifier = secrets.token_urlsafe(32)
            SESSIONS[identifier] = {'csrf': secrets.token_urlsafe(32), 'seen': now, 'credentials': None,
                                    'results': {}, 'lock': threading.Lock()}
        item = SESSIONS[identifier]
        item['seen'] = now
        return identifier, item


def status(item):
    filename, redirect = configuration()
    return {'configured': filename.is_file(), 'connected': item['credentials'] is not None,
            'csrf': item['csrf'], 'redirect_uri': redirect, 'client_file': str(filename),
            'scope': SCOPES[0], 'progress': item.get('progress', '')}


def start(item):
    from google_auth_oauthlib.flow import Flow
    filename, redirect = configuration()
    if not filename.is_file():
        raise ValueError('Configura prima la credenziale OAuth seguendo le istruzioni Collega Google.')
    config = json.loads(filename.read_text(encoding='utf-8-sig'))
    if 'web' not in config:
        raise ValueError('La credenziale OAuth deve essere di tipo Applicazione web.')
    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect)
    url, state = flow.authorization_url(access_type='offline', prompt='consent select_account', include_granted_scopes='false')
    with item['lock']:
        item['pending'] = {'flow': flow, 'state': state, 'time': time.time()}
    return url


def finish(item, state, code, error=None):
    with item['lock']:
        pending = item.pop('pending', None)
        if not pending or not secrets.compare_digest(str(state), pending['state']) or time.time() - pending['time'] > 600:
            raise ValueError('Collegamento scaduto o non valido. Premi nuovamente Collega Google.')
        if error or not code:
            raise ValueError('Collegamento Google annullato o non autorizzato.')
        flow = pending['flow']
        flow.fetch_token(code=code)
        credentials = flow.credentials
        granted = credentials.granted_scopes or flow.oauth2session.token.get('scope', '')
        if isinstance(granted, str):
            granted = granted.split()
        if not set(SCOPES).issubset(set(granted)):
            raise ValueError('Autorizza l?accesso ai file creati dall?app per completare il collegamento.')
        item['credentials'] = credentials
        item['results'] = {}


def disconnect(item):
    with item['lock']:
        credentials = item['credentials']
        if credentials:
            import requests
            response = requests.post('https://oauth2.googleapis.com/revoke',
                                     data={'token': credentials.refresh_token or credentials.token}, timeout=30)
            if response.status_code not in (200, 400):
                raise ValueError('Google non ha confermato la revoca. Riprova a scollegare.')
        item['credentials'] = None
        item.pop('pending', None)
        item['results'] = {}


class GoogleError(ValueError):
    pass


def request(client, method, url, **kwargs):
    import requests
    # A timed-out write may already have succeeded: never replay it blindly.
    attempts = 3 if method.upper() == 'GET' else 1
    for attempt in range(attempts):
        try:
            response = client.request(method, url, timeout=(10, 90), **kwargs)
            break
        except requests.Timeout as error:
            if attempt + 1 < attempts:
                time.sleep(attempt + 1)
                continue
            service = 'Google Drive' if 'drive/' in url else 'Google Moduli'
            raise GoogleError(
                f'{service} non ha risposto entro il tempo di attesa. '
                'La connessione potrebbe essere lenta o il servizio temporaneamente occupato. '
                'Riprova tra qualche minuto. Se il problema persiste, controlla la connessione. '
                'Una richiesta di modifica potrebbe essere stata completata da Google.'
            ) from error
    if response.status_code >= 300:
        try:
            error = response.json().get('error', {})
            message = error.get('message', 'Richiesta Google non riuscita.')
            reasons = [entry.get('reason') for entry in error.get('details', [])]
            if 'SERVICE_DISABLED' in reasons:
                message = 'Abilita Google Forms API e Google Drive API nel progetto della credenziale OAuth. ' + message
            elif 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' in reasons:
                message = 'Scollega Google e ricollegalo autorizzando i file creati dall?app.'
        except (ValueError, AttributeError):
            message = 'Richiesta Google non riuscita.'
        raise GoogleError(f'Google ({response.status_code}): {message}')
    return response.json() if response.content else {}


def image_source(client, file_id):
    """Verify public Drive endpoints without relying on temporary thumbnail URLs."""
    import requests
    import io
    from PIL import Image
    candidates = (
        'https://drive.google.com/thumbnail?id=' + file_id + '&sz=w2048',
        'https://drive.google.com/uc?export=download&id=' + file_id,
    )
    def accessible(candidate):
        try:
            response = requests.get(candidate, timeout=(3, 6))
            if response.status_code == 200 and response.headers.get('Content-Type', '').startswith('image/') and len(response.content) <= 10 * 1024 * 1024:
                with Image.open(io.BytesIO(response.content)) as picture:
                    picture.verify()
                return True
        except (requests.RequestException, OSError, ValueError):
            pass
        return False

    # Sharing and thumbnail generation can lag behind a successful upload.
    # A signed thumbnailLink may pass our GET yet be rejected by Forms later.
    for attempt in range(4):
        for candidate in candidates:
            if accessible(candidate):
                return candidate
        if attempt < 3:
            time.sleep(attempt + 1)
    raise GoogleError('Immagine non accessibile pubblicamente. Verifica la condivisione tramite link consentita dal tuo account.')



def _image_jobs(jobs, client, client_factory, action):
    """Bound network concurrency; never share an HTTP session between workers.

    Executor shutdown waits for all uploads before callers can start cleanup,
    including when a worker fails after another worker has created a file.
    """
    if not jobs:
        return
    if client_factory is None:
        for job in jobs:
            action(client, job)
        return
    count = min(4, len(jobs))

    def run(chunk):
        worker_client = client_factory()
        try:
            for job in chunk:
                action(worker_client, job)
        finally:
            worker_client.close()

    with ThreadPoolExecutor(max_workers=count) as pool:
        list(pool.map(run, [jobs[index::count] for index in range(count)]))


def create_form(item, artifact):
    from google.auth.transport.requests import AuthorizedSession
    from google_form_export import google_form_payload
    import base64
    # Validate and render before mutating anything in Google.
    started = time.perf_counter()
    item['progress'] = 'Preparazione delle formule... '
    try:
        payload = google_form_payload(artifact)
    except Exception:
        item['progress'] = ''
        raise
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with item['lock']:
        if not item['credentials']:
            raise ValueError('Collega prima il tuo account Google.')
        client = AuthorizedSession(item['credentials'])
        try:
            if key in item['results']:
                saved = item['results'][key]
                try:
                    request(client, 'GET', FORMS + '/' + saved['form_id'])
                    return {**saved, 'reused': True}
                except GoogleError as error:
                    if 'Google (404)' not in str(error):
                        raise
                    del item['results'][key]
            prepared = time.perf_counter() - started
            def client_factory():
                return AuthorizedSession(copy.copy(item['credentials']))

            result = _create(client, payload, item, key, base64, client_factory=client_factory)
            result['timings']['preparation_seconds'] = round(prepared, 3)
            result['timings']['total_seconds'] = round(time.perf_counter() - started, 3)
            return result
        finally:
            client.close()
            item['progress'] = ''


def _create(client, payload, item, key, base64, client_factory=None):
    files, warnings = [], []
    form_id = None
    image_cache = {}
    timings = {'images_seconds': 0.0, 'import_seconds': 0.0, 'cleanup_seconds': 0.0}

    state_lock = threading.Lock()

    def upload(image_client, job):
        digest, encoded = job
        file = request(image_client, 'POST', 'https://www.googleapis.com/upload/drive/v3/files?uploadType=media&fields=id&ignoreDefaultVisibility=true',
                       data=base64.b64decode(encoded), headers={'Content-Type': 'image/png'})
        # Register before sharing/verification, even if a different worker fails.
        with state_lock:
            files.append(file)
        permission = request(image_client, 'POST', DRIVE + '/' + file['id'] + '/permissions?fields=id',
                             json={'type': 'anyone', 'role': 'reader', 'allowFileDiscovery': False})
        file['permission'] = permission['id']
        source = image_source(image_client, file['id'])
        with state_lock:
            image_cache[digest] = source
            item['progress'] = f'Caricamento immagini: {len(image_cache)} di {len(encoded_images)}...'

    def image(encoded, alt, width, name):
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        return {'sourceUri': image_cache[digest], 'altText': alt, 'properties': {'width': width}}

    encoded_images = {}
    for question in payload['questions']:
        for encoded in [question.get('image_base64'), *question['option_images_base64']]:
            if encoded:
                encoded_images.setdefault(hashlib.sha256(encoded.encode()).hexdigest(), encoded)

    try:
        # Complete all uploads before creating a form or importing any images.
        item['progress'] = f'Caricamento di {len(encoded_images)} immagini...'
        images_started = time.perf_counter()
        _image_jobs(list(encoded_images.items()), client, client_factory, upload)
        timings['images_seconds'] = round(time.perf_counter() - images_started, 3)
        requests = [
            {'updateSettings': {'settings': {'quizSettings': {'isQuiz': True}}, 'updateMask': 'quizSettings.isQuiz'}},
            {'updateFormInfo': {'info': {'description': 'Quiz a risposta multipla. Seleziona una risposta per domanda.'}, 'updateMask': 'description'}}]
        for index, question in enumerate(payload['questions']):
            item['progress'] = f"Importazione domanda {index + 1} di {len(payload['questions'])}..."
            options = []
            for option_index, label in enumerate(question['option_labels']):
                option = {'value': label}
                encoded = question['option_images_base64'][option_index]
                if encoded:
                    option['image'] = image(encoded, question['options'][option_index], question['option_image_widths'][option_index], f'opzione-{index+1}-{option_index+1}.png')
                options.append(option)
            question_item = {'question': {'required': True, 'choiceQuestion': {'type': 'RADIO', 'options': options, 'shuffle': False},
                'grading': {'pointValue': question['points'], 'correctAnswers': {'answers': [{'value': question['option_labels'][question['correct_index']]}]}}}}
            title = f"{index+1}. {question['title']}"
            if question.get('image_base64'):
                question_item['image'] = image(question['image_base64'], question['title'], 740, f'domanda-{index+1}.png')
                title = f'Domanda {index+1} - Seleziona una risposta'
            requests.append({'createItem': {'item': {'title': title, 'questionItem': question_item}, 'location': {'index': index}}})
            if form_id is None:
                form = request(client, 'POST', FORMS + '?unpublished=true', json={'info': {'title': payload['title']}})
                form_id = form['formId']
            # Import the first question immediately, then groups of five.
            # This preserves early validation without one network call per question.
            if index == 0 or index % 5 == 0 or index == len(payload['questions']) - 1:
                item['progress'] = f'Inserimento domande fino alla {index + 1}...'
                import_started = time.perf_counter()
                try:
                    request(client, 'POST', FORMS + '/' + form_id + ':batchUpdate', json={'requests': requests})
                except GoogleError as error:
                    raise GoogleError(f'Inserimento fino alla domanda {index + 1}: {error}') from error
                timings['import_seconds'] += time.perf_counter() - import_started
                requests = []
        item['progress'] = 'Pubblicazione del modulo...'

        publish_started = time.perf_counter()
        request(client, 'POST', FORMS + '/' + form_id + ':setPublishSettings',
                json={'publishSettings': {'publishState': {'isPublished': True, 'isAcceptingResponses': True}}, 'updateMask': 'publishState'})
        form = request(client, 'GET', FORMS + '/' + form_id)
        timings['publish_seconds'] = round(time.perf_counter() - publish_started, 3)
        result = {'form_id': form_id, 'edit_url': f'https://docs.google.com/forms/d/{form_id}/edit',
                  'response_url': form['responderUri'], 'warnings': warnings, 'reused': False,
                  'timings': timings}
        item['results'][key] = result
        return result
    except Exception as error:
        if form_id:
            try:
                request(client, 'PATCH', DRIVE + '/' + form_id, json={'trashed': True})
            except Exception:
                raise GoogleError(f'{error} Modulo incompleto da controllare: https://docs.google.com/forms/d/{form_id}/edit') from error
        raise
    finally:
        cleanup_started = time.perf_counter()
        item['progress'] = 'Pulizia delle immagini temporanee...'
        def cleanup(image_client, file):
            if file.get('permission'):
                try:
                    request(image_client, 'DELETE', DRIVE + '/' + file['id'] + '/permissions/' + file['permission'])
                except Exception:
                    with state_lock:
                        warnings.append('Revoca condivisione immagine temporanea non riuscita: ' + file['id'])
            try:
                request(image_client, 'PATCH', DRIVE + '/' + file['id'], json={'trashed': True})
            except Exception:
                with state_lock:
                    warnings.append('Pulizia immagine temporanea non riuscita: ' + file['id'])

        try:
            _image_jobs(files, client, client_factory, cleanup)
        except Exception:
            # A worker/session failure must not hide the original result/error.
            # Retrying cleanup is safe; never retry uploads or form writes here.
            for file in files:
                cleanup(client, file)
        timings['cleanup_seconds'] = round(time.perf_counter() - cleanup_started, 3)
        timings['unique_images'] = len(files)
