import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('workspace print styling does not hide legacy pages', () => {
  const css = readFileSync(new URL('../src/workspace/workspace.css', import.meta.url), 'utf8');
  assert.doesNotMatch(css, /@media print\s*\{\s*body \*/);
  assert.match(css, /body\.inquiry-print/);
});
