
<template>
  <section class="agent-dag-view" aria-labelledby="dag-heading">
    <header class="dag-header">
      <div><span class="eyebrow">AGENT ORCHESTRATION</span><h2 id="dag-heading">Agent 编排图</h2><p>查看本次运行的真实计划与执行记录。图仅供观察，教学内容仍在画布中编辑。</p></div>
      <div class="dag-toolbar">
        <RunHistory :runs="history" :selected="selectedRun" :has-more="!!nextCursor" :loading="historyLoading" @select="selectRun" @more="loadMore"/>
        <button type="button" :disabled="!graph?.nodes.length" @click="relayout">重新布局</button>
        <button type="button" :disabled="!graph?.nodes.length" @click="zoomOut()" aria-label="缩小画布">−</button><button type="button" :disabled="!graph?.nodes.length" @click="fit">适配画布</button><button type="button" :disabled="!graph?.nodes.length" @click="zoomIn()" aria-label="放大画布">＋</button>
      </div>
    </header>
    <div v-if="historyError" class="dag-notice" role="alert">{{ historyError }} <button type="button" @click="loadHistory">重试</button></div>
    <div v-if="error" class="dag-notice" role="alert">{{ error }} <button type="button" @click="refresh">重新检查</button></div>
    <div v-else-if="disconnected" class="dag-notice" role="status">实时连接中断，正在重新连接；显示最近一次验证的状态。</div>
    <div v-if="loading && !graph" class="dag-empty" role="status">正在读取运行图…</div>
    <div v-else-if="!selectedRun && !historyLoading" class="dag-empty">暂无可访问的运行。创建或生成教学空间后，可在这里查看编排图。</div>
    <template v-else-if="graph">
      <div class="dag-run-summary" role="status">
        <strong>{{ runStatusLabels[graph.status] || graph.status }}</strong>
        <span>{{ graph.mode === 'replan' ? '局部重编排' : graph.mode === 'experiment' ? '独立实验设计' : '教学设计' }}</span>
        <span>{{ graph.nodes.filter(node => node.status === 'succeeded').length }} / {{ graph.nodes.length }} 节点完成</span><span v-if="graph.status === 'waiting_review'">等待教师在协作面板确认；已完成节点仍保持原状态。</span>
        <span v-if="graph.incomplete">历史记录不完整，未记录的信息不会推断。</span>
        <span v-if="graph.error">{{ graph.error }}</span>
      </div>
      <div v-if="!graph.nodes.length" class="dag-empty">{{ graph.empty_reason || '暂无规划节点。' }}</div><AgentExecutionTimeline v-if="!graph.nodes.length" :workspace-id="workspaceId" :run-id="selectedRun" :cursor="graph.event_cursor"/>
      <template v-else>
        <div class="dag-work-area">
          <div class="dag-flow-wrap">
            <VueFlow :id="flowId" :nodes="flowNodes" :edges="flowEdges" :nodes-draggable="false" :nodes-connectable="false" :elements-selectable="true" :delete-key-code="null" :zoom-on-double-click="false" :min-zoom="0.03" :max-zoom="2.5" @node-click="onNodeClick" @nodes-initialized="fit">
              <template #node-agent="slotProps"><AgentDagNode :node="slotProps.data.node" :selected="slotProps.data.node.id === selectedNodeId"/></template>
            </VueFlow>
            <div class="dag-flow-hint">可拖动画布、滚轮缩放；选择节点查看详情</div>
          </div>
          <div class="dag-insights"><AgentDagDetails :node="selectedNode"/><AgentExecutionTimeline :workspace-id="workspaceId" :run-id="selectedRun" :cursor="graph.event_cursor"/></div>
        </div>
        <div class="dag-accessible-list"><h3>节点列表</h3><p>也可使用键盘选择节点，查看相同的执行详情。</p><div><button v-for="node in graph.nodes" :key="node.id" type="button" :aria-pressed="node.id===selectedNodeId" @click="selectedNodeId=node.id; emit('interaction')"><span>{{ capabilityName(node.capability) }}</span><small>{{ nodeStatusLabels[node.status] || node.status }}</small></button></div></div>
      </template>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, toRef, watch } from 'vue';
