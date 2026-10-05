import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from solvepack.runner import run_solver
from solvepack.provenance import child_environment


class RunnerIntegrationTests(unittest.TestCase):
    def test_empty_literal_arguments_binary_output_and_credentials_are_preserved_or_filtered(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'SOLVEPACK_TEST_SECRET':'must-not-inherit'}):
            root=Path(directory)
            script="import os,sys; assert sys.argv[1]=='',sys.argv; assert sys.argv[2]==';touch marker'; assert 'SOLVEPACK_TEST_SECRET' not in os.environ; sys.stdout.buffer.write(b'\\xff\\x00hitcon{synthetic_bytes}\\n'); sys.stderr.buffer.write(b'\\x80')"
            result=run_solver([sys.executable,'-c',script,'',';touch marker'],root,child_environment())
            self.assertEqual(result.run_status,'OK')
            self.assertEqual(result.stdout,b'\xff\x00hitcon{synthetic_bytes}\n')
            self.assertEqual(result.stderr,b'\x80')
            self.assertFalse((root/'marker').exists())


if __name__ == '__main__':unittest.main()
