"""One complete persisted trusted-solve workflow; commands come from current manifests."""
import base64
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import uuid
from .capsules import finite, output_bytes, validate_capsule
from .model import Snapshot, validate_manifest, extract_candidates, solver_argument
from .provenance import child_environment, fingerprint, changed_fields, digest
from .runner import run_solver, RunResult
from .store import atomic_json, load_json, workspace_lock, capsule_path


def evaluation(record,baseline=None):
    issues=[];before=record['snapshot_before'];after=record['snapshot_after']
    if baseline:
        if before is None:issues.append('pre_run_provenance_unavailable')
        else:issues.extend(changed_fields(Snapshot(**baseline['snapshot_after']),Snapshot(**before)))
        if record['working_directory']!=baseline['working_directory']:issues.append('working_directory')
        if record['command']!=baseline['command']:issues.append('command')
    if before is not None and after is not None:issues.extend(changed_fields(Snapshot(**before),Snapshot(**after)))
    elif record['execution_status']!='NOT_RUN' and after is None:issues.append('post_run_provenance_unavailable')
    issues=list(dict.fromkeys(issues))
    if record['execution_status'] in ('FAILED','TIMEOUT','OUTPUT_LIMIT','ERROR'):return record['execution_status'],issues
    if record['problem'] or issues:return 'STALE',issues
    if record['execution_status']=='NOT_RUN':return 'ERROR',issues
    candidates=record['candidates']
    if not candidates:return 'NO_CANDIDATE',issues
    if len(candidates)>1:return 'AMBIGUOUS',issues
    if not baseline:return 'CANDIDATE',issues
    same=all(record['output'][name+'_sha256']==baseline['output'][name+'_sha256'] for name in ('stdout','stderr'))
    return ('REPRODUCED' if same else 'DIFFERENT'),issues


def load_run(root: Path, run_id: str):
    record=validate_capsule(load_json(capsule_path(root,run_id)))
    if record['id']!=run_id:raise ValueError('Capsule ID disagrees with its filename.')
    baseline=None
    if record['kind']=='replay':
        baseline=validate_capsule(load_json(capsule_path(root,record['baseline_id'])))
        if baseline['kind']!='capture':raise ValueError('Replay baseline must be a capture, not another replay.')
        if baseline['id']!=record['baseline_id'] or evaluation(baseline)!= (baseline['status'],baseline['issues']):raise ValueError('Baseline status/provenance is inconsistent.')
        if baseline['status']!='CANDIDATE':raise ValueError('Replay baseline must be a complete single-candidate capture.')
        if baseline['challenge_id']!=record['challenge_id'] or baseline['synthetic']!=record['synthetic']:raise ValueError('Replay identity disagrees with capture.')
        if baseline['timeout_s']!=record['timeout_s']:raise ValueError('Replay timeout disagrees with capture.')
    if evaluation(record,baseline)!=(record['status'],record['issues']):raise ValueError('Stored status/provenance disagrees with its evidence.')
    return record


def _manifest(root):
    return validate_manifest(root,load_json(root/'challenge.json'))


def _execute(root,manifest,before,timeout_s,baseline=None,problem=None):
    command=[] if before is None else [before.runtime['interpreter'],solver_argument(manifest.solver),*manifest.args]
    issues=[]
    if baseline and before:
        issues=changed_fields(Snapshot(**baseline['snapshot_after']),before)
        if str(root)!=baseline['working_directory']:issues.append('working_directory')
        if command!=baseline['command']:issues.append('command')
    result=RunResult('NOT_RUN',None,0,b'',b'');after=None
    if not problem and not issues:
        result=run_solver(command,root,child_environment(),timeout_s=timeout_s)
        try:after=fingerprint(root,manifest)
        except (ValueError,OSError) as error:problem=str(error)
    raw_manifest={'schema_version':1,**asdict(manifest)}
    output={}
    for name,raw in [('stdout',result.stdout),('stderr',result.stderr)]:
        output[name+'_base64']=base64.b64encode(raw).decode();output[name+'_sha256']=digest(raw)
    record={'schema_version':1,'capsule_type':'solvepack-run','id':uuid.uuid4().hex,'kind':'replay' if baseline else 'capture',
            'baseline_id':baseline['id'] if baseline else None,'created_at':datetime.now(timezone.utc).isoformat(),
            'challenge_id':manifest.challenge_id,'category':manifest.category,'synthetic':manifest.synthetic,
            'manifest':raw_manifest,'working_directory':str(root),'snapshot_before':asdict(before) if before else None,
            'snapshot_after':asdict(after) if after else None,'command':command,'timeout_s':timeout_s,'output_limit':1048576,
            'execution_status':result.run_status,'exit_code':result.exit_code,'elapsed_s':result.elapsed_s,'output':output,
            'candidates':extract_candidates(result.stdout,result.stderr),'status':'ERROR','issues':[],'problem':problem}
    record['status'],record['issues']=evaluation(record,baseline)
    validate_capsule(record)
    atomic_json(capsule_path(root,record['id']),record,exclusive=True)
    return record


def capture(root: Path,timeout_s=30.0):
    finite(timeout_s,'Timeout',.1,3600)
    root=Path(root).resolve(strict=True)
    with workspace_lock(root):
        manifest=_manifest(root);before=fingerprint(root,manifest)
        return _execute(root,manifest,before,float(timeout_s))


def replay(root: Path,baseline_id: str):
    root=Path(root).resolve(strict=True)
    with workspace_lock(root):
        baseline=load_run(root,baseline_id)
        if baseline['kind']!='capture' or baseline['status']!='CANDIDATE':raise ValueError('Choose a complete single-candidate capture as the baseline; recapture locally if it needs review.')
        problem=None;before=None
        try:manifest=_manifest(root);before=fingerprint(root,manifest)
        except (ValueError,OSError) as error:
            manifest=validate_manifest(root,baseline['manifest'],check_files=False);problem=str(error)
        # Changed challenge identity also blocks; retain baseline identity for an intelligible replay record.
        if (manifest.challenge_id,manifest.category,manifest.synthetic)!=(baseline['challenge_id'],baseline['category'],baseline['synthetic']):
            problem='Manifest challenge/category/synthetic identity changed. Review it and capture again.'
            manifest=validate_manifest(root,baseline['manifest'],check_files=False);before=None
        return _execute(root,manifest,before,baseline['timeout_s'],baseline,problem)


def show(root: Path,run_id: str):
    from .receipts import receipt_history
    root=Path(root).resolve(strict=True);record=load_run(root,run_id);history=receipt_history(root,record)
    note='No organizer acceptance recorded.'
    if history:
        note='Synthetic receipt history — not organizer acceptance.' if record['synthetic'] else 'Manually recorded receipt history; organizer response authenticity is unverified.'
    return {**record,'receipt_history':history,'acceptance_note':note}
