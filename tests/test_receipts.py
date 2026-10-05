import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from solvepack.workflow import capture,show
from solvepack.receipts import record_receipt
from tests.test_workflow import make_workspace

TIME='2026-10-24T00:00:00+00:00'


class ReceiptTests(unittest.TestCase):
    def prepare(self,root,script="print('hitcon{synthetic_workflow}')"):
        make_workspace(root,script);(root/'receipt.txt').write_text('SYNTHETIC RECEIPT — NOT ORGANIZER ACCEPTANCE\n')
        return capture(root)

    def save(self,root,run,state='accepted',candidate='hitcon{synthetic_workflow}',**changes):
        values=dict(official_time=TIME,source='Synthetic response fixture',evidence='receipt.txt',points=12)
        values.update(changes)
        return record_receipt(root,run['id'],candidate,state,**values)

    def test_capture_has_no_acceptance_and_outcome_requires_time_source_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();run=self.prepare(root)
            self.assertEqual(show(root,run['id'])['receipt_history'],[])
            for changes in [dict(official_time=None),dict(official_time='2026-10-24T00:00:00'),dict(source=None),dict(evidence=None),dict(evidence='../escape')]:
                with self.subTest(changes=changes),self.assertRaises(ValueError):self.save(root,run,**changes)
            attempted=record_receipt(root,run['id'],run['candidates'][0],'attempted')
            self.assertEqual(attempted['state'],'attempted')
            self.assertIsNone(attempted['official_time'])

    def test_candidate_binding_requires_explicit_choice_and_complete_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory).resolve();root=parent/'ambiguous';run=self.prepare(root,"print('hitcon{a} hitcon{b}')")
            with self.assertRaises(ValueError):self.save(root,run,candidate='hitcon{wrong}')
            self.save(root,run,candidate='hitcon{b}')
            self.assertEqual(show(root,run['id'])['receipt_history'][0]['candidate'],'hitcon{b}')
            bad=parent/'failed';failed=self.prepare(bad,"print('hitcon{synthetic_workflow}');raise SystemExit(7)")
            with self.assertRaisesRegex(ValueError,'complete'):self.save(bad,failed)
            self.assertEqual(record_receipt(bad,failed['id'],failed['candidates'][0],'attempted')['state'],'attempted')

    def test_hash_integrity_and_restart_history_preserve_earlier_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();run=self.prepare(root)
            self.save(root,run);self.save(root,run,state='rejected',points=None)
            history=show(root,run['id'])['receipt_history'];self.assertEqual([entry['state'] for entry in history],['accepted','rejected'])
            self.assertTrue(all(entry['evidence_valid'] for entry in history))
            self.assertTrue(all(entry['synthetic'] for entry in history))
            self.assertIn('Synthetic',show(root,run['id'])['acceptance_note'])
            old=(root/'.solvepack/receipts.json').read_bytes();(root/'receipt.txt').write_text('changed')
            damaged=show(root,run['id'])['receipt_history'];self.assertTrue(all(entry['evidence_valid'] is False for entry in damaged))
            self.assertIn('changed',damaged[0]['evidence_problem'])
            self.assertEqual((root/'.solvepack/receipts.json').read_bytes(),old)
            (root/'receipt.txt').unlink();self.assertFalse(show(root,run['id'])['receipt_history'][0]['evidence_valid'])

    def test_invalid_points_symlink_and_partial_ledger_write_preserve_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();run=self.prepare(root);self.save(root,run)
            path=root/'.solvepack/receipts.json';old=path.read_bytes()
            for value in [-1,True,1.5]:
                with self.assertRaises(ValueError):self.save(root,run,points=value)
            (root/'alias').symlink_to(root/'receipt.txt')
            with self.assertRaises(ValueError):self.save(root,run,evidence='alias')
            with patch('solvepack.store.os.replace',side_effect=OSError('injected')):
                with self.assertRaises(OSError):self.save(root,run,state='rejected')
            self.assertEqual(path.read_bytes(),old)


if __name__=='__main__':unittest.main()
