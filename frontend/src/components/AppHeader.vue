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
    <div v-else class="header-context header-context-empty">{{ currentRole === 'parent' ? '输入探究主题，开始设计家庭活动' : '创建一个课题，开始协同设计' }}</div>

    <div class="header-actions">
      <button v-if="inquiryWorkspaceAvailable" class="header-admin-button inquiry-workspace-trigger" type="button" :disabled="streaming || saving" @click="$emit('open-inquiry-workspace')">探究教学工作空间</button>
      <div v-if="workspaceRoles.length > 1" class="role-switcher">
        <button v-if="workspaceRoles.includes('teacher')"
          :class="{ active: currentRole === 'teacher' }"
          :disabled="streaming || saving"
          @click="switchRole('teacher')"
        >
          教师工作台
        </button>
        <button v-if="workspaceRoles.includes('study_travel')"
          :class="{ active: currentRole === 'study_travel' }"
          :disabled="streaming || saving"
          @click="switchRole('study_travel')"
        >
          研学基地工作台
        </button>
        <button v-if="workspaceRoles.includes('parent')"
          :class="{ active: currentRole === 'parent' }"
          :disabled="streaming || saving"
          @click="switchRole('parent')"
        >
          家长工作台
        </button>
      </div>
      <button v-if="workspaceRoles.includes(currentRole)" class="header-admin-button task-center-trigger" type="button" :disabled="streaming || saving" @click="$emit('open-task-center')">
        {{ currentRole === 'study_travel' ? '项目协同' : '任务大厅' }}
      </button>
      <button class="header-admin-button user-guide-trigger" type="button" @click="$emit('open-user-guide')"><BookOpen :size="15" /><span>使用手册</span></button>
      <ExpertSelector v-model="expertId" :experts="experts" :role-category="currentRole" :disabled="streaming || saving || !session" />
      <button v-if="user?.is_admin" class="header-admin-button" type="button" @click="$emit('open-graph-admin')">图谱管理</button>
      <span class="connection-status" :class="{ streaming }" :title="streaming ? '当前操作正在处理' : saving ? '正在保存当前阶段内容' : '工作台已就绪；发送、保存或推进阶段时会显示对应状态。'"><i></i>{{ streaming ? '正在处理' : saving ? '正在保存' : '工作台就绪' }}</span>
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
import { computed } from "vue";
import { BookOpen, ChevronDown, GraduationCap, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Sun } from "lucide-vue-next";
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
  saving: boolean;
  sidebarCollapsed: boolean;
  themeMode: 'light' | 'dark';
  currentRole: UserRole;
  workspaceRoles: UserRole[];
  inquiryWorkspaceAvailable: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string];
  'toggle-sidebar': [];
  'toggle-theme': [];
  'open-graph-admin': [];
  'open-task-center': [];
  'open-user-guide': [];
  'open-inquiry-workspace': [];
  logout: [];
  'switch-role': [role: UserRole];
}>();

function switchRole(role: UserRole) {
  if (!props.workspaceRoles.includes(role)) return;
  emit('switch-role', role);
}

const labels = computed(() => {
  if (props.currentRole === "study_travel") {
    return {
      brandTitle: "研学基地工作台",
      brandSubtitle: "Study Travel Studio",
    };
  }
  if (props.currentRole === "parent") {
    return { brandTitle: "家庭探究工作台", brandSubtitle: "Family Inquiry Studio" };
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

.task-center-trigger {
  white-space: nowrap;
}

.header-actions .inquiry-workspace-trigger {
  white-space: nowrap;
  color: var(--brand);
  background: var(--brand-soft);
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

@media (max-width: 680px) {
  .workspace-header { grid-template-columns: auto minmax(0, 1fr); }
  .header-actions { justify-content: flex-start; overflow-x: auto; }
  .header-actions > * { flex-shrink: 0; }
}
</style>
