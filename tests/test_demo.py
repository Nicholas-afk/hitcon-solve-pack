import hashlib
import json
import re
import unittest

from solvepack.demo_report import build_demo


class DemoTests(unittest.TestCase):
    def test_real_synthetic_workflow_and_failure_evidence(self):
        report = build_demo()
        self.assertEqual((report['schema_version'], report['synthetic'], report['report_type']),
                         (1, True, 'solvepack-synthetic'))
        rows = {r['id']: r for r in report['records']}
        self.assertEqual(rows['modular-capture']['output']['stdout'], 'hitcon{synthetic_modular_257}\n')
        self.assertEqual(rows['modular-replay']['output'], rows['modular-capture']['output'])
        self.assertEqual(rows['bytes-replay']['output']['stdout'], 'hitcon{synthetic_xor_bytes}\n')
        self.assertEqual(rows['modular-stale']['execution_status'], 'NOT_RUN')
        self.assertEqual(rows['modular-stale']['duration_ms'], 0)
        self.assertNotEqual(rows['modular-stale']['files'][0]['baseline_sha256'], rows['modular-stale']['files'][0]['observed_sha256'])
        self.assertEqual(len(re.findall(r'hitcon\{[^}]+\}', rows['ambiguous-capture']['output']['stdout'])), 2)
        self.assertEqual(rows['failed-capture']['exit_code'], 7)
        self.assertEqual(rows['timeout-capture']['execution_status'], 'TIMEOUT')
        for record in rows.values():
            self.assertTrue(record['created_at'].endswith('+00:00'))
            for stream in ['stdout', 'stderr']:
                self.assertEqual(record['output'][stream + '_sha256'], hashlib.sha256(record['output'][stream].encode()).hexdigest())

    def test_report_has_no_personal_paths_or_acceptance(self):
        report = build_demo()
        text = json.dumps(report)
        for value in ['ncywtanner', '/Users/', '2008', 'accepted', 'receipts']:
            self.assertNotIn(value, text.lower() if value == 'accepted' else text)
        self.assertLess(len(text.encode()), 2097152)


if __name__ == '__main__':
    unittest.main()
