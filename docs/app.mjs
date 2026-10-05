import {parseReport, verifyReport, recordStatus, viewVerdict, candidateScan, checkFile, createSelectionGate, MAX_REPORT_BYTES} from './model.mjs';

const $ = id => document.getElementById(id);
const gate = createSelectionGate();
let report = null, selected = null, bundled = false, pending = null, lastCheck = null;
const checks = new Map();
const tone = code => ['REPRODUCED','MATCH'].includes(code) ? 'matched' : ['FAILED','TIMEOUT','OUTPUT_LIMIT','ERROR','FILE_ERROR'].includes(code) ? 'error' : ['STALE','AMBIGUOUS','DIFFERENT','BLOCKED','NO_CANDIDATE','CANDIDATE_LIMIT'].includes(code) ? 'attention' : 'neutral';
const labels = {REPRODUCED:'Matched replay',CAPTURED:'Capture',STALE:'Changed input',AMBIGUOUS:'Ambiguous output',FAILED:'Exit error',TIMEOUT:'Timeout',OUTPUT_LIMIT:'Output limit',ERROR:'Start error',DIFFERENT:'Output differs',BLOCKED:'Blocked',NO_CANDIDATE:'No candidate',CANDIDATE_LIMIT:'Review limited'};

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function announce(message) { $('announcement').textContent = message; }
function busy(message = '') {
  $('notice').hidden = !message;
  $('notice').textContent = message;
  $('main').setAttribute('aria-busy', String(Boolean(message)));
  document.querySelectorAll('button, select').forEach(control => control.disabled = Boolean(message));
  if (message) announce(message);
}
function error(message) {
  const box = $('report-error'); box.replaceChildren(node('strong', '', 'Couldn’t open this report'), node('p', '', message + ' Choose another synthetic report or reopen the worked example.'));
  const recover = node('button', 'button secondary', 'Open worked example');
  recover.type = 'button'; recover.addEventListener('click', example); box.append(recover);
  box.hidden = false;
}
function clearError() { $('report-error').hidden = true; $('report-error').replaceChildren(); }

async function openReport(read, isBundled) {
  const token = gate.next(); pending = null;
  busy('Reading report and checking output hashes…'); clearError();
  try {
    const data = await read();
    const next = await verifyReport(parseReport(data));
    if (!gate.isCurrent(token)) return;
    report = next; bundled = isBundled; checks.clear(); lastCheck = null;
    selected = report.records.find(record => record.id === 'modular-replay') || report.records.find(record => record.kind === 'replay') || report.records[0];
    $('empty').hidden = true; $('workspace').hidden = false;
    renderRail(); renderRecord();
    announce('Report opened. ' + recordStatus(report, selected).title + '.');
  } catch (caught) {
    if (gate.isCurrent(token)) error(caught.message || 'The file could not be read.');
  } finally { if (gate.isCurrent(token)) busy(); }
}

function example() {
  return openReport(async () => {
    const response = await fetch('./demo.json', {cache:'no-store'});
    if (!response.ok) throw new Error(`The example could not be loaded (HTTP ${response.status}).`);
    const length = Number(response.headers.get('content-length'));
    if (length > MAX_REPORT_BYTES) throw new Error('Report exceeds the 2 MiB limit.');
    return response.text();
  }, true);
}
$('open-example').addEventListener('click', example);
$('reopen-example').addEventListener('click', example);
$('open-report').addEventListener('click', () => {$('report-input').value = ''; $('report-input').click();});
$('report-input').addEventListener('change', event => {
  const file = event.target.files[0];
  if (!file) return;
  openReport(async () => {
    if (file.size > MAX_REPORT_BYTES) throw new Error('Report exceeds the 2 MiB limit.');
    return file.text();
  }, false);
});

function selectRecord(id) {
  gate.next(); pending = null; lastCheck = null; checks.clear(); busy();
  selected = report.records.find(record => record.id === id);
  renderRail(); renderRecord();
  announce(`${selected.challenge}. ${recordStatus(report, selected).title}.`);
}
$('run-select').addEventListener('change', event => selectRecord(event.target.value));

