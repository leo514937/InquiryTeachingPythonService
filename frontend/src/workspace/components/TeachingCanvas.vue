<template>
  <section class="teaching-document" aria-labelledby="canvas-heading">
    <header class="document-heading"><div><span class="eyebrow">INQUIRY DESIGN</span><h2 id="canvas-heading">教学画布</h2><p>{{ title }}</p></div><span class="document-count">{{ artifacts.length }} 个教学对象</span></header>
    <div v-if="!artifacts.length" class="canvas-empty"><span class="empty-symbol">✳</span><h3>让一个问题，开启一次探究</h3><p>描述教学目标并生成适合主题的活动。</p></div>
    <section v-for="group in groups" v-show="group.items.length" :id="`group-${group.key}`" :key="group.key" class="document-group">
      <div class="group-heading"><div><span class="group-number">{{ group.number }}</span><h3>{{ group.label }}</h3><small>{{ group.items.length }}</small></div><span>{{ group.caption }}</span></div>
      <article v-for="(item, index) in group.items" :id="`artifact-${item.id}`" :key="item.id" class="teaching-card" :class="[`card-${group.key}`, {selected: item.id === selectedId}]">
        <div class="card-top"><div class="card-kicker"><input :id="`select-${item.id}`" type="checkbox" :checked="selectedIds.includes(item.id)" :aria-label="`选择 ${item.content.title || group.label}`" @change="$emit('toggle-multi', item.id)"><span>{{ labels[item.type] || item.type }}</span><span v-if="item.status === 'stale'" class="state-pill warning">待更新</span><span v-if="item.review_status === 'needs_review'" class="state-pill warning">待审核</span><span v-if="item.locked" class="state-pill">已锁定</span></div><div class="card-actions"><button type="button" :aria-label="`上移 ${item.content.title || group.label}`" :disabled="busy || group.key === 'other' || index === 0" @click="$emit('move', group.items, index, -1)">↑</button><button type="button" :aria-label="`下移 ${item.content.title || group.label}`" :disabled="busy || group.key === 'other' || index === group.items.length - 1" @click="$emit('move', group.items, index, 1)">↓</button><button type="button" :aria-label="`${collapsed.has(item.id) ? '展开' : '折叠'} ${item.content.title || group.label}`" @click="toggle(item.id)">{{ collapsed.has(item.id) ? '+' : '−' }}</button></div></div>
        <div v-if="editing.has(item.id)" class="inline-edit"><label :for="`title-${item.id}`">标题</label><input :id="`title-${item.id}`" v-model="inlineTitles[item.id]"><button type="button" :disabled="busy || !inlineTitles[item.id]?.trim()" @click="saveTitle(item)">保存标题</button><button type="button" @click="editing.delete(item.id)">取消</button></div>
        <template v-else><h4>{{ item.content.title || labels[item.type] || item.type }}</h4><button type="button" class="text-button" @click="startEdit(item)">内联编辑标题</button></template>
        <div v-show="!collapsed.has(item.id)" class="card-body"><p v-if="item.content.description || item.content.question">{{ item.content.description || item.content.question }}</p><p v-for="field in activityFields(item.type,item.content)" :key="field.label" class="card-meta">{{ field.label }}：{{ field.value }}</p>
          <div v-if="getActivityComponent(item.content.component_type)?.renderer === 'ReflectionExperiment' && item.type === 'Experiment'" class="mini-experiment"><div><strong>光的反射</strong><small>理想平面镜模型 · 相对法线测量</small><label :for="`mini-${item.id}`">入射角 {{ angleFor(item.id) }}°</label><input :id="`mini-${item.id}`" type="range" min="0" max="80" step="1" :value="angleFor(item.id)" @input="angles[item.id] = Number(($event.target as HTMLInputElement).value)"></div><svg viewBox="0 0 180 90" role="img" :aria-label="`入射角 ${angleFor(item.id)} 度，反射角 ${angleFor(item.id)} 度`"><line x1="12" y1="78" x2="168" y2="78" stroke="currentColor" stroke-width="3"/><line x1="90" y1="3" x2="90" y2="84" stroke="currentColor" stroke-dasharray="3 4" opacity=".4"/><line :x1="90 + rays(item.id).incident.x / 2" :y1="78 + rays(item.id).incident.y / 2" x2="90" y2="78" stroke="#d77c36" stroke-width="3"/><line x1="90" y1="78" :x2="90 + rays(item.id).reflected.x / 2" :y2="78 + rays(item.id).reflected.y / 2" stroke="#218873" stroke-width="3"/></svg></div>
          <p v-if="item.content.student_instructions" class="student-task"><strong>学生任务：</strong>{{ item.content.student_instructions }}</p><p v-if="related(item.id).length" class="card-relation">关联：{{ related(item.id).join('、') }}</p><p v-else class="card-relation">暂无已记录的关联</p>
          <div class="card-footer"><button type="button" class="text-button" @click="$emit('inspect', item)">编辑属性</button><button v-if="getActivityComponent(item.content.component_type)?.renderer === 'ReflectionExperiment' && item.type === 'Experiment'" type="button" class="text-button" @click="$emit('experiment', item.id)">打开实验 →</button></div>
        </div>
      </article>
    </section>
    <details class="special-components"><summary>可选专业交互组件</summary><button type="button" class="add-experiment" :disabled="busy" @click="$emit('add-experiment')">＋ 添加光的反射实验</button></details>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue';
