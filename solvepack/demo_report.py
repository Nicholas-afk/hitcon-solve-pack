"""Generate a public-safe report from actual fixed toy solver executions."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

from .runner import run_solver

DOCS = Path(__file__).resolve().parents[1] / 'docs'
FILES = DOCS / 'example-files'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_demo() -> dict:
    fixtures = {
        'input.json': {'modulus': 257, 'multiplier': 17, 'offset': 29,
                       'encoded': [(ord(char) * 17 + 29) % 257 for char in 'hitcon{synthetic_modular_257}']},
        'bytes-input.json': {'key': 91, 'encoded': [ord(char) ^ 91 for char in 'hitcon{synthetic_xor_bytes}']},
    }
    for name, value in fixtures.items():
        (FILES / name).write_text(json.dumps(value, indent=2) + '\n')
    changed = dict(fixtures['input.json'], offset=30)
    (FILES / 'input-changed.json').write_text(json.dumps(changed, indent=2) + '\n')
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C',
           'LC_ALL': 'C', 'TZ': 'UTC', 'PYTHONHASHSEED': '0'}
    records = []
    with tempfile.TemporaryDirectory(prefix='solvepack-synthetic-') as directory:
        root = Path(directory)
        for path in FILES.iterdir():
            if path.is_file():
                (root / path.name).write_bytes(path.read_bytes())

        def add(identifier, challenge, category, argv, declared, baseline=None, changed_input=False, timeout=2):
            file_rows = []
            for name in declared:
                source = FILES / name
                observed = FILES / 'input-changed.json' if changed_input and name == 'input.json' else source
                file_rows.append({'path': name, 'role': 'solver' if name.endswith('.py') else 'input',
                                  'baseline_sha256': digest(source.read_bytes()),
                                  'observed_sha256': digest(observed.read_bytes())})
            result = None if changed_input else run_solver(argv, root, env, timeout)
            stdout = result.stdout.decode('utf-8') if result else ''
            stderr = result.stderr.decode('utf-8') if result else ''
            record = {'id': identifier, 'challenge': challenge, 'category': category,
                      'kind': 'replay' if baseline else 'capture', 'created_at': now(),
                      'runtime': f'Python {platform.python_version()} · {platform.system()} {platform.machine()}',
                      'duration_ms': round(result.elapsed_s * 1000, 3) if result else 0,
                      'command': ['python3', *argv[1:]],
                      'timeout_s': timeout, 'exit_code': result.exit_code if result else None,
                      'execution_status': result.run_status if result else 'NOT_RUN',
                      'files': file_rows,
                      'output': {'stdout': stdout, 'stderr': stderr,
                                 'stdout_sha256': digest(stdout.encode()), 'stderr_sha256': digest(stderr.encode())}}
            if baseline:
                record['baseline_id'] = baseline
            records.append(record)

        add('modular-capture', 'Modular arithmetic', 'Crypto', [sys.executable, 'solve.py'], ['input.json', 'solve.py'])
        add('modular-replay', 'Modular arithmetic', 'Crypto', [sys.executable, 'solve.py'], ['input.json', 'solve.py'], 'modular-capture')
        add('modular-stale', 'Modular arithmetic', 'Crypto', [sys.executable, 'solve.py'], ['input.json', 'solve.py'], 'modular-capture', True)
        add('bytes-capture', 'XOR byte recovery', 'Reverse', [sys.executable, 'bytes-solve.py'], ['bytes-input.json', 'bytes-solve.py'])
        add('bytes-replay', 'XOR byte recovery', 'Reverse', [sys.executable, 'bytes-solve.py'], ['bytes-input.json', 'bytes-solve.py'], 'bytes-capture')
        add('ambiguous-capture', 'Two possible candidates', 'Diagnostics',
            [sys.executable, 'ambiguous.py'], ['ambiguous.py'])
        add('failed-capture', 'Output before failure', 'Diagnostics',
            [sys.executable, 'failed.py'], ['failed.py'])
        add('timeout-capture', 'Deadline reached', 'Diagnostics',
            [sys.executable, 'timeout.py'], ['timeout.py'], timeout=.1)
    return {'schema_version': 1, 'report_type': 'solvepack-synthetic', 'synthetic': True,
            'title': 'Worked synthetic examples', 'generated_at': now(), 'records': records}


def main():
    report = build_demo()
    serialized = json.dumps(report, indent=2) + '\n'
    if len(serialized.encode()) > 2097152:
        raise ValueError('Generated report exceeds 2 MiB.')
    (DOCS / 'demo.json').write_text(serialized)
    print(f'Generated {len(report["records"])} real synthetic run records in docs/demo.json')


if __name__ == '__main__':
    main()
