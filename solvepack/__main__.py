"""Explicit local commands; stdout is JSON and errors have actionable stderr."""
import argparse
import json
from pathlib import Path
import sys
from .model import validate_manifest
from .store import atomic_json
from .workflow import capture,replay,show


class Parser(argparse.ArgumentParser):
    def error(self,message):
        self.print_usage(sys.stderr);self.exit(1,'Solve Pack: '+message+'\n')


def parser():
    command=Parser(description='Capture and reproduce trusted local solves; organizer acceptance stays separate.')
    commands=command.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init',help='Create a new manifest for existing trusted files')
    init.add_argument('root',type=Path);init.add_argument('--challenge',required=True);init.add_argument('--solver',required=True)
    init.add_argument('--arg',action='append',default=[]);init.add_argument('--input',action='append',default=[])
    init.add_argument('--dependency',action='append',default=[]);init.add_argument('--category',default='Uncategorised');init.add_argument('--synthetic',action='store_true')
    cap=commands.add_parser('capture',help='Run the current manifest and persist new evidence')
    cap.add_argument('root',type=Path);cap.add_argument('--timeout',type=float,default=30.0)
    rep=commands.add_parser('replay',help='Check provenance, then rerun a complete capture')
    rep.add_argument('root',type=Path);rep.add_argument('run_id')
    view=commands.add_parser('show',help='Read validated run evidence and separate receipt history')
    view.add_argument('root',type=Path);view.add_argument('run_id');view.add_argument('--full',action='store_true')
    receipt=commands.add_parser('receipt',help='Attach manual response evidence; never infer acceptance')
    receipt.add_argument('root',type=Path);receipt.add_argument('run_id');receipt.add_argument('--candidate',required=True)
    receipt.add_argument('--state',required=True,choices=['attempted','accepted','rejected']);receipt.add_argument('--official-time')
    receipt.add_argument('--source');receipt.add_argument('--evidence');receipt.add_argument('--points',type=int)
    return command


def summary(record):
    names=['id','challenge_id','synthetic','status','execution_status','exit_code','elapsed_s','candidates','issues','problem','receipt_history','acceptance_note']
    return {name:record[name] for name in names}


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='init':
            root=args.root.resolve(strict=True)
            raw={'schema_version':1,'challenge_id':args.challenge,'solver':args.solver,'args':args.arg,'inputs':args.input,
                 'dependencies':args.dependency,'category':args.category,'synthetic':args.synthetic}
            validate_manifest(root,raw);atomic_json(root/'challenge.json',raw,exclusive=True)
            print(json.dumps({'manifest':str(root/'challenge.json'),'synthetic':args.synthetic}));return 0
        if args.command=='receipt':
            from .receipts import record_receipt
            entry=record_receipt(args.root,args.run_id,args.candidate,args.state,args.official_time,args.source,args.evidence,args.points)
            print(json.dumps(entry,indent=2));return 0
        if args.command=='capture':result=capture(args.root,args.timeout)
        elif args.command=='replay':result=replay(args.root,args.run_id)
        else:result=show(args.root,args.run_id)
        record=show(args.root,result['id']) if args.command!='show' else result
        print(json.dumps(record if getattr(args,'full',False) else summary(record),indent=2))
        return 0 if args.command=='show' or result['status'] in ('CANDIDATE','REPRODUCED') else 2
    except (ValueError,OSError,RuntimeError) as error:
        print('Solve Pack: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
