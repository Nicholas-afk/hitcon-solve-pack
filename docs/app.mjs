import {parseReport, verifyReport, recordStatus, viewVerdict, candidateScan, displayOutput, checkFile, createSelectionGate, MAX_REPORT_BYTES} from './model.mjs';

const $ = id => document.getElementById(id);
const gate = createSelectionGate();
const capability = $('local-capability')?.content || '';
const localMode = Boolean(capability && ['127.0.0.1','localhost'].includes(globalThis.location?.hostname));
let report = null, selected = null, bundled = false, pending = null, lastCheck = null;
const checks = new Map();
const tone = code => ['REPRODUCED','MATCH'].includes(code) ? 'matched' : ['FAILED','TIMEOUT','OUTPUT_LIMIT','ERROR','FILE_ERROR'].includes(code) ? 'error' : ['STALE','AMBIGUOUS','DIFFERENT','BLOCKED','NO_CANDIDATE','CANDIDATE_LIMIT'].includes(code) ? 'attention' : 'neutral';
const labels = {REPRODUCED:'Matched replay',CAPTURED:'Capture',STALE:'Provenance changed',AMBIGUOUS:'Ambiguous output',FAILED:'Exit error',TIMEOUT:'Timeout',OUTPUT_LIMIT:'Output limit',ERROR:'Start error',DIFFERENT:'Output differs',BLOCKED:'Blocked',NO_CANDIDATE:'No candidate',CANDIDATE_LIMIT:'Review limited'};

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
  document.querySelectorAll('button, select').forEach(control => control.disabled = Boolean(message) || control.dataset.fixedDisabled === 'true');
  if (message) announce(message);
}
function error(message, code) {
  const reopen = localMode && code === 'REOPEN_REQUIRED';
  const box = $('report-error'); box.replaceChildren(node('strong', '', 'Couldn’t open this report'), node('p', '', message + (localMode ? (reopen ? ' Previous verified evidence remains available until you reload.' : ' Fix the local issue and refresh to retry. Previous verified evidence remains available.') : ' Choose another synthetic report or reopen the worked example.')));
  if (localMode) {const retry=node('button','button secondary',reopen?'Reload local viewer':'Retry workspace records');retry.type='button';retry.addEventListener('click',reopen?()=>globalThis.location.reload():refreshLocal);box.append(retry);}
  const recover = node('button', 'button secondary', 'Open worked example');
  recover.type = 'button'; recover.addEventListener('click', example); box.append(recover);
  box.hidden = false;
}
function clearError() { $('report-error').hidden = true; $('report-error').replaceChildren(); }

async function openReport(read, isBundled, fromWorkspace = false) {
  const token = gate.next(); pending = null;
  busy('Reading report and checking output hashes…'); clearError();
  try {
    const data = await read();
    const options = {allowLocal: fromWorkspace && localMode};
    const next = await verifyReport(parseReport(data,options),options);
    if (!gate.isCurrent(token)) return;
    const previous = selected?.id;
    report = next; bundled = isBundled; checks.clear(); lastCheck = null;
    const privateView = report.report_type === 'solvepack-local';
    $('report-context').textContent = privateView ? report.title : 'Sample report · '+report.title;
    $('report-context').hidden = false;
    $('rail-note').textContent = privateView ? 'Recent local records and their captures. Up to 64 recent receipts per run. Refresh after CLI actions.' : 'Synthetic examples · Local evidence only';
    $('storage-note').textContent = privateView ? 'Records stored locally · No uploads' : 'No uploads · No saved session';
    if (!report.records.length) {
      selected=null;$('workspace').hidden=true;$('empty').hidden=false;
      $('empty-title').textContent='No saved runs yet.';$('empty-description').textContent='Capture a trusted solver from the terminal, then refresh workspace records here.';
      announce('Local workspace has no saved runs.');return;
    }
    selected = (fromWorkspace && report.records.find(record=>record.id===previous)) || (privateView ? report.records.at(-1) : report.records.find(record => record.id === 'modular-replay') || report.records.find(record => record.kind === 'replay') || report.records[0]);
    $('empty').hidden = true; $('workspace').hidden = false;
    renderRail(); renderRecord();
    announce('Report opened. ' + recordStatus(report, selected).title + '.');
  } catch (caught) {
    if (gate.isCurrent(token)) error(caught.message || 'The file could not be read.',caught.code);
  } finally { if (gate.isCurrent(token)) busy(); }
}

