<template>
  <section class="execution-timeline" aria-label="运行事件">
    <h3>实时执行记录</h3>
    <p v-if="error" role="status">{{ error }}</p>
    <p v-else-if="!items.length" class="dag-muted">暂无可展示的运行事件。</p>
    <ol v-else><li v-for="item in items.slice(-30).reverse()" :key="item.sequence"><span class="timeline-mark">·</span><div><strong>{{ labels[item.kind] || '运行状态更新' }}</strong><small>序号 {{ item.sequence }}<template v-if="item.nodeId"> · {{ item.nodeId }}</template></small></div></li></ol>
  </section>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue';
import { workspaceEventsUrl } from '../api';
import { parseExecutionEvents, mergeExecutionEvents, type ExecutionEvent } from '../executionEvents';
const props = defineProps<{workspaceId:string; runId:string; cursor:number}>();
const items = ref<ExecutionEvent[]>([]), error = ref('');
const labels:Record<string,string> = {queued:'任务已接收',planning:'Planner 正在规划',running:'DAG 开始执行',node_started:'节点开始执行',node_attempt:'节点执行尝试',node_retry:'节点正在重试',node_succeeded:'节点执行完成',node_failed:'节点执行失败',node_skipped:'节点已跳过',node_cancelled:'节点已取消',node_result_discarded:'节点结果未采纳',completed:'运行完成',failed:'运行失败',cancelled:'运行已取消',cancel_requested:'已请求取消',waiting_review:'等待教师审核',review_approved:'审核已通过'};
watch(() => [props.workspaceId, props.runId, props.cursor] as const, async ([workspaceId, runId, cursor], _old, onCleanup) => {
  const controller = new AbortController(); onCleanup(() => controller.abort());
  items.value=[]; error.value='';
  if (!workspaceId || !runId || !cursor) return;
  try {
    let after=0, collected:ExecutionEvent[]=[];
    while(after < cursor) {
      const url=workspaceEventsUrl(workspaceId,runId,after).replace('follow=true','follow=false');
      const response=await fetch(url,{credentials:'include',signal:controller.signal});
      if (!response.ok) {
        if (response.status===403 || response.status===401) window.dispatchEvent(new CustomEvent('inquiry-workspace:access-denied',{detail:{path:`/${workspaceId}/runs/${runId}`}}));
        throw new Error('运行事件暂时不可用');
      }
      const batch=parseExecutionEvents(await response.text()).filter(event=>event.sequence<=cursor);
      if(!batch.length) break;
      collected=mergeExecutionEvents(collected,batch);
      const next=batch[batch.length-1].sequence;
      if(next<=after) break;
      after=next;
      if(batch.length<200) break;
    }
    if(!controller.signal.aborted) items.value=collected;
  } catch (e) { if(!controller.signal.aborted) {items.value=[];error.value=e instanceof Error ? e.message : '运行事件暂时不可用';} }
}, {immediate:true});
</script>
