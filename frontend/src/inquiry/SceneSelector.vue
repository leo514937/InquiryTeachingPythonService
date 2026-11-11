<template>
  <div class="backdrop" @click.self="$emit('close')" @keydown.esc="$emit('close')">
    <section class="dialog" role="dialog" aria-modal="true" aria-labelledby="scene-title">
      <div class="heading"><h2 id="scene-title">选择课程场景</h2><button type="button" aria-label="关闭" @click="$emit('close')">×</button></div>
      <p>场景是可选的；来源仅显示当前可用的授权资料。</p>
      <label>搜索场景<input v-model="search" autofocus placeholder="输入场景名称"></label>
      <div v-if="filtered.length" class="scene-list">
        <label v-for="scene in filtered" :key="scene.id" class="scene-card">
          <input type="checkbox" :checked="selected.includes(scene.id)" :disabled="!selected.includes(scene.id) && selected.length >= 3" @change="$emit('toggle', scene.id)">
          <span><strong>{{ scene.name }}</strong><small>{{ scene.description }}</small></span>
        </label>
      </div><p v-else>没有匹配的场景。</p>
      <div v-if="selected.includes('custom')" class="sources"><strong>可用教学资料</strong><p v-if="!sources.length">暂无可用的授权资料。</p>
        <label v-for="source in sources" :key="source.id"><input type="checkbox" :checked="selectedSources.includes(source.id)" @change="$emit('toggle-source', source.id)"> {{ source.title }}</label>
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
const filtered = computed(() => props.scenes.filter(s => `${s.name} ${s.description}`.toLowerCase().includes(search.value.trim().toLowerCase())));
</script>
<style scoped>
.backdrop{position:fixed;inset:0;background:#183a3366;display:grid;place-items:center;padding:16px;z-index:100}.dialog{background:white;color:#183a33;border-radius:16px;padding:24px;width:min(620px,100%);max-height:85vh;overflow:auto}.heading{display:flex;justify-content:space-between;align-items:center}.heading h2{margin:0}.heading button{border:0;background:none;font-size:24px}.dialog p,small{color:#607b6e}.dialog input:not([type=checkbox]){display:block;width:100%;padding:9px;border:1px solid #d5e4dc;border-radius:8px;margin:6px 0 14px}.scene-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.scene-card{display:flex;gap:8px;border:1px solid #d5e4dc;border-radius:10px;padding:12px}.scene-card small{display:block}.sources label{display:block;margin:6px 0}.primary{background:#27816c;color:white;border:0;border-radius:9px;padding:9px 16px}@media(max-width:600px){.scene-list{grid-template-columns:1fr}}
</style>
