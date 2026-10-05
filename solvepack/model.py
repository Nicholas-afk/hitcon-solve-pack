"""Small validated data boundaries for private solve evidence."""
from dataclasses import dataclass
from pathlib import Path
import re
import stat


@dataclass(frozen=True)
class Manifest:
    challenge_id: str
    solver: str
    args: list[str]
    inputs: list[str]
    dependencies: list[str]
    category: str = 'Uncategorised'
    synthetic: bool = False


@dataclass(frozen=True)
class Snapshot:
    files: dict[str, str]
    runtime: dict[str, object]
    environment_sha256: str


def text(value, label: str, maximum=1024, empty=False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > maximum or '\0' in value:
        raise ValueError(f'{label} must be text of at most {maximum} characters, without NUL.')
    return value


def fields(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f'{label} must be an object with supported fields: {", ".join(allowed)}.')


def relative_path(relative: str) -> str:
    text(relative, 'Relative file path', 256)
    parts = relative.split('/')
    if ('\\' in relative or ':' in relative or any(part in ('', '.', '..', '.solvepack', '.git') for part in parts)):
        raise ValueError(f'Unsafe relative file path: {relative}. Use a file inside the challenge folder.')
    return relative


def safe_file(root: Path, relative: str) -> Path:
    relative_path(relative)
    parts=relative.split('/')
    current = root
    try:
        for part in parts:
            current = current / part
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode): raise ValueError(f'Symlink is not a declared regular file: {relative}.')
        if not stat.S_ISREG(mode): raise ValueError(f'Declared path is not a regular file: {relative}.')
    except OSError as error:
        raise ValueError(f'Cannot read declared file {relative}: {error.strerror or error}.') from error
    return current


def validate_manifest(root: Path, raw: dict, check_files=True) -> Manifest:
    fields(raw, ['schema_version','challenge_id','solver','args','inputs','dependencies','category','synthetic'], 'Manifest')
    if type(raw.get('schema_version')) is not int or raw['schema_version'] != 1:
        raise ValueError('Manifest schema_version must be 1.')
    challenge = text(raw.get('challenge_id'), 'Challenge ID', 128)
    solver = text(raw.get('solver'), 'Solver path', 256)
    args, inputs, dependencies = (raw.get(name, []) for name in ('args','inputs','dependencies'))
    for name, values, maximum in [('args',args,32),('inputs',inputs,62),('dependencies',dependencies,32)]:
        if not isinstance(values,list) or len(values)>maximum: raise ValueError(f'Manifest {name} must be a list of at most {maximum} values.')
    for argument in args: text(argument,'Solver argument',4096,empty=True)
    for path in inputs: text(path,'Input path',256)
    if solver == 'challenge.json' or 'challenge.json' in inputs or solver in inputs or len(set(inputs)) != len(inputs):
        raise ValueError('Manifest/solver paths are reserved and input paths must be unique.')
    for path in [solver,*inputs]:
        relative_path(path)
        if check_files: safe_file(root,path)
    canonical=[]
    for package in dependencies:
        text(package,'Dependency name',128)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',package): raise ValueError(f'Invalid dependency name: {package}.')
        canonical.append(re.sub(r'[-_.]+','-',package).lower())
    if len(set(canonical)) != len(canonical): raise ValueError('Dependency names must be unique.')
    category=text(raw.get('category','Uncategorised'),'Category',128)
    synthetic=raw.get('synthetic',False)
    if type(synthetic) is not bool: raise ValueError('Manifest synthetic must be true or false.')
    return Manifest(challenge,solver,list(args),list(inputs),list(dependencies),category,synthetic)


def extract_candidates(stdout: bytes, stderr: bytes) -> list[str]:
    """Linear independent byte scans; shape is not organizer correctness."""
    found = dict()
    for stream in (stdout,stderr):
        position=0
        while True:
            start=stream.find(b'hitcon{',position)
            if start<0: break
            end=start+7
            while end<len(stream) and 32<=stream[end]<=126 and stream[end]!=125: end+=1
            if end<len(stream) and stream[end]==125 and end>start+7:
                found[stream[start:end+1].decode('ascii')]=None
            position=end+1
    return list(found)
