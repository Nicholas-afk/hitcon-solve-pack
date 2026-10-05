import base64
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from solvepack.workflow import capture, replay, show
from solvepack.store import capsule_path, load_json, atomic_json


def make_workspace(root, script="print('hitcon{synthetic_workflow}')", **changes):
    root.mkdir(parents=True,exist_ok=True)
    (root/'solve.py').write_text(script)
    (root/'input.json').write_text('{"value":1}\n')
    manifest=dict(schema_version=1,challenge_id='synthetic-workflow',solver='solve.py',args=['input.json'],
                  inputs=['input.json'],dependencies=[],synthetic=True,category='Test',**changes)
    (root/'challenge.json').write_text(json.dumps(manifest))
    return root


class WorkflowTests(unittest.TestCase):
    def test_capture_replay_survive_reload_without_replacing_baseline_and_preserve_binary(self):
        with tempfile.TemporaryDirectory(prefix='solve pack ') as directory:
            root=make_workspace(Path(directory).resolve(),"import sys;sys.stdout.buffer.write(b'\\xffhitcon{synthetic_workflow}\\n');sys.stderr.buffer.write(b'\\x80')")
            first=capture(root);before=capsule_path(root,first['id']).read_bytes()
            self.assertEqual(first['status'],'CANDIDATE');self.assertEqual(first['candidates'],['hitcon{synthetic_workflow}'])
            self.assertEqual(base64.b64decode(first['output']['stderr_base64']),b'\x80')
            second=replay(root,first['id'])
            self.assertEqual(second['status'],'REPRODUCED')
            self.assertNotEqual(second['id'],first['id'])
            self.assertEqual(show(root,second['id'])['status'],'REPRODUCED')
            self.assertEqual(capsule_path(root,first['id']).read_bytes(),before)
            self.assertEqual(first['timeout_s'],30.0)

    def test_input_solver_manifest_runtime_and_moved_workspace_block_before_launch(self):
        script="from pathlib import Path;Path('launched').write_text('yes');print('hitcon{synthetic_workflow}')"
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory).resolve()
            for change in ['input','solver','manifest','runtime','missing','moved']:
                with self.subTest(change=change):
                    root=make_workspace(parent/change,script);first=capture(root);(root/'launched').unlink()
                    if change=='input':(root/'input.json').write_text('{"value":2}\n')
                    if change=='solver':(root/'solve.py').write_text(script+'\n# changed')
                    if change=='manifest':(root/'challenge.json').write_text((root/'challenge.json').read_text()+'\n')
                    if change=='missing':(root/'input.json').unlink()
                    if change=='moved':
                        moved=parent/'relocated';shutil.move(root,moved);root=moved
                    if change=='runtime':
                        with patch('solvepack.provenance.platform.machine',return_value='different-machine'):
                            second=replay(root,first['id'])
                    else:second=replay(root,first['id'])
                    self.assertEqual(second['status'],'STALE')
                    self.assertEqual(second['execution_status'],'NOT_RUN')
                    self.assertFalse((root/'launched').exists())
                    self.assertEqual(show(root,second['id'])['status'],'STALE')

    def test_post_run_input_mutation_invalidates_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=make_workspace(Path(directory).resolve(),"from pathlib import Path;Path('input.json').write_text('changed');print('hitcon{synthetic_workflow}')")
            result=capture(root)
            self.assertEqual(result['status'],'STALE')
            self.assertIn('files.input.json',result['issues'])

    def test_ambiguity_failure_timeout_and_uncovered_nondeterminism_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory).resolve()
            for name,script,expected in [('ambiguous',"print('hitcon{a} hitcon{b}')",'AMBIGUOUS'),
                                         ('failed',"print('hitcon{a}');raise SystemExit(7)",'FAILED'),
                                         ('timeout','import time;time.sleep(2)','TIMEOUT'),
                                         ('none',"print('no candidate')",'NO_CANDIDATE')]:
                result=capture(make_workspace(parent/name,script),timeout_s=.1)
                self.assertEqual(result['status'],expected)
            root=make_workspace(parent/'different',"from pathlib import Path;p=Path('undeclared-counter');n=int(p.read_text())+1 if p.exists() else 1;p.write_text(str(n));print('hitcon{synthetic_'+str(n)+'}')")
            first=capture(root);self.assertEqual(replay(root,first['id'])['status'],'DIFFERENT')

    def test_timeout_is_validated_and_reused_and_only_capture_can_be_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root=make_workspace(Path(directory).resolve())
            for value in [True,0,.01,float('nan'),float('inf'),3601]:
                with self.assertRaises(ValueError):capture(root,timeout_s=value)
            first=capture(root,timeout_s=120)
            second=replay(root,first['id']);self.assertEqual(second['timeout_s'],120)
            with self.assertRaisesRegex(ValueError,'capture'):replay(root,second['id'])

    def test_tampered_stream_status_command_snapshot_and_schema_reject_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root=make_workspace(Path(directory).resolve());first=capture(root);path=capsule_path(root,first['id']);old=path.read_bytes()
            for mutate in [lambda r:r.update(status='REPRODUCED'),lambda r:r.update(status=[]),
                           lambda r:r.update(execution_status={}),lambda r:r.update(schema_version=9),
                           lambda r:r['output'].update(stdout_base64='aGl0Y29ue2ZvcmdlZH0='),
                           lambda r:r.update(command=['/bad','escape.py']),
                           lambda r:r['snapshot_before']['files'].pop('input.json'),
                           lambda r:r.update(candidates=['hitcon{forged}'])]:
                raw=json.loads(old);mutate(raw);atomic_json(path,raw)
                with self.assertRaises(ValueError):show(root,first['id'])
                path.write_bytes(old)

    def test_both_shipped_examples_have_known_candidates_and_reproduce(self):
        package=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            for name,want in [('arithmetic','hitcon{synthetic_modular_257}'),('bytes','hitcon{synthetic_xor_bytes}')]:
                root=Path(directory).resolve()/name
                shutil.copytree(package/'examples'/name,root)
                first=capture(root)
                self.assertEqual(first['candidates'],[want]);self.assertEqual(replay(root,first['id'])['status'],'REPRODUCED')

    def test_large_candidate_metadata_is_not_written_and_existing_record_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            root=make_workspace(Path(directory).resolve());first=capture(root);path=capsule_path(root,first['id']);old=path.read_bytes()
            (root/'solve.py').write_text("import sys;sys.stdout.write('hitcon{'+('x'*900000)+'}')")
            with self.assertRaisesRegex(ValueError,'2 MiB'):capture(root)
            self.assertEqual(path.read_bytes(),old)
            self.assertEqual(len(list(path.parent.glob('*.json'))),1)


if __name__ == '__main__':unittest.main()
