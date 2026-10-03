"""Explicit directive cache; no generation retries or silent fallback."""
import hashlib
import json
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from google.genai import types

FILE=Path(__file__).resolve().parent/'gemini_cache_index.json'
LOCK=threading.Lock()


def acquire(client,model,instructions,schema,api_key,minutes):
    signature=hashlib.sha256(json.dumps([model,instructions,schema,api_key,minutes],sort_keys=True).encode()).hexdigest()
    now=datetime.now(timezone.utc)
    with LOCK:
        try:entries=json.loads(FILE.read_text(encoding='utf8'))
        except (OSError,ValueError):entries={}
        entries={k:v for k,v in entries.items() if datetime.fromisoformat(v['expires'])>now+timedelta(seconds=30)}
        if signature in entries:return dict(entries[signature],state='reused')
        cache=client.caches.create(model=model,config=types.CreateCachedContentConfig(
            display_name='AgenteDocente-'+signature[:12],system_instruction=instructions,ttl=f'{minutes*60}s'))
        entry={'name':cache.name,'expires':cache.expire_time.isoformat()}
        entries[signature]=entry
        tmp=FILE.with_suffix('.tmp');tmp.write_text(json.dumps(entries),encoding='utf8');tmp.replace(FILE)
        return dict(entry,state='created')
