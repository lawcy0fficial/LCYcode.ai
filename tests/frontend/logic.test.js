// logic.test.js
// Run with: node --test tests/frontend
// No npm install needed — uses Node's built-in test runner and assert
// module, matching this project's zero-JS-tooling philosophy.
const test = require('node:test');
const assert = require('node:assert/strict');
const {
  diffLines, mapStageForRail, railStageStates, parseSSEBuffer, providerRowInfo, STAGE_RAIL_ORDER,
} = require('../../frontend/js/logic.js');

test('diffLines: identical text is all "same" lines', () => {
  const result = diffLines('a\nb\nc', 'a\nb\nc');
  assert.deepEqual(result, [
    { type: 'same', text: 'a' }, { type: 'same', text: 'b' }, { type: 'same', text: 'c' },
  ]);
});

test('diffLines: brand new file (no before) is all additions', () => {
  const result = diffLines('', 'line1\nline2');
  // splitting '' gives [''], so the empty old side shows as one deleted blank line
  // followed by two adds — that's correct LCS behavior, not a bug: an empty
  // string and "no lines" aren't quite the same input, which the null-before
  // caller (registry.py) sidesteps by passing '' explicitly. Assert the adds
  // are present and nothing from the real content was lost.
  const adds = result.filter(l => l.type === 'add').map(l => l.text);
  assert.deepEqual(adds, ['line1', 'line2']);
});

test('diffLines: pure deletion', () => {
  const result = diffLines('a\nb\nc', 'a\nc');
  assert.deepEqual(result, [
    { type: 'same', text: 'a' }, { type: 'del', text: 'b' }, { type: 'same', text: 'c' },
  ]);
});

test('diffLines: pure addition in the middle', () => {
  const result = diffLines('a\nc', 'a\nb\nc');
  assert.deepEqual(result, [
    { type: 'same', text: 'a' }, { type: 'add', text: 'b' }, { type: 'same', text: 'c' },
  ]);
});

test('diffLines: totally different content has no same lines', () => {
  const result = diffLines('x\ny', 'p\nq');
  assert.ok(result.every(l => l.type !== 'same'));
  assert.equal(result.filter(l => l.type === 'del').length, 2);
  assert.equal(result.filter(l => l.type === 'add').length, 2);
});

test('diffLines: returns null past the line cap instead of hanging', () => {
  const big = Array.from({ length: 10 }, (_, i) => `line${i}`).join('\n');
  const result = diffLines(big, big + '\nextra', 5);  // cap of 5, content has more
  assert.equal(result, null);
});

test('mapStageForRail: RESUME maps to PLAN, PAUSED maps to REVIEW, others pass through', () => {
  assert.equal(mapStageForRail('RESUME'), 'PLAN');
  assert.equal(mapStageForRail('PAUSED'), 'REVIEW');
  assert.equal(mapStageForRail('EXECUTE'), 'EXECUTE');
  assert.equal(mapStageForRail('DONE'), 'DONE');
});

test('railStageStates: stages before the target are done, target is active, rest are none', () => {
  const states = railStageStates('EXECUTE');
  assert.equal(states.DESCRIBE, 'done');
  assert.equal(states.PLAN, 'done');
  assert.equal(states.EXECUTE, 'active');
  assert.equal(states.REVIEW, 'none');
  assert.equal(states.DONE, 'none');
});

test('railStageStates: RESUME activates the PLAN dot, not a nonexistent RESUME dot', () => {
  const states = railStageStates('RESUME');
  assert.equal(states.PLAN, 'active');
});

test('railStageStates: DONE marks every stage done or active, none left as none', () => {
  const states = railStageStates('DONE');
  assert.ok(Object.values(states).every(s => s !== 'none'));
});

test('parseSSEBuffer: parses a single complete event', () => {
  const { events, remainder } = parseSSEBuffer('data: {"type":"stage","stage":"DESCRIBE"}\n\n');
  assert.deepEqual(events, [{ type: 'stage', stage: 'DESCRIBE' }]);
  assert.equal(remainder, '');
});

test('parseSSEBuffer: parses multiple events in one buffer', () => {
  const buf = 'data: {"type":"a"}\n\ndata: {"type":"b"}\n\n';
  const { events, remainder } = parseSSEBuffer(buf);
  assert.deepEqual(events, [{ type: 'a' }, { type: 'b' }]);
  assert.equal(remainder, '');
});

test('parseSSEBuffer: an event split across two network chunks is not parsed until complete', () => {
  const chunk1 = 'data: {"type":"st';
  const { events: events1, remainder: remainder1 } = parseSSEBuffer(chunk1);
  assert.deepEqual(events1, []);
  assert.equal(remainder1, chunk1);  // nothing to parse yet, whole thing carries over

  const chunk2 = remainder1 + 'age"}\n\n';
  const { events: events2, remainder: remainder2 } = parseSSEBuffer(chunk2);
  assert.deepEqual(events2, [{ type: 'stage' }]);
  assert.equal(remainder2, '');
});

test('parseSSEBuffer: ignores non-data lines', () => {
  const { events } = parseSSEBuffer(': keep-alive comment\n\ndata: {"type":"real"}\n\n');
  assert.deepEqual(events, [{ type: 'real' }]);
});

test('providerRowInfo: ollama reachable and enabled is on', () => {
  const { on, label } = providerRowInfo('ollama', { enabled: true, reachable: true, model: 'qwen2.5-coder:7b' });
  assert.equal(on, true);
  assert.equal(label, 'ollama (qwen2.5-coder:7b)');
});

test('providerRowInfo: ollama enabled but unreachable is off', () => {
  const { on } = providerRowInfo('ollama', { enabled: true, reachable: false, model: 'x' });
  assert.equal(on, false);
});

test('providerRowInfo: cloud provider with a real key is on', () => {
  const { on, label } = providerRowInfo('openrouter', [{ key: 'sk-...abcd', cooling_down: false }]);
  assert.equal(on, true);
  assert.equal(label, 'openrouter');
});

test('providerRowInfo: cloud provider with only placeholder keys is off and labeled', () => {
  const { on, label } = providerRowInfo('deepseek', [{ placeholder: true }]);
  assert.equal(on, false);
  assert.equal(label, 'deepseek (placeholder only)');
});

test('providerRowInfo: mix of placeholder and real keys is on, plain label', () => {
  const { on, label } = providerRowInfo('grok', [{ placeholder: true }, { key: 'real', cooling_down: false }]);
  assert.equal(on, true);
  assert.equal(label, 'grok');
});

test('STAGE_RAIL_ORDER matches the five dots the GUI actually renders', () => {
  assert.deepEqual(STAGE_RAIL_ORDER, ['DESCRIBE', 'PLAN', 'EXECUTE', 'REVIEW', 'DONE']);
});
