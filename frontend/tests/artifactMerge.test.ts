import assert from 'node:assert/strict';
import test from 'node:test';
import { mergeArtifactDraft } from '../src/workspace/components/artifactMerge.ts';

test('merge preserves concurrent unknown fields and reports overlapping edits', () => {
  const base = {title:'原题', description:'原内容', custom:{note:'原注', kept:true}};
  const local = {title:'我的标题', description:'原内容', custom:{note:'原注', kept:true}};
  const latest = {title:'同事标题', description:'同事内容', custom:{note:'同事注', kept:true, extra:'新增'}};
  const result = mergeArtifactDraft(base, local, latest);
  assert.deepEqual(result.content, {title:'我的标题', description:'同事内容', custom:{note:'同事注', kept:true, extra:'新增'}});
  assert.deepEqual(result.conflicts, ['/title']);
});
