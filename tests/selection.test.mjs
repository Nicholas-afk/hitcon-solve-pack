import test from 'node:test';
import assert from 'node:assert/strict';
import { createSelectionGate } from '../docs/model.mjs';

test('later report, record or file selection discards previous async results', () => {
  const gate = createSelectionGate();
  const fileCheck = gate.next();
  const newRecord = gate.next();
  assert.equal(gate.isCurrent(fileCheck), false);
  assert.equal(gate.isCurrent(newRecord), true);
  const reportLoad = gate.next();
  assert.equal(gate.isCurrent(newRecord), false);
  assert.equal(gate.isCurrent(reportLoad), true);
});
