"""Declared provenance only; transitive tools and undeclared files are not covered."""
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
from .model import Manifest, Snapshot, safe_file


def child_environment() -> dict[str,str]:
    return {'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C','LC_ALL':'C','TZ':'UTC','PYTHONHASHSEED':'0'}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''): value.update(block)
    return value.hexdigest()


def json_digest(value) -> str:
    return digest(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


def fingerprint(root: Path, manifest: Manifest) -> Snapshot:
    files={path:file_digest(safe_file(root,path)) for path in ['challenge.json',manifest.solver,*manifest.inputs]}
    launcher=Path(sys.executable).absolute()
    # Resolving a venv's final symlink launches the base runtime, losing its
    # package search path. Hash the actual binary but retain the venv launcher.
    executable=launcher if sys.prefix!=sys.base_prefix else launcher.resolve(strict=True)
    packages={}
    for name in manifest.dependencies:
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ValueError(f'Declared dependency {name} is not installed in this Python environment. Install it deliberately before capture.') from error
    runtime={'interpreter':str(executable),'interpreter_sha256':file_digest(executable),
             'python_version':sys.version,'implementation':sys.implementation.name,
             'platform':platform.platform(),'architecture':platform.machine(),'packages':packages}
    return Snapshot(files,runtime,json_digest(child_environment()))


def changed_fields(before: Snapshot, after: Snapshot) -> list[str]:
    changed=[]
    for name in sorted(before.files.keys() | after.files.keys()):
        if before.files.get(name)!=after.files.get(name): changed.append('files.'+name)
    for name in sorted(before.runtime.keys() | after.runtime.keys()):
        if before.runtime.get(name)!=after.runtime.get(name): changed.append('runtime.'+name)
    if before.environment_sha256!=after.environment_sha256: changed.append('environment_sha256')
    return changed
