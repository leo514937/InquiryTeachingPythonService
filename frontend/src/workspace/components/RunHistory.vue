
<template>
  <div class="dag-history">
    <label for="dag-run-select">历史运行</label>
    <select id="dag-run-select" :value="selected" :disabled="loading || !runs.length" @change="emit('select', ($event.target as HTMLSelectElement).value)">
      <option v-if="!runs.length" value="">暂无可访问运行</option>
      <option v-for="run in runs" :key="run.id" :value="run.id">{{ run.mode === 'replan' ? '局部重编排' : run.mode === 'experiment' ? '独立实验' : '教学设计' }} · {{ runStatusLabels[run.status] || run.status }} · {{ showTime(run.created_at) }}</option>
    </select>
    <button v-if="hasMore" type="button" :disabled="loading" @click="emit('more')">加载更多</button>
  </div>
</template>
<script setup lang="ts">
import type { DagRunSummary } from '../api';
import { runStatusLabels } from '../dagLayout';
defineProps<{runs: DagRunSummary[]; selected: string; hasMore: boolean; loading: boolean}>();
const emit = defineEmits<{select:[id:string]; more:[]}>();
function showTime(value: string) { const d = new Date(value); return Number.isNaN(d.getTime()) ? value : d.toLocaleString(); }
</script>

