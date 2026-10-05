"""Read-only loopback viewer. No solver execution, writes, uploads, or arbitrary file routes."""
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from .report import local_report
from .store import MAX_DOCUMENT_BYTES

DOCS=Path(__file__).resolve().parents[1]/'docs'
TYPES={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.mjs':'text/javascript; charset=utf-8',
       '.json':'application/json','.svg':'image/svg+xml','.py':'text/plain; charset=utf-8'}
ROUTES={('/'+path.relative_to(DOCS).as_posix()):path for path in [DOCS/name for name in ('index.html','style.css','app.mjs','model.mjs','demo.json','icon.svg')]+list((DOCS/'example-files').glob('*')) if path.is_file()}
ROUTES['/']=DOCS/'index.html'


def make_review_server(root: Path,port=0,limit=16):
    root=Path(root).resolve(strict=True)
    if not root.is_dir():raise ValueError('Review root must be a directory.')
    if type(port) is not int or not 0<=port<=65535:raise ValueError('Review port must be 0–65535.')
    if type(limit) is not int or not 1<=limit<=64:raise ValueError('Review limit must be 1–64 recent runs.')
    capability=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body,content_type='application/json'):
            self.send_response(status)
            for name,value in {'Content-Type':content_type,'Content-Length':str(len(body)),'Cache-Control':'no-store',
                               'X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff'}.items():self.send_header(name,value)
            self.end_headers();self.wfile.write(body)
        def failure(self,status,message):self.reply(status,json.dumps({'error':message}).encode())
        def do_GET(self):
            hosts={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in hosts or self.headers.get('Origin') not in {None,*['http://'+host for host in hosts]} or self.headers.get('Sec-Fetch-Site') in ('cross-site','cross-origin'):
                self.failure(403,'Use this viewer directly on localhost.');return
            if self.path=='/private-report.json':
                if not hmac.compare_digest(self.headers.get('X-SolvePack-Capability',''),capability):
                    self.failure(403,'Open the local viewer first.');return
                try:
                    body=json.dumps(local_report(root,limit),ensure_ascii=True,allow_nan=False).encode()
                    if len(body)>MAX_DOCUMENT_BYTES:self.failure(413,'Local report exceeds 2 MiB. Restart review with --limit 1 or use show --full for individual records.');return
                    self.reply(200,body)
                except (ValueError,OSError,RuntimeError) as error:self.failure(409,str(error))
                return
            path=ROUTES.get(self.path)
            if path is None:self.failure(404,'This route is not available.');return
            try:
                body=path.read_bytes()
                if path.name=='index.html':body=body.replace(b'id="local-capability" content=""',b'id="local-capability" content="'+capability.encode()+b'"')
                self.reply(200,body,TYPES.get(path.suffix,'application/octet-stream'))
            except OSError:self.failure(503,'Viewer asset unavailable; restore the installed source files and retry.')
        def do_POST(self):self.failure(405,'This viewer is read-only. Use the local CLI to capture, replay or record receipts.')
        do_PUT=do_POST;do_DELETE=do_POST;do_PATCH=do_POST
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)
