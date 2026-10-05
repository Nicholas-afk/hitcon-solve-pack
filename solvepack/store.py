"""Bounded private JSON storage; no replacement of immutable run IDs."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import tempfile

MAX_DOCUMENT_BYTES=2*1024*1024


def valid_id(value: str) -> str:
    if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32}',value):
        raise ValueError('Run ID must be the 32 lowercase hex characters printed by capture/replay.')
    return value


def private_store(root: Path, create=False) -> Path:
    root=Path(root).resolve(strict=True)
    if not root.is_dir(): raise ValueError('Challenge workspace must be a directory.')
    path=root/'.solvepack'
    for folder in [path,path/'capsules']:
        if not folder.exists() and not folder.is_symlink():
            if not create: raise ValueError('No saved Solve Pack workspace. Run capture first.')
            folder.mkdir(mode=0o700)
        mode=folder.lstat().st_mode
        if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            raise ValueError(f'Private storage must be a real directory, not a symlink: {folder.name}.')
        if create: folder.chmod(0o700)
    return path


def capsule_path(root: Path, run_id: str) -> Path:
    valid_id(run_id)
    return private_store(root)/'capsules'/(run_id+'.json')


def _pairs(values):
    result={}
    for key,value in values:
        if key in result: raise ValueError(f'Duplicate JSON field: {key}.')
        result[key]=value
    return result


def load_json(path: Path) -> dict:
    path=Path(path)
    try:
        if not stat.S_ISREG(path.lstat().st_mode): raise ValueError(f'JSON must be a regular file, not a symlink: {path.name}.')
        with os.fdopen(os.open(path,os.O_RDONLY | getattr(os,'O_NOFOLLOW',0)),'rb') as stream:
            if os.fstat(stream.fileno()).st_size>MAX_DOCUMENT_BYTES: raise ValueError('JSON document exceeds the 2 MiB limit.')
            data=stream.read(MAX_DOCUMENT_BYTES+1)
        if len(data)>MAX_DOCUMENT_BYTES: raise ValueError('JSON document exceeds the 2 MiB limit.')
        def constant(_): raise ValueError('Nonfinite JSON numbers are not supported.')
        value=json.loads(data.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=constant)
        if not isinstance(value,dict): raise ValueError('JSON document must be an object.')
        return value
    except (UnicodeError,json.JSONDecodeError,RecursionError) as error:
        raise ValueError(f'Cannot read {path.name}: invalid UTF-8 JSON or excessive nesting.') from error


def atomic_json(path: Path, value: dict, exclusive=False) -> None:
    if not isinstance(value,dict): raise ValueError('Saved JSON must be an object.')
    try: data=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')
    except (TypeError,ValueError,RecursionError) as error: raise ValueError(f'Cannot serialize record as finite JSON: {error}.') from error
    if len(data)>MAX_DOCUMENT_BYTES: raise ValueError('Serialized JSON exceeds the 2 MiB limit; no record was replaced. Keep large output in ordinary private files.')
    path=Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()): raise ValueError(f'JSON destination must be a regular file: {path.name}.')
    descriptor,temporary=tempfile.mkstemp(prefix='.tmp-',dir=path.parent)
    temporary=Path(temporary)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        if exclusive: os.link(temporary,path)
        else: os.replace(temporary,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally: temporary.unlink(missing_ok=True)


@contextmanager
def workspace_lock(root: Path):
    storage=private_store(root,create=True); path=storage/'lock'
    try: descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    except FileExistsError as error:
        raise ValueError(f'Workspace is locked at {path}. Finish the other command; after an interrupted command, verify the owner is no longer running before manually removing only this lock.') from error
    identity=os.fstat(descriptor)
    try:
        with os.fdopen(descriptor,'w') as stream:
            json.dump({'pid':os.getpid(),'created_at':datetime.now(timezone.utc).isoformat()},stream)
            stream.flush();os.fsync(stream.fileno())
        yield storage
    finally:
        try: current=path.lstat()
        except FileNotFoundError as error: raise ValueError('Workspace lock disappeared; check storage before retrying.') from error
        if (current.st_dev,current.st_ino)!=(identity.st_dev,identity.st_ino):
            raise ValueError('Workspace lock ownership changed; the replacement was left intact.')
        path.unlink()
