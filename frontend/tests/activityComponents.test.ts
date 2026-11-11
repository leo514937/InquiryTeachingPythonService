import {test} from 'node:test';
import assert from 'node:assert/strict';
import {getActivityComponent} from '../src/workspace/activityComponents.ts';

test('known optional component resolves without replacing unknown activities',()=>{
 assert.equal(getActivityComponent('light_reflection_v1')?.renderer,'ReflectionExperiment');
 assert.equal(getActivityComponent('not-registered'),undefined);
 assert.equal(getActivityComponent(undefined),undefined);
});