async function refreshLocal() {
  const origin=$('refresh-local'), restoreFocus=document.activeElement===origin;
  try {return await openReport(async()=>{
    const response=await fetch('./private-report.json',{cache:'no-store',headers:{'X-SolvePack-Capability':capability}});
    if (Number(response.headers.get('content-length'))>MAX_REPORT_BYTES) throw new Error('Report exceeds the 2 MiB limit. Use a smaller review --limit or show --full.');
    const source=await response.text();
    if (!response.ok) {let detail;try{detail=JSON.parse(source);}catch{}const failure=new Error(detail?.error || `Workspace could not be loaded (HTTP ${response.status}).`);failure.code=detail?.code;throw failure;}
    return source;
  },false,true);} finally {
    if (restoreFocus && document.activeElement===document.body) origin.focus();
  }
}
$('refresh-local').addEventListener('click',refreshLocal);
if (localMode) {$('refresh-local').hidden=false;refreshLocal();}

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

function selectRecord(id, keepRailFocus = false) {
  gate.next(); pending = null; lastCheck = null; checks.clear(); busy();
  selected = report.records.find(record => record.id === id);
  renderRail(keepRailFocus); renderRecord();
  announce(`${selected.challenge}. ${recordStatus(report, selected).title}.`);
}
$('run-select').addEventListener('change', event => selectRecord(event.target.value));

function renderRail(keepFocus = false) {
  const list = $('run-list'), select = $('run-select'); list.replaceChildren(); select.replaceChildren();
  $('record-count').textContent = report.records.length;
  const categories = [...new Set(report.records.map(record => record.category))];
  for (const category of categories) {
    const group = node('div', 'run-group'); group.append(node('p','run-category',category));
    for (const record of report.records.filter(record => record.category === category)) {
      const status = recordStatus(report, record);
      const button = node('button', 'run-button'); button.type = 'button';
      const caption=(report.report_type==='solvepack-local'?`${record.kind} ${record.id.slice(0,6)} · `:'')+(labels[status.code] || status.title);
      button.append(node('strong', '', record.challenge), node('span','',caption));
      button.append(node('span','run-time',recordedTime(record)));
      button.setAttribute('aria-label', `${record.challenge} · ${caption} · ${recordedTime(record)}`);
      button.setAttribute('aria-current', String(record === selected));
      button.addEventListener('click', () => selectRecord(record.id,true)); group.append(button);
      const mobileCaption=(labels[status.code] || status.title)+' · '+record.kind+(report.report_type==='solvepack-local'?' '+record.id.slice(0,6):'')+' · '+recordedTime(record)+' · '+record.challenge;
      const option = node('option','',mobileCaption); option.value = record.id; option.selected = record === selected; select.append(option);
    }
    list.append(group);
  }
  if (keepFocus) {
    for (const group of list.children) for (const button of group.children)
      if (button.getAttribute?.('aria-current') === 'true') button.focus();
  }
}

function recordedTime(record) {
  return new Date(record.created_at).toISOString().slice(0,19).replace('T',' ')+' UTC';
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
  $('record-identity').textContent = `Record ${selected.id.slice(0,6)} · ${recordedTime(selected)}`;
  $('record-meta').textContent = `${selected.category} / Recorded ${selected.kind}`;
  $('evidence-label').textContent = selected.synthetic === false ? 'Local operator evidence' : 'Synthetic evidence';
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
  $('stdout').textContent = displayOutput(selected,'stdout') || '(no standard output)';
  $('stderr-region').hidden = !selected.output.stderr;
  $('stderr').textContent = displayOutput(selected,'stderr');
  $('output-note').textContent='Flag-shaped text is a candidate, not a correctness check.'+(selected.output.encoding==='base64'?' Display decoded as UTF-8; invalid bytes appear as �. Hashes verify the original bytes, available in show --full.':'');
  renderFiles(); renderDetails(); renderDownloads(); renderReceipts();
}

