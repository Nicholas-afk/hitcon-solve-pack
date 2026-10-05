import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {parseReport, verifyReport, viewVerdict} from '../docs/model.mjs';
const report = await verifyReport(parseReport(await readFile(new URL('../docs/demo.json',import.meta.url),'utf8')));
const selected = id => report.records.find(record=>record.id===id);
const match = {name:'input.json',path:'input.json',matches:true};

test('one current-file match cannot overshadow stale, ambiguous or failed execution',()=>{
  for(const [id,code] of [['modular-stale','STALE'],['ambiguous-capture','AMBIGUOUS'],['failed-capture','FAILED'],['timeout-capture','TIMEOUT']]){
    assert.equal(viewVerdict(report,selected(id),match).code,code);
  }
});
test('current-file mismatch is a clear local warning while preserving the recorded result',()=>{
  const record=selected('modular-replay');
  assert.equal(viewVerdict(report,record,match).title,'Current file matches');
  const result=viewVerdict(report,record,{...match,name:'input-changed.json',matches:false});
  assert.equal(result.title,'Current file differs');
  assert.equal(result.code,'STALE');
  assert.match(result.reason,/Only this file/);
});
