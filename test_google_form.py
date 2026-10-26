import copy
import json
import subprocess
import unittest
from pydantic import ValidationError
from test_flat_schema import sample
from models_api_flat import FlatResponse
from validation import validated_artifacts
from response_recovery import inspect_response
from renderers import artifact_file
from google_form_export import validate_requested_quiz


def quiz_sample():
    data = sample()
    data['artifacts'] = [{'id': 'modulogoogle', 'kind': 'modulogoogle', 'format': 'gs',
        'audience': 'teacher', 'title': 'Equazioni', 'containers': [],
        'quiz_questions': [{'title': 'Quanto vale x se x + 1 = 3?',
            'options': ['1', '2', '3', '4'], 'correct_index': 1, 'points': 1}]}]
    return data


class GoogleFormTests(unittest.TestCase):
    def test_contract_export_and_history_recovery(self):
        raw = json.dumps(quiz_sample())
        artifact = validated_artifacts(raw)[0]
        recovered, warnings = inspect_response(raw)
        self.assertEqual(recovered, [artifact])
        self.assertEqual(warnings, [])
        self.assertEqual(artifact['formats'], ['pdf', 'docx', 'gs'])
        content, mime, filename = artifact_file(artifact, 'gs')
        self.assertEqual(filename, 'modulogoogle.gs')
        self.assertIn('text/plain', mime)
        self.assertIn(b'function creaModuloGoogle()', content)
        with self.assertRaises(ValueError): artifact_file(artifact, 'pptx')

    def test_printable_exports_contain_questions_options_and_answer_key(self):
        import io
        from docx import Document
        artifact = validated_artifacts(json.dumps(quiz_sample()))[0]
        self.assertIn('Soluzioni per il docente', artifact['sections'][-1]['title'])
        pdf, mime, name = artifact_file(artifact, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertEqual(name, 'modulogoogle.pdf')
        self.assertEqual(mime, 'application/pdf')
        data, mime, name = artifact_file(artifact, 'docx')
        text = '\n'.join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        self.assertIn('Quanto vale x se x + 1 = 3?', text)
        self.assertIn('2. 2', text)
        self.assertIn('Soluzioni per il docente', text)
        self.assertIn('Risposta 2: 2', text)
        self.assertEqual(name, 'modulogoogle.docx')
        self.assertIn('wordprocessingml', mime)

    def test_invalid_questions_and_formats_rejected(self):
        for patch in [{'correct_index': -1}, {'correct_index': 4}, {'points': 0},
                      {'options': ['a', 'a']}, {'options': ['a', ' ']}, {'title': ''}]:
            data = quiz_sample()
            data['artifacts'][0]['quiz_questions'][0].update(patch)
            with self.assertRaises(ValidationError): FlatResponse.model_validate(data)
        for patch in [{'format': 'pdf'}, {'quiz_questions': []}, {'title': ''}]:
            data = quiz_sample(); data['artifacts'][0].update(patch)
            with self.assertRaises(ValidationError): FlatResponse.model_validate(data)
        data = sample(); data['artifacts'][0]['format'] = 'gs'
        with self.assertRaises(ValidationError): FlatResponse.model_validate(data)

    def test_math_image_embedded_and_printable_rich_segments(self):
        import base64
        import io
        import re
        from PIL import Image
        data = quiz_sample()
        question = data['artifacts'][0]['quiz_questions'][0]
        question['title'] = r'Calcola $$\frac{1}{2}+\frac{1}{3}$$.'
        question['options'] = [r'$$\frac{5}{6}$$', r'$$2$$', r'$$\frac{1}{6}$$', r'$$\sqrt{2}$$']
        artifact = validated_artifacts(json.dumps(data))[0]
        self.assertTrue(any(s['type'] == 'formula' for s in artifact['sections'][0]['blocks'][0]['segments']))
        script = artifact_file(artifact, 'gs')[0].decode()
        payload = json.loads(re.search(r'const MODULO_GOOGLE = ([^\n]+);', script)[1])
        image = Image.open(io.BytesIO(base64.b64decode(payload['questions'][0]['image_base64'])))
        self.assertEqual(image.width, 1480)
        self.assertGreater(image.height, 100)
        self.assertLess(image.height, 300)
        self.assertEqual(payload["questions"][0]["option_labels"][1], "2")
        self.assertIsNone(payload["questions"][0]["option_images_base64"][1])
        self.assertIn('form.addImageItem()', script)
        self.assertNotIn("'Risposta ' + (i + 1)", script)
        result = subprocess.run(['node', '--check', '-'],input=script,text=True,capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        mock = r"""
const assert = require('assert');
let imageCount = 0, choiceCount = 0;
const properties = {};
let uploads = 0, cleaned = 0, updates = 0;
const image = {setTitle() { return this; }, setHelpText() { throw Error('Raw LaTeX must not appear above the image'); },
 setImage(blob) { assert.equal(blob[0], 137); imageCount++; return this; },
 setWidth(width) { assert.equal(width, 740); return this; }};
const item = {setTitle() {}, setRequired() {}, setPoints() {}, showOtherOption() {},
 createChoice(value, correct) { return {value, correct}; },
 setChoices(choices) { choiceCount++; assert.deepEqual(choices.map(c=>c.value), ['\u2063', '2', '\u2063'.repeat(3), '\u2063'.repeat(4)]); assert.equal(choices.filter(c=>c.correct).length, 1); assert.equal(choices[1].correct, true); }};
const form = {setIsQuiz() {},setDescription() {},addImageItem() { return image; },
 addMultipleChoiceItem() { return item; },getId() { return 'id'; },getEditUrl() { return 'edit'; },getPublishedUrl() { return 'public'; }};
const FormApp = {create() { return form; },openById() { return form; }};
const LockService = {getScriptLock() { return {waitLock() {},releaseLock() {}}; }};
const PropertiesService = {getScriptProperties() { return {getProperty(k) {return properties[k];},setProperty(k,v) {properties[k]=v;}}; }};
const Utilities = {DigestAlgorithm:{SHA_256:'sha'},computeDigest() {return 'hash';},base64EncodeWebSafe(x) {return x;},base64Decode(x) {return Buffer.from(x,'base64');},newBlob(bytes, type, name) {bytes.getBytes=()=>bytes; bytes.getName=()=>name; return bytes;}};
const ScriptApp = {AuthMode:{FULL:'full'},requireScopes(mode, scopes) {assert.equal(mode,'full'); assert(scopes.includes('https://www.googleapis.com/auth/forms.body')); assert(!scopes.includes('https://www.googleapis.com/auth/drive'));},getOAuthToken() {return 'test-token';}};
const UrlFetchApp = {fetch(url, options) {
 assert.equal(options.headers.Authorization, 'Bearer test-token');
 if(url.includes('/drive/v3/files')) {
   let body = {};
   if(url.includes('/upload/')) { assert.equal(options.payload[0],137); uploads++; body={id:'image'+uploads}; }
   else if(options.method==='delete') { assert(url.endsWith('/permissions/public')); }
   else {
     const data=JSON.parse(options.payload);
     if(url.includes('/permissions')) { assert.equal(data.type,'anyone'); body={id:'public'}; }
     else if(data.trashed) { cleaned++; }
     else { assert(data.name.startsWith('opzione-')); }
   }
   return {getResponseCode() {return options.method==='delete'?204:200;},getContentText() {return options.method==='delete'?'':JSON.stringify(body);}};
 }

 if(options.method==='get') return {getResponseCode() {return 200;},getContentText() {return JSON.stringify({items:[{imageItem:{}},{itemId:'q1',questionItem:{question:{}}}]});}};
 updates++;
 const request=JSON.parse(options.payload).requests[0].updateItem;
 assert.equal(request.location.index,1);
 assert.equal(request.item.itemId,'q1');
 const question=request.item.questionItem.question;
 assert.equal(question.choiceQuestion.options.length,4);
 assert.equal(question.choiceQuestion.options[1].value,'2');
 assert.equal(question.choiceQuestion.options[1].image,undefined);
 assert.equal(question.choiceQuestion.options.filter(o=>o.image).length,3);
 assert.equal(question.grading.correctAnswers.answers[0].value,'2');
 assert.equal(question.grading.pointValue,1);
 return {getResponseCode() {return 200;},getContentText() {return '{}';}};
}};

"""
        result = subprocess.run(['node', '-'],input=mock + script + '\ncreaModuloGoogle(); creaModuloGoogle(); assert.equal(imageCount,1); assert.equal(choiceCount,1); assert.equal(uploads,3); assert.equal(cleaned,3); assert.equal(updates,1);',text=True,capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        pdf, _, _ = artifact_file(artifact, 'pdf')
        docx, _, _ = artifact_file(artifact, 'docx')
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertTrue(docx.startswith(b'PK'))

    def test_numeric_options_and_separate_question_image(self):
        from google_form_math import option_text, question_image
        from unittest.mock import patch
        for text, expected in [('$$10$$', '10'), (r'\(-3,5\)', '-3,5'),
                               ('$0$', '0'), ('5', '5'), ('$$+2.5$$', '+2.5')]:
            self.assertEqual(option_text(text), expected)
        self.assertIsNone(option_text(r'$$\frac{1}{2}$$'))
        with patch('google_form_math.text_image', return_value=b'image') as render:
            self.assertEqual(question_image({'title': 'Solo domanda', 'options': ['$$10$$']}), b'image')
            render.assert_called_once_with('Solo domanda')

    def test_drive_access_is_limited_and_manifest_is_exported(self):
        import re
        artifact = validated_artifacts(json.dumps(quiz_sample()))[0]
        script = artifact_file(artifact, 'gs')[0].decode()
        manifest = json.loads(re.search(r'const MANIFEST_GOOGLE = ([^\n]+);', script)[1])
        self.assertIn('https://www.googleapis.com/auth/drive.file', manifest['oauthScopes'])
        self.assertNotIn('https://www.googleapis.com/auth/drive', manifest['oauthScopes'])
        self.assertNotIn('DriveApp', script)
        self.assertNotIn('https://www.googleapis.com/auth/drive"', script)
        self.assertIn('ignoreDefaultVisibility=true', script)

    def test_temporary_files_are_cleaned_after_sharing_or_import_errors(self):
        artifact = validated_artifacts(json.dumps(quiz_sample()))[0]
        script = artifact_file(artifact, 'gs')[0].decode()
        mock = r"""
const assert = require('assert');
const console = {warn() {}};
const Utilities = {base64Decode() {return [137];},newBlob(bytes, type, name) {return {getBytes() {return bytes;},getName() {return name;}};}};
MODULO_GOOGLE.questions[0].option_images_base64[0]='png';
let mode, operations;
richiestaForms = (id, suffix) => {
 if(suffix) throw Error('import failed');
 return {items:[{itemId:'q',questionItem:{}}]};
};
richiestaDrive = (url, method, payload) => {
 operations.push({url,method,payload});
 if(url.includes('/upload/')) return {id:'created-image'};
 assert(url.includes('/files/created-image'));
 if(method==='post') {
   if(mode==='sharing') throw Error('sharing failed');
   return {id:'public'};
 }
 if(method==='delete' && mode==='revocation') throw Error('revocation failed');
 return {};
};
for(mode of ['sharing','import','revocation']) {
 operations=[];
 assert.throws(()=>inserisciImmaginiRisposte('form'), /failed/);
 assert.equal(operations.filter(o=>o.payload?.trashed).length,1);
 if(mode!=='sharing') assert.equal(operations.filter(o=>o.method==='delete').length,1);
}
"""
        result = subprocess.run(['node', '-'], input=script + mock, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_consent_stops_before_creating_a_form(self):
        artifact = validated_artifacts(json.dumps(quiz_sample()))[0]
        script = artifact_file(artifact, 'gs')[0].decode()
        checks = r"""
const assert = require('assert');
let created = 0, locked = 0;
const FormApp = {create() {created++;}};
const LockService = {getScriptLock() {locked++;}};
const ScriptApp = {AuthMode:{FULL:'full'},requireScopes(mode, scopes) {
 assert.equal(mode,'full');
 assert(scopes.includes('https://www.googleapis.com/auth/forms.body'));
 throw Error('Missing consent');
}};
assert.throws(()=>creaModuloGoogle(), /Missing consent/);
assert.equal(created,0);
assert.equal(locked,0);
"""
        result = subprocess.run(['node', '-'], input=script + checks, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_short_formula_image_has_no_wide_blank_canvas(self):
        import io
        from PIL import Image
        from google_form_math import text_image
        picture = Image.open(io.BytesIO(text_image('$$2^5$$', width=740, margin=24, tight=True)))
        self.assertLess(picture.width, 200)
        self.assertLess(picture.height, 150)

    def test_requested_counts(self):
        raw = json.dumps(quiz_sample())
        request = {'google_form_questions': 1, 'google_form_answers': 4}
        validate_requested_quiz(raw, request)
        for patch in [{'google_form_questions': 2}, {'google_form_answers': 3}]:
            with self.assertRaises(ValueError): validate_requested_quiz(raw, request | patch)
        with self.assertRaises(ValueError): validate_requested_quiz(json.dumps(sample()), request)

    def test_script_creates_correct_quiz_without_duplicate_or_code_injection(self):
        data = quiz_sample()
        data['artifacts'][0]['quiz_questions'][0]['title'] = '\"; throw Error(\"injected\"); //'
        artifact = validated_artifacts(json.dumps(data))[0]
        script = artifact_file(artifact, 'gs')[0].decode()
        mock = r"""
const assert = require('assert');
let created = 0, locked = false;
const saved = {};
const ScriptApp = {AuthMode:{FULL:'full'},requireScopes() {}};
const items = [];
const form = {
  setIsQuiz(v) { assert.equal(v, true); }, setDescription() {},
  getId() { return 'id'; }, getEditUrl() { return 'edit'; }, getPublishedUrl() { return 'public'; },
  addMultipleChoiceItem() {
    const item = {
      setTitle(v) { this.title = v; }, setRequired(v) { this.required = v; },
      setPoints(v) { this.points = v; }, createChoice(value, correct) { return {value, correct}; },
      setChoices(v) { this.choices = v; }, showOtherOption(v) { this.other = v; }
    }; items.push(item); return item;
  }
};
const FormApp = {create(title, published) { created++; assert.equal(published, true); return form; }, openById(id) { assert.equal(id, 'id'); return form; }};
const LockService = {getScriptLock() { return {waitLock() { locked = true; }, releaseLock() { locked = false; }}; }};
const PropertiesService = {getScriptProperties() { return {getProperty(k) { return saved[k]; }, setProperty(k, v) { saved[k] = v; }}; }};
const Utilities = {DigestAlgorithm: {SHA_256: 'sha'}, computeDigest(a, text) { return text; }, base64EncodeWebSafe(text) { return text; }};

"""
        checks = r"""
assert.equal(creaModuloGoogle(), 'edit');
assert.equal(creaModuloGoogle(), 'edit');
assert.equal(created, 1); assert.equal(items.length, 1);
assert.equal(items[0].choices.length, 4);
assert.deepEqual(items[0].choices.map(c => c.correct), [false, true, false, false]);
assert.equal(items[0].points, 1); assert.equal(items[0].required, true);
assert.equal(locked, false);
assert(items[0].title.includes('throw Error'));
"""
        result = subprocess.run(['node', '-'], input=mock + script + checks,
            text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
