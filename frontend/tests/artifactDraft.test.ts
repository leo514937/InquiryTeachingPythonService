import assert from 'node:assert/strict';
import test from 'node:test';
import { artifactDraftDirty } from '../src/workspace/components/artifactDraft.ts';

test('artifact draft is dirty only when teacher changed the title or body', () => {
  const artifact = { type: 'InquiryQuestion', content: { title: '问题', question: '为什么？' } };
  assert.equal(artifactDraftDirty(artifact, '问题', '为什么？'), false);
  assert.equal(artifactDraftDirty(artifact, '新问题', '为什么？'), true);
  assert.equal(artifactDraftDirty(artifact, '问题', '变化'), true);
});