function renderRail() {
  const list = $('run-list'), select = $('run-select'); list.replaceChildren(); select.replaceChildren();
  $('record-count').textContent = report.records.length;
  const categories = [...new Set(report.records.map(record => record.category))];
  for (const category of categories) {
    const group = node('div', 'run-group'); group.append(node('p','run-category',category));
    for (const record of report.records.filter(record => record.category === category)) {
      const status = recordStatus(report, record);
      const button = node('button', 'run-button'); button.type = 'button';
      button.append(node('strong', '', record.challenge), node('span','',labels[status.code] || status.title));
      button.setAttribute('aria-label', `${record.challenge} · ${labels[status.code] || status.title}`);
      button.setAttribute('aria-current', String(record === selected));
      button.addEventListener('click', () => selectRecord(record.id)); group.append(button);
      const option = node('option','',`${record.challenge} · ${labels[status.code] || status.title}`); option.value = record.id; option.selected = record === selected; select.append(option);
    }
    list.append(group);
  }
}

function renderVerdict() {
  const status = recordStatus(report, selected);
  const view = viewVerdict(report, selected, lastCheck);
  $('verdict').dataset.tone = tone(view.code);
  $('verdict-title').textContent = view.title; $('verdict-reason').textContent = view.reason;
  $('recorded-result').hidden = !lastCheck;
  $('recorded-result').textContent = 'Recorded result: ' + status.title + '.';
}

function renderRecord() {
  $('challenge-title').textContent = selected.challenge;
  $('record-meta').textContent = `${selected.category} / Recorded ${selected.kind}`;
  $('exit-summary').textContent = selected.exit_code === null ? 'No exit code' : `Exit ${selected.exit_code} · ${(selected.duration_ms/1000).toFixed(3)}s`;
  renderVerdict();
  const list = $('candidate-list'); list.replaceChildren();
  const scan = candidateScan(selected), found = scan.values;
  const status = recordStatus(report, selected);
  for (const [index, candidate] of found.entries()) {
    const line = node('div', 'candidate'); const code = node('code', '', candidate);
    const button = node('button','button secondary', found.length > 1 ? `Copy candidate ${index + 1}` : 'Copy candidate');
    button.type = 'button';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await navigator.clipboard.writeText(candidate);
        button.textContent = 'Copied'; announce('Candidate copied. Organizer correctness is unverified.');
      } catch {
        announce('Couldn’t copy automatically. Select and copy the candidate text.');
        $('notice').textContent = 'Couldn’t copy automatically. Select and copy the candidate text.'; $('notice').hidden = false;
      } finally {button.disabled = false;}
    });
    line.append(code, button); list.append(line);
  }
  if (found.length && ['FAILED','TIMEOUT','OUTPUT_LIMIT','ERROR'].includes(status.code)) list.prepend(node('p','small muted','Diagnostic candidates — this execution did not succeed.'));
  if (scan.limited) list.append(node('p','small muted','Candidate display limited: up to 32 distinct values, each at most 4096 characters. Inspect the full raw output locally.'));
  if (!found.length) list.append(node('p','small muted',scan.limited?'No candidate fits the display limits.':'No flag-shaped candidate in this output.'));
  $('stdout').textContent = selected.output.stdout || '(no standard output)';
  $('stderr-region').hidden = !selected.output.stderr;
  $('stderr').textContent = selected.output.stderr;
  renderFiles(); renderDetails(); renderDownloads();
}

