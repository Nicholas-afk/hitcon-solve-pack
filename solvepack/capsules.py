"""Independent shape and byte-integrity validation for persisted capsules."""
import base64
from datetime import datetime,timezone
import math
from pathlib import Path
import re
from .model import fields, text, validate_manifest, extract_candidates, solver_argument
from .provenance import digest

HASH=re.compile(r'[a-f0-9]{64}')
STATUSES={'CANDIDATE','REPRODUCED','STALE','AMBIGUOUS','NO_CANDIDATE','DIFFERENT','FAILED','TIMEOUT','OUTPUT_LIMIT','ERROR'}
EXECUTION={'OK','FAILED','TIMEOUT','OUTPUT_LIMIT','ERROR','NOT_RUN'}


def aware_time(value, label='Timestamp') -> str:
    text(value,label,64)
    try:
        instant=datetime.fromisoformat(value.replace('Z','+00:00'))
        if instant.utcoffset() is None: raise ValueError()
        return instant.astimezone(timezone.utc).isoformat()
    except (ValueError,OverflowError) as error: raise ValueError(f'{label} must be an ISO timestamp with a timezone and representable UTC instant.') from error


def finite(value,label,low=0,high=3600):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(f'{label} must be finite, from {low} to {high}.')


def hash_value(value,label):
    if not isinstance(value,str) or not HASH.fullmatch(value): raise ValueError(f'{label} must be a lowercase SHA-256 hash.')


def snapshot(value,manifest):
    fields(value,['files','runtime','environment_sha256'],'Snapshot')
    if set(value)!= {'files','runtime','environment_sha256'}:raise ValueError('Snapshot fields are incomplete.')
    paths={'challenge.json',manifest.solver,*manifest.inputs}
    if not isinstance(value['files'],dict) or set(value['files'])!=paths:raise ValueError('Snapshot declared file set disagrees with its manifest.')
    for path,hashed in value['files'].items():hash_value(hashed,'File '+path)
    runtime=value['runtime'];names={'interpreter','interpreter_sha256','python_version','implementation','platform','architecture','packages'}
    fields(runtime,names,'Runtime')
    if set(runtime)!=names:raise ValueError('Runtime fields are incomplete.')
    for name in names-{'interpreter_sha256','packages'}:text(runtime[name],'Runtime '+name,4096 if name=='interpreter' else 512)
    if not Path(runtime['interpreter']).is_absolute():raise ValueError('Interpreter path must be absolute.')
    hash_value(runtime['interpreter_sha256'],'Interpreter hash');hash_value(value['environment_sha256'],'Environment hash')
    if not isinstance(runtime['packages'],dict) or set(runtime['packages'])!=set(manifest.dependencies):raise ValueError('Runtime package set disagrees with manifest.')
    for version in runtime['packages'].values():text(version,'Package version',512)


def output_bytes(record,stream):
    value=record['output'][stream+'_base64']
    if not isinstance(value,str) or len(value)>1398104:raise ValueError('Stored output must be bounded base64 text.')
    try:raw=base64.b64decode(value,validate=True)
    except ValueError as error:raise ValueError('Stored output is not valid base64.') from error
    if base64.b64encode(raw).decode()!=value:raise ValueError('Stored output is not canonical base64.')
    return raw


def validate_capsule(record):
    names={'schema_version','capsule_type','id','kind','baseline_id','created_at','challenge_id','category','synthetic',
           'manifest','working_directory','snapshot_before','snapshot_after','command','timeout_s','output_limit',
           'execution_status','exit_code','elapsed_s','output','candidates','status','issues','problem'}
    fields(record,names,'Capsule')
    if set(record)!=names or type(record['schema_version']) is not int or record['schema_version']!=1 or record['capsule_type']!='solvepack-run':raise ValueError('Unsupported or incomplete capsule schema.')
    if not isinstance(record['id'],str) or not re.fullmatch(r'[a-f0-9]{32}',record['id']):raise ValueError('Invalid capsule ID.')
    if record['kind'] not in ('capture','replay'):raise ValueError('Capsule kind must be capture or replay.')
    if (record['kind']=='capture' and record['baseline_id'] is not None) or (record['kind']=='replay' and (not isinstance(record['baseline_id'],str) or not re.fullmatch(r'[a-f0-9]{32}',record['baseline_id']))):raise ValueError('Invalid baseline ID.')
    manifest=validate_manifest(Path('/'),record['manifest'],check_files=False)
    if (record['challenge_id'],record['category'],record['synthetic'])!=(manifest.challenge_id,manifest.category,manifest.synthetic) or type(record['synthetic']) is not bool:raise ValueError('Capsule identity disagrees with its manifest.')
    aware_time(record['created_at']);text(record['working_directory'],'Working directory',4096)
    if not Path(record['working_directory']).is_absolute():raise ValueError('Working directory must be absolute.')
    finite(record['timeout_s'],'Timeout',.1,3600);finite(record['elapsed_s'],'Elapsed time',0,86400)
    if type(record['output_limit']) is not int or record['output_limit']!=1048576:raise ValueError('Unsupported output limit.')
    if (not isinstance(record['execution_status'],str) or record['execution_status'] not in EXECUTION or
        not isinstance(record['status'],str) or record['status'] not in STATUSES):raise ValueError('Unknown capsule status.')
    code=record['exit_code']
    if code is not None and (type(code) is not int or not -(2**31)<=code<2**31):raise ValueError('Invalid exit code.')
    execution=record['execution_status']
    if (execution=='OK' and code!=0) or (execution=='FAILED' and (code is None or code==0)) or (execution in ('ERROR','NOT_RUN') and code is not None):raise ValueError('Execution contradicts its exit code.')
    for name in ('snapshot_before','snapshot_after'):
        if record[name] is not None:snapshot(record[name],manifest)
    before=record['snapshot_before']
    expected=[] if before is None else [before['runtime']['interpreter'],solver_argument(manifest.solver),*manifest.args]
    if record['command']!=expected:raise ValueError('Stored command disagrees with the declared manifest/runtime.')
    if before is None and (record['kind']!='replay' or execution!='NOT_RUN'):raise ValueError('Executed capsule requires pre-run provenance.')
    if record['problem'] is not None:text(record['problem'],'Recorded problem',4096)
    if execution!='NOT_RUN' and record['snapshot_after'] is None and not record['problem']:raise ValueError('Missing post-run provenance must have an explicit problem.')
    if not isinstance(record['issues'],list) or len(record['issues'])>256:raise ValueError('Invalid provenance issue list.')
    for issue in record['issues']:text(issue,'Provenance issue',1024)
    fields(record['output'],['stdout_base64','stderr_base64','stdout_sha256','stderr_sha256'],'Output')
    if len(record['output'])!=4:raise ValueError('Output fields are incomplete.')
    streams={name:output_bytes(record,name) for name in ('stdout','stderr')}
    if sum(map(len,streams.values()))>1048576:raise ValueError('Combined output exceeds 1 MiB.')
    for name,raw in streams.items():
        hash_value(record['output'][name+'_sha256'],name+' hash')
        if digest(raw)!=record['output'][name+'_sha256']:raise ValueError(f'Stored {name} does not match its hash.')
    if record['candidates']!=extract_candidates(streams['stdout'],streams['stderr']):raise ValueError('Stored candidates disagree with raw output.')
    if execution=='NOT_RUN' and (code is not None or record['elapsed_s']!=0 or any(streams.values()) or record['snapshot_after'] is not None):raise ValueError('A blocked run cannot include execution evidence.')
    return record
