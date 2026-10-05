export const MAX_REPORT_BYTES = 2 * 1024 * 1024;
export const MAX_FILE_BYTES = 16 * 1024 * 1024;
const encoder = new TextEncoder();
const verified = new WeakSet();
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

export function parseReport(source) {
  if (typeof source !== 'string') fail('Report must be JSON text.');
  if (encoder.encode(source).length > MAX_REPORT_BYTES) fail('Report exceeds the 2 MiB limit.');
  let report;
  try { report = JSON.parse(source); } catch { fail('Report is not valid JSON.'); }
  keys(report, ['schema_version', 'report_type', 'synthetic', 'title', 'generated_at', 'records'], 'Report');
  if (report.schema_version !== 1 || report.report_type !== 'solvepack-synthetic' || report.synthetic !== true) fail('Open a schema-v1 Solve Pack report explicitly marked synthetic.');
  text(report.title, 'Report title'); timestamp(report.generated_at, 'Report timestamp');
  if (!Array.isArray(report.records) || !report.records.length || report.records.length > 128) fail('Report must have 1–128 records.');
  const ids = new Map();
  for (const record of report.records) {
    keys(record, ['id','challenge','category','kind','created_at','runtime','duration_ms','timeout_s','exit_code','execution_status','files','output','baseline_id','command'], 'Record');
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
    if (!Array.isArray(record.command) || !record.command.length || record.command.length > 32) fail('Recorded command must be a literal argument list.');
    for (const arg of record.command) text(arg, 'Command argument', 1024);
    if (!Array.isArray(record.files) || !record.files.length || record.files.length > 64) fail('Record must declare 1–64 files.');
    const paths = new Set();
    for (const file of record.files) {
      keys(file, ['path','role','baseline_sha256','observed_sha256'], 'File');
      text(file.path, 'File path');
      if (file.path.includes('\\') || file.path.includes(':') || file.path.startsWith('/') || file.path.split('/').some(part => !part || part === '.' || part === '..') || paths.has(file.path)) fail('File paths must be unique, relative and stay inside the example.');
      paths.add(file.path);
      if (!['input', 'solver'].includes(file.role)) fail('File role must be input or solver.');
      hash(file.baseline_sha256, 'Baseline file hash'); hash(file.observed_sha256, 'Observed file hash');
    }
    keys(record.output, ['stdout','stderr','stdout_sha256','stderr_sha256'], 'Output');
    for (const stream of ['stdout', 'stderr']) {
      if (typeof record.output[stream] !== 'string') fail(`${stream} must be text.`);
      hash(record.output[`${stream}_sha256`], `${stream} hash`);
    }
    if (encoder.encode(record.output.stdout).length + encoder.encode(record.output.stderr).length > 1048576) fail('Combined output exceeds 1 MiB.');
    if (record.execution_status === 'NOT_RUN' && (record.exit_code !== null || record.duration_ms !== 0 || record.output.stdout || record.output.stderr)) fail('A blocked run cannot include execution results.');
  }
  for (const record of report.records) {
    if (record.kind === 'capture') {
      if (record.baseline_id !== undefined) fail('A capture cannot have a baseline.');
      continue;
    }
    const base = ids.get(record.baseline_id);
    if (!base || base.kind !== 'capture' || base.challenge !== record.challenge || base.category !== record.category) fail('Replay baseline must be a capture for the same challenge.');
    if (base.files.length !== record.files.length || record.files.some(file => {
      const previous = base.files.find(item => item.path === file.path && item.role === file.role);
      return !previous || previous.observed_sha256 !== file.baseline_sha256;
    })) fail('Replay file set or baseline hash disagrees with its capture.');
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

export async function verifyReport(report) {
  // Validate an independent snapshot; caller mutation cannot race digest checks.
  const snapshot = parseReport(JSON.stringify(report));
  for (const record of snapshot.records) {
    for (const stream of ['stdout', 'stderr']) {
      if (await sha256(encoder.encode(record.output[stream])) !== record.output[`${stream}_sha256`]) fail(`Record ${record.id}: ${stream} does not match its recorded hash.`);
    }
  }
  freeze(snapshot); verified.add(snapshot);
  return snapshot;
}

export function candidates(record) {
  return [...new Set((record.output.stdout + '\n' + record.output.stderr).match(/hitcon\{[\x20-\x7E]+?\}/g) || [])];
}

export function recordStatus(report, record) {
  const status = (code, title, reason) => ({code, title, reason});
  if (!verified.has(report) || !report.records.includes(record)) return status('UNVERIFIED', 'Evidence not checked', 'Open and verify this report before reviewing its outcome.');
  const execution = record.execution_status;
  if (execution === 'FAILED') return status('FAILED', 'Solver exited with an error', `Exit code ${record.exit_code}. Candidate-shaped output is diagnostic evidence only.`);
  if (execution === 'TIMEOUT') return status('TIMEOUT', 'Solver reached its deadline', `The process exceeded its ${record.timeout_s}s limit. Review the bounded output before rerunning locally.`);
  if (execution === 'OUTPUT_LIMIT') return status('OUTPUT_LIMIT', 'Output limit reached', 'Output was truncated. This record cannot establish a complete replay.');
  if (execution === 'ERROR') return status('ERROR', 'Solver could not start', 'Review the diagnostic output and local environment.');
  const drift = record.files.find(file => file.baseline_sha256 !== file.observed_sha256);
  if (drift) return status('STALE', 'Input changed', `${drift.path} differs from its captured hash. Review the change and recapture locally.`);
  const base = report.records.find(item => item.id === record.baseline_id);
  if (base && (base.runtime !== record.runtime || JSON.stringify(base.command) !== JSON.stringify(record.command))) return status('STALE', 'Runtime or command changed', 'The replay environment differs from its capture. Recapture locally before relying on it.');
  if (execution === 'NOT_RUN') return status('BLOCKED', 'Solver was not run', 'The report records no execution. Review the local preparation steps.');
  const found = candidates(record);
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