const shortHash = hash => hash.slice(0, 14) + '…' + hash.slice(-10);
function hashLine(label, hash) {const div=node('div','full-hash',label); div.append(node('code','',hash)); return div;}
function renderFiles() {
  $('files').replaceChildren();
  for (const file of selected.files) {
    const row = node('div','file-row');
    const heading = node('div','file-title'), name = node('div');
    name.append(node('code','',file.path), node('span','small',file.role));
    const button = node('button','button secondary',`Check ${file.path}`);
    button.type='button'; button.addEventListener('click', () => {
      pending = {file, record:selected, report, token:gate.next()};
      $('current-input').value = ''; $('current-input').click();
    });
    heading.append(name, button); row.append(heading);
    const pair=node('div','hash-pair');
    for (const [label,value] of [['Captured hash',file.baseline_sha256],['Recorded hash',file.observed_sha256]]) {
      const cell=node('div','hash-cell');cell.append(node('span','hash-label',label),node('code','',shortHash(value)));pair.append(cell);
    }
    row.append(pair, node('p',file.baseline_sha256 === file.observed_sha256 ? 'file-comparison' : 'file-comparison changed',file.baseline_sha256 === file.observed_sha256 ? 'Recorded bytes match' : 'Recorded bytes differ — review this change'));
    const full=node('details','hash-details'); full.append(node('summary','',`Full hashes for ${file.path}`),hashLine('Captured',file.baseline_sha256),hashLine('Recorded',file.observed_sha256));row.append(full);
    const checked=checks.get(file.path);
    if(checked){const result=node('div','file-result');result.dataset.tone=checked.error?'error':checked.matches?'matched':'attention';result.append(node('strong','',checked.error?'File check failed':checked.matches?'Current file matches':'Current file differs'),node('p','',`${checked.name} → ${file.path}${checked.error?' · '+checked.error:''}`));if(checked.hash)result.append(node('code','',checked.hash));row.append(result);}
    $('files').append(row);
  }
}
$('current-input').addEventListener('change', async event => {
  const file=event.target.files[0], target=pending; pending=null;
  if(!file || !target || !gate.isCurrent(target.token) || target.record!==selected || target.report!==report)return;
  lastCheck={name:file.name,path:target.file.path,pending:true};checks.delete(target.file.path);
  renderVerdict();renderFiles();
  busy(`Checking ${file.name}…`);
  try {
    const result=await checkFile(file,target.file.baseline_sha256);
    if(!gate.isCurrent(target.token))return;
    lastCheck={...result,name:file.name,path:target.file.path};checks.set(target.file.path,lastCheck);
    renderVerdict();renderFiles();announce(`${result.matches?'Current file matches':'Current file differs'}. Only ${target.file.path} checked.`);
  }catch(caught){if(gate.isCurrent(target.token)){lastCheck={name:file.name,path:target.file.path,error:caught.message || 'The file could not be read.'};checks.set(target.file.path,lastCheck);renderVerdict();renderFiles();announce(lastCheck.error);}}
  finally{if(gate.isCurrent(target.token))busy();}
});

function renderDetails() {
  const details=$('run-details');details.replaceChildren();
  for(const [key,value] of [['Record',selected.id],['Captured at',new Date(selected.created_at).toLocaleString()+' (your timezone)'],['Runtime',selected.runtime],['Command',JSON.stringify(selected.command)],['Duration',`${selected.duration_ms.toFixed(3)} ms, observed`],['Deadline',`${selected.timeout_s} seconds`],['Execution',selected.execution_status],['Compared with',selected.baseline_id || 'No earlier capture']]){details.append(node('dt','',key),node('dd',key==='Command'?'mono':'',value));}
  $('output-hashes').replaceChildren(hashLine('stdout',selected.output.stdout_sha256),hashLine('stderr',selected.output.stderr_sha256));
}

function renderDownloads() {
  $('example-downloads').hidden = !bundled;
  $('download-links').replaceChildren();
  if(!bundled)return;
  const paths=selected.files.map(file=>file.path);
  if(paths.includes('input.json'))paths.splice(1,0,'input-changed.json');
  for(const path of paths){const link=node('a','',path);link.href='./example-files/'+encodeURIComponent(path);link.download=path;$('download-links').append(link);}
}
