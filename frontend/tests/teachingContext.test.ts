import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cleanTeachingContext, changedTeachingFields} from '../src/workspace/teachingContext.ts';

test('reusing context never sends stale topic or stale assumptions',()=>{
 const result=cleanTeachingContext({subject:'语文',grade:'四年级',topic:'旧主题',assumptions:['学科未提供']} as any);
 assert.deepEqual(result,{subject:'语文',grade:'四年级'});
});

test('detects changed teaching conditions without treating derived fields as inputs',()=>{
 assert.deepEqual(changedTeachingFields({grade:'三年级',resources:['纸']},{grade:'四年级',resources:['纸','尺'],assumptions:['derived']} as any),['grade','resources']);
 assert.deepEqual(changedTeachingFields({resources:[]},{resources:undefined}),[]);
});

