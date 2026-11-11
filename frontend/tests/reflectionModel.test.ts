import assert from 'node:assert/strict';
import test from 'node:test';
import { reflectionRays } from '../src/workspace/artifacts/reflectionModel.ts';

test('reflection rays are symmetric about the normal', () => {
  for (const angle of [0, 30, 45, 80]) {
    const rays = reflectionRays(angle);
    assert.equal(rays.incident.x + rays.reflected.x, 0);
    assert.equal(rays.incident.y, rays.reflected.y);
    assert.equal(rays.reflectedAngle, angle);
  }
});

test('rejects angles outside the model or fractional angles', () => {
  for (const angle of [-1, 81, 1.5, NaN]) assert.throws(() => reflectionRays(angle));
});
