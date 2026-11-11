<template>
  <section class="reflection">
    <div><button type="button" @click="goBack">← 返回画布</button><h2>光的反射交互实验</h2><p>理想平面镜模型 · 角度相对于法线测量</p></div>
    <div class="reflection-layout">
      <div><label for="angle">入射角：{{ angle }}°</label><input id="angle" v-model.number="angle" type="range" min="0" max="80" step="1"><input v-model.number="angle" aria-label="入射角度数" type="number" min="0" max="80" step="1"><button type="button" @click="angle = 30">重置角度</button><button type="button" :disabled="busy || !valid" @click="saveRecord">记录一组数据</button></div>
      <svg viewBox="0 0 400 240" role="img" :aria-label="`入射角 ${angle} 度，反射角 ${angle} 度；光线相对于法线对称`">
        <line x1="30" y1="180" x2="370" y2="180" stroke="#274d48" stroke-width="8"/><line x1="200" y1="20" x2="200" y2="200" stroke="#60716d" stroke-dasharray="6 5"/>
        <line :x1="200 + rays.incident.x" :y1="180 + rays.incident.y" x2="200" y2="180" stroke="#ed9b28" stroke-width="4"/>
        <line x1="200" y1="180" :x2="200 + rays.reflected.x" :y2="180 + rays.reflected.y" stroke="#1f8f77" stroke-width="4"/>
        <text x="35" y="220">平面镜</text><text x="210" y="35">法线</text>
      </svg>
      <div><h3>实验记录</h3><p v-if="!rows.length">还没有记录。调整角度后记录数据。</p><table v-else><thead><tr><th>入射角</th><th>反射角</th><th>操作</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.incident_angle_deg }}°</td><td>{{ row.reflected_angle_deg }}°</td><td><button type="button" :disabled="busy" @click="deleteRecord(row.id)">删除</button></td></tr></tbody></table><label for="conclusion">观察结论</label><textarea id="conclusion" v-model="conclusion" rows="4"/><button type="button" :disabled="busy || !record" @click="saveConclusion">保存结论</button><label v-if="record"><input type="checkbox" :checked="Boolean(record.content.include_in_report)" :disabled="busy" @change="toggleReport"> 将记录加入报告</label></div>
    </div>
    <p role="status">{{ status }}</p><p v-if="error" role="alert">{{ error }}</p><button v-if="conflict" type="button" @click="reload">载入最新记录并保留输入</button>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { reflectionRays } from './reflectionModel';
import { jsonRequest, workspaceRequest, WorkspaceRequestError, type Artifact, type Workspace } from '../api';

const props = defineProps<{ workspaceId: string; experiment: Artifact; record?: Artifact }>();
const emit = defineEmits<{ back: []; updated: [record: Artifact]; refreshed: [workspace: Workspace] }>();
const angle = ref(30), busy = ref(false), status = ref(''), error = ref(''), conflict = ref(false);
const conclusion = ref(String(props.record?.content.conclusion || ''));
const pendingRecord = ref<{angle: number; key: string; expectedVersion: number | null} | null>(null);
const valid = computed(() => Number.isInteger(angle.value) && angle.value >= 0 && angle.value <= 80);
const rays = computed(() => reflectionRays(valid.value ? angle.value : 0));
const rows = computed(() => (props.record?.content.records || []) as Array<{id: string; incident_angle_deg: number; reflected_angle_deg: number}>);
async function saveRecord() {
  busy.value = true; error.value = ''; status.value = '正在保存…';
  if (!pendingRecord.value || pendingRecord.value.angle !== angle.value) pendingRecord.value = { angle: angle.value, key: crypto.randomUUID(), expectedVersion: props.record?.version ?? null };
  try {
    const record = await workspaceRequest<Artifact>(`/${props.workspaceId}/artifacts/${props.experiment.id}/records`, jsonRequest('POST', { angle: pendingRecord.value.angle, expected_version: pendingRecord.value.expectedVersion, idempotency_key: pendingRecord.value.key }));
    emit('updated', record); pendingRecord.value = null; status.value = `已保存 · 版本 ${record.version}`;
  } catch (e) { conflict.value = e instanceof WorkspaceRequestError && e.status === 409; error.value = conflict.value ? '记录已更新，请载入最新记录后重试。' : e instanceof Error ? e.message : '保存失败'; status.value = '未保存，请重试'; }
  finally { busy.value = false; }
}
async function saveConclusion() {
  if (!props.record) return;
  busy.value = true; error.value = ''; status.value = '正在保存…';
  try {
    const record = await workspaceRequest<Artifact>(`/${props.workspaceId}/artifacts/${props.record.id}`, jsonRequest('PATCH', { expected_version: props.record.version, conclusion: conclusion.value }));
    emit('updated', record); status.value = `已保存 · 版本 ${record.version}`;
  } catch (e) { conflict.value = e instanceof WorkspaceRequestError && e.status === 409; error.value = conflict.value ? '记录已更新，请载入最新记录后合并结论。' : e instanceof Error ? e.message : '保存失败'; status.value = '未保存，请重试'; }
  finally { busy.value = false; }
}
async function reload() { try { const workspace = await workspaceRequest<Workspace>(`/${props.workspaceId}`); emit('refreshed', workspace); pendingRecord.value = null; conflict.value = false; error.value = ''; status.value = '已载入最新记录，保留当前输入'; } catch (e) { error.value = e instanceof Error ? e.message : '载入失败'; } }
async function toggleReport(event: Event) {
  if (!props.record) return;
  busy.value = true; error.value = '';
  try { const record = await workspaceRequest<Artifact>(`/${props.workspaceId}/artifacts/${props.record.id}/report-selection`, jsonRequest('PUT', { expected_version: props.record.version, include: (event.target as HTMLInputElement).checked })); emit('updated', record); status.value = `已保存 · 版本 ${record.version}`; }
  catch (e) { (event.target as HTMLInputElement).checked = Boolean(props.record.content.include_in_report); error.value = e instanceof Error ? e.message : '保存失败'; }
  finally { busy.value = false; }
}
async function deleteRecord(id: string) {
  if (!props.record) return;
  busy.value = true; error.value = '';
  try { const record = await workspaceRequest<Artifact>(`/${props.workspaceId}/artifacts/${props.record.id}/records/${id}?expected_version=${props.record.version}`, { method: 'DELETE' }); emit('updated', record); status.value = `已保存 · 版本 ${record.version}`; }
  catch (e) { conflict.value = e instanceof WorkspaceRequestError && e.status === 409; error.value = conflict.value ? '记录已更新，请载入最新记录。' : e instanceof Error ? e.message : '删除失败'; }
  finally { busy.value = false; }
}
function unsaved() { return conclusion.value !== String(props.record?.content.conclusion || ''); }
defineExpose({ isDirty: unsaved });
function goBack() { if (!unsaved() || window.confirm('观察结论尚未保存，确定离开吗？')) emit('back'); }
function beforeUnload(event: BeforeUnloadEvent) { if (unsaved()) { event.preventDefault(); event.returnValue = ''; } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload));
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload));
</script>
