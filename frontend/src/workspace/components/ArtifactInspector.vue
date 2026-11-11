<template>
  <div class="inspector-content">
    <div v-if="!artifact" class="side-empty"><span class="empty-symbol">◇</span><h3>选择一个教学对象</h3><p>在画布中选择对象，查看属性、关联与版本。</p></div>
    <template v-else>
      <div class="side-heading"><div><span class="eyebrow">OBJECT PROPERTIES</span><h3>{{ labels[artifact.type] || '教学对象' }}</h3></div><span class="state-pill">v{{ artifact.version }}</span></div>
      <p class="side-help">按教学需要调整内容；保存会创建新版本。</p>
      <label class="field-label">标题<input :value="draft.title || ''" @input="set('title', ($event.target as HTMLInputElement).value)"></label>
      <label class="field-label">{{ artifact.type === 'InquiryQuestion' ? '问题内容' : '内容说明' }}<textarea :value="draft[bodyField] || ''" rows="4" @input="set(bodyField, ($event.target as HTMLTextAreaElement).value)"/></label>
      <label v-if="'student_instructions' in draft" class="field-label">学生任务语言<textarea :value="draft.student_instructions || ''" rows="3" @input="set('student_instructions', ($event.target as HTMLTextAreaElement).value)"/></label>
      <template v-if="artifact.type === 'Experiment'"><label v-for="field in experimentFields" :key="field.key" class="field-label">{{ field.label }}<textarea :value="listValue(field.key)" rows="3" @input="setList(field.key, ($event.target as HTMLTextAreaElement).value)"/><small>每行一项</small></label></template>
      <label v-if="artifact.type === 'Assessment'" class="field-label">评价标准<textarea :value="listValue('criteria')" rows="3" @input="setList('criteria', ($event.target as HTMLTextAreaElement).value)"/><small>每行一项</small></label>
      <fieldset v-if="Array.isArray(draft.goal_ids) && (artifact.type === 'InquiryActivity' || artifact.type === 'Assessment')" class="goal-field"><legend>关联目标</legend><label v-for="goal in goals" :key="goal.id"><input type="checkbox" :checked="draft.goal_ids.includes(goal.id)" @change="toggleGoal(goal.id)"> {{ goal.content.title || '未命名目标' }}</label><p v-if="missingGoals">有 {{ missingGoals }} 个关联对象不可用，保存时保留原关联。</p></fieldset>
      <div v-if="artifact.source_refs?.length" class="sources"><strong>课程依据</strong><p v-for="source in artifact.source_refs" :key="source.expert_id + source.source">{{ source.source }}</p></div><p v-else class="side-help">暂无可用课程标准依据</p>
      <p v-if="conflict" class="conflict-notice" role="alert">对象已更新，本地输入已保留。请对照最新内容手动合并。</p>
      <pre v-if="conflict && latest" class="conflict-latest">{{ JSON.stringify(latest.content, null, 2) }}</pre>
      <div class="inspector-actions"><button type="button" class="primary" :disabled="busy || !dirty" @click="$emit('save')">保存修改</button><button v-if="dirty" type="button" :disabled="busy" @click="$emit('discard')">放弃修改</button><button v-if="conflict" type="button" @click="$emit('merge-latest')">以最新版本继续合并</button><button type="button" :disabled="busy || dirty" @click="$emit('lock')">{{ artifact.locked ? '解锁' : '锁定' }}</button><button type="button" :disabled="busy || dirty" @click="$emit('versions')">对象版本</button></div>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue';
import type { Artifact } from '../api';
const props = defineProps<{artifact: Artifact | null; draft: Record<string, any>; artifacts: Artifact[]; busy: boolean; dirty: boolean; conflict: boolean; latest: Artifact | null}>();
const emit = defineEmits<{change:[key:string,value:unknown]; save:[]; discard:[]; lock:[]; versions:[]; 'merge-latest':[]}>();
const labels: Record<string,string> = {LearningGoal:'学习目标',InquiryQuestion:'探究问题',Experiment:'实验设计',InquiryActivity:'探究活动',Assessment:'学习评价',KnowledgeCard:'知识依据'};
const experimentFields = [{key:'materials',label:'实验材料'}, {key:'steps',label:'实验步骤'}, {key:'safety_measures',label:'安全措施'}];
const bodyField = computed(() => props.artifact?.type === 'InquiryQuestion' ? 'question' : 'description');
const goals = computed(() => props.artifacts.filter(a => a.type === 'LearningGoal'));
const missingGoals = computed(() => (Array.isArray(props.draft.goal_ids) ? props.draft.goal_ids : []).filter((id:string) => !goals.value.some(g => g.id === id)).length);
function set(key:string, value:unknown) { emit('change', key, value); }
function listValue(key:string) { const value = props.draft[key]; return Array.isArray(value) ? value.join('\n') : String(value || ''); }
function setList(key:string, text:string) { set(key, typeof props.draft[key] === 'string' ? text : text.split('\n').filter(Boolean)); }
function toggleGoal(id:string) { const ids = props.draft.goal_ids as string[]; set('goal_ids', ids.includes(id) ? ids.filter(value => value !== id) : [...ids,id]); }
</script>
