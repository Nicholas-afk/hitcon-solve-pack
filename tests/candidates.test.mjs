import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {candidates, parseReport, verifyReport, recordStatus, sha256} from '../docs/model.mjs';

const raw = await readFile(new URL('../docs/demo.json', import.meta.url), 'utf8');
async function checkedOutput(stdout) {
  const data = JSON.parse(raw);
  data.records = [data.records[0]];
  data.records[0].output.stdout = stdout;
  data.records[0].output.stdout_sha256 = await sha256(new TextEncoder().encode(stdout));
  return verifyReport(parseReport(JSON.stringify(data)));
}

test('maximum accepted unmatched prefixes finish promptly through verified status derivation', () => {
  const script = `
    import {readFile} from 'node:fs/promises';
    import {parseReport, verifyReport, recordStatus, sha256} from './docs/model.mjs';
    const data = JSON.parse(await readFile('./docs/demo.json', 'utf8'));
    data.records = [data.records[0]];
    const output = data.records[0].output;
    output.stdout = 'hitcon{'.repeat(149000);
    output.stdout_sha256 = await sha256(new TextEncoder().encode(output.stdout));
    const report = await verifyReport(parseReport(JSON.stringify(data)));
    if (recordStatus(report, report.records[0]).code !== 'NO_CANDIDATE') throw Error('false candidate');
  `;
  assert.doesNotThrow(() => execFileSync(process.execPath, ['--input-type=module', '-e', script], {
    cwd: new URL('..', import.meta.url), timeout: 2000, stdio: 'pipe'
  }));
});

test('candidate display is bounded and never claims complete single-candidate evidence after a limit', async () => {
  for (const output of [Array.from({length: 40}, (_, i) => `hitcon{synthetic_${i}}`).join('\n'),
    'hitcon{' + 'x'.repeat(5000) + '}']) {
    const report = await checkedOutput(output);
    const record = report.records[0];
    assert.equal(recordStatus(report, record).code, 'CANDIDATE_LIMIT');
    assert.ok(candidates(record).length <= 32);
    assert.ok(candidates(record).every(value => value.length <= 4096));
  }
});

test('linear scanning preserves printable, nonempty, distinct candidate semantics', () => {
  const record = {output: {stdout: 'hitcon{unfinished\n' +
    'hitcon{synthetic_a} hitcon{synthetic_a} hitcon{outer hitcon{inner}} hitcon{}',
    stderr: 'hitcon{synthetic_b}'}};
  assert.deepEqual(candidates(record), ['hitcon{synthetic_a}', 'hitcon{outer hitcon{inner}', 'hitcon{synthetic_b}']);
});
