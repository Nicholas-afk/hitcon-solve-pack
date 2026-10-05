import http.client
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from solvepack.review import make_review_server
from solvepack.workflow import capture
from tests.test_workflow import make_workspace


class ReviewTests(unittest.TestCase):
    def test_private_data_requires_capability_loopback_host_origin_and_fixed_read_only_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=make_workspace(Path(directory).resolve());first=capture(root)
            server=make_review_server(root);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_port
            def request(path,headers=None,method='GET'):
                client=http.client.HTTPConnection('127.0.0.1',port,timeout=5);client.request(method,path,headers=headers or {})
                response=client.getresponse();body=response.read();result=(response.status,dict(response.getheaders()),body);client.close();return result
            try:
                status,headers,body=request('/');self.assertEqual(status,200)
                token=re.search(rb'id="local-capability"[^>]*content="([^"]+)"',body)[1].decode()
                self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['X-Frame-Options'],'DENY')
                self.assertEqual(request('/private-report.json')[0],403)
                good={'X-SolvePack-Capability':token}
                for extra in [{'Host':'attacker.example'},{'Origin':'https://attacker.example'},{'Sec-Fetch-Site':'cross-site'}]:
                    self.assertEqual(request('/private-report.json',{**good,**extra})[0],403)
                response=request('/private-report.json',good);self.assertEqual(response[0],200)
                self.assertEqual(json.loads(response[2])['records'][0]['id'],first['id'])
                second=capture(root)
                self.assertEqual(len(json.loads(request('/private-report.json',good)[2])['records']),2)
                self.assertNotIn('Access-Control-Allow-Origin',response[1])
                for path in ['/challenge.json','/.solvepack/receipts.json','/../challenge.json','/%2e%2e/challenge.json']:
                    self.assertEqual(request(path,good)[0],404)
                self.assertEqual(request('/private-report.json',good,'POST')[0],405)
                self.assertEqual(request('/app.mjs')[0],200)
            finally:server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()
