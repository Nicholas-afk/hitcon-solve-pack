export const MAX_REPORT_BYTES = 2 * 1024 * 1024;
export const MAX_FILE_BYTES = 16 * 1024 * 1024;
const encoder = new TextEncoder();
const verified = new WeakSet();
const candidateCache = new WeakMap();
const HASH = /^[a-f0-9]{64}$/;
const STATES = new Set(['OK', 'FAILED', 'TIMEOUT', 'OUTPUT_LIMIT', 'ERROR', 'NOT_RUN']);
const fail = message => { throw new Error(message); };
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function keys(value, allowed, label) {
  if (!object(value)) fail(`${label} must be an object.`);
  for (const name of Object.keys(value)) if (!allowed.includes(name)) fail(`${label}: unsupported field “${name}”.`);
}

function text(value, label, max = 256) {
  if (typeof value !== 'string' || !value || value.length > max) fail(`${label} must be nonempty text, at most ${max} characters.`);
}

function hash(value, label) {
  if (typeof value !== 'string' || !HASH.test(value)) fail(`${label} must be a lowercase SHA-256 hash.`);
}

function timestamp(value, label) {
  text(value, label, 40);
  if (!/^\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value))) fail(`${label} must include an ISO date and timezone.`);
}

export function outputBytes(record, stream) {
  if (record.output.encoding !== 'base64') return encoder.encode(record.output[stream]);
  let binary;
  try { binary = atob(record.output[stream]); } catch { fail('Stored output must be valid base64.'); }
  if (btoa(binary) !== record.output[stream]) fail('Stored output must be canonical base64.');
  return Uint8Array.from(binary, character => character.charCodeAt(0));
}

export const displayOutput = (record, stream) => new TextDecoder().decode(outputBytes(record, stream));

function receiptShape(receipt, record) {
  keys(receipt, ['id','run_id','candidate','candidate_sha256','state','recorded_at','official_time','source','evidence','points','synthetic','evidence_valid','evidence_problem'], 'Receipt');
  if (Object.keys(receipt).length !== 13) fail('Receipt fields are incomplete.');
  text(receipt.id,'Receipt id'); text(receipt.candidate,'Receipt candidate',1048576); hash(receipt.candidate_sha256,'Receipt candidate hash');
  if (receipt.run_id !== record.id || receipt.synthetic !== record.synthetic) fail('Receipt identity disagrees with its run.');
  if (!['attempted','accepted','rejected'].includes(receipt.state)) fail('Unknown receipt state.');
  timestamp(receipt.recorded_at,'Receipt recorded time');
  if (receipt.official_time !== null) timestamp(receipt.official_time,'Receipt official time');
  if (receipt.source !== null) text(receipt.source,'Receipt source',1024);
  if (receipt.points !== null && (!Number.isSafeInteger(receipt.points) || receipt.points < 0)) fail('Receipt points must be a nonnegative exact integer.');
  if (receipt.evidence !== null) {
    keys(receipt.evidence,['path','sha256'],'Receipt evidence');
    text(receipt.evidence.path,'Receipt evidence path');hash(receipt.evidence.sha256,'Receipt evidence hash');
    if (receipt.evidence.path.includes('\\') || receipt.evidence.path.includes(':') || receipt.evidence.path.split('/').some(part => !part || ['.','..','.solvepack','.git'].includes(part))) fail('Receipt evidence path must stay inside the workspace.');
    if (typeof receipt.evidence_valid !== 'boolean') fail('Receipt evidence validity must be explicit.');
  } else if (receipt.evidence_valid !== null) fail('Missing evidence cannot be checked.');
  if (receipt.evidence_problem !== null) text(receipt.evidence_problem,'Receipt evidence problem',4096);
  if (receipt.state !== 'attempted' && (receipt.official_time === null || receipt.source === null || receipt.evidence === null || record.execution_status !== 'OK' || record.issues.length || record.problem || record.files.some(file=>file.baseline_sha256!==file.observed_sha256))) fail('Receipt requires a complete candidate-bearing run and timestamp, source and evidence.');
}

