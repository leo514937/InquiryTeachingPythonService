<template>
  <form class="task-composer" :class="{'is-busy':busy}" @submit.prevent="submit">
    <div class="task-composer-head"><strong>✧ 描述你的探究教学目标</strong><span>Orchestrator Agent</span></div>
    <textarea v-model="goal" aria-label="编排教学需求" rows="2" placeholder="描述教学主题、学生年级和课堂目标" :disabled="busy"/>
    <TeachingContextEditor :model-value="scope === 'new' ? newContext : context" @update:model-value="updateContext"/>
    <fieldset class="generation-scope"><legend>生成方式</legend><label><input v-model="scope" type="radio" value="new" aria-label="新建工作空间生成"> 新建工作空间</label><label><input v-model="scope" type="radio" value="append" aria-label="追加到当前工作空间"> 追加到当前工作空间</label></fieldset>
    <p v-if="scope === 'append' && changedFields.length" role="status">已更改教学条件：{{ changedFields.map(field => fieldLabels[field]).join('、') }}。目前无法按条件字段准确确定最小影响范围；追加生成不会自动更新已有对象。可使用对象重编排预览检查依赖，已锁定对象仍受保护。</p>
    <div class="task-composer-foot"><label>生成范围 <select :value="mode" :disabled="busy" @change="$emit('update:mode', ($event.target as HTMLSelectElement).value as 'lesson' | 'experiment')"><option value="lesson">完整教学设计</option><option value="experiment">独立实验设计</option></select></label><button class="primary" type="submit" :disabled="busy || !goal.trim()">{{ busy ? '编排执行中…' : '开始自动编排' }}</button></div>
  </form>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import TeachingContextEditor from './TeachingContextEditor.vue';
import type { TeachingContextInput } from '../api';
import { changedTeachingFields } from '../teachingContext';
const props=defineProps<{title:string; mode:'lesson'|'experiment'; context:TeachingContextInput; baselineContext:TeachingContextInput; busy:boolean}>();
const emit=defineEmits<{submit:[goal:string, scope:'new'|'append', context:TeachingContextInput]; 'update:mode':[mode:'lesson'|'experiment']; 'update:context':[context:TeachingContextInput]}>();
const goal=ref(props.title), scope=ref<'new'|'append'>('new'), newContext=ref<TeachingContextInput>({});
const fieldLabels:Record<string,string>={subject:'学科',stage:'学段',grade:'年级',duration_minutes:'课程时长',learning_goals:'教学目标',prior_knowledge:'已有知识',language_level:'语言水平',real_life_context:'生活情境',resources:'教学资源',activity_formats:'活动形式',safety_constraints:'安全约束',teacher_requirements:'教师要求'};
const changedFields=computed(()=>changedTeachingFields(props.baselineContext,props.context));
function updateContext(value:TeachingContextInput){if(scope.value==='new')newContext.value=value;else emit('update:context',value);}
watch(()=>props.title, value=>{goal.value=value;newContext.value={};scope.value='new';});
function submit(){if(goal.value.trim() && !props.busy) emit('submit',goal.value.trim(),scope.value,scope.value==='new' ? newContext.value : props.context);}
</script>
