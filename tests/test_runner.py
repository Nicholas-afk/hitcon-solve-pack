import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from solvepack.runner import run_solver


class RunnerTests(unittest.TestCase):
    def run_code(self, code, *, timeout=2, limit=1048576, args=()):
        return run_solver([sys.executable, '-c', code, *args], Path.cwd(),
                          {'PATH': os.environ.get('PATH', '/usr/bin:/bin')}, timeout, limit)

    def test_literal_argument_and_dual_streams(self):
        r = self.run_code("import sys;print(sys.argv[1]);print('error text',file=sys.stderr)",
                          args=('a; $(no command)',))
        self.assertEqual((r.run_status, r.stdout, r.stderr), ('OK', b'a; $(no command)\n', b'error text\n'))

    def test_output_cap_stops_flood(self):
        r = self.run_code("import os;[os.write(1,b'x'*4096) for _ in range(1000)]", limit=4096)
        self.assertEqual(r.run_status, 'OUTPUT_LIMIT')
        self.assertLessEqual(len(r.stdout) + len(r.stderr), 4096)
        self.assertLess(r.elapsed_s, 2)

    def test_flag_text_does_not_override_exit_failure(self):
        r = self.run_code("print('hitcon{synthetic_decoy}');raise SystemExit(7)")
        self.assertEqual((r.run_status, r.exit_code), ('FAILED', 7))

    def test_timeout_returns(self):
        r = self.run_code("import time;time.sleep(2)", timeout=.1)
        self.assertEqual(r.run_status, 'TIMEOUT')
        self.assertLess(r.elapsed_s, 2)

    def test_successful_parent_does_not_leave_a_same_group_child_running(self):
        with tempfile.TemporaryDirectory() as root:
            marker = str(Path(root) / 'pid')
            child = "import os,time,pathlib;pathlib.Path(" + repr(marker) + ").write_text(str(os.getpid()));time.sleep(2)"
            code = "import subprocess,sys,time,pathlib;subprocess.Popen([sys.executable,'-c'," + repr(child) + "],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\nwhile not pathlib.Path(" + repr(marker) + ").exists(): time.sleep(.01)"
            r = self.run_code(code)
            self.assertEqual(r.run_status, 'OK')
            pid = Path(marker).read_text()
            stat = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', pid], capture_output=True, text=True).stdout.strip()
            self.assertTrue(not stat or stat.startswith('Z'), stat)

    def test_saturated_dual_streams_are_complete(self):
        r = self.run_code("import os;[(os.write(1,b'a'*2048),os.write(2,b'b'*2048)) for _ in range(64)]")
        self.assertEqual((r.run_status, len(r.stdout), len(r.stderr)), ('OK', 131072, 131072))

    def test_terminated_leader_and_term_ignoring_child_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            marker = str(Path(root) / 'pid')
            child = "import os,signal,time,pathlib;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path(" + repr(marker) + ").write_text(str(os.getpid()));time.sleep(2)"
            code = "import subprocess,sys;subprocess.Popen([sys.executable,'-c'," + repr(child) + "])"
            r = self.run_code(code, timeout=.4)
            self.assertEqual(r.run_status, 'TIMEOUT')
            self.assertTrue(Path(marker).exists())
            pid = Path(marker).read_text()
            stat = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', pid], capture_output=True, text=True).stdout.strip()
            self.assertTrue(not stat or stat.startswith('Z'), stat)

    def test_invalid_limits_and_missing_executable(self):
        for limit in [0, -1, 1.5]:
            with self.assertRaises(ValueError):
                self.run_code('pass', limit=limit)
        for timeout in [0, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                self.run_code('pass', timeout=timeout)
        r = run_solver(['/a/nonexistent/solvepack-executable'], Path.cwd(), {}, .1, 100)
        self.assertEqual(r.run_status, 'ERROR')


if __name__ == '__main__':
    unittest.main()
