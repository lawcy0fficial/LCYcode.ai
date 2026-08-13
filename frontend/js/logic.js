// logic.js
// Pure, DOM-free functions extracted from app.js so they're testable
// with plain Node (see tests/frontend/logic.test.js) without pulling
// in a browser test harness or build step — this project stays
// zero-npm-dependency by design, same as the rest of it.
//
// Loaded as a plain <script> before app.js in index.html (exposes
// window.LCYLogic), and also usable via require() from Node for
// tests (module.exports below). Same file, same behavior, both ways.

const DIFF_LINE_CAP = 2000;

// Line-based diff via longest-common-subsequence. Capped so a huge
// file doesn't hang the tab (O(n*m) DP table) — returns null past the
// cap, and callers fall back to a plain full-file view in that case.
function diffLines(oldText, newText, cap) {
  cap = cap || DIFF_LINE_CAP;
  const a = (oldText || '').split('\n');
  const b = (newText || '').split('\n');
  const n = a.length, m = b.length;
  if (n > cap || m > cap) return null;

  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const result = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { result.push({ type: 'same', text: a[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { result.push({ type: 'del', text: a[i] }); i++; }
    else { result.push({ type: 'add', text: b[j] }); j++; }
  }
  while (i < n) { result.push({ type: 'del', text: a[i] }); i++; }
  while (j < m) { result.push({ type: 'add', text: b[j] }); j++; }
  return result;
}

// The pipeline rail only has five dots (DESCRIBE/PLAN/EXECUTE/REVIEW/DONE);
// RESUME and PAUSED are agent_loop stages that don't have their own dot,
// so they map onto the nearest one for the active/done highlighting.
function mapStageForRail(stage) {
  if (stage === 'RESUME') return 'PLAN';
  if (stage === 'PAUSED') return 'REVIEW';
  return stage;
}

const STAGE_RAIL_ORDER = ['DESCRIBE', 'PLAN', 'EXECUTE', 'REVIEW', 'DONE'];

// Given the current rail order and a (mapped) target stage, returns
// which stages are 'active', 'done', or neither — the pure decision
// setStage() renders.
function railStageStates(targetStage) {
  const mapped = mapStageForRail(targetStage);
  const states = {};
  STAGE_RAIL_ORDER.forEach(s => {
    if (s === mapped) states[s] = 'active';
    else if (STAGE_RAIL_ORDER.indexOf(s) < STAGE_RAIL_ORDER.indexOf(mapped)) states[s] = 'done';
    else states[s] = 'none';
  });
  return states;
}

// Splits an accumulating SSE buffer into complete "data: {...}" events
// plus whatever incomplete trailing bytes should carry over to the next
// chunk. This is the parsing loop inside streamFrom(), pulled out so it
// can be tested against arbitrary chunk boundaries without a real fetch
// stream — SSE chunks can split a JSON event across network reads, and
// that's exactly the case worth covering.
function parseSSEBuffer(buffer) {
  const parts = buffer.split('\n\n');
  const remainder = parts.pop();
  const events = [];
  for (const part of parts) {
    if (!part.startsWith('data: ')) continue;
    events.push(JSON.parse(part.slice(6)));
  }
  return { events, remainder };
}

// Provider sidebar row: given the value from /api/status for one
// provider key, decides whether it renders as "on" (green dot) and
// what label to show — including the placeholder-only case, which
// should never look like a live, usable key.
function providerRowInfo(providerName, value) {
  if (providerName === 'ollama') {
    return {
      on: !!(value && value.enabled && value.reachable),
      label: `ollama (${(value && value.model) || '?'})`,
    };
  }
  if (Array.isArray(value)) {
    const realKeys = value.filter(k => !k.placeholder);
    const placeholders = value.length - realKeys.length;
    const on = realKeys.length > 0;
    return { on, label: (!on && placeholders > 0) ? `${providerName} (placeholder only)` : providerName };
  }
  return { on: false, label: providerName };
}

const LCYLogic = { diffLines, mapStageForRail, railStageStates, parseSSEBuffer, providerRowInfo, STAGE_RAIL_ORDER };

if (typeof window !== 'undefined') {
  window.LCYLogic = LCYLogic;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = LCYLogic;
}
