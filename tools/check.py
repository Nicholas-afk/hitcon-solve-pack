"""Run both behavior suites using local installed runtimes."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=root, check=True)
subprocess.run(['node', '--test', *[str(path.relative_to(root)) for path in sorted((root/'tests').glob('*.test.mjs'))]], cwd=root, check=True)
print('All Python and browser-model behavior checks passed.')
