import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseReport, verifyReport, recordStatus, sha256, checkFile, MAX_REPORT_BYTES, MAX_FILE_BYTES } from '../docs/model.mjs';

const raw = await readFile(new URL('../docs/demo.json', import.meta.url), 'utf8');
const fresh = () => JSON.parse(raw);
const parsed = (data = fresh()) => parseReport(JSON.stringify(data));
const row = (report, id) => report.records.find(record => record.id === id);

test('known bytes use SHA-256 and changed bytes fail the file check', async () => {
  const abc = new TextEncoder().encode('abc');
  const expected = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad';
  assert.equal(await sha256(abc), expected);
  assert.equal((await checkFile(new File([abc], 'input'), expected)).matches, true);
  assert.equal((await checkFile(new File(['abd'], 'input'), expected)).matches, false);
  await assert.rejects(checkFile({size: MAX_FILE_BYTES + 1}, expected), /16 MiB/);
});

test('real reports derive match, stale, ambiguity, failure and timeout separately', async () => {
  const report = await verifyReport(parsed());
  for (const [id, code] of Object.entries({'modular-replay': 'REPRODUCED', 'modular-capture': 'CAPTURED',
    'modular-stale': 'STALE', 'bytes-replay': 'REPRODUCED', 'ambiguous-capture': 'AMBIGUOUS',
    'failed-capture': 'FAILED', 'timeout-capture': 'TIMEOUT'})) {
    assert.equal(recordStatus(report, row(report, id)).code, code, id);
  }
  assert.ok(Object.isFrozen(report));
  assert.ok(Object.isFrozen(report.records[0].output));
});

test('unverified or tampered stream data cannot show reproduction', async () => {
  const report = parsed();
  assert.equal(recordStatus(report, row(report, 'modular-replay')).code, 'UNVERIFIED');
  const data = fresh();
  row(data, 'modular-replay').output.stdout += 'tampered';
  await assert.rejects(verifyReport(parsed(data)), /stdout.*hash/i);
});

test('schema, type, duplicate ids, oversized report and acceptance claims reject', () => {
  for (const change of [d => d.synthetic = false, d => d.schema_version = 2, d => d.records = {},
    d => d.records.push(d.records[0]), d => d.accepted = true, d => d.records[0].receipts = [],
    d => d.records[0].duration_ms = -1, d => d.records[0].output.stdout = {},
    d => d.records[0].files[0].path = '../secret', d => d.records[0].execution_status = 'ACCEPTED',
    d => d.records[0].exit_code = 7]) {
    const data = fresh(); change(data); assert.throws(() => parsed(data));
  }
  assert.throws(() => parseReport(' '.repeat(MAX_REPORT_BYTES + 1)), /2 MiB/);
  assert.throws(() => parseReport('{oops'), /JSON/);
});

test('comparison requires a capture for the same challenge with the same file set', () => {
  for (const change of [r => r.baseline_id = 'missing', r => r.baseline_id = 'bytes-capture',
    r => r.baseline_id = 'modular-replay', r => r.files.pop(),
    r => r.files[0].baseline_sha256 = '0'.repeat(64)]) {
    const data = fresh(); change(row(data, 'modular-replay')); assert.throws(() => parsed(data), /baseline|file/i);
  }
});

test('runtime and output drift prevent a confident match, even with one candidate', async () => {
  const data = fresh();
  row(data, 'modular-replay').runtime += ' changed';
  const report = await verifyReport(parsed(data));
  assert.equal(recordStatus(report, row(report, 'modular-replay')).code, 'STALE');
  const changed = fresh();
  const output = row(changed, 'modular-replay').output;
  output.stderr = 'new diagnostic\n';
  output.stderr_sha256 = await sha256(new TextEncoder().encode(output.stderr));
  const checked = await verifyReport(parsed(changed));
  assert.equal(recordStatus(checked, row(checked, 'modular-replay')).code, 'DIFFERENT');
});

test('hostile output remains literal and flag candidates never imply organizer acceptance', async () => {
  const data = fresh();
  const target = row(data, 'modular-capture');
  target.output.stdout = '<img src=x onerror=alert(1)>\nhitcon{synthetic_literal}\n';
  target.output.stdout_sha256 = await sha256(new TextEncoder().encode(target.output.stdout));
  const report = await verifyReport(parsed(data));
  assert.equal(row(report, target.id).output.stdout, target.output.stdout);
  assert.equal(recordStatus(report, row(report, target.id)).code, 'CAPTURED');
  assert.ok(!report.records.some(record => recordStatus(report, record).code === 'ACCEPTED'));
});
