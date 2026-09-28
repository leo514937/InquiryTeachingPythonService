<template>
  <div ref="rootRef" class="expert-selector">
    <button
      class="expert-selector-trigger"
      type="button"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :disabled="disabled"
      @click="toggle"
    >
      <Bot :size="16" />
      <span class="expert-selector-label">本轮咨询：</span>
      <strong>{{ selectedExpert?.name || defaultMainTutor.label }}</strong>
      <ChevronDown :size="15" :class="{ rotated: open }" />
    </button>

    <div v-if="open" class="expert-selector-popover" role="listbox" aria-label="选择本轮咨询专家">
      <button
        class="expert-option"
        :class="{ selected: !modelValue }"
        type="button"
        role="option"
        :aria-selected="!modelValue"
        @click="selectExpert('')"
      >
        <GraduationCap :size="18" />
        <span><strong>{{ defaultMainTutor.label }}</strong><small>{{ defaultMainTutor.description }}</small></span>
        <Check v-if="!modelValue" :size="16" />
      </button>
      <button
        v-for="expert in experts"
        :key="expert.id"
        class="expert-option"
        :class="{ selected: expert.id === modelValue }"
        type="button"
        role="option"
        :aria-selected="expert.id === modelValue"
        @click="selectExpert(expert.id)"
      >
        <Bot :size="18" />
        <span><strong>{{ expert.name }}</strong><small>{{ expert.role }} · {{ expert.description }}</small></span>
        <Check v-if="expert.id === modelValue" :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { Bot, Check, ChevronDown, GraduationCap } from "lucide-vue-next";
import type { ExpertAgentItem } from "@/types";

const props = defineProps<{
  modelValue: string;
  experts: ExpertAgentItem[];
  disabled?: boolean;
  role_category?: "teacher" | "study_travel";
}>();

const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const open = ref(false);
const rootRef = ref<HTMLElement | null>(null);
const selectedExpert = computed(() => props.experts.find((expert) => expert.id === props.modelValue) || null);
const defaultMainTutor = computed(() => {
  if (props.role_category === "study_travel") {
    return {
      label: "研学主导师",
      description: "阶段引导、方案生成与研学基地流程推进",
    };
  }
  return {
    label: "主导师",
    description: "阶段引导、草案生成与教学方案推进",
  };
});

function toggle() {
  open.value = !open.value;
}

function selectExpert(id: string) {
  emit("update:modelValue", id);
  open.value = false;
}

function closeOnOutsideClick(event: MouseEvent) {
  if (!rootRef.value?.contains(event.target as Node)) open.value = false;
}

document.addEventListener("click", closeOnOutsideClick);
onBeforeUnmount(() => document.removeEventListener("click", closeOnOutsideClick));
</script>