import { reflectionRays } from '../artifacts/reflectionModel';
import { getActivityComponent } from '../activityComponents';
import { activityFields } from '../activityPresentation';
import type { Artifact, Dependency } from '../api';
const props = defineProps<{title: string; artifacts: Artifact[]; dependencies: Dependency[]; selectedId: string; selectedIds: string[]; busy: boolean}>();
const emit = defineEmits<{inspect: [item: Artifact]; experiment: [id: string]; move: [items: Artifact[], index: number, direction: number]; 'toggle-multi': [id: string]; 'save-title': [item: Artifact, title: string, baseVersion: number]; 'add-experiment': []}>();
const labels: Record<string, string> = {LearningGoal:'学习目标', KnowledgeCard:'知识依据', InquiryQuestion:'探究问题', Experiment:'实验', InquiryActivity:'探究活动', Assessment:'学习评价',ObservationTask:'观察任务',SurveyTask:'调查任务',ReadingInquiryTask:'阅读探究',DataInquiryTask:'数据探究',CollaborationTask:'合作任务',EvidenceRecord:'证据记录',PresentationTask:'成果表达'};
const definitions = [{key:'goals',number:'01',label:'学习目标',caption:'明确学生将理解什么',types:['LearningGoal']},{key:'questions',number:'02',label:'探究问题',caption:'从问题出发',types:['InquiryQuestion']},{key:'knowledge',number:'03',label:'知识依据',caption:'连接可访问的课程资料',types:['KnowledgeCard']},{key:'activities',number:'04',label:'实验与活动',caption:'让探究真实发生',types:['Experiment','InquiryActivity','ObservationTask','SurveyTask','ReadingInquiryTask','DataInquiryTask','CollaborationTask','EvidenceRecord','PresentationTask']},{key:'assessment',number:'05',label:'学习评价',caption:'看见学习的证据',types:['Assessment']}];
const groups = computed(() => { const known = definitions.flatMap(g => g.types); return [...definitions.map(g => ({...g, items: props.artifacts.filter(a => g.types.includes(a.type))})), {key:'other', number:'06', label:'其他对象',caption:'教学补充内容',types:[],items:props.artifacts.filter(a => !known.includes(a.type))}]; });
const angles = reactive<Record<string, number>>({});
const collapsed = reactive(new Set<string>());
const editing = reactive(new Set<string>()), inlineTitles = reactive<Record<string,string>>({}), inlineVersions = reactive<Record<string,number>>({}), inlineBaselines = reactive<Record<string,string>>({});
function angleFor(id: string) { return angles[id] ?? 30; }
function rays(id: string) { return reflectionRays(angleFor(id)); }
function toggle(id: string) { collapsed.has(id) ? collapsed.delete(id) : collapsed.add(id); }
function startEdit(item: Artifact) { editing.add(item.id); inlineTitles[item.id] = String(item.content.title || ''); inlineBaselines[item.id] = inlineTitles[item.id]; inlineVersions[item.id] = item.version; }
function saveTitle(item: Artifact) { emit('save-title', item, inlineTitles[item.id], inlineVersions[item.id]); }
function related(id: string) { const ids = props.dependencies.flatMap(d => d.upstream_id === id ? [d.downstream_id] : d.downstream_id === id ? [d.upstream_id] : []); return [...new Set(ids)].map(id => String(props.artifacts.find(a => a.id === id)?.content.title || '关联对象不可用')); }
function isDirty() { return [...editing].some(id => inlineTitles[id] !== inlineBaselines[id]); }
defineExpose({ isDirty });
watch(() => props.artifacts, () => { for (const id of editing) { const item = props.artifacts.find(a => a.id === id); if (item && item.version > inlineVersions[id] && item.content.title === inlineTitles[id]) editing.delete(id); } }, {deep:true});
</script>
