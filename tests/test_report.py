import base64
from pathlib import Path
import tempfile
import unittest
from solvepack.workflow import capture,replay
from solvepack.receipts import record_receipt
from solvepack.report import local_report
from tests.test_workflow import make_workspace


class ReportTests(unittest.TestCase):
    def test_workspace_title_distinguishes_same_named_folders_and_bounds_long_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            a=root/'a'/'practice';b=root/'b'/'practice'
            a.mkdir(parents=True);b.mkdir(parents=True)
            self.assertEqual(local_report(a)['title'],'Local workspace: '+str(a))
            self.assertNotEqual(local_report(a)['title'],local_report(b)['title'])
            long=root
            for _ in range(5):long=long/('z'*60)
            long.mkdir(parents=True)
            title=local_report(long)['title']
            self.assertLessEqual(len(title),256)
            self.assertTrue(title.endswith(str(long)[-229:]))
            self.assertIn('…',title)

    def test_new_receipt_time_is_canonical_utc(self):
        with tempfile.TemporaryDirectory() as directory:
            root=make_workspace(Path(directory).resolve());run=capture(root);(root/'receipt.txt').write_text('synthetic fixture')
            entry=record_receipt(root,run['id'],run['candidates'][0],'accepted','2026-10-24 08:00:00+08:00','Synthetic fixture','receipt.txt')
            self.assertEqual(entry['official_time'],'2026-10-24T00:00:00+00:00')

    def test_existing_aware_times_project_to_a_verifiable_browser_report_without_rewriting_history(self):
        import json,subprocess
        from solvepack.store import load_json,atomic_json,capsule_path
        with tempfile.TemporaryDirectory() as directory:
            root=make_workspace(Path(directory).resolve());run=capture(root);(root/'receipt.txt').write_text('synthetic fixture')
            record_receipt(root,run['id'],run['candidates'][0],'accepted','2026-10-24T00:00:00Z','Synthetic fixture','receipt.txt')
            ledger_path=root/'.solvepack/receipts.json';ledger=load_json(ledger_path)
            ledger['entries'][0]['official_time']='2026-10-24 08:00:00+08:00'
            ledger['entries'][0]['recorded_at']='2026-10-24 00:00:00+00:00';atomic_json(ledger_path,ledger);old=ledger_path.read_bytes()
            path=capsule_path(root,run['id']);raw=load_json(path);raw['created_at']='2026-10-24 00:00:00+00:00';atomic_json(path,raw);old_run=path.read_bytes()
            report=local_report(root)
            module=(Path(__file__).resolve().parents[1]/'docs/model.mjs').as_uri()
            script=f"import {{parseReport,verifyReport}} from {json.dumps(module)};let raw='';for await(const chunk of process.stdin)raw+=chunk;const report=await verifyReport(parseReport(raw,{{allowLocal:true}}),{{allowLocal:true}});console.log(report.records[0].receipts[0].official_time);"
            result=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(report),text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),'2026-10-24T00:00:00+00:00')
            self.assertEqual(ledger_path.read_bytes(),old);self.assertEqual(path.read_bytes(),old_run)

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
