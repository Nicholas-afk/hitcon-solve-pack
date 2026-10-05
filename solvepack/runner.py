"""Bounded execution for trusted local fixtures. This is not a sandbox."""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time


@dataclass(frozen=True)
class RunResult:
    run_status: str
    exit_code: int | None
    elapsed_s: float
    stdout: bytes
    stderr: bytes


def _stop_group(process: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        if sig == signal.SIGTERM:
            time.sleep(.2)
            # Reap the leader before escalating a group with surviving children.
            process.poll()
    process.wait(timeout=1)


def run_solver(argv: list[str], cwd: Path, env: dict[str, str],
               timeout_s: float = 30, max_output_bytes: int = 1048576) -> RunResult:
    if os.name != 'posix':
        raise RuntimeError('Trusted execution requires POSIX process groups.')
    if isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 3600:
        raise ValueError('Timeout must be finite, positive and at most 3600 seconds.')
    if type(max_output_bytes) is not int or not 0 < max_output_bytes <= 1048576:
        raise ValueError('Output limit must be an integer from 1 to 1048576 bytes.')
    if not argv or not all(isinstance(arg, str) and arg for arg in argv):
        raise ValueError('argv must contain literal nonempty strings.')
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   shell=False, start_new_session=True, bufsize=0)
    except OSError as error:
        return RunResult('ERROR', None, time.monotonic() - started, b'', str(error).encode())
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    selector = selectors.DefaultSelector()
    status = 'OK'
    try:
        for name in streams:
            pipe = getattr(process, name)
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        while selector.get_map() or process.poll() is None:
            remaining = timeout_s - (time.monotonic() - started)
            if remaining <= 0:
                status = 'TIMEOUT'
                break
            for key, _ in selector.select(min(.02, remaining)):
                data = os.read(key.fd, 8192)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                available = max_output_bytes - sum(map(len, streams.values()))
                streams[key.data].extend(data[:available])
                if len(data) > available:
                    status = 'OUTPUT_LIMIT'
                    break
            if status != 'OK':
                break
        if status == 'OK':
            process.wait(timeout=max(.001, timeout_s - (time.monotonic() - started)))
            status = 'FAILED' if process.returncode else 'OK'
        else:
            _stop_group(process)
    finally:
        selector.close()
        for name in streams:
            getattr(process, name).close()
        if process.poll() is None:
            _stop_group(process)
    return RunResult(status, process.returncode, time.monotonic() - started,
                     bytes(streams['stdout']), bytes(streams['stderr']))
