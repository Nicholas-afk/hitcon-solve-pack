import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners=new Map();this.dataset={};}
  set textContent(value){this.text=value;this.children=[];}
  get textContent(){return (this.text||'')+this.children.map(child=>child.textContent).join('');}
  append(...children){this.children.push(...children);} prepend(...children){this.children.unshift(...children);}
  replaceChildren(...children){this.text='';this.children=children;}
  setAttribute(name,value){this[name]=value;}getAttribute(name){return this[name];}addEventListener(name,handler){this.listeners.set(name,handler);}
  focus(){globalThis.document.activeElement=this;}
  set disabled(value){this.disabledValue=value;if(value && globalThis.document?.activeElement===this)globalThis.document.activeElement=globalThis.document.body;}
  get disabled(){return this.disabledValue;}
  click(){return this.listeners.get('click')?.({target:this});}
}
test('actual localhost refresh opens real records, preserves selection, recovers errors and handles a genuinely empty workspace',async()=>{
  const html=await readFile(new URL('../docs/index.html',import.meta.url),'utf8');
  const elements=new Map([...html.matchAll(/id="([^"]+)"/g)].map(match=>[match[1],new Element()]));
  elements.get('local-capability').content='test-ephemeral-capability';
  let reloads=0;globalThis.location={hostname:'127.0.0.1',reload:()=>reloads++};
  const body=new Element('body');globalThis.document={body,activeElement:body,getElementById:id=>elements.get(id),createElement:tag=>new Element(tag),querySelectorAll:()=>[elements.get('refresh-local')]};
  const demo=JSON.parse(await readFile(new URL('../docs/demo.json',import.meta.url),'utf8'));
  const local=structuredClone(demo);local.report_type='solvepack-local';local.synthetic=false;local.title='Local workspace: /fixtures/a/practice';local.records=local.records.slice(0,2);
  for(const row of local.records){row.synthetic=false;row.issues=[];row.problem=null;row.receipts=[];row.output.encoding='base64';for(const stream of ['stdout','stderr'])row.output[stream]=Buffer.from(row.output[stream]).toString('base64');}
  let response=local,failed=false,reopen=false,beforeReply;
  globalThis.fetch=async(path,options)=>{
    assert.equal(path,'./private-report.json');assert.equal(options.headers['X-SolvePack-Capability'],'test-ephemeral-capability');
    if(beforeReply)await beforeReply();
    const raw=JSON.stringify(failed?{error:reopen?'Reload the local viewer after restarting review.':'Workspace temporarily unavailable.',...(reopen?{code:'REOPEN_REQUIRED'}:{})}:response);
    return {ok:!failed,status:failed?409:200,headers:{get:()=>String(raw.length)},text:async()=>raw};
  };
  await import('../docs/app.mjs');
  for(let index=0;index<40 && !elements.get('challenge-title').textContent;index++)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements.get('verdict-title').textContent,'Replay output matched');
  assert.equal(elements.get('workspace-name')?.textContent,'Local workspace: practice','the workspace name stays compact and visible');
  assert.equal(elements.get('workspace-path')?.textContent,local.title,'the full verified path remains available');
  assert.equal(elements.get('workspace-path-details')?.hidden,false);
  const selectedTime=new Date(local.records[1].created_at).toISOString().slice(0,19).replace('T',' ')+' UTC';
  assert.equal(elements.get('record-identity')?.textContent,`Record ${local.records[1].id.slice(0,6)} · ${selectedTime}`);
  assert.match(elements.get('run-select').children[1].textContent,/^Matched replay · replay/,'status precedes long challenge titles in the narrow selector');
  assert.equal(elements.get('evidence-label').textContent,'Local operator evidence');
  assert.match(elements.get('acceptance-body').textContent,/No organizer receipt/);
  const firstRun=elements.get('run-list').children[0].children[1];
  assert.match(firstRun['aria-label'],new RegExp(local.records[0].id.slice(0,6)));
  firstRun.focus();await firstRun.click();
  const firstTime=new Date(local.records[0].created_at).toISOString().slice(0,19).replace('T',' ')+' UTC';
  assert.equal(elements.get('record-identity').textContent,`Record ${local.records[0].id.slice(0,6)} · ${firstTime}`,'selection changes the visible identity with the evidence');
  const replaced=elements.get('run-list').children[0].children[1];
  assert.equal(globalThis.document.activeElement,replaced,'record activation must preserve focus on the replacement button');
  assert.equal(replaced['aria-current'],'true');
  await elements.get('run-list').children[0].children[2].click();
  elements.get('refresh-local').focus();await elements.get('refresh-local').click();assert.equal(elements.get('verdict-title').textContent,'Replay output matched');
  assert.equal(globalThis.document.activeElement,elements.get('refresh-local'),'refresh success returns focus when disabling lost it');
  failed=true;await elements.get('refresh-local').click();assert.match(elements.get('report-error').textContent,/Workspace temporarily unavailable/);
  assert.equal(elements.get('workspace-path').textContent,local.title,'failed loads must preserve verified identity');
  assert.equal(globalThis.document.activeElement,elements.get('refresh-local'),'refresh failure also returns focus');
  assert.equal(elements.get('verdict-title').textContent,'Replay output matched');
  reopen=true;await elements.get('refresh-local').click();
  const reload=elements.get('report-error').children.find(child=>child.textContent==='Reload local viewer');
  assert.ok(reload,'an expired server capability requires a reload, not an ineffective retry');
  await reload.click();assert.equal(reloads,1);reopen=false;
  failed=false;beforeReply=async()=>elements.get('stdout').focus();elements.get('refresh-local').focus();
  await elements.get('refresh-local').click();assert.equal(globalThis.document.activeElement,elements.get('stdout'),'refresh does not steal deliberate focus movement');beforeReply=undefined;
  failed=false;response={...local,records:[]};await elements.get('refresh-local').click();
  assert.equal(elements.get('workspace').hidden,true);assert.match(elements.get('empty-title').textContent,/No saved runs/);
  assert.equal(elements.get('workspace-path').textContent,local.title,'empty workspaces still expose the actual workspace');
  response=local;await elements.get('refresh-local').click();assert.equal(elements.get('workspace').hidden,false);
});
