import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from solvepack.model import validate_manifest, Snapshot
from solvepack.provenance import child_environment, fingerprint, changed_fields


class ProvenanceTests(unittest.TestCase):
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
