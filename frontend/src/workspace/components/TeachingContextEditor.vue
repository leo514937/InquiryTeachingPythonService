<template>
  <details class="context-editor"><summary>补充教学条件（可选）</summary>
    <div class="context-grid">
      <label>学科<input :value="modelValue.subject || ''" @input="set('subject', text($event))" placeholder="例如：语文"></label>
      <label>学段<input :value="modelValue.stage || ''" @input="set('stage', text($event))" placeholder="例如：小学"></label>
      <label>年级<input :value="modelValue.grade || ''" @input="set('grade', text($event))" placeholder="例如：四年级"></label>
      <label>课程时长（分钟）<input type="number" min="1" max="1440" :value="modelValue.duration_minutes || ''" @input="set('duration_minutes', text($event) ? Number(text($event)) : undefined)"></label>
      <label>教学目标<textarea :value="lines(modelValue.learning_goals)" @input="set('learning_goals', split($event))" placeholder="每行一项"/></label>
      <label>已有知识基础<textarea :value="modelValue.prior_knowledge || ''" @input="set('prior_knowledge', text($event))"/></label>
      <label>阅读与语言水平<textarea :value="modelValue.language_level || ''" @input="set('language_level', text($event))"/></label>
      <label>真实生活情境<textarea :value="modelValue.real_life_context || ''" @input="set('real_life_context', text($event))"/></label>
      <label>教学资源<textarea :value="lines(modelValue.resources)" @input="set('resources', split($event))" placeholder="每行一项"/></label>
      <label>学生活动形式<textarea :value="lines(modelValue.activity_formats)" @input="set('activity_formats', split($event))" placeholder="每行一项"/></label>
      <label>安全与环境约束<textarea :value="modelValue.safety_constraints || ''" @input="set('safety_constraints', text($event))"/></label>
      <label>教师特殊要求<textarea :value="modelValue.teacher_requirements || ''" @input="set('teacher_requirements', text($event))"/></label>
    </div>
    <p>未填写的条件会标为未提供，不会自动当作事实。</p>
  </details>
</template>
<script setup lang="ts">
import type { TeachingContextInput } from '../api';
const props=defineProps<{modelValue:TeachingContextInput}>();
const emit=defineEmits<{'update:modelValue':[value:TeachingContextInput]}>();
function set(key:keyof TeachingContextInput,value:unknown){emit('update:modelValue',{...props.modelValue,[key]:value});}
function text(event:Event){return (event.target as HTMLInputElement | HTMLTextAreaElement).value;}
function split(event:Event){return text(event).split('\n').map(s=>s.trim()).filter(Boolean);}
function lines(value:string[]|undefined){return (value || []).join('\n');}
</script>
