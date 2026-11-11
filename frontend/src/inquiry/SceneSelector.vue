<template>
  <div class="backdrop" @click.self="$emit('close')" @keydown.esc="$emit('close')">
    <section class="dialog" role="dialog" aria-modal="true" aria-labelledby="scene-title">
      <div class="heading"><h2 id="scene-title">选择课程场景</h2><button type="button" aria-label="关闭" @click="$emit('close')">×</button></div>
      <p>场景可用于补充教学情境；场景资料接入状态如下。未接入资料的场景仍可选择，并使用通用教学建议。</p>
      <label>搜索场景<input v-model="search" autofocus placeholder="输入场景名称"></label>
      <div v-if="filtered.length" class="scene-list">
        <label v-for="scene in filtered" :key="scene.id" class="scene-card">
          <input type="checkbox" :checked="selected.includes(scene.id)" :disabled="!selected.includes(scene.id) && selected.length >= 3" @change="$emit('toggle', scene.id)">
          <span><strong>{{ scene.name }}</strong><small>{{ scene.description }}</small><small class="source-status">{{ scene.id === 'custom' ? (sources.length ? '可选择已授权资料' : '暂无可用授权资料') : scene.has_configured_sources === false ? '场景资料未接入' : scene.has_configured_sources === true ? '资料来源已配置，使用时校验授权' : '场景资料状态未知' }}</small></span>
        </label>
      </div><p v-else>没有匹配的场景。</p>
      <div v-if="selected.includes('custom')" class="sources"><strong>可用教学资料</strong><p>仅列出当前授权的资料 · 已选择 {{ selectedSources.length }} 项</p><input v-model="sourceSearch" placeholder="搜索教学资料" aria-label="搜索教学资料"><p v-if="!filteredSources.length">{{ sources.length ? '没有匹配的资料。' : '暂无可用的授权资料。' }}</p>
        <label v-for="source in filteredSources" :key="source.id"><input type="checkbox" :checked="selectedSources.includes(source.id)" @change="$emit('toggle-source', source.id)"> {{ source.title }}</label>
      </div>
      <p>已选：{{ selected.map(id => scenes.find(s => s.id === id)?.name || '').join('、') || '无' }}</p>
      <button class="primary" type="button" @click="$emit('close')">完成</button>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue';
import type { Scene, Source } from './api';
const props = defineProps<{scenes: Scene[]; sources: Source[]; selected: string[]; selectedSources: string[]}>();
defineEmits<{close: []; toggle: [id: string]; 'toggle-source': [id: string]}>();
const search = ref('');
const sourceSearch = ref('');
const filtered = computed(() => props.scenes.filter(s => `${s.name} ${s.description}`.toLowerCase().includes(search.value.trim().toLowerCase())));
const filteredSources = computed(() => props.sources.filter(s => s.title.toLowerCase().includes(sourceSearch.value.trim().toLowerCase())));
</script>
<style scoped>
.scene-card .source-status{display:inline-flex;margin-top:7px;padding:2px 7px;border-radius:6px;background:#eef2ef;color:#596e61;font-size:11px;line-height:1.5}
.backdrop{position:fixed;inset:0;background:#18312688;display:grid;place-items:center;padding:16px;z-index:100}.dialog{background:white;color:var(--studio-ink);border:1px solid var(--studio-line);box-shadow:0 20px 60px #18312630;border-radius:18px;padding:24px;width:min(680px,100%);max-height:85vh;overflow:auto}.heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.heading h2{margin:0;font-size:20px}.heading button{border:0;background:none;font-size:24px;cursor:pointer}.dialog p,small{color:var(--studio-muted)}.dialog input:not([type=checkbox]){display:block;width:100%;padding:10px;border:1px solid var(--studio-line);border-radius:10px;margin:6px 0 14px;background:#fbfcfb;font:inherit}.scene-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.scene-card{display:flex;gap:10px;border:1px solid #e4ece6;border-radius:12px;padding:13px;background:#fbfcfb}.scene-card:has(input:checked){border-color:#8fc9a6;background:var(--studio-soft)}.scene-card small{display:block}.sources{margin-top:18px;padding:14px;border-radius:12px;background:#f1f6f2}.sources label{display:block;margin:8px 0}.primary{background:var(--studio-green);color:white;border:0;border-radius:10px;padding:10px 16px;cursor:pointer;font:inherit;font-weight:700}.primary:hover{background:var(--studio-green-dark)}button:focus-visible,input:focus-visible{outline:3px solid #8fc9a6;outline-offset:2px}@media(max-width:600px){.scene-list{grid-template-columns:1fr}}
</style>
