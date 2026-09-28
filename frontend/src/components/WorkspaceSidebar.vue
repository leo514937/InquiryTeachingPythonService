<template>
  <aside class="workspace-sidebar" :class="{ collapsed }">
    <div class="sidebar-actions">
      <button class="sidebar-action primary" type="button" title="新建会话" @click="$emit('new-session')"><Plus :size="18" /><span>{{ labels.newSession }}</span></button>
      <label class="sidebar-search" title="搜索会话">
        <Search :size="17" />
        <input v-model="searchText" type="search" :placeholder="labels.searchPlaceholder" />
      </label>
    </div>

    <template v-if="!collapsed">
      <section class="sidebar-session-section">
        <div class="sidebar-section-head"><span>{{ labels.mySessions }}</span><button type="button" title="删除当前会话" :disabled="!session" @click="$emit('delete-session')"><Trash2 :size="15" /></button></div>
        <select :value="selectedSessionId" :disabled="uploading || !sessions.length" @change="$emit('select-session', ($event.target as HTMLSelectElement).value)">
          <option v-if="!sessions.length" value="">暂无会话</option>
          <option v-for="item in filteredSessions" :key="item.id" :value="item.id">{{ item.topic }} · {{ item.flow_display_name }}</option>
        </select>
        <p v-if="sessions.length && !filteredSessions.length" class="sidebar-empty">{{ labels.noMatch }}</p>
      </section>
      <div class="sidebar-section-head stage-section-head"><span>{{ labels.flowLabel }}</span><small v-if="session">{{ progress }}</small></div>
    </template>

    <StageTimeline
      v-if="session"
      :stages="stages"
      :selected-stage-id="selectedStageId"
      :current-stage-id="currentStageId"
      :output="output"
      @select-stage="$emit('select-stage', $event)"
    />
    <div v-else class="sidebar-blank"><BookOpen :size="20" /><span>{{ labels.selectOrCreate }}</span></div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { BookOpen, Plus, Search, Trash2 } from "lucide-vue-next";
import StageTimeline from "@/components/StageTimeline.vue";
import type { FlowStage, SessionDetail, SessionListItem, StageOutput } from "@/types";

const props = defineProps<{
  collapsed: boolean;
  session: SessionDetail | null;
  sessions: SessionListItem[];
  selectedSessionId: string;
  stages: FlowStage[];
  selectedStageId: string;
  currentStageId: string;
  progress: string;
  uploading: boolean;
  search: string;
  role_category?: "teacher" | "study_travel";
  output: (stageId: string) => StageOutput | undefined;
}>();

const emit = defineEmits<{
  'update:search': [value: string];
  'new-session': [];
  'delete-session': [];
  'select-session': [id: string];
  'select-stage': [id: string];
}>();

const labels = computed(() => ({
  newSession: "新建草案",
  searchPlaceholder: "搜索草案",
  mySessions: "我的草案",
  flowLabel: "流程",
  noMatch: "没有匹配的草案",
  selectOrCreate: "选择或新建草案",
}));

const searchText = computed({ get: () => props.search, set: (value: string) => emit('update:search', value) });
const filteredSessions = computed(() => {
  const query = props.search.trim().toLowerCase();
  if (!query) return props.sessions;
  return props.sessions.filter((item) => `${item.topic} ${item.flow_display_name}`.toLowerCase().includes(query));
});
</script>
