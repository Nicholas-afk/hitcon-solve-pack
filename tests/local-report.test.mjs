import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {parseReport,verifyReport,recordStatus,displayOutput} from '../docs/model.mjs';

const demo=JSON.parse(await readFile(new URL('../docs/demo.json',import.meta.url),'utf8'));
function local() {
  const report=structuredClone(demo);report.report_type='solvepack-local';report.synthetic=false;report.records=report.records.slice(0,2);
  for(const row of report.records){
    row.synthetic=true;row.issues=[];row.problem=null;row.receipts=[];row.output.encoding='base64';
    for(const stream of ['stdout','stderr']){
      const bytes=stream==='stdout'?Buffer.concat([Buffer.from([255]),Buffer.from(row.output[stream]),Buffer.from([128])]):Buffer.from(row.output[stream]);
      row.output[stream]=bytes.toString('base64');row.output[stream+'_sha256']=createHash('sha256').update(bytes).digest('hex');
    }
  }
  return report;
}

test('local Unicode text uses the core code-point limits, including non-BMP filenames and literal arguments',async()=>{
  const data=local();const path=Array(4).fill('🧪'.repeat(37)).join('/')+'/solve.py';
  for(const row of data.records){row.files.find(file=>file.role==='solver').path=path;row.command[1]=path;row.command.push('🧪'.repeat(4096));}
  const report=await verifyReport(parseReport(JSON.stringify(data),{allowLocal:true}),{allowLocal:true});
  assert.equal(recordStatus(report,report.records[1]).code,'REPRODUCED');
  const excess=structuredClone(data);excess.records[0].command.push('🧪'.repeat(4097));
  assert.throws(()=>parseReport(JSON.stringify(excess),{allowLocal:true}),/at most 4096/);
});

test('private mode is explicit and raw binary digests are verified before a replay match',async()=>{
  const data=local();assert.throws(()=>parseReport(JSON.stringify(data)),/synthetic|local/i);
  const report=await verifyReport(parseReport(JSON.stringify(data),{allowLocal:true}),{allowLocal:true});
  assert.equal(recordStatus(report,report.records[1]).code,'REPRODUCED');
  assert.match(displayOutput(report.records[1],'stdout'),/^�hitcon\{synthetic_modular_257\}/);
  const damaged=local();damaged.records[1].output.stdout='YWJj';
  await assert.rejects(verifyReport(parseReport(JSON.stringify(damaged),{allowLocal:true}),{allowLocal:true}),/hash/i);
});

test('missing/new hashes and declared provenance issues cannot become a replay match',async()=>{
  const data=local();const row=data.records[1];row.execution_status='NOT_RUN';row.exit_code=null;row.duration_ms=0;
  for(const stream of ['stdout','stderr']){row.output[stream]='';row.output[stream+'_sha256']=createHash('sha256').update('').digest('hex');}
  row.files.push({path:'new.bin',role:'input',baseline_sha256:null,observed_sha256:'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'});
  row.issues=['files.new.bin'];row.problem=null;
  const report=await verifyReport(parseReport(JSON.stringify(data),{allowLocal:true}),{allowLocal:true});
  assert.equal(recordStatus(report,report.records[1]).code,'STALE');
  const moved=local();moved.records[1].issues=['working_directory'];
  const checked=await verifyReport(parseReport(JSON.stringify(moved),{allowLocal:true}),{allowLocal:true});
  assert.equal(recordStatus(checked,checked.records[1]).code,'STALE');
});

test('manual receipt candidates and hashes bind to complete recorded output without establishing acceptance',async()=>{
  const data=local(),row=data.records[1];const candidate='hitcon{synthetic_modular_257}';
  const receipt={id:'a'.repeat(32),run_id:row.id,candidate,candidate_sha256:createHash('sha256').update(candidate).digest('hex'),state:'accepted',recorded_at:row.created_at,official_time:row.created_at,source:'Synthetic fixture',evidence:{path:'receipt.txt',sha256:'a'.repeat(64)},points:12,synthetic:true,evidence_valid:true,evidence_problem:null};
  row.receipts=[receipt];
  const report=await verifyReport(parseReport(JSON.stringify(data),{allowLocal:true}),{allowLocal:true});
  assert.equal(recordStatus(report,report.records[1]).code,'REPRODUCED');
  const forged=structuredClone(data);forged.records[1].receipts[0].candidate='hitcon{absent}';
  assert.throws(()=>parseReport(JSON.stringify(forged),{allowLocal:true}),/candidate/i);
  const wrongHash=structuredClone(data);wrongHash.records[1].receipts[0].candidate_sha256='b'.repeat(64);
  await assert.rejects(verifyReport(parseReport(JSON.stringify(wrongHash),{allowLocal:true}),{allowLocal:true}),/candidate.*hash/i);
  const failed=structuredClone(data);failed.records[1].execution_status='FAILED';failed.records[1].exit_code=1;
  assert.throws(()=>parseReport(JSON.stringify(failed),{allowLocal:true}),/receipt.*complete/i);
});
