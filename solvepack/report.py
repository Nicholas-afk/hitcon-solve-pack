"""Bounded browser projection of independently validated private run evidence."""
from datetime import datetime,timezone
from pathlib import Path
from .provenance import json_digest
from .store import private_store,valid_id
from .workflow import load_run,show


def _row(run,base,receipts):
    before=run['snapshot_before'];after=run['snapshot_after']
    original=(base['snapshot_after'] if base else before)
    observed=after if run['execution_status']!='NOT_RUN' else before
    captured=original['files'] if original else {}
    current=observed['files'] if observed else {}
    paths=sorted(set(captured)|set(current))
    manifest=run['manifest']
    files=[{'path':path,'role':'manifest' if path=='challenge.json' else 'solver' if path==manifest['solver'] else 'input',
            'baseline_sha256':captured.get(path),'observed_sha256':current.get(path)} for path in paths]
    runtime='Unavailable before execution'
    if before:
        version=before['runtime']['python_version'].split()[0]
        identity=json_digest({'runtime':before['runtime'],'environment':before['environment_sha256'],'directory':run['working_directory']})
        runtime=f'Python {version} / {before["runtime"]["architecture"]} / provenance {identity}'
    row={'id':run['id'],'challenge':run['challenge_id'],'category':run['category'],'kind':run['kind'],
         'created_at':run['created_at'],'runtime':runtime,'duration_ms':run['elapsed_s']*1000,'timeout_s':run['timeout_s'],
         'exit_code':run['exit_code'],'execution_status':run['execution_status'],'command':run['command'],'files':files,
         'output':{'encoding':'base64',**{name:run['output'][name+'_base64'] for name in ('stdout','stderr')},
                   **{name+'_sha256':run['output'][name+'_sha256'] for name in ('stdout','stderr')}},
         'synthetic':run['synthetic'],'issues':run['issues'],'problem':run['problem'],'receipts':receipts[-64:]}
    if base:row['baseline_id']=base['id']
    return row


def local_report(root: Path,limit=16):
    if type(limit) is not int or not 1<=limit<=64:raise ValueError('Review limit must be 1–64 recent runs.')
    root=Path(root).resolve(strict=True)
    report={'schema_version':1,'report_type':'solvepack-local','synthetic':False,'title':'Local workspace: '+root.name[:200],
            'generated_at':datetime.now(timezone.utc).isoformat(),'records':[]}
    if not (root/'.solvepack').exists() and not (root/'.solvepack').is_symlink():return report
    paths=list((private_store(root)/'capsules').glob('*.json'))
    chosen=sorted(paths,key=lambda path:(path.lstat().st_mtime_ns,path.name))[-limit:]
    runs={}
    for path in chosen:
        valid_id(path.stem);run=load_run(root,path.stem);runs[run['id']]=run
        if run['kind']=='replay':runs[run['baseline_id']]=load_run(root,run['baseline_id'])
    for run in sorted(runs.values(),key=lambda item:(item['created_at'],item['id'])):
        history=show(root,run['id'])['receipt_history']
        report['records'].append(_row(run,runs.get(run['baseline_id']),history))
    return report
