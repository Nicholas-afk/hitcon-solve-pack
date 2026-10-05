import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

// Small DOM substitute invokes the actual app's registered handlers; no browser globals are exported by production.
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.listeners = new Map(); this.dataset = {}; }
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  contains(element) { return this===element || this.children.some(child=>child.contains(element)); }
  replaceChildren(...children) { if(this.children.some(child=>child.contains(globalThis.document?.activeElement)))globalThis.document.activeElement=globalThis.document.body;this.text = ''; this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  focus() { globalThis.document.activeElement = this; }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  click() { return this.emit('click'); }
  async emit(name) { return this.listeners.get(name)?.({target: this}); }
}

test('actual file-check handlers invalidate previous success during a replacement and expose its failure', async () => {
  const html = await readFile(new URL('../docs/index.html', import.meta.url), 'utf8');
  const elements = new Map([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], new Element()]));
  const body=new Element('body');globalThis.document = {body,activeElement:body,getElementById: id => elements.get(id), createElement: tag => new Element(tag), querySelectorAll: () => []};
  const raw = await readFile(new URL('../docs/demo.json', import.meta.url), 'utf8');
  globalThis.fetch = async () => ({ok: true, headers: {get: () => String(raw.length)}, text: async () => raw});
  await import('../docs/app.mjs');
  await elements.get('open-example').click();
  const chooser = elements.get('current-input');
  const check = async file => {
    const button = elements.get('files').children[0].children[0].children.find(child => child.tagName === 'button');
    await button.click(); chooser.files = [file]; return chooser.emit('change');
  };
  const bytes = await readFile(new URL('../docs/example-files/input.json', import.meta.url));
  await check(new File([bytes], 'input.json'));
  assert.equal(elements.get('verdict-title').textContent, 'Current file matches');
  assert.equal(globalThis.document.activeElement,elements.get('files').children[0].children[0].children.find(child=>child.tagName==='button'),'restore focus after the file chooser succeeds');
  await check({name: 'too-large.bin', size: 16 * 1024 * 1024 + 1});
  assert.equal(elements.get('verdict-title').textContent, 'File check failed');
  assert.match(elements.get('verdict-reason').textContent, /too-large\.bin.*16 MiB/);
  assert.equal(globalThis.document.activeElement,elements.get('files').children[0].children[0].children.find(child=>child.tagName==='button'),'restore focus after the file chooser fails');
  assert.match(elements.get('recorded-result').textContent, /Replay output matched/);
  await check(new File([bytes], 'input.json'));
  let rejectRead;
  const reading = check({name: 'unreadable.json', size: 10, arrayBuffer: () => new Promise((_, reject) => {rejectRead = reject;})});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements.get('verdict-title').textContent, 'Checking current file');
  elements.get('stdout').focus();
  rejectRead(new Error('Read failed.')); await reading;
  assert.equal(elements.get('verdict-title').textContent, 'File check failed');
  assert.match(elements.get('verdict-reason').textContent, /unreadable\.json.*Read failed/);
  assert.equal(globalThis.document.activeElement,elements.get('stdout'),'completion respects deliberate focus movement during the read');
  let resolveRead;
  const slowCheck=check({name:'input.json',size:bytes.length,arrayBuffer:()=>new Promise(resolve=>{resolveRead=resolve;})});
  await new Promise(resolve=>setImmediate(resolve));
  const details=elements.get('files').children[0].children.find(child=>child.tagName==='details');
  details.open=true;details.children[0].parentElement=details;details.children[0].focus();
  resolveRead(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));await slowCheck;
  const replacementDetails=elements.get('files').children[0].children.find(child=>child.tagName==='details');
  assert.equal(globalThis.document.activeElement,replacementDetails.children[0],'a focused hash disclosure remains the active disclosure');
  assert.equal(replacementDetails.open,true,'preserve the focused disclosure state');
});
