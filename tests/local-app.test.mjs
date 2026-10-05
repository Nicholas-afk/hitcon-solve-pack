import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners=new Map();this.dataset={};}
  set textContent(value){this.text=value;this.children=[];}
  get textContent(){return (this.text||'')+this.children.map(child=>child.textContent).join('');}
  append(...children){this.children.push(...children);} prepend(...children){this.children.unshift(...children);}
  replaceChildren(...children){this.text='';this.children=children;}
  setAttribute(name,value){this[name]=value;}addEventListener(name,handler){this.listeners.set(name,handler);}
  click(){return this.listeners.get('click')?.({target:this});}
}
test('actual localhost refresh opens real records, preserves selection, recovers errors and handles a genuinely empty workspace',async()=>{
  const html=await readFile(new URL('../docs/index.html',import.meta.url),'utf8');
  const elements=new Map([...html.matchAll(/id="([^"]+)"/g)].map(match=>[match[1],new Element()]));
  elements.get('local-capability').content='test-ephemeral-capability';
  globalThis.location={hostname:'127.0.0.1'};
  globalThis.document={getElementById:id=>elements.get(id),createElement:tag=>new Element(tag),querySelectorAll:()=>[]};
  const demo=JSON.parse(await readFile(new URL('../docs/demo.json',import.meta.url),'utf8'));
  const local=structuredClone(demo);local.report_type='solvepack-local';local.synthetic=false;local.records=local.records.slice(0,2);
  for(const row of local.records){row.synthetic=false;row.issues=[];row.problem=null;row.receipts=[];row.output.encoding='base64';for(const stream of ['stdout','stderr'])row.output[stream]=Buffer.from(row.output[stream]).toString('base64');}
  let response=local,failed=false;
  globalThis.fetch=async(path,options)=>{
    assert.equal(path,'./private-report.json');assert.equal(options.headers['X-SolvePack-Capability'],'test-ephemeral-capability');
    const raw=JSON.stringify(failed?{error:'Workspace temporarily unavailable.'}:response);
    return {ok:!failed,status:failed?409:200,headers:{get:()=>String(raw.length)},text:async()=>raw};
  };
  await import('../docs/app.mjs');
  for(let index=0;index<40 && !elements.get('challenge-title').textContent;index++)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements.get('verdict-title').textContent,'Replay output matched');
  assert.equal(elements.get('evidence-label').textContent,'Local operator evidence');
  assert.match(elements.get('acceptance-body').textContent,/No organizer receipt/);
  const firstRun=elements.get('run-list').children[0].children[1];
  assert.match(firstRun['aria-label'],new RegExp(local.records[0].id.slice(0,6)));
  await elements.get('refresh-local').click();assert.equal(elements.get('verdict-title').textContent,'Replay output matched');
  failed=true;await elements.get('refresh-local').click();assert.match(elements.get('report-error').textContent,/Workspace temporarily unavailable/);
  assert.equal(elements.get('verdict-title').textContent,'Replay output matched');
  failed=false;response={...local,records:[]};await elements.get('refresh-local').click();
  assert.equal(elements.get('workspace').hidden,true);assert.match(elements.get('empty-title').textContent,/No saved runs/);
  response=local;await elements.get('refresh-local').click();assert.equal(elements.get('workspace').hidden,false);
});
