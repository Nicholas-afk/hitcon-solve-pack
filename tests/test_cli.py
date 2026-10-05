import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE=Path(__file__).resolve().parents[1]
def cli(*args):return subprocess.run([sys.executable,'-m','solvepack',*map(str,args)],cwd=PACKAGE,capture_output=True,text=True,timeout=10)


class CliTests(unittest.TestCase):
    def test_init_capture_replay_show_spaces_and_meaningful_exit_codes(self):
        with tempfile.TemporaryDirectory(prefix='private solve ') as directory:
            root=Path(directory).resolve();(root/'solve.py').write_text("import sys;assert sys.argv[1]=='';print('hitcon{synthetic_cli}')")
            created=cli('init',root,'--challenge','synthetic-cli','--solver','solve.py','--arg=','--synthetic')
            self.assertEqual(created.returncode,0,created.stderr)
            self.assertEqual(cli('init',root,'--challenge','x','--solver','solve.py').returncode,1)
            first=cli('capture',root);self.assertEqual(first.returncode,0,first.stderr);run=json.loads(first.stdout)
            self.assertEqual(run['status'],'CANDIDATE');self.assertEqual(run['receipt_history'],[])
            second=cli('replay',root,run['id']);self.assertEqual(second.returncode,0,second.stderr)
            record=json.loads(second.stdout);self.assertEqual(record['status'],'REPRODUCED')
            shown=cli('show',root,record['id']);self.assertEqual(json.loads(shown.stdout)['candidates'],['hitcon{synthetic_cli}'])
            (root/'solve.py').write_text("raise SystemExit('should not run')")
            stale=cli('replay',root,run['id']);self.assertEqual(stale.returncode,2);self.assertEqual(json.loads(stale.stdout)['status'],'STALE')
            bad=cli('capture',root,'--timeout','nan');self.assertEqual(bad.returncode,1);self.assertIn('Timeout',bad.stderr);self.assertNotIn('Traceback',bad.stderr)
            self.assertEqual(cli('show',root,'../escape').returncode,1)


if __name__=='__main__':unittest.main()