import { VueFlow, useVueFlow, type NodeMouseEvent } from '@vue-flow/core';
import '@vue-flow/core/dist/style.css';
import AgentDagNode from './AgentDagNode.vue';
import AgentDagDetails from './AgentDagDetails.vue';
import AgentExecutionTimeline from './AgentExecutionTimeline.vue';
import RunHistory from './RunHistory.vue';
import { useRunDag } from '../composables/useRunDag';
import { capabilityName, layoutDag, nodeStatusLabels, runStatusLabels } from '../dagLayout';
import { workspaceRequest, type DagRunSummary } from '../api';

const emit = defineEmits<{interaction: []}>();
const props = defineProps<{workspaceId: string; latestRunId: string; active: boolean}>();
const workspaceId = toRef(props, 'workspaceId'), active = toRef(props, 'active');
const selectedRun = ref(''), selectedNodeId = ref('');
const history = ref<DagRunSummary[]>([]), nextCursor = ref<string | null>(null);
const historyLoading = ref(false), historyError = ref('');
const positions = ref<Record<string, {x:number;y:number}>>({});
const flowId = 'workspace-agent-dag';
const { fitView, zoomIn, zoomOut } = useVueFlow(flowId);
const { graph, loading, disconnected, error, refresh } = useRunDag(workspaceId, selectedRun, active);
const selectedNode = computed(() => graph.value?.nodes.find(node => node.id === selectedNodeId.value) || null);
const flowNodes = computed(() => graph.value?.nodes.map((node, index) => ({id: node.id, style:{'--node-delay': `${Math.min(index, 12) * 45}ms`}, type:'agent', position: positions.value[node.id] || {x:0,y:0}, data:{node}, draggable:false, connectable:false})) || []);
const flowEdges = computed(() => (graph.value?.edges || []).map(edge => {
  const source = graph.value?.nodes.find(node => node.id === edge.source);
  const target = graph.value?.nodes.find(node => node.id === edge.target);
  return {...edge, class: target?.status === 'running' && source?.status === 'succeeded' ? 'edge-running' : source?.status === 'succeeded' && target?.status === 'succeeded' ? 'edge-completed' : ''};
}));
const topology = computed(() => graph.value ? JSON.stringify([graph.value.nodes.map(n=>n.id), graph.value.edges.map(e=>[e.source,e.target])]) : '');
async function fit() { await nextTick(); await fitView({padding:0.18, duration:250}); }
async function relayout() { if (!graph.value) return; positions.value = layoutDag(graph.value); await fit(); }
function onNodeClick(event: NodeMouseEvent) { emit('interaction'); selectedNodeId.value = event.node.id; }
function selectRun(id:string) { emit('interaction'); selectedNodeId.value=''; selectedRun.value=id; }
async function fetchHistory(cursor?:string) {
  if (!props.workspaceId || historyLoading.value) return;
  historyLoading.value=true; historyError.value='';
  const id=props.workspaceId;
  try {
    const data=await workspaceRequest<{items:DagRunSummary[]; next_cursor:string|null}>('/'+encodeURIComponent(id)+'/runs?limit=20'+(cursor?'&cursor='+encodeURIComponent(cursor):''));
    if (id!==props.workspaceId) return;
    history.value=cursor ? [...history.value,...data.items] : data.items;
    nextCursor.value=data.next_cursor;
    if (!history.value.some(item=>item.id===selectedRun.value)) selectedRun.value=history.value[0]?.id || '';
  } catch (e) { if (id===props.workspaceId) { history.value=[]; selectedRun.value=''; historyError.value=e instanceof Error?e.message:'无法加载运行历史'; } }
  finally { historyLoading.value=false; }
}
function loadHistory(){ void fetchHistory(); }
function loadMore(){ if(nextCursor.value) void fetchHistory(nextCursor.value); }
watch(topology, async value=>{ if(value && graph.value?.nodes.length) await relayout(); else positions.value={}; });
watch(() => [props.workspaceId, props.active] as const, ([,visible], old) => {
  if (old && props.workspaceId !== old[0]) { history.value=[]; selectedRun.value=''; selectedNodeId.value=''; }
  if (visible) loadHistory();
}, {immediate:true});
watch(() => props.latestRunId, (id, previous) => {
  if (id && id !== previous && props.active) { selectedRun.value=id; loadHistory(); }
});
</script>

