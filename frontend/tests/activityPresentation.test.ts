import {test} from 'node:test';
import assert from 'node:assert/strict';
import {activityFields} from '../src/workspace/activityPresentation.ts';

test('reading and survey tasks expose different structured fields',()=>{
 assert.deepEqual(activityFields('ReadingInquiryTask',{passages:['片段'],questions:['谁说的？']}),[{label:'阅读材料',value:'片段'},{label:'思考问题',value:'谁说的？'}]);
 assert.deepEqual(activityFields('SurveyTask',{questions:['你喜欢哪类书？'],steps:['采访']}),[{label:'调查问题',value:'你喜欢哪类书？'},{label:'活动步骤',value:'采访'}]);
});
