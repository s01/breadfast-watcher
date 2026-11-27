"""Compressed public catalogue GETs with optional validated ETag caching."""
import hashlib, json, os, subprocess, tempfile, threading
from pathlib import Path

_lock=threading.Lock()
_stats={'requests':0,'not_modified':0,'download_bytes':0}

class HTTPFailure(RuntimeError):
    def __init__(self,status,retry_after=60):
        self.status=status;self.retry_after=retry_after
        super().__init__('Catalogue HTTP request failed ('+str(status)+')')

def statistics():
    with _lock:return dict(_stats)

def read_json(url):
    directory=os.environ.get('BREADFAST_HTTP_CACHE_DIR')
    cache=None; cached=None
    if directory:
        root=Path(directory);root.mkdir(parents=True,exist_ok=True)
        cache=root/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        try:
            value=json.loads(cache.read_text())
            if isinstance(value.get('etag'),str) and not any(c in value['etag'] for c in '\r\n') and 'data' in value:cached=value
        except (OSError,ValueError,AttributeError):pass
    for attempt in range(2):
        with tempfile.TemporaryDirectory(prefix='breadfast-http-') as temporary:
            body=Path(temporary)/'body';headers=Path(temporary)/'headers'
            command=['curl','--silent','--show-error','--fail','--compressed','--max-time','30',
                     '--dump-header',str(headers),'--output',str(body),'--write-out','%{http_code} %{size_download}']
            if cached:command+=['--header','If-None-Match: '+cached['etag']]
            result=subprocess.run(command+[url],capture_output=True,text=True)
            status,_,download=result.stdout.partition(' ')
            with _lock:
                _stats['requests']+=1
                try:_stats['download_bytes']+=int(download)
                except ValueError:pass
            response_headers={}
            if headers.exists():
                for line in headers.read_text().splitlines():
                    if line.startswith('HTTP/'):response_headers={}
                    elif ':' in line:
                        key,value=line.split(':',1);response_headers[key.lower()]=value.strip()
            if result.returncode:
                retry=response_headers.get('retry-after','60')
                raise HTTPFailure(int(status) if status.isdigit() else 0,min(3600,int(retry)) if retry.isdigit() else 60)
            if status=='304':
                if cached:
                    with _lock:_stats['not_modified']+=1
                    return cached['data']
                continue
            if status!='200':raise RuntimeError('Unexpected catalogue HTTP status '+status)
            data=json.loads(body.read_text())
            etag=response_headers.get('etag')
            if cache and etag:
                # No authorization headers, cookies or URL values are persisted.
                raw=json.dumps({'etag':etag,'data':data},ensure_ascii=False)
                stage=cache.with_suffix('.tmp');stage.write_text(raw);stage.replace(cache)
            return data
    raise RuntimeError('Catalogue returned 304 without a valid cached response')
