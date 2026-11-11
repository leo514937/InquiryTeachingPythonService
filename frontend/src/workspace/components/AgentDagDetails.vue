
<template>
  <aside class="dag-details" aria-label="节点详情面板">
    <h3>节点详情</h3>
    <p v-if="!node" class="dag-muted">选择图中节点或下方节点列表，查看本次执行的实际记录。</p>
    <template v-else>
      <div class="dag-detail-title"><strong>{{ capabilityName(node.capability) }}</strong><span>{{ nodeStatusLabels[node.status] || node.status }}</span></div>
      <dl>
        <dt>能力</dt><dd>{{ node.capability }}</dd>
        <dt>节点 ID</dt><dd>{{ node.id }}</dd>
        <dt>依赖</dt><dd>{{ node.depends_on.length ? node.depends_on.join('、') : '无' }}</dd>
        <dt>执行次数</dt><dd>{{ node.attempts }}</dd>
        <dt>开始时间</dt><dd>{{ formatTime(node.started_at) }}</dd>
        <dt>结束时间</dt><dd>{{ formatTime(node.finished_at) }}</dd>
        <dt>执行用时</dt><dd>{{ duration }}</dd>
        <dt>输入摘要</dt><dd>{{ node.input_summary }}</dd>
        <dt>输出摘要</dt><dd>{{ node.output_summary }}</dd>
        <dt>对象变更</dt><dd>{{ changeLabel }}</dd>
        <template v-if="node.error_message"><dt>错误原因</dt><dd class="dag-error-text">{{ node.error_message }}</dd></template>
      </dl>
      <h4>来源依据</h4><ul v-if="node.source_refs?.length" class="dag-refs"><li v-for="source in node.source_refs" :key="source.expert_id + ':' + source.source">{{ source.source }} · {{ source.expert_id }}</li></ul><p v-else class="dag-muted">暂无可展示的来源依据。</p>
      <h4>结果引用</h4>
      <ul v-if="node.result_refs.length" class="dag-refs"><li v-for="ref in node.result_refs" :key="ref.id + ':' + ref.version"><span>{{ ref.operation === 'created' ? '新增' : ref.operation === 'updated' ? '更新' : '引用' }}</span> {{ ref.id }} · 版本 {{ ref.version }}</li></ul>
      <p v-else class="dag-muted">未记录可访问的对象引用。</p>
    </template>
  </aside>
</template>
<script setup lang="ts">
import { computed } from 'vue';
import type { DagNodeData } from '../api';
import { capabilityName, nodeStatusLabels } from '../dagLayout';
const props = defineProps<{node: DagNodeData | null}>();
const duration = computed(() => { if (!props.node?.started_at || !props.node.finished_at) return '未记录'; const ms = Date.parse(props.node.finished_at) - Date.parse(props.node.started_at); return Number.isFinite(ms) && ms >= 0 ? (ms / 1000).toFixed(1) + ' 秒' : '未记录'; });
const changeLabel = computed(() => ({created:'新增对象',updated:'更新对象',mixed:'新增及更新对象',none:'辅助节点'} as Record<string,string>)[props.node?.change_kind || ''] || '未记录');
function formatTime(value: string | null) { if (!value) return '未记录'; const d = new Date(value); return Number.isNaN(d.getTime()) ? value : d.toLocaleString(); }
</script>

