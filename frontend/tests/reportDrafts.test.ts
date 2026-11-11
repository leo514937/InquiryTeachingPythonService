import assert from 'node:assert/strict';
import test from 'node:test';
import { mergeDrafts } from '../src/workspace/components/reportDrafts.ts';

test('refresh preserves dirty drafts and initializes new narratives', () => {
  const result = mergeDrafts({ a: '教师未保存', b: '原文' }, { a: '原文', b: '原文' }, { a: '原文', b: '新服务端版本', c: '新段落' });
  assert.deepEqual(result, { a: '教师未保存', b: '新服务端版本', c: '新段落' });
});
