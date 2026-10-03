"""Persistent generated images. Only generate_images may contact the provider."""
import hashlib
import io
import json
import os
import threading
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types
from visual_assets import Asset

ROOT = Path(__file__).resolve().parent / 'generated_assets'
LOCK = threading.Lock()
MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-2.5-flash-image')


def asset_key(resource):
    return hashlib.sha256((MODEL+'\n'+resource.get('generation_prompt','')).encode()).hexdigest()


def cached_image(resource):
    if not resource.get('generation_prompt'):return None
    path=ROOT/(asset_key(resource)+'.png')
    if not path.is_file():return None
    with Image.open(path) as im:w,h=im.size
    scale=min(360/w,240/h)
    return Asset(path,w*scale,h*scale,resource.get('alt_text','Immagine'))


def request_image(prompt):
    key=os.environ.get('GEMINI_API_KEY','')
    if not key:raise ValueError('GEMINI_API_KEY non configurata')
    options=types.HttpOptions(timeout=180000,retry_options=types.HttpRetryOptions(attempts=1))
    with genai.Client(api_key=key,http_options=options) as client:
        result=client.models.generate_content(model=MODEL,contents=prompt,config=types.GenerateContentConfig(response_modalities=['IMAGE']))
    for candidate in result.candidates or []:
        for part in candidate.content.parts if candidate.content else []:
            if part.inline_data and part.inline_data.mime_type.startswith('image/'):
                return part.inline_data.data
    raise ValueError('Il servizio non ha restituito un?immagine')


def generate_images(raw, limit):
    try:manifest=json.loads(raw)
    except (ValueError,TypeError):return ["Immagini non generate: risposta JSON non valida."]
    if not isinstance(manifest,dict):return ["Immagini non generate: struttura JSON non valida."]
    messages=[];calls=0
    used={b.get('ref') for a in manifest.get('artifacts',[]) for c in a.get('containers',[]) for b in c.get('blocks',[]) if b.get('kind')=='image'}
    seen=set()
    with LOCK:
        for resource in manifest.get('generated_images',[]):
            if resource.get('id') not in used or not resource.get('generation_prompt'):continue
            key=asset_key(resource)
            if key in seen:continue
            seen.add(key)
            if cached_image(resource):continue
            if calls>=limit:
                messages.append(f"{resource['id']}: limite immagini raggiunto ({limit}).");continue
            calls+=1
            try:
                content=request_image(resource['generation_prompt'])
                with Image.open(io.BytesIO(content)) as source:
                    source.load();out=io.BytesIO();source.convert('RGB').save(out,format='PNG')
                ROOT.mkdir(exist_ok=True)
                tmp=ROOT/(key+'.tmp');tmp.write_bytes(out.getvalue());tmp.replace(ROOT/(key+'.png'))
            except Exception as error:
                messages.append(f"{resource['id']}: generazione immagine non riuscita ({type(error).__name__}); nessun nuovo tentativo.")
    return messages
