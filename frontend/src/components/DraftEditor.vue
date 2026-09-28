<template>
  <section class="draft-editor-shell">
    <div class="draft-editor-head"><strong>{{ labels.editorTitle }}</strong><span>可直接编辑，选中文字后可添加到对话</span></div>
    <div v-if="selectionLabel" class="draft-selection-bar"><span>{{ selectionLabel }}</span><div><button v-if="attachedLabel !== selectionLabel" type="button" @click="$emit('add-selection')">添加到对话</button><button type="button" @click="$emit('clear-selection')">取消</button></div></div>
    <div class="draft-editor-pane">
      <div class="draft-line-gutter" aria-hidden="true"><div class="draft-line-gutter-inner" :style="{ transform: `translateY(-${scrollTop}px)` }"><span v-for="line in visualLines" :key="line.key" class="draft-line-number" :class="{ active: line.logicalLine === cursorLine, continuation: line.continuation }" :style="{ height: `${lineHeight}px`, lineHeight: `${lineHeight}px` }">{{ line.label }}</span></div></div>
      <textarea ref="editor" v-model="content" class="draft-editor-textarea" spellcheck="false" placeholder="这里可以直接编辑 Markdown 草稿" @input="$emit('input')" @scroll="$emit('scroll')" @select="$emit('capture-selection')" @keyup="$emit('capture-selection')" @mouseup="$emit('capture-selection')"></textarea>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

type VisualLine = { key: string; label: string; logicalLine: number; continuation: boolean };
const props = defineProps<{
  modelValue: string;
  visualLines: VisualLine[];
  scrollTop: number;
  lineHeight: number;
  cursorLine: number;
  selectionLabel: string;
  attachedLabel: string;
  role_category?: "teacher" | "study_travel";
}>();
const emit = defineEmits<{
  'update:modelValue': [value: string]; 'editor-ready': [element: HTMLTextAreaElement]; input: []; scroll: []; 'capture-selection': []; 'add-selection': []; 'clear-selection': [];
}>();

const labels = computed(() => ({
  editorTitle: "Markdown 草案制定",
}));

const editor = ref<HTMLTextAreaElement | null>(null);
const content = computed({ get: () => props.modelValue, set: (value: string) => emit('update:modelValue', value) });
onMounted(() => { if (editor.value) emit('editor-ready', editor.value); });
</script>
