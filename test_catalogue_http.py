import gzip, http.server, json, os, tempfile, threading, unittest
from unittest.mock import patch
import catalogue_http

class CacheTests(unittest.TestCase):
    def test_gzip_cache_is_revalidated_and_changed_prices_are_downloaded(self):
        current={'sale':50};responses=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                etag='"sale-'+str(current['sale'])+'"'
                if self.headers.get('If-None-Match')==etag:
                    responses.append(304);self.send_response(304);self.end_headers();return
                responses.append(200);data=gzip.compress(json.dumps({'salePrice':current['sale']}).encode())
                self.send_response(200);self.send_header('ETag',etag);self.send_header('Content-Encoding','gzip');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'BREADFAST_HTTP_CACHE_DIR':d}):
                url=f'http://127.0.0.1:{server.server_port}/products'
                self.assertEqual(catalogue_http.read_json(url),{'salePrice':50})
                self.assertEqual(catalogue_http.read_json(url),{'salePrice':50})
                current['sale']=1
                self.assertEqual(catalogue_http.read_json(url),{'salePrice':1})
                self.assertEqual(responses,[200,304,200])
                # Broken local cache must cause a fresh request, not stale success.
                from pathlib import Path
                next(Path(d).glob('*.json')).write_text('broken')
                self.assertEqual(catalogue_http.read_json(url),{'salePrice':1})
                self.assertEqual(responses[-1],200)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
