<template>
  <header class="workspace-header">
    <div class="header-brand">
      <button class="header-icon-button" type="button" :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'" @click="$emit('toggle-sidebar')">
        <PanelLeftOpen v-if="sidebarCollapsed" :size="19" />
        <PanelLeftClose v-else :size="19" />
      </button>
      <div class="brand-mark"><GraduationCap :size="19" /></div>
      <div class="brand-copy">
        <strong>{{ labels.brandTitle }}</strong>
        <span>{{ labels.brandSubtitle }}</span>
      </div>
    </div>

    <div class="header-context" v-if="session">
      <strong>{{ session.topic }}</strong>
      <span>{{ session.flow_display_name }} · {{ stageProgress }} · {{ stage?.name || '准备开始' }}</span>
    </div>
    <div v-else class="header-context header-context-empty">创建一个课题，开始协同设计</div>

    <div class="header-actions">
      <div class="role-switcher">
        <button
          :class="{ active: currentRole === 'teacher' }"
          @click="switchRole('teacher')"
        >
          教师工作台
        </button>
        <button
          :class="{ active: currentRole === 'study_travel' }"
          @click="switchRole('study_travel')"
        >
          研学基地工作台
        </button>
      </div>
      <ExpertSelector v-model="expertId" :experts="experts" :role-category="currentRole" :disabled="streaming || !session" />
      <button v-if="user?.is_admin" class="header-admin-button" type="button" @click="$emit('open-graph-admin')">图谱管理</button>
      <span class="connection-status" :class="{ streaming }"><i></i>{{ streaming ? '正在生成' : '已连接' }}</span>
      <button class="header-icon-button" type="button" :title="themeMode === 'light' ? '切换深色模式' : '切换浅色模式'" @click="$emit('toggle-theme')">
        <Moon v-if="themeMode === 'light'" :size="17" />
        <Sun v-else :size="17" />
      </button>
      <details class="user-menu">
        <summary>{{ user?.username }}<ChevronDown :size="14" /></summary>
        <button type="button" @click="$emit('logout')"><LogOut :size="15" />退出登录</button>
      </details>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ChevronDown, GraduationCap, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Sun } from "lucide-vue-next";
import ExpertSelector from "@/components/ExpertSelector.vue";
import type { AuthUser, ExpertAgentItem, FlowStage, SessionDetail, UserRole } from "@/types";

const props = defineProps<{
  modelValue: string;
  experts: ExpertAgentItem[];
  user: AuthUser | null;
  session: SessionDetail | null;
  stage: FlowStage | null;
  stageProgress: string;
  streaming: boolean;
  sidebarCollapsed: boolean;
  themeMode: 'light' | 'dark';
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string];
  'toggle-sidebar': [];
  'toggle-theme': [];
  'open-graph-admin': [];
  logout: [];
  'switch-role': [role: UserRole];
}>();

const currentRole = ref<UserRole>(
  (localStorage.getItem('user_role') as UserRole) || 'teacher'
);

function switchRole(role: UserRole) {
  currentRole.value = role;
  localStorage.setItem('user_role', role);
  emit('switch-role', role);
}

const labels = computed(() => {
  if (currentRole.value === "study_travel") {
    return {
      brandTitle: "研学基地工作台",
      brandSubtitle: "Study Travel Studio",
    };
  }
  return {
    brandTitle: "探究式教学工作台",
    brandSubtitle: "Inquiry Teaching Studio",
  };
});

const expertId = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
});
</script>

<style scoped>
.role-switcher {
  display: flex;
  gap: 4px;
  padding: 2px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--surface-subtle);
}

.role-switcher button {
  padding: 5px 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.role-switcher button.active {
  background: var(--surface);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}
</style>
