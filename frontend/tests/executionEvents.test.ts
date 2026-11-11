import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseExecutionEvents, mergeExecutionEvents } from '../src/workspace/executionEvents.ts';

test('parses safe sequenced SSE events and merges without duplicates', () => {
  const batch = parseExecutionEvents('id: 2\nevent: node_started\ndata: {"node_id":"goal","status":"running"}\n\nid: 3\nevent: node_succeeded\ndata: {"node_id":"goal"}\n\n');
  assert.deepEqual(batch.map(e => [e.sequence, e.kind, e.nodeId]), [[2,'node_started','goal'],[3,'node_succeeded','goal']]);
  assert.deepEqual(mergeExecutionEvents(batch, batch).map(e => e.sequence), [2,3]);
});

test('ignores malformed events rather than inventing execution data', () => {
  assert.deepEqual(parseExecutionEvents('id: bad\nevent: running\ndata: {}\n\nid: 4\nevent: running\ndata: invalid\n\n'), []);
});
