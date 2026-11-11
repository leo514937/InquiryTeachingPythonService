
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { layoutDag, nodeStatusLabels } from '../src/workspace/dagLayout.ts';

test('DAG layout follows real edges and handles parallel branches', () => {
  const graph = {
    id:'r', mode:'lesson', status:'running', created_at:'', updated_at:'', error:null,
    incomplete:false, empty_reason:null, event_cursor:0,
    nodes:['root','left','right','join'].map(id => ({id, capability:'x', depends_on:[], status:'queued', attempts:0, started_at:null, finished_at:null, error_code:null, error_message:null, input_summary:'', output_summary:'', result_refs:[], change_kind:null})),
    edges:[{id:'a',source:'root',target:'left'},{id:'b',source:'root',target:'right'},
      {id:'c',source:'left',target:'join'},{id:'d',source:'right',target:'join'}],
  };
  const positions=layoutDag(graph);
  assert.ok(positions.root.y < positions.left.y && positions.root.y < positions.right.y);
  assert.ok(positions.join.y > positions.left.y && positions.join.y > positions.right.y);
  assert.notEqual(positions.left.x, positions.right.x);
});

test('discarded in-flight results never claim the worker was stopped', () => {
  assert.match(nodeStatusLabels.result_discarded, /状态未知/);
});

