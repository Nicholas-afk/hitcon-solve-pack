import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from solvepack.store import atomic_json, load_json, workspace_lock, capsule_path


class StoreTests(unittest.TestCase):
    def test_new_record_is_private_and_exclusive_and_lock_releases_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            with self.assertRaisesRegex(RuntimeError,'injected'):
                with workspace_lock(root):
                    path=capsule_path(root,'a'*32)
                    atomic_json(path,{'observed':'first'},exclusive=True)
                    self.assertEqual(path.stat().st_mode & 0o777,0o600)
                    self.assertEqual(path.parent.stat().st_mode & 0o777,0o700)
                    old=path.read_bytes()
                    with self.assertRaises(FileExistsError): atomic_json(path,{'observed':'second'},exclusive=True)
                    self.assertEqual(path.read_bytes(),old)
                    with self.assertRaisesRegex(ValueError,'locked'):
                        with workspace_lock(root): pass
                    raise RuntimeError('injected')
            with workspace_lock(root): self.assertEqual(load_json(path),{'observed':'first'})

    def test_atomic_failure_and_oversize_preserve_old_ledger_and_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            with workspace_lock(root):
                path=root/'.solvepack/receipts.json'; atomic_json(path,{'history':['first']})
                old=path.read_bytes()
                with patch('solvepack.store.os.replace',side_effect=OSError('injected write failure')):
                    with self.assertRaises(OSError): atomic_json(path,{'history':['second']})
                self.assertEqual(path.read_bytes(),old)
                with self.assertRaisesRegex(ValueError,'2 MiB'): atomic_json(path,{'x':'x'*(2*1024*1024)})
                self.assertEqual(path.read_bytes(),old)
                self.assertFalse(list(path.parent.glob('.tmp-*')))

    def test_invalid_duplicate_nonfinite_oversized_and_symlink_json_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); path=root/'record.json'
            for source in ['{bad','[]','{"a":1,"a":2}','{"x":NaN}',' '* (2*1024*1024+1)]:
                path.write_text(source)
                with self.assertRaises(ValueError): load_json(path)
            alias=root/'alias.json';alias.symlink_to(path)
            with self.assertRaises(ValueError):load_json(alias)
            with self.assertRaises(ValueError):atomic_json(alias,{})
            with self.assertRaises(ValueError):atomic_json(path,{'nan':float('nan')})

    def test_symlink_store_and_traversing_ids_do_not_write_outside_workspace(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as elsewhere:
            root=Path(directory).resolve(); target=Path(elsewhere).resolve();(root/'.solvepack').symlink_to(target)
            with self.assertRaises(ValueError):
                with workspace_lock(root):pass
            self.assertFalse(list(target.iterdir()))
            for value in ['../record','A'*32,'a'*31,'a'*33]:
                with self.assertRaises(ValueError):capsule_path(root,value)


if __name__ == '__main__': unittest.main()