export function parseReport(source, {allowLocal = false} = {}) {
  if (typeof source !== 'string') fail('Report must be JSON text.');
  if (encoder.encode(source).length > MAX_REPORT_BYTES) fail('Report exceeds the 2 MiB limit.');
  let report;
  try { report = JSON.parse(source); } catch { fail('Report is not valid JSON.'); }
  keys(report, ['schema_version', 'report_type', 'synthetic', 'title', 'generated_at', 'records'], 'Report');
  const local = allowLocal && report.report_type === 'solvepack-local' && report.synthetic === false;
  if (report.schema_version !== 1 || (!local && (report.report_type !== 'solvepack-synthetic' || report.synthetic !== true))) fail('Open a schema-v1 Solve Pack report explicitly marked synthetic; private local reports require the local viewer.');
  text(report.title, 'Report title'); timestamp(report.generated_at, 'Report timestamp');
  if (!Array.isArray(report.records) || (!local && !report.records.length) || report.records.length > 128) fail('Report must have 1–128 records (an empty local workspace is allowed).');
  const ids = new Map();
  for (const record of report.records) {
    keys(record, ['id','challenge','category','kind','created_at','runtime','duration_ms','timeout_s','exit_code','execution_status','files','output','baseline_id','command',...(local?['synthetic','issues','problem','receipts']:[])], 'Record');
    if (local) {
      if (typeof record.synthetic !== 'boolean' || !Array.isArray(record.issues) || record.issues.length > 256 || !Array.isArray(record.receipts) || record.receipts.length > 64) fail('Local evidence fields are incomplete or exceed their limits.');
      for (const issue of record.issues) text(issue,'Provenance issue',1024);
      if (record.problem !== null) text(record.problem,'Recorded problem',4096);
    }
    for (const field of ['id','challenge','category','runtime']) text(record[field], `Record ${field}`);
    if (ids.has(record.id)) fail(`Duplicate record id: ${record.id}.`);
    ids.set(record.id, record);
    if (!['capture', 'replay'].includes(record.kind)) fail('Record kind must be capture or replay.');
    timestamp(record.created_at, 'Record timestamp');
    if (!Number.isFinite(record.duration_ms) || record.duration_ms < 0) fail('Record duration must be a nonnegative number.');
    if (!Number.isFinite(record.timeout_s) || record.timeout_s <= 0 || record.timeout_s > 3600) fail('Record timeout must be positive and at most 3600 seconds.');
    if (record.exit_code !== null && !Number.isSafeInteger(record.exit_code)) fail('Record exit code must be an integer or null.');
    if (!STATES.has(record.execution_status)) fail('Unknown execution status.');
    if ((record.execution_status === 'OK' && record.exit_code !== 0) || (record.execution_status === 'FAILED' && (record.exit_code === null || record.exit_code === 0))) fail('Execution status contradicts the exit code.');
    if (!Array.isArray(record.command) || (!record.command.length && !(local && record.execution_status === 'NOT_RUN')) || record.command.length > (local ? 34 : 32)) fail('Recorded command must be a literal argument list.');
    for (const arg of record.command) { if (local && arg === '') continue; text(arg, 'Command argument', local ? 4096 : 1024); if (arg.includes('\0')) fail('Command argument cannot contain NUL.'); }
    if (!Array.isArray(record.files) || !record.files.length || record.files.length > (local ? 128 : 64)) fail('Record declared file set exceeds its limit.');
    const paths = new Set();
    for (const file of record.files) {
      keys(file, ['path','role','baseline_sha256','observed_sha256'], 'File');
      text(file.path, 'File path');
      if (file.path.includes('\\') || file.path.includes(':') || file.path.startsWith('/') || file.path.split('/').some(part => !part || part === '.' || part === '..') || paths.has(file.path)) fail('File paths must be unique, relative and stay inside the example.');
      paths.add(file.path);
      if (!['input', 'solver',...(local?['manifest']:[])].includes(file.role)) fail('Unknown declared file role.');
      for (const [label,value] of [['Baseline file hash',file.baseline_sha256],['Observed file hash',file.observed_sha256]]) if (!(local && value === null)) hash(value,label);
    }
    keys(record.output, ['stdout','stderr','stdout_sha256','stderr_sha256',...(local?['encoding']:[])], 'Output');
    if (local && record.output.encoding !== 'base64') fail('Private output must preserve raw bytes as base64.');
    for (const stream of ['stdout', 'stderr']) {
      if (typeof record.output[stream] !== 'string') fail(`${stream} must be text.`);
      hash(record.output[`${stream}_sha256`], `${stream} hash`);
    }
    if (outputBytes(record,'stdout').length + outputBytes(record,'stderr').length > 1048576) fail('Combined output exceeds 1 MiB.');
    if (record.execution_status === 'NOT_RUN' && (record.exit_code !== null || record.duration_ms !== 0 || record.output.stdout || record.output.stderr)) fail('A blocked run cannot include execution results.');
    if (local) {
      const receiptIds = new Set();
      for (const receipt of record.receipts) { receiptShape(receipt,record); if (receiptIds.has(receipt.id)) fail('Duplicate receipt ID.'); receiptIds.add(receipt.id); }
      const matches = candidateScan(record).receiptMatches;
      for (const receipt of record.receipts) if (!matches.includes(receipt.candidate)) fail('Receipt candidate is not part of the recorded output.');
    }
  }
  for (const record of report.records) {
    if (record.kind === 'capture') {
      if (record.baseline_id !== undefined) fail('A capture cannot have a baseline.');
      continue;
    }
    const base = ids.get(record.baseline_id);
    if (!base || base.kind !== 'capture' || base.challenge !== record.challenge || base.category !== record.category) fail('Replay baseline must be a capture for the same challenge.');
    const driftedSet = base.files.length !== record.files.length || record.files.some(file => !base.files.some(previous=>previous.path===file.path && previous.role===file.role));
    if ((!local || !record.issues.length) && driftedSet) fail('Replay file set disagrees with its capture.');
    if (record.files.some(file => {const previous=base.files.find(item=>item.path===file.path);return previous ? previous.observed_sha256 !== file.baseline_sha256 : file.baseline_sha256 !== null;})) fail('Replay baseline hash disagrees with its capture.');
    if (local && base.synthetic !== record.synthetic) fail('Replay synthetic identity disagrees with its capture.');
  }
  return report;
}

