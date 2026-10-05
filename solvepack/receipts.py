"""Operator-entered submission history with attached, rechecked evidence."""
from datetime import datetime,timezone
from pathlib import Path
import uuid
from .capsules import aware_time,hash_value
from .model import fields,text,safe_file
from .provenance import digest,file_digest
from .store import private_store,load_json,atomic_json,workspace_lock,valid_id


def _validate_entry(entry):
    names={'id','run_id','candidate_sha256','state','recorded_at','official_time','source','evidence','points','synthetic'}
    fields(entry,names,'Receipt')
    if set(entry)!=names:raise ValueError('Receipt fields are incomplete.')
    valid_id(entry['id']);valid_id(entry['run_id']);hash_value(entry['candidate_sha256'],'Candidate hash')
    if not isinstance(entry['state'],str) or entry['state'] not in ('attempted','accepted','rejected'):raise ValueError('Receipt state must be attempted, accepted or rejected.')
    aware_time(entry['recorded_at'],'Recorded time')
    if type(entry['synthetic']) is not bool:raise ValueError('Receipt synthetic must be true or false.')
    if entry['official_time'] is not None:aware_time(entry['official_time'],'Official time')
    if entry['source'] is not None:text(entry['source'],'Receipt source',1024)
    if entry['evidence'] is not None:
        fields(entry['evidence'],['path','sha256'],'Receipt evidence')
        if set(entry['evidence'])!={'path','sha256'}:raise ValueError('Receipt evidence fields are incomplete.')
        from .model import relative_path
        relative_path(entry['evidence']['path']);hash_value(entry['evidence']['sha256'],'Evidence hash')
    if entry['state'] in ('accepted','rejected') and any(entry[name] is None for name in ('official_time','source','evidence')):
        raise ValueError('Accepted/rejected records require an official timestamp with timezone, source and evidence file.')
    points=entry['points']
    if points is not None and (type(points) is not int or not 0<=points<=9007199254740991):raise ValueError('Points must be a nonnegative integer that can be represented exactly in the browser.')


def _ledger(root):
    path=private_store(root)/'receipts.json'
    if not path.exists() and not path.is_symlink():return {'schema_version':1,'ledger_type':'solvepack-receipts','entries':[]}
    ledger=load_json(path);fields(ledger,['schema_version','ledger_type','entries'],'Receipt ledger')
    if (set(ledger)!= {'schema_version','ledger_type','entries'} or type(ledger['schema_version']) is not int or
        ledger['schema_version']!=1 or ledger['ledger_type']!='solvepack-receipts' or
        not isinstance(ledger['entries'],list) or len(ledger['entries'])>4096):raise ValueError('Unsupported or incomplete receipt ledger.')
    ids=set()
    for entry in ledger['entries']:
        _validate_entry(entry)
        if entry['id'] in ids:raise ValueError('Duplicate receipt ID.')
        ids.add(entry['id'])
    return ledger


def _bind(entry,run):
    if entry['run_id']!=run['id'] or entry['synthetic']!=run['synthetic']:raise ValueError('Receipt identity disagrees with its run.')
    candidate=next((value for value in run['candidates'] if digest(value.encode('ascii'))==entry['candidate_sha256']),None)
    if candidate is None:raise ValueError('Receipt candidate is not part of the recorded output.')
    if entry['state']!='attempted' and (run['execution_status']!='OK' or run['status'] not in ('CANDIDATE','REPRODUCED','AMBIGUOUS','DIFFERENT')):
        raise ValueError('Accepted/rejected evidence requires a complete successful candidate-bearing run without stale provenance.')
    return candidate


def receipt_history(root: Path,run):
    result=[]
    for entry in _ledger(root)['entries']:
        if entry['run_id']!=run['id']:continue
        candidate=_bind(entry,run);valid=None;problem=None
        if entry['evidence']:
            try:
                valid=file_digest(safe_file(root,entry['evidence']['path']))==entry['evidence']['sha256']
                if not valid:problem='Evidence bytes changed since the receipt was recorded.'
            except (ValueError,OSError) as error:valid=False;problem=str(error)
        result.append({**entry,'candidate':candidate,'evidence_valid':valid,'evidence_problem':problem})
    return result


def record_receipt(root: Path,run_id: str,candidate: str,state: str,official_time=None,source=None,evidence=None,points=None):
    from .workflow import load_run
    root=Path(root).resolve(strict=True)
    with workspace_lock(root):
        run=load_run(root,run_id)
        text(candidate,'Candidate',1048576)
        if candidate not in run['candidates']:raise ValueError('Choose an explicit candidate from this run; flag shape alone is not enough.')
        proof=None
        if evidence is not None:proof={'path':evidence,'sha256':file_digest(safe_file(root,evidence))}
        entry={'id':uuid.uuid4().hex,'run_id':run_id,'candidate_sha256':digest(candidate.encode('ascii')),'state':state,
               'recorded_at':datetime.now(timezone.utc).isoformat(),'official_time':official_time,'source':source,
               'evidence':proof,'points':points,'synthetic':run['synthetic']}
        _validate_entry(entry);_bind(entry,run)
        ledger=_ledger(root)
        if len(ledger['entries'])>=4096:raise ValueError('Receipt history is full; preserve it and use another private workspace or notes.')
        ledger['entries'].append(entry)
        atomic_json(private_store(root)/'receipts.json',ledger)
        return entry
