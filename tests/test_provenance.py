import json
import os
import tempfile
import subprocess
import venv
import unittest
from pathlib import Path
from unittest.mock import patch
from solvepack.model import validate_manifest, Snapshot
from solvepack.provenance import child_environment, fingerprint, changed_fields


class ProvenanceTests(unittest.TestCase):
    def test_real_virtual_environment_uses_its_launcher_and_installed_dependency(self):
        # No network or pip: a real venv with one fixture-only package.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); runtime=root/'runtime'
            venv.EnvBuilder(with_pip=False,symlinks=True).create(runtime)
            python=runtime/'bin'/'python'
            probe=subprocess.run([str(python),'-c',"import sysconfig;print(sysconfig.get_path('purelib'))"],capture_output=True,text=True,check=True)
            site=Path(probe.stdout.strip());site.mkdir(parents=True,exist_ok=True)
            (site/'solvepack_fixture_dependency.py').write_text("VALUE='hitcon{venv_dependency}'\n")
            metadata=site/'solvepack_venv_fixture-1.0.dist-info';metadata.mkdir()
            (metadata/'METADATA').write_text('Metadata-Version: 2.1\nName: solvepack-venv-fixture\nVersion: 1.0\n')
            challenge=root/'challenge';challenge.mkdir()
            (challenge/'solve.py').write_text('from solvepack_fixture_dependency import VALUE\nprint(VALUE)\n')
            raw=dict(schema_version=1,challenge_id='venv-fixture',solver='solve.py',args=[],inputs=[],dependencies=['solvepack-venv-fixture'],synthetic=True)
            (challenge/'challenge.json').write_text(json.dumps(raw))
            package=Path(__file__).resolve().parents[1]
            run=subprocess.run([str(python),'-m','solvepack','capture',str(challenge)],cwd=package,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            result=json.loads(run.stdout);self.assertEqual(result['candidates'],['hitcon{venv_dependency}'])
            saved=json.loads((challenge/'.solvepack'/'capsules'/(result['id']+'.json')).read_text())
            self.assertEqual(saved['command'][0],str(python))
            self.assertEqual(saved['snapshot_before']['runtime']['packages'],{'solvepack-venv-fixture':'1.0'})
            replay=subprocess.run([str(python),'-m','solvepack','replay',str(challenge),result['id']],cwd=package,capture_output=True,text=True)
            self.assertEqual(replay.returncode,0,replay.stdout+replay.stderr)
            self.assertEqual(json.loads(replay.stdout)['status'],'REPRODUCED')

    def test_credentials_are_not_inherited_and_known_file_bytes_are_hashed(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'SOLVEPACK_TEST_SECRET':'private'}):
            root = Path(directory); (root/'solve.py').write_text('print(1)'); (root/'in.bin').write_bytes(b'abc')
            raw = dict(schema_version=1,challenge_id='toy',solver='solve.py',args=[],inputs=['in.bin'],dependencies=[])
            (root/'challenge.json').write_text(json.dumps(raw))
            snapshot = fingerprint(root,validate_manifest(root,raw))
            self.assertEqual(snapshot.files['in.bin'],'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
            self.assertNotIn('SOLVEPACK_TEST_SECRET',child_environment())
            self.assertEqual(set(child_environment()),{'PATH','LANG','LC_ALL','TZ','PYTHONHASHSEED'})
            changed = Snapshot({**snapshot.files,'in.bin':'0'*64},
                               {**snapshot.runtime,'python_version':'different'},'0'*64)
            self.assertEqual(changed_fields(snapshot,changed),['files.in.bin','runtime.python_version','environment_sha256'])

    def test_declared_package_missing_is_actionable_not_an_empty_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'solve.py').write_text('print(1)')
            raw=dict(schema_version=1,challenge_id='toy',solver='solve.py',args=[],inputs=[],
                     dependencies=['solvepack-fixture-missing-a98e21'])
            (root/'challenge.json').write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError,'dependency.*solvepack-fixture-missing'):
                fingerprint(root,validate_manifest(root,raw))


if __name__ == '__main__': unittest.main()