export async function sha256(bytes) {
  if (!(bytes instanceof Uint8Array)) fail('Hash input must be bytes.');
  if (!globalThis.crypto?.subtle) fail('File checking needs a secure browser context (HTTPS or localhost).');
  const result = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(result), byte => byte.toString(16).padStart(2, '0')).join('');
}

function freeze(value) {
  if (object(value) || Array.isArray(value)) {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}

export async function verifyReport(report, options) {
  // Validate an independent snapshot; caller mutation cannot race digest checks.
  const snapshot = parseReport(JSON.stringify(report), options);
  for (const record of snapshot.records) {
    for (const stream of ['stdout', 'stderr']) {
      if (await sha256(outputBytes(record,stream)) !== record.output[`${stream}_sha256`]) fail(`Record ${record.id}: ${stream} does not match its recorded hash.`);
    }
    for (const receipt of record.receipts || []) if (await sha256(encoder.encode(receipt.candidate)) !== receipt.candidate_sha256) fail('Receipt candidate does not match its hash.');
  }
  freeze(snapshot); verified.add(snapshot);
  return snapshot;
}

export function candidateScan(record) {
  if (candidateCache.has(record)) return candidateCache.get(record);
  const source = record.output.encoding === 'base64' ? atob(record.output.stdout) + '\n' + atob(record.output.stderr) : record.output.stdout + '\n' + record.output.stderr;
  const values = new Set();
  const wanted = new Set((record.receipts || []).map(receipt=>receipt.candidate)), receiptMatches = new Set();
  let start = -1, limited = false;
  // Scan once: an unmatched prefix must never restart a scan of its suffix.
  for (let index = 0; index < source.length; index++) {
    if (start < 0) {
      if (source.startsWith('hitcon{', index)) { start = index; index += 6; }
      continue;
    }
    const point = source.charCodeAt(index);
    if (point < 0x20 || point > 0x7e) { start = -1; continue; }
    if (source[index] !== '}') continue;
    if (index === start + 7) {start = -1;continue;}
    if (wanted.size) {const value=source.slice(start,index+1);if (wanted.has(value)) receiptMatches.add(value);}
    if (index - start + 1 > 4096) limited = true;
    else {
      const value = source.slice(start, index + 1);
      if (!values.has(value)) {
        if (values.size === 32) limited = true;
        else values.add(value);
      }
    }
    start = -1;
  }
  const result = Object.freeze({values: Object.freeze([...values]), limited, receiptMatches: Object.freeze([...receiptMatches])});
  if (Object.isFrozen(record) && Object.isFrozen(record.output)) candidateCache.set(record, result);
  return result;
}

export const candidates = record => candidateScan(record).values;

export function recordStatus(report, record) {
  const status = (code, title, reason) => ({code, title, reason});
  if (!verified.has(report) || !report.records.includes(record)) return status('UNVERIFIED', 'Evidence not checked', 'Open and verify this report before reviewing its outcome.');
  const execution = record.execution_status;
  if (execution === 'FAILED') return status('FAILED', 'Solver exited with an error', `Exit code ${record.exit_code}. Candidate-shaped output is diagnostic evidence only.`);
  if (execution === 'TIMEOUT') return status('TIMEOUT', 'Solver reached its deadline', `The process exceeded its ${record.timeout_s}s limit. Review the bounded output before rerunning locally.`);
  if (execution === 'OUTPUT_LIMIT') return status('OUTPUT_LIMIT', 'Output limit reached', 'Output was truncated. This record cannot establish a complete replay.');
  if (execution === 'ERROR') return status('ERROR', 'Solver could not start', 'Review the diagnostic output and local environment.');
  if (record.problem || record.issues?.length) return status('STALE','Provenance needs review',record.problem || `Changed provenance: ${record.issues.join(', ')}. Review it and recapture locally.`);
  if (record.files.some(file=>file.baseline_sha256 === null || file.observed_sha256 === null)) return status('STALE','File evidence unavailable','A declared file has no captured or observed hash. Review it and recapture locally.');
  const drift = record.files.find(file => file.baseline_sha256 !== file.observed_sha256);
  if (drift) return status('STALE', 'Input changed', `${drift.path} differs from its captured hash. Review the change and recapture locally.`);
  const base = report.records.find(item => item.id === record.baseline_id);
  if (base && (base.runtime !== record.runtime || JSON.stringify(base.command) !== JSON.stringify(record.command))) return status('STALE', 'Runtime or command changed', 'The replay environment differs from its capture. Recapture locally before relying on it.');
  if (execution === 'NOT_RUN') return status('BLOCKED', 'Solver was not run', 'The report records no execution. Review the local preparation steps.');
  const scan = candidateScan(record), found = scan.values;
  if (scan.limited) return status('CANDIDATE_LIMIT', 'Candidate review limited', 'At most 32 distinct candidates of up to 4096 characters are shown. Review the full raw output locally; a complete count or single-candidate result is not established.');
  if (found.length > 1) return status('AMBIGUOUS', `${found.length} candidates found`, 'Resolve the ambiguity locally; this report does not choose a candidate.');
  if (found.length === 0) return status('NO_CANDIDATE', 'No candidate found', 'The process completed without a flag-shaped candidate. Inspect its output.');
  if (!base) return status('CAPTURED', 'Candidate captured', 'One candidate was recorded. A separate local replay is still needed.');
  if (recordStatus(report, base).code !== 'CAPTURED') return status('BLOCKED', 'Capture needs review', 'The baseline is not a complete single-candidate capture.');
  if (base.output.stdout_sha256 !== record.output.stdout_sha256 || base.output.stderr_sha256 !== record.output.stderr_sha256) return status('DIFFERENT', 'Replay output differs', 'At least one output stream differs from the capture. Inspect both runs.');
  return status('REPRODUCED', 'Replay output matched', 'The recorded local replay matches the capture’s files, runtime, command and output. This is not organizer acceptance.');
}

export async function checkFile(file, expectedHash) {
  hash(expectedHash, 'Expected file hash');
  if (!Number.isFinite(file?.size) || file.size < 0 || file.size > MAX_FILE_BYTES) fail('Choose a file of at most 16 MiB.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (bytes.byteLength > MAX_FILE_BYTES) fail('Choose a file of at most 16 MiB.');
  const value = await sha256(bytes);
  return {hash: value, matches: value === expectedHash};
}

export function createSelectionGate() {
  let generation = 0;
  return {next: () => ++generation, isCurrent: token => token === generation};
}

export function viewVerdict(report, record, currentFile) {
  const status = recordStatus(report, record);
  if (!currentFile || !['REPRODUCED', 'CAPTURED'].includes(status.code)) return status;
  if (currentFile.pending) return {code: 'CHECKING', title: 'Checking current file',
    reason: `Checking ${currentFile.name} against the captured hash for ${currentFile.path}. The current-file result is pending.`};
  if (currentFile.error) return {code: 'FILE_ERROR', title: 'File check failed',
    reason: `${currentFile.name} could not be checked against ${currentFile.path}. ${currentFile.error} No current-file match is established by this selection.`};
  return {code: currentFile.matches ? 'MATCH' : 'STALE',
    title: currentFile.matches ? 'Current file matches' : 'Current file differs',
    reason: `${currentFile.name} ${currentFile.matches ? 'matches' : 'does not match'} the captured hash for ${currentFile.path}. Only this file was checked here; a complete local replay is still needed.`};
}
