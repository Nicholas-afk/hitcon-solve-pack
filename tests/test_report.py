import base64
from pathlib import Path
import tempfile
import unittest
from solvepack.workflow import capture,replay
from solvepack.receipts import record_receipt
from solvepack.report import local_report
from tests.test_workflow import make_workspace


class ReportTests(unittest.TestCase):
    def test_real_private_records_preserve_bytes_issues_and_explicit_synthetic_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=make_workspace(Path(directory).resolve(),"import sys;sys.stdout.buffer.write(b'\\xffhitcon{synthetic_workflow}\\n')")
            first=capture(root);second=replay(root,first['id'])
            (root/'receipt.txt').write_text('SYNTHETIC RECEIPT — NOT ORGANIZER ACCEPTANCE')
            record_receipt(root,second['id'],second['candidates'][0],'accepted','2026-10-24T00:00:00Z','Synthetic fixture','receipt.txt')
            (root/'input.json').write_text('changed');third=replay(root,first['id'])
            report=local_report(root)
            self.assertEqual(report['report_type'],'solvepack-local');self.assertFalse(report['synthetic'])
            rows={row['id']:row for row in report['records']}
            self.assertEqual(base64.b64decode(rows[second['id']]['output']['stdout']),b'\xffhitcon{synthetic_workflow}\n')
            self.assertTrue(rows[second['id']]['synthetic']);self.assertTrue(rows[second['id']]['receipts'][0]['evidence_valid'])
            self.assertEqual(rows[third['id']]['execution_status'],'NOT_RUN')
            self.assertIn('files.input.json',rows[third['id']]['issues'])

    def test_new_declared_file_has_no_invented_captured_hash_and_empty_workspace_is_real(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            self.assertEqual(local_report(root)['records'],[])
            make_workspace(root);first=capture(root)
            raw=json.loads((root/'challenge.json').read_text());raw['inputs'].append('new.bin');(root/'new.bin').write_bytes(b'abc');(root/'challenge.json').write_text(json.dumps(raw))
            changed=replay(root,first['id']);row=next(r for r in local_report(root)['records'] if r['id']==changed['id'])
            new=next(file for file in row['files'] if file['path']=='new.bin')
            self.assertIsNone(new['baseline_sha256']);self.assertEqual(new['observed_sha256'],'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')


if __name__=='__main__':unittest.main()
