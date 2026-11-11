import { test } from 'node:test';
import assert from 'node:assert/strict';
import { layoutDag } from '../src/workspace/dagLayout.ts';

test('DAG lays out dependencies top to bottom with parallel branches', () => {
  const graph = {id:'r', mode:'lesson', status:'running', created_at:'', updated_at:'', error:null, incomplete:false, empty_reason:null, event_cursor:0,
    nodes:['root','left','right','join'].map(id => ({id, capability:'x', depends_on:[], status:'queued', attempts:0, started_at:null, finished_at:null, error_code:null, error_message:null, input_summary:'', output_summary:'', result_refs:[], change_kind:null})),
    edges:[{id:'a',source:'root',target:'left'},{id:'b',source:'root',target:'right'},{id:'c',source:'left',target:'join'},{id:'d',source:'right',target:'join'}]};
  const positions=layoutDag(graph);
  assert.ok(positions.root.y < positions.left.y && positions.root.y < positions.right.y);
  assert.ok(positions.join.y > positions.left.y && positions.join.y > positions.right.y);
  assert.notEqual(positions.left.x, positions.right.x);
});

test('layout separates thirty nodes in a wide parallel graph', () => {
  const nodes=Array.from({length:30},(_,i)=>({id:`node-${i}`,capability:'x',depends_on:[],status:'queued',attempts:0,started_at:null,finished_at:null,error_code:null,error_message:null,input_summary:'',output_summary:'',result_refs:[],change_kind:null}));
  const graph={id:'r',mode:'lesson',status:'running',created_at:'',updated_at:'',error:null,incomplete:false,empty_reason:null,event_cursor:0,nodes,edges:nodes.slice(1).map((node,i)=>({id:String(i),source:'node-0',target:node.id}))};
  const positions=layoutDag(graph);
  assert.equal(Object.keys(positions).length,30);
  assert.equal(new Set(Object.values(positions).map(p=>`${p.x},${p.y}`)).size,30);
  assert.ok(nodes.slice(1).every(node=>positions[node.id].y>positions['node-0'].y));
});
