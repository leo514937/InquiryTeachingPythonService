
<template>
  <div class="agent-node" :class="['state-' + node.status, {selected}]" :aria-label="capabilityName(node.capability) + '，' + statusLabel">
    <Handle type="target" :position="Position.Top" :connectable="false" />
    <Handle type="source" :position="Position.Bottom" :connectable="false" />
    <div class="agent-node-top"><span class="agent-node-symbol" aria-hidden="true">{{ symbol }}</span><span class="agent-node-state">{{ statusLabel }}</span></div>
    <strong>{{ capabilityName(node.capability) }}</strong>
    <small>{{ node.id }}</small>
    <span v-if="changeLabel" class="agent-node-change">{{ changeLabel }}</span>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue';
import { Handle, Position } from '@vue-flow/core';
import type { DagNodeData } from '../api';
import { capabilityName, nodeStatusLabels } from '../dagLayout';
const props = defineProps<{node: DagNodeData; selected?: boolean}>();
const statusLabel = computed(() => nodeStatusLabels[props.node.status] || props.node.status || '状态未记录');
const symbol = computed(() => ({queued:'○',running:'◌',succeeded:'✓',failed:'!',skipped:'–',cancelled:'×',result_discarded:'?',unknown:'?'} as Record<string,string>)[props.node.status] || '?');
const changeLabel = computed(() => ({created:'新增对象',updated:'更新对象',mixed:'新增及更新对象',none:'辅助节点'} as Record<string,string>)[props.node.change_kind || ''] || '');
</script>