const shortHash = hash => hash === null ? 'Unavailable' : hash.slice(0, 14) + '…' + hash.slice(-10);
function hashLine(label, hash) {const div=node('div','full-hash',label); div.append(node('code','',hash === null ? 'Unavailable' : hash)); return div;}
function renderFiles(focusPath) {
  const active=document.activeElement;
  let focusTarget;
  $('files').replaceChildren();
  for (const file of selected.files) {
    const row = node('div','file-row');
    const heading = node('div','file-title'), name = node('div');
    name.append(node('code','',file.path), node('span','small',file.role));
    const button = node('button','button secondary',`Check ${file.path}`);
    if (file.path === focusPath) focusTarget=button;
    button.type='button'; button.addEventListener('click', () => {
      if (!file.baseline_sha256) return;
      pending = {file, record:selected, report, token:gate.next()};
      $('current-input').value = ''; $('current-input').click();
    });
    if (!file.baseline_sha256) {button.disabled=true;button.dataset.fixedDisabled='true';button.textContent='No captured hash';}
    heading.append(name, button); row.append(heading);
    const pair=node('div','hash-pair');
    for (const [label,value] of [['Captured hash',file.baseline_sha256],['Recorded hash',file.observed_sha256]]) {
      const cell=node('div','hash-cell');cell.append(node('span','hash-label',label),node('code','',shortHash(value)));pair.append(cell);
    }
    row.append(pair, node('p',file.baseline_sha256 && file.baseline_sha256 === file.observed_sha256 ? 'file-comparison' : 'file-comparison changed',!file.baseline_sha256 || !file.observed_sha256 ? 'File evidence unavailable — review provenance' : file.baseline_sha256 === file.observed_sha256 ? 'Recorded bytes match' : 'Recorded bytes differ — review this change'));
    const full=node('details','hash-details'), summary=node('summary','',`Full hashes for ${file.path}`);
    if (active?.tagName?.toLowerCase()==='summary' && active.textContent===summary.textContent) {focusTarget=summary;full.open=Boolean(active.parentElement?.open);}
    full.append(summary,hashLine('Captured',file.baseline_sha256),hashLine('Recorded',file.observed_sha256));row.append(full);
    const checked=checks.get(file.path);
    if(checked){const result=node('div','file-result');result.dataset.tone=checked.error?'error':checked.matches?'matched':'attention';result.append(node('strong','',checked.error?'File check failed':checked.matches?'Current file matches':'Current file differs'),node('p','',`${checked.name} → ${file.path}${checked.error?' · '+checked.error:''}`));if(checked.hash)result.append(node('code','',checked.hash));row.append(result);}
    $('files').append(row);
  }
  focusTarget?.focus();
}

function renderReceipts() {
  const body=$('acceptance-body');body.replaceChildren();
  const receipts=selected.receipts || [];
  if (!receipts.length) {body.append(node('p','','No organizer receipt. '+(selected.synthetic === false ? 'Local reproduction does not establish acceptance or competition points.' : 'These are self-generated examples. Recorded replay and file matches do not earn competition points.')));return;}
  body.append(node('p','',selected.synthetic ? 'Synthetic receipt history — not organizer acceptance.' : 'Operator-entered receipt history. Source authenticity is unverified; local replay is a separate conclusion.'));
  for (const receipt of receipts) {
    const row=node('div','receipt-row');
    row.append(node('strong','',`${receipt.state[0].toUpperCase()+receipt.state.slice(1)} · ${receipt.synthetic?'synthetic fixture':'manually recorded'}`));
    row.append(node('p','small',`Recorded ${receipt.recorded_at}${receipt.official_time ? ' · Response time '+receipt.official_time : ''}`));
    if (receipt.source) row.append(node('p','',receipt.source));
    row.append(hashLine('Candidate SHA-256',receipt.candidate_sha256));
    if (receipt.points !== null) row.append(node('p','small',`Recorded point snapshot: ${receipt.points}. No score total is inferred.`));
    if (receipt.evidence) {row.append(node('p',receipt.evidence_valid?'small':'small changed',`${receipt.evidence.path} · ${receipt.evidence_valid?'Local tool reports evidence hash matches':receipt.evidence_problem || 'Evidence unavailable'}`),hashLine('Evidence SHA-256',receipt.evidence.sha256));}
    body.append(row);
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
    renderVerdict();announce(`${result.matches?'Current file matches':'Current file differs'}. Only ${target.file.path} checked.`);
  }catch(caught){if(gate.isCurrent(target.token)){lastCheck={name:file.name,path:target.file.path,error:caught.message || 'The file could not be read.'};checks.set(target.file.path,lastCheck);renderVerdict();announce(lastCheck.error);}}
  finally{if(gate.isCurrent(target.token)){busy();renderFiles(document.activeElement===document.body?target.file.path:undefined);}}
});

function renderDetails() {
  const details=$('run-details');details.replaceChildren();
  for(const [key,value] of [['Record',selected.id],['Recorded at',recordedTime(selected)],['Runtime',selected.runtime],['Command',JSON.stringify(selected.command)],['Duration',`${selected.duration_ms.toFixed(3)} ms, observed`],['Deadline',`${selected.timeout_s} seconds`],['Execution',selected.execution_status],['Compared with',selected.baseline_id || 'No earlier capture']]){details.append(node('dt','',key),node('dd',key==='Command'?'mono':'',value));}
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
