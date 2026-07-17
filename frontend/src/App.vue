<template>
  <div
    class="app-shell"
    :class="{
      'left-sidebar-collapsed': !leftSidebarVisible,
      'right-sidebar-collapsed': !rightSidebarVisible,
    }"
  >
    <!-- LEFT COLUMN: Document Explorer -->
    <aside class="explorer-column">
      <section class="brand-card glass">
        <div class="brand-main">
          <div>
            <p class="eyebrow">AI 教师探究式教学指导平台</p>
            <h1>探究式教案工作台</h1>
          </div>
          <div class="brand-actions">
            <button class="ghost-button compact theme-toggle-btn" @click="toggleTheme">
              {{ themeMode === "dark" ? "浅色模式" : "深色模式" }}
            </button>
            <div class="status-pill" :class="{ live: isStreaming }">
              <span class="status-dot"></span>
              {{ isStreaming ? "SSE 流式中" : "已连接" }}
            </div>
          </div>
        </div>
      </section>

      <section class="glass panel explorer-panel">
        <div class="panel-head">
          <h2>教案文档列表</h2>
          <div class="panel-actions">
            <button class="icon-button compact danger" @click="handleDeleteSession" :disabled="!currentSession" title="删除当前会话">🗑 删除</button>
            <button class="icon-button compact" @click="showNewSessionModal = true" title="新建会话">＋ 新建</button>
          </div>
        </div>

        <div class="session-selector-panel">
          <div class="selector-row">
            <label>当前会话</label>
            <select :value="selectedSessionId" @change="e => selectSession((e.target as HTMLSelectElement).value)" class="input compact">
              <option v-for="item in sessions" :key="item.id" :value="item.id">
                {{ item.topic }}
              </option>
            </select>
          </div>
          <div class="selector-row" v-if="currentSession">
            <label>教学流程</label>
            <select :value="selectedFlowName" @change="e => switchFlow((e.target as HTMLSelectElement).value)" class="input compact">
              <option v-for="flow in flows" :key="flow.name" :value="flow.name">
                {{ flow.display_name }}
              </option>
            </select>
          </div>
        </div>

        <div v-if="currentSession && currentStage" class="stage-summary-card">
          <div class="stage-summary-head">
            <strong>当前阶段</strong>
            <span>{{ currentSession.status === 'completed' ? '已完成' : `第 ${currentStageIndex + 1}/${activeStages.length} 阶段` }}</span>
          </div>
          <div class="stage-summary-title">{{ currentStage.name }}</div>
          <div class="stage-summary-meta">
            <span>负责专家：{{ currentStage.expert }}</span>
            <span>流程：{{ currentSession.flow_display_name }}</span>
          </div>
        </div>

        <div class="doc-list" v-if="currentSession">
          <div
            v-for="stage in activeStages"
            :key="stage.id"
            class="doc-item"
            :class="{
              active: stage.id === selectedStageId,
              current: stage.id === currentStageId
            }"
            @click="inspectStage(stage.id)"
          >
            <div class="doc-header">
              <span class="doc-title">{{ stage.name }}</span>
              <span
                class="doc-badge"
                :class="{
                  confirmed: activeStageOutput(stage.id)?.confirmed,
                  active: stage.id === currentStageId && currentSession.status !== 'completed',
                  pending: stage.id !== currentStageId && !activeStageOutput(stage.id)?.confirmed
                }"
              >
                {{ activeStageOutput(stage.id)?.confirmed ? '已定稿' : (stage.id === currentStageId && currentSession.status !== 'completed' ? '进行中' : '未开始') }}
              </span>
            </div>
            <div class="doc-meta">
              智能体: {{ stage.expert }}
            </div>
            <div
              class="doc-preview markdown-preview"
              v-html="renderMarkdown(activeStageOutput(stage.id)?.draft_content || activeStageOutput(stage.id)?.final_content || '暂无内容，等待对话生成...')"
            ></div>
          </div>
        </div>
        <div v-else class="empty-state">
          请先创建或选择一个会话。
        </div>
      </section>
    </aside>

    <!-- CENTER COLUMN: Main Conversation -->
    <section class="chat-column">
      <section class="glass progress-panel" v-if="currentSession">
        <div class="progress-container">
          <div class="progress-header">
            <span class="progress-title">探究进度 ({{ currentSession.flow_display_name }})</span>
            <div class="progress-header-actions">
              <span class="progress-percentage">
                {{ currentSession.status === 'completed' ? '已完成' : `第 ${currentStageIndex + 1}/${activeStages.length} 阶段` }}
              </span>
              <div class="sidebar-toggle-group" aria-label="边栏显示控制">
                <button
                  class="sidebar-toggle-button"
                  :class="{ active: leftSidebarVisible }"
                  type="button"
                  :title="leftSidebarVisible ? '收起左侧边栏' : '展开左侧边栏'"
                  @click="toggleLeftSidebar"
                >
                  <span class="sidebar-toggle-icon left" aria-hidden="true"></span>
                </button>
                <button
                  class="sidebar-toggle-button"
                  :class="{ active: rightSidebarVisible }"
                  type="button"
                  :title="rightSidebarVisible ? '收起右侧边栏' : '展开右侧边栏'"
                  @click="toggleRightSidebar"
                >
                  <span class="sidebar-toggle-icon right" aria-hidden="true"></span>
                </button>
              </div>
            </div>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: progressPercentage + '%' }"></div>
            <div class="progress-steps">
              <div
                v-for="(stage, idx) in activeStages"
                :key="stage.id"
                class="progress-step-dot"
                :class="{
                  completed: idx < currentStageIndex || currentSession.status === 'completed',
                  active: idx === currentStageIndex && currentSession.status !== 'completed',
                  pending: idx > currentStageIndex && currentSession.status !== 'completed'
                }"
                :style="{ left: activeStages.length > 1 ? (idx / (activeStages.length - 1)) * 100 + '%' : '50%' }"
              >
                <span class="step-num">{{ idx + 1 }}</span>
                <span class="step-tooltip">{{ stage.name }} ({{ stage.expert }})</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="glass conversation-panel">
        <div class="panel-head">
          <h2>主对话</h2>
          <div class="toolbar">
            <button
              class="stage-agent-pill mode-toggle"
              :class="{ active: chatMode === 'subagent' }"
              v-if="currentStage"
              @click="toggleChatMode"
              :disabled="isStreaming"
              :title="chatMode === 'subagent' ? '当前为Agent模式，点击切回主流程' : '当前为主流程模式，点击切到Agent'"
            >
              {{ chatMode === 'subagent' ? 'Agent对话' : '主流程对话' }}
            </button>
            <button class="ghost-button compact" @click="rollbackRecent" :disabled="!currentSession" title="撤销最近一轮对话">
              ↺ 回滚
            </button>
          </div>
        </div>

        <div v-if="streamWarning" class="stream-warning">
          {{ streamWarning }}
        </div>

        <div class="message-feed" ref="feedRef">
          <article
            v-for="message in messages"
            :key="message.id || message.created_at || `${message.message_type}-${message.content}`"
            class="message-card"
            :class="[message.role, message.message_type || 'chat']"
          >
            <div class="message-meta">
              <div class="message-meta-main">
                <span>{{ messageRoleLabel(message) }}</span>
                <small>{{ stageNameMap[message.stage_id] || message.stage_id }}</small>
                <small v-if="message.agent_id">{{ message.agent_id }}</small>
              </div>
              <div v-if="showWorkflowBadgeForMessage(message)" class="message-meta-status">
                <span v-if="workflowPhase === 'guide'" class="workflow-status-badge guide active">流程引导中</span>
                <span v-if="workflowPhase === 'draft'" class="workflow-status-badge draft active">草案生成中</span>
                <span v-if="workflowPhase === 'expert'" class="workflow-status-badge expert active">专家点评中</span>
              </div>
            </div>
            <div class="message-content markdown-content" v-html="renderMarkdown(message.content)"></div>
          </article>

          <div v-if="!messages.length" class="empty-state">
            在左侧选择会话并开始对话，系统将引导您完成教学设计。
          </div>
        </div>

        <div class="composer">
          <div class="composer-box">
            <div v-if="attachedChatSelectionLabel" class="composer-attachments">
              <button class="composer-attachment-pill" type="button" @click="clearAttachedChatSelection()">
                <span>{{ attachedChatSelectionLabel }}</span>
                <strong>×</strong>
              </button>
            </div>
            <textarea
              ref="chatInputRef"
              v-model="chatInput"
              class="chat-input"
              rows="3"
              placeholder="输入课堂切入点、问题追问、实验思路或阶段补充内容；可先从右侧添加 @行号引用。Enter 发送，Shift+Enter 换行"
              @keydown="handleComposerKeydown"
            />
            <div class="composer-actions">
              <button
                class="primary-button send-btn"
                :disabled="isStreaming || (isDraftMode && !!draftContent.trim() && !attachedChatSelection?.selected_text?.trim())"
                @click="sendChat"
              >
                {{ isDraftMode ? draftPrimaryActionLabel : "发送对话" }}
              </button>
              <button class="ghost-button compact draft-mode-btn" :class="{ active: isDraftMode }" :disabled="isStreaming || !currentSession" @click="toggleDraftMode">
                {{ isDraftMode ? "退出草案模式" : "进入草案模式" }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </section>

    <!-- RIGHT COLUMN: Document Display & Editor -->
    <section class="glass panel document-column" :class="{ 'document-column-drafting': workflowPhase === 'draft' }">
      <div class="document-header">
        <div class="document-title-area">
          <h2>教案文档展示</h2>
          <p v-if="currentSession">课题: {{ currentSession.topic }} · {{ currentSession.flow_display_name }}</p>
        </div>
        <div class="document-actions" v-if="currentSession">
          <button class="ghost-button compact" @click="goPreviousStage" :disabled="currentStageIndex === 0 || isStreaming">
            ◀ 上一阶段
          </button>
          <button class="primary-button compact" @click="goNextStage" :disabled="isStreaming || currentSession.status === 'completed' || selectedStageId !== currentStageId">
            定稿并进入下一阶段 ▶
          </button>
          <button class="ghost-button compact" @click="saveDraftToServer" :disabled="!selectedStageId">
            保存
          </button>
          <button class="ghost-button compact" @click="exportCurrentPlan">
            ⤓ 导出
          </button>
        </div>
      </div>

      <div class="document-body" v-if="currentSession && selectedStageId">
        <div
          class="draft-workbench draft-workbench-unified glass"
          :class="{ active: isDraftMode }"
        >
          <div class="draft-workbench-head">
            <div>
              <strong>草案工作台</strong>
              <p>右侧专注于 Markdown 原稿编辑；解析后的预览与差异审批统一放在全屏审阅幕布中完成。</p>
            </div>
            <div class="draft-head-actions">
              <button class="ghost-button compact" @click="openDraftReviewOverlay">
                进入预览
              </button>
              <div v-if="isDraftMode" class="draft-tip-anchor" tabindex="0" aria-label="草案模式说明">
                <span class="draft-tip-icon">i</span>
                <div class="draft-tip-popover">
                  {{ draftWorkbenchEmptyText }}
                </div>
              </div>
              <span v-if="draftProposal" class="draft-proposal-status" :class="draftProposal.status">
                {{ proposalStatusLabel(draftProposal.status) }}
              </span>
            </div>
          </div>

          <div class="draft-editor-shell">
            <div class="draft-editor-head">
              <strong>Markdown 草案</strong>
              <span>可直接编辑，也可选中后在对话框发起修改</span>
            </div>
            <div
              v-if="lastDraftSelection && currentSelectionReferenceLabel"
              class="draft-selection-action"
            >
              <span>{{ currentSelectionReferenceLabel }}</span>
              <div class="draft-selection-action-buttons">
                <button
                  v-if="attachedChatSelectionLabel !== currentSelectionReferenceLabel"
                  class="ghost-button compact"
                  @click="addSelectionToChat"
                >
                  添加到对话
                </button>
                <button class="ghost-button compact" @click="clearDraftSelection">
                  取消选取
                </button>
              </div>
            </div>
            <div class="draft-editor-pane">
              <div class="draft-line-gutter" aria-hidden="true">
                <div
                  class="draft-line-gutter-inner"
                  :style="{ transform: `translateY(-${draftEditorScrollTop}px)` }"
                >
                  <span
                    v-for="line in draftVisualLines"
                    :key="line.key"
                    class="draft-line-number"
                    :class="{ active: line.logicalLine === currentDraftCursorLine, continuation: line.continuation }"
                    :style="{ height: `${draftEditorLineHeight}px`, lineHeight: `${draftEditorLineHeight}px` }"
                  >
                    {{ line.label }}
                  </span>
                </div>
              </div>
              <textarea
                ref="draftEditorRef"
                v-model="draftContent"
                class="document-textarea draft-editor-textarea"
                spellcheck="false"
                placeholder="这里可以直接编辑 Markdown 草稿"
                @input="onDraftEditorInput"
                @scroll="syncDraftEditorScroll"
                @select="captureDraftSelection"
                @keyup="captureDraftSelection"
                @mouseup="captureDraftSelection"
              ></textarea>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        请从左侧列表选择一个阶段文档进行查看或编辑。
      </div>
    </section>

    <div
      v-if="showDraftReviewOverlay"
      class="draft-review-overlay"
    >
      <div class="draft-review-canvas glass">
        <div class="draft-review-overlay-head">
          <div>
            <strong>{{ draftProposal ? "草案差异审阅" : "Markdown 预览" }}</strong>
            <p>
              {{
                draftProposal
                  ? draftProposalDescription
                  : "这里展示当前草案解析后的 Markdown 效果；即使当前没有待审阅修改，也可以随时打开查看。"
              }}
            </p>
          </div>
          <div class="draft-review-overlay-actions">
            <span v-if="draftProposal" class="draft-proposal-status" :class="draftProposal.status">
              {{ proposalStatusLabel(draftProposal.status) }}
            </span>
            <button
              v-if="draftProposal"
              class="ghost-button compact"
              @click="applyAllDraftProposalActions('accept')"
              :disabled="!visibleDraftSegments.some(segment => segment.status === 'pending')"
            >
              全部接受
            </button>
            <button
              v-if="draftProposal"
              class="ghost-button compact"
              @click="applyAllDraftProposalActions('reject')"
              :disabled="!visibleDraftSegments.some(segment => segment.status === 'pending')"
            >
              全部拒绝
            </button>
            <button class="ghost-button compact" @click="closeDraftReviewOverlay">
              关闭
            </button>
          </div>
        </div>

        <div class="draft-review-overlay-body">
          <section class="draft-review-document-pane">
            <div class="draft-review-document-head">
              <div>
                <strong>正文预览</strong>
                <p>
                  {{
                    activeReviewSegment
                      ? `${draftSegmentLabel(activeReviewSegment)} · ${segmentStatusLabel(activeReviewSegment.status)}`
                      : draftProposal
                        ? "左侧会定位当前审阅项对应的正文位置。"
                        : "这里展示当前草案解析后的 Markdown 预览。"
                  }}
                </p>
              </div>
            </div>
            <div ref="reviewPreviewRef" class="draft-review-document-body">
              <article
                v-for="block in reviewPreviewBlocks"
                :key="block.id"
                class="draft-review-document-block"
                :class="{ active: block.id === activePreviewBlockId }"
                :data-block-id="block.id"
              >
                <div class="markdown-preview" v-html="renderMarkdown(block.raw)"></div>
              </article>
            </div>
          </section>

          <aside class="draft-review-sidebar">
            <div v-if="draftProposal?.target_summary" class="draft-target-summary draft-overlay-target-summary">
              <strong>本次修改目标</strong>
              <p>{{ draftProposal.target_summary }}</p>
            </div>

            <div v-if="draftProposal" class="draft-review-list">
              <article
                v-for="segment in visibleDraftSegments"
                :key="segment.id"
                class="draft-review-list-item"
                :class="[
                  segment.kind,
                  segment.status,
                  {
                    active: activeReviewSegmentId === segment.id,
                    highlighted: draftProposal.highlight_segment_ids?.includes(segment.id),
                  },
                ]"
              >
                <button class="draft-review-list-main" @click="selectReviewSegment(segment.id)">
                  <div class="draft-review-list-meta">
                    <span class="draft-review-list-kind">{{ draftSegmentLabel(segment) }}</span>
                    <span class="draft-review-list-status">{{ segmentStatusLabel(segment.status) }}</span>
                  </div>
                  <p>{{ reviewSegmentSummary(segment) }}</p>
                </button>
                <div class="draft-review-list-actions">
                  <button
                    class="ghost-button compact"
                    @click="applyDraftProposalAction(segment.id, 'accept')"
                    :disabled="segment.status !== 'pending'"
                  >
                    接受
                  </button>
                  <button
                    class="ghost-button compact"
                    @click="applyDraftProposalAction(segment.id, 'reject')"
                    :disabled="segment.status !== 'pending'"
                  >
                    拒绝
                  </button>
                </div>
                <div class="draft-review-list-detail">
                  <div class="draft-diff-column old">
                    <span class="draft-diff-column-label">原内容</span>
                    <div class="markdown-preview draft-diff-body" v-html="renderMarkdown(segment.base_text || '（无原内容）')"></div>
                  </div>
                  <div class="draft-diff-column new">
                    <span class="draft-diff-column-label">候选内容</span>
                    <div class="markdown-preview draft-diff-body" v-html="renderMarkdown(segment.candidate_text || '（无新增内容）')"></div>
                  </div>
                </div>
              </article>
            </div>

            <div v-else class="draft-confirmation-panel draft-overlay-confirmation">
              <p>当前没有待审阅修改。您可以先在左侧查看解析后的 Markdown 效果，关闭后继续编辑右侧草案正文。</p>
            </div>
          </aside>
        </div>
      </div>
    </div>

    <!-- New Session Modal -->
    <div v-if="showNewSessionModal" class="modal-overlay" @click.self="showNewSessionModal = false">
      <div class="modal-content glass">
        <h3>新建探究会话</h3>
        <label class="field">
          <span>课题名称</span>
          <input v-model="topicInput" class="input" placeholder="例如：光的反射" />
        </label>
        <label class="field">
          <span>选择教学流</span>
          <select v-model="selectedFlowName" class="input">
            <option v-for="flow in flows" :key="flow.name" :value="flow.name">
              {{ flow.display_name }} ({{ flow.stage_count }}阶段)
            </option>
          </select>
        </label>
        <div class="modal-actions">
          <button class="ghost-button" @click="showNewSessionModal = false">取消</button>
          <button class="primary-button" @click="handleCreateSession">创建</button>
        </div>
      </div>
    </div>

    <div v-if="saveSuccessVisible" class="save-toast glass" role="status" aria-live="polite">
      <strong>保存成功</strong>
      <span>当前阶段草稿已保存到服务器。</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  createSession,
  deleteSession,
  applyDraftProposalActions,
  getDraftProposal,
  getChatMode,
  exportSession,
  getFlows,
  getMessages,
  getSession,
  getSessions,
  rollbackSession,
  saveDraft,
  selectFlow,
  setDraftMode,
  setChatMode,
  streamChat,
} from "@/api";
import type {
  ChatMode,
  DraftProposal,
  DraftSelection,
  DraftProposalSegment,
  FlowInfo,
  FlowStage,
  MessageItem,
  SessionDetail,
  SessionListItem,
} from "@/types";
import { renderMarkdown } from "@/utils/markdown";

const flows = ref<FlowInfo[]>([]);
const sessions = ref<SessionListItem[]>([]);
const currentSession = ref<SessionDetail | null>(null);
const messages = ref<MessageItem[]>([]);
const selectedFlowName = ref("inquiry_7_stage");
const selectedSessionId = ref("");
const selectedStageId = ref("");
const topicInput = ref("光的反射");
const chatInput = ref("");
const draftContent = ref("");
const draftProposal = ref<DraftProposal | null>(null);
const draftStreamingContent = ref("");
const statusText = ref("准备就绪");
const streamWarning = ref("");
const isStreaming = ref(false);
const chatMode = ref<ChatMode>("main");
const themeMode = ref<"dark" | "light">("dark");
const saveSuccessVisible = ref(false);
const workflowPhase = ref<"idle" | "guide" | "draft" | "expert">("idle");
const workflowStatusText = ref("准备就绪");
const leftSidebarVisible = ref(true);
const rightSidebarVisible = ref(true);
const feedRef = ref<HTMLElement | null>(null);
const chatInputRef = ref<HTMLTextAreaElement | null>(null);
const draftEditorRef = ref<HTMLTextAreaElement | null>(null);
const reviewPreviewRef = ref<HTMLElement | null>(null);
const showDraftReviewOverlay = ref(false);
const activeReviewSegmentId = ref<string | null>(null);
const expandedReviewSegmentIds = ref<string[]>([]);
const draftWorkbenchState = ref<"idle" | "generate_streaming" | "edit_streaming" | "proposal_review" | "save_ready">("idle");
const lastDraftSelection = ref<DraftSelection | null>(null);
const attachedChatSelection = ref<DraftSelection | null>(null);
const attachedChatSelectionLabel = ref("");
const currentDraftCursorLine = ref(1);
const draftEditorScrollTop = ref(0);
const draftEditorMeasureWidth = ref(0);
const draftEditorLineHeight = ref(21.6);
const draftEditorFont = ref("");
let saveSuccessTimer: number | undefined;
let workflowStatusTimer: number | undefined;
let draftEditorResizeObserver: ResizeObserver | null = null;
let draftMeasureCanvas: HTMLCanvasElement | null = null;

// New ref for modal
const showNewSessionModal = ref(false);

function applyTheme(mode: "dark" | "light") {
  document.body.classList.toggle("theme-light", mode === "light");
  document.body.classList.toggle("theme-dark", mode === "dark");
}

function toggleTheme() {
  themeMode.value = themeMode.value === "dark" ? "light" : "dark";
}

function toggleLeftSidebar() {
  leftSidebarVisible.value = !leftSidebarVisible.value;
}

function toggleRightSidebar() {
  rightSidebarVisible.value = !rightSidebarVisible.value;
}

function updateWorkflowStatus(
  phase: "idle" | "guide" | "draft" | "expert",
  text: string,
  state: "start" | "done" | "error" = "start",
) {
  workflowStatusText.value = text;
  if (workflowStatusTimer) {
    window.clearTimeout(workflowStatusTimer);
    workflowStatusTimer = undefined;
  }

  if (state === "start") {
    workflowPhase.value = phase;
    return;
  }

  workflowStatusTimer = window.setTimeout(() => {
    workflowPhase.value = "idle";
    workflowStatusText.value = "准备就绪";
    workflowStatusTimer = undefined;
  }, 900);
}

const stageNameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const stage of activeStages.value) {
    map[stage.id] = stage.name;
  }
  return map;
});

const activeStages = computed<FlowStage[]>(() => {
  if (!currentSession.value) {
    return flows.value.find((item) => item.name === selectedFlowName.value)?.stages || [];
  }
  return flows.value.find((item) => item.name === currentSession.value?.flow_name)?.stages || [];
});

const currentStage = computed<FlowStage | null>(() => {
  if (!currentSession.value) {
    return null;
  }
  return currentSession.value.current_stage;
});

const currentStageId = computed(() => currentStage.value?.id || selectedStageId.value);

const currentStageIndex = computed(() => currentSession.value?.current_stage_index ?? 0);

const progressPercentage = computed(() => {
  if (!activeStages.value.length) return 0;
  if (currentSession.value?.status === "completed") return 100;
  if (activeStages.value.length <= 1) return 100;
  return (currentStageIndex.value / (activeStages.value.length - 1)) * 100;
});

const isDraftMode = computed(() => Boolean(currentSession.value?.draft_mode_enabled));

const visibleDraftSegments = computed(() => {
  return draftProposal.value?.segments.filter((segment) => segment.kind !== "equal") || [];
});

const pendingReviewCount = computed(() => {
  return visibleDraftSegments.value.filter((segment) => segment.status === "pending").length;
});

const draftPrimaryActionLabel = computed(() => {
  if (!draftContent.value.trim()) {
    return "生成草案";
  }
  if (!attachedChatSelection.value?.selected_text?.trim()) {
    return "先选中再编辑";
  }
  return "编辑草案";
});

const currentSelectionReferenceLabel = computed(() => {
  if (!lastDraftSelection.value?.selected_text?.trim()) {
    return "";
  }
  return formatSelectionReferenceLabel(lastDraftSelection.value);
});

const draftVisualLines = computed(() => {
  const lines = draftContent.value.split("\n");
  const availableWidth = draftEditorMeasureWidth.value;
  if (!availableWidth) {
    return lines.map((_, index) => ({
      key: `line-${index + 1}-0`,
      label: `${index + 1}`,
      logicalLine: index + 1,
      continuation: false,
    }));
  }
  return lines.flatMap((line, index) => {
    const logicalLine = index + 1;
    const rows = estimateWrappedRowCount(line || " ", availableWidth, draftEditorFont.value);
    return Array.from({ length: rows }, (_, rowIndex) => ({
      key: `line-${logicalLine}-${rowIndex}`,
      label: rowIndex === 0 ? `${logicalLine}` : "",
      logicalLine,
      continuation: rowIndex > 0,
    }));
  });
});

const draftWorkbenchEmptyText = computed(() => {
  if (!draftContent.value.trim()) {
    return "草案模式已开启，发送消息后会先生成一版初稿。";
  }
  return "草案模式已开启。编辑已有草案时，请先选中右侧要修改的一段，再发送给草案编辑 Agent。";
});

const draftProposalDescription = computed(() => {
  if (!draftProposal.value) {
    return "";
  }
  if (draftProposal.value.proposal_kind === "edit") {
    return "当前候选草案保留整篇视图，并重点高亮了本次命中的修改片段。";
  }
  return "当前候选草案与已采纳草案的差异如下。";
});

const activeReviewSegment = computed(() => {
  return visibleDraftSegments.value.find((segment) => segment.id === activeReviewSegmentId.value) || null;
});

const reviewPreviewContent = computed(() => {
  if (!draftProposal.value) {
    return draftContent.value;
  }
  if (activeReviewSegment.value?.kind === "delete") {
    return draftProposal.value.base_content || draftContent.value || draftProposal.value.candidate_content;
  }
  return draftProposal.value.candidate_content || draftContent.value || draftProposal.value.base_content;
});

const reviewPreviewBlocks = computed(() => {
  const source = reviewPreviewContent.value || "";
  const parts = source
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (!parts.length) {
    return [{ id: "block-empty", raw: "### 暂无可审阅内容" }];
  }
  return parts.map((raw, index) => ({
    id: `block-${index}`,
    raw,
  }));
});

const activePreviewBlockId = computed(() => {
  const segment = activeReviewSegment.value;
  if (!segment) {
    return reviewPreviewBlocks.value[0]?.id || null;
  }
  const needle = normalizeForMatch(
    segment.kind === "delete" ? segment.base_text : segment.candidate_text || segment.base_text,
  );
  if (!needle) {
    return reviewPreviewBlocks.value[0]?.id || null;
  }
  const matched = reviewPreviewBlocks.value.find((block) => normalizeForMatch(block.raw).includes(needle));
  return matched?.id || reviewPreviewBlocks.value[0]?.id || null;
});

function pickStageIdFromSession(session: SessionDetail) {
  if (session.current_stage?.id) {
    return session.current_stage.id;
  }
  const output = session.outputs[session.current_stage_index] || session.outputs[session.outputs.length - 1];
  return output?.stage_id || "";
}

function activeStageOutput(stageId: string) {
  return currentSession.value?.outputs.find((item) => item.stage_id === stageId);
}

function proposalStatusLabel(status: DraftProposal["status"]) {
  if (status === "accepted") {
    return "已采纳";
  }
  if (status === "rejected") {
    return "已拒绝";
  }
  return "待审阅";
}

function segmentStatusLabel(status: DraftProposalSegment["status"]) {
  if (status === "accepted") {
    return "已采纳";
  }
  if (status === "rejected") {
    return "已拒绝";
  }
  return "待处理";
}

function draftSegmentLabel(segment: DraftProposalSegment) {
  if (segment.kind === "insert") {
    return "新增内容";
  }
  if (segment.kind === "delete") {
    return "删除内容";
  }
  return "替换内容";
}

function normalizeForMatch(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function segmentPreviewText(value: string) {
  const text = value.replace(/\s+/g, " ").trim();
  if (!text) {
    return "（空内容）";
  }
  return text.length > 90 ? `${text.slice(0, 90).trim()}...` : text;
}

function reviewSegmentSummary(segment: DraftProposalSegment) {
  if (segment.kind === "insert") {
    return `建议新增：${segmentPreviewText(segment.candidate_text)}`;
  }
  if (segment.kind === "delete") {
    return `建议删除：${segmentPreviewText(segment.base_text)}`;
  }
  return `建议改为：${segmentPreviewText(segment.candidate_text || segment.base_text)}`;
}

function pickInitialReviewSegmentId(proposal: DraftProposal | null) {
  if (!proposal) {
    return null;
  }
  const visible = proposal.segments.filter((segment) => segment.kind !== "equal");
  const highlighted = visible.find((segment) => proposal.highlight_segment_ids?.includes(segment.id));
  if (highlighted) {
    return highlighted.id;
  }
  const pending = visible.find((segment) => segment.status === "pending");
  if (pending) {
    return pending.id;
  }
  return visible[0]?.id || null;
}

function syncDraftFromSelection() {
  const stageId = selectedStageId.value || currentStageId.value;
  if (!stageId) {
    draftContent.value = "";
    return;
  }
  const output = activeStageOutput(stageId);
  draftContent.value = output?.draft_content || output?.final_content || "";
}

function syncDraftEditor() {
  const editor = draftEditorRef.value;
  if (!editor || editor.value === draftContent.value) {
    return;
  }
  editor.value = draftContent.value;
  syncDraftEditorMetrics();
}

function lineNumberAtOffset(source: string, offset: number) {
  const safeOffset = Math.max(0, Math.min(offset, source.length));
  return source.slice(0, safeOffset).split("\n").length;
}

function formatSelectionReferenceLabel(selection: DraftSelection) {
  const startLine = lineNumberAtOffset(draftContent.value, selection.start_offset);
  const endLine = lineNumberAtOffset(draftContent.value, selection.end_offset);
  return `@${startLine}行-${endLine}行`;
}

function clearAttachedChatSelection(removeLabel = true) {
  attachedChatSelection.value = null;
  attachedChatSelectionLabel.value = "";
}

function addSelectionToChat() {
  const selection = lastDraftSelection.value;
  if (!selection?.selected_text?.trim()) {
    return;
  }
  const nextLabel = formatSelectionReferenceLabel(selection);
  if (attachedChatSelectionLabel.value && attachedChatSelectionLabel.value !== nextLabel) {
    clearAttachedChatSelection(true);
  }
  attachedChatSelection.value = { ...selection };
  attachedChatSelectionLabel.value = nextLabel;
  nextTick(() => {
    const input = chatInputRef.value;
    if (!input) {
      return;
    }
    input.focus();
    const cursor = input.value.length;
    input.setSelectionRange(cursor, cursor);
  });
}

function clearDraftSelection() {
  const editor = draftEditorRef.value;
  if (editor) {
    const cursor = editor.selectionEnd ?? editor.selectionStart ?? 0;
    editor.focus();
    editor.setSelectionRange(cursor, cursor);
  }
  lastDraftSelection.value = null;
}

function getDraftMeasureContext(font: string) {
  if (!draftMeasureCanvas) {
    draftMeasureCanvas = document.createElement("canvas");
  }
  const context = draftMeasureCanvas.getContext("2d");
  if (!context) {
    return null;
  }
  context.font = font;
  return context;
}

function estimateWrappedRowCount(text: string, availableWidth: number, font: string) {
  if (!availableWidth) {
    return 1;
  }
  const context = getDraftMeasureContext(font);
  if (!context) {
    return 1;
  }
  let rows = 1;
  let currentWidth = 0;
  for (const char of text) {
    const charWidth = context.measureText(char).width || 0;
    if (currentWidth > 0 && currentWidth + charWidth > availableWidth) {
      rows += 1;
      currentWidth = charWidth;
    } else {
      currentWidth += charWidth;
    }
  }
  return Math.max(rows, 1);
}

function updateDraftCursorLine() {
  const editor = draftEditorRef.value;
  if (!editor) {
    currentDraftCursorLine.value = 1;
    return;
  }
  currentDraftCursorLine.value = lineNumberAtOffset(draftContent.value, editor.selectionStart ?? 0);
}

function syncDraftEditorScroll() {
  draftEditorScrollTop.value = draftEditorRef.value?.scrollTop ?? 0;
}

function syncDraftEditorMetrics() {
  const editor = draftEditorRef.value;
  if (!editor) {
    draftEditorMeasureWidth.value = 0;
    return;
  }
  const styles = window.getComputedStyle(editor);
  const paddingLeft = Number.parseFloat(styles.paddingLeft || "0");
  const paddingRight = Number.parseFloat(styles.paddingRight || "0");
  const lineHeight = Number.parseFloat(styles.lineHeight || "21.6");
  draftEditorMeasureWidth.value = Math.max(editor.clientWidth - paddingLeft - paddingRight, 0);
  draftEditorLineHeight.value = Number.isFinite(lineHeight) ? lineHeight : 21.6;
  draftEditorFont.value = styles.font || `${styles.fontSize} ${styles.fontFamily}`;
  syncDraftEditorScroll();
}

function attachDraftEditorObserver() {
  draftEditorResizeObserver?.disconnect();
  draftEditorResizeObserver = null;
  if (!draftEditorRef.value || typeof ResizeObserver === "undefined") {
    return;
  }
  draftEditorResizeObserver = new ResizeObserver(() => {
    syncDraftEditorMetrics();
  });
  draftEditorResizeObserver.observe(draftEditorRef.value);
}

function captureDraftSelection() {
  const editor = draftEditorRef.value;
  if (!editor) {
    return;
  }
  updateDraftCursorLine();
  syncDraftEditorMetrics();
  const start = editor.selectionStart ?? 0;
  const end = editor.selectionEnd ?? 0;
  const selectedText = draftContent.value.slice(start, end).trim();
  if (!selectedText) {
    lastDraftSelection.value = null;
    return;
  }
  lastDraftSelection.value = {
    selected_text: selectedText,
    start_offset: start,
    end_offset: end,
    stage_id: selectedStageId.value || currentStageId.value,
    block_id: null,
  };
}

async function refreshDraftProposal() {
  if (!currentSession.value || !selectedStageId.value || !currentSession.value.draft_mode_enabled) {
    draftProposal.value = null;
    activeReviewSegmentId.value = null;
    expandedReviewSegmentIds.value = [];
    draftStreamingContent.value = "";
    draftWorkbenchState.value = draftContent.value.trim() ? "save_ready" : "idle";
    return;
  }
  const proposal = await getDraftProposal(currentSession.value.id, selectedStageId.value);
  draftProposal.value = proposal;
  activeReviewSegmentId.value = pickInitialReviewSegmentId(proposal);
  expandedReviewSegmentIds.value = activeReviewSegmentId.value ? [activeReviewSegmentId.value] : [];
  draftWorkbenchState.value = proposal ? "proposal_review" : draftContent.value.trim() ? "save_ready" : "idle";
}

function selectReviewSegment(segmentId: string) {
  activeReviewSegmentId.value = segmentId;
}

function scrollActiveReviewBlockIntoView() {
  requestAnimationFrame(() => {
    const container = reviewPreviewRef.value;
    const blockId = activePreviewBlockId.value;
    if (!container || !blockId) {
      return;
    }
    const target = container.querySelector<HTMLElement>(`[data-block-id="${blockId}"]`);
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  });
}

function openDraftReviewOverlay() {
  showDraftReviewOverlay.value = true;
  const nextSegmentId = pickInitialReviewSegmentId(draftProposal.value);
  activeReviewSegmentId.value = nextSegmentId;
  expandedReviewSegmentIds.value = nextSegmentId ? [nextSegmentId] : [];
}

function closeDraftReviewOverlay() {
  showDraftReviewOverlay.value = false;
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && showDraftReviewOverlay.value) {
    closeDraftReviewOverlay();
  }
}

function onDraftEditorInput() {
  draftContent.value = draftEditorRef.value?.value ?? draftContent.value;
  draftWorkbenchState.value = draftContent.value.trim() ? "save_ready" : "idle";
  updateDraftCursorLine();
  syncDraftEditorMetrics();
}

async function refreshWorkspace() {
  statusText.value = "刷新流程与会话中...";
  const [flowList, sessionList] = await Promise.all([getFlows(), getSessions()]);
  flows.value = flowList;
  sessions.value = sessionList;
  try {
    chatMode.value = await getChatMode();
  } catch {
    chatMode.value = "main";
  }
  if (!selectedFlowName.value && flowList[0]) {
    selectedFlowName.value = flowList[0].name;
  }
  statusText.value = "工作区已刷新";
}

async function loadSession(sessionId: string, loadMessages = true, preserveWarning = false) {
  const session = await getSession(sessionId);
  if (!preserveWarning) {
    streamWarning.value = "";
  }
  currentSession.value = session;
  selectedSessionId.value = session.id;
  selectedFlowName.value = session.flow_name;
  selectedStageId.value = pickStageIdFromSession(session);
  if (loadMessages) {
    messages.value = await getMessages(sessionId);
  }
  clearAttachedChatSelection(true);
  syncDraftFromSelection();
  draftStreamingContent.value = "";
  await nextTick();
  syncDraftEditor();
  updateDraftCursorLine();
  await refreshDraftProposal();
  statusText.value = `已切换到 ${session.topic}`;
}

async function selectSession(sessionId: string) {
  await loadSession(sessionId, true);
}

async function toggleChatMode() {
  if (isStreaming.value) {
    return;
  }
  const nextMode: ChatMode = chatMode.value === "main" ? "subagent" : "main";
  try {
    const savedMode = await setChatMode(nextMode);
    chatMode.value = savedMode;
    statusText.value = savedMode === "subagent" ? "已切换到Agent模式" : "已切换到主流程模式";
  } catch (err: any) {
    statusText.value = `切换失败：${err.message || err}`;
  }
}

async function toggleDraftMode() {
  if (isStreaming.value || !currentSession.value) {
    return;
  }
  try {
    const updated = await setDraftMode(currentSession.value.id, !currentSession.value.draft_mode_enabled);
    currentSession.value = updated;
    await nextTick();
    if (updated.draft_mode_enabled) {
      statusText.value = "已进入草案模式";
      await refreshDraftProposal();
    } else {
      clearAttachedChatSelection(true);
      draftProposal.value = null;
      draftStreamingContent.value = "";
      lastDraftSelection.value = null;
      draftWorkbenchState.value = "idle";
      statusText.value = "已退出草案模式";
    }
  } catch (err: any) {
    statusText.value = `切换草案模式失败：${err.message || err}`;
  }
}

async function handleDeleteSession() {
  if (!currentSession.value) return;
  const topic = currentSession.value.topic;
  if (!confirm(`确认删除会话《${topic}》吗？此操作不可恢复。`)) {
    return;
  }
  try {
    statusText.value = `正在删除会话《${topic}》...`;
    await deleteSession(currentSession.value.id);
    sessions.value = sessions.value.filter((item) => item.id !== currentSession.value!.id);
    if (sessions.value.length > 0) {
      await loadSession(sessions.value[0].id, true);
    } else {
      currentSession.value = null;
      selectedSessionId.value = "";
      messages.value = [];
      clearAttachedChatSelection(false);
      draftContent.value = "";
      draftProposal.value = null;
      draftStreamingContent.value = "";
      lastDraftSelection.value = null;
      draftWorkbenchState.value = "idle";
      statusText.value = "所有会话已删除";
    }
  } catch (err: any) {
    statusText.value = `删除失败: ${err.message || err}`;
  }
}

async function createWorkspaceSession() {
  const topic = topicInput.value.trim();
  if (!topic) {
    statusText.value = "请先输入课题名称";
    return;
  }
  const created = await createSession(topic, selectedFlowName.value);
  sessions.value = [created, ...sessions.value.filter((item) => item.id !== created.id)];
  await loadSession(created.id, true);
  statusText.value = `已创建会话：${topic}`;
}

async function handleCreateSession() {
  const topic = topicInput.value.trim();
  if (!topic) {
    statusText.value = "请先输入课题名称";
    return;
  }
  await createWorkspaceSession();
  showNewSessionModal.value = false;
}

async function switchFlow(flowName: string) {
  selectedFlowName.value = flowName;
  if (!currentSession.value) {
    return;
  }
  const updated = await selectFlow(currentSession.value.id, flowName);
  currentSession.value = updated;
  await loadSession(updated.id, true);
  sessions.value = [updated, ...sessions.value.filter((item) => item.id !== updated.id)];
  statusText.value = `流程已切换为 ${updated.flow_display_name}`;
}

function inspectStage(stageId: string) {
  selectedStageId.value = stageId;
  const output = activeStageOutput(stageId);
  draftContent.value = output?.draft_content || output?.final_content || "";
  clearAttachedChatSelection(true);
  lastDraftSelection.value = null;
  void refreshDraftProposal();
  void nextTick(() => {
    syncDraftEditor();
    updateDraftCursorLine();
  });
  statusText.value = `正在查看 ${stageNameMap.value[stageId] || stageId}`;
}

function messageRoleLabel(message: MessageItem) {
  if (message.role === "user") {
    return "教师";
  }
  if (message.message_type === "stage_expert") {
    const stage = activeStages.value.find((item) => item.id === message.stage_id);
    return message.agent_name || stage?.expert || "阶段专家";
  }
  if (message.message_type === "main_tutor" || message.agent_id === "main_agent") {
    return message.agent_name || "流程引导Agent";
  }
  if (message.message_type === "draft_tutor" || message.agent_id === "draft_agent") {
    return message.agent_name || "草案修订Agent";
  }
  return "导师";
}

function createPendingAssistantMessage(
  requestMode: "main" | "subagent" | "draft",
  stageId: string,
  initialText: string,
): { key: string; message: MessageItem } {
  if (requestMode === "subagent") {
    return {
      key: "stage_expert",
      message: {
        stage_id: stageId,
        role: "assistant",
        content: initialText,
        agent_id: currentStage.value?.agent_id || null,
        agent_name: currentStage.value?.expert || "阶段专家",
        message_type: "stage_expert",
      },
    };
  }
  return {
    key: requestMode === "draft" ? "draft_status" : "main_tutor",
    message: {
      stage_id: stageId,
      role: "assistant",
      content: initialText,
      agent_id: "main_agent",
      agent_name: "流程引导Agent",
      message_type: "main_tutor",
    },
  };
}

function showWorkflowBadgeForMessage(message: MessageItem) {
  if (workflowPhase.value === "idle" || message.role !== "assistant") {
    return false;
  }
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const current = messages.value[index];
    if (current.role === "assistant") {
      return current === message;
    }
  }
  return false;
}

async function saveDraftToServer() {
  if (!currentSession.value || !selectedStageId.value) {
    return;
  }
  await saveDraft(currentSession.value.id, selectedStageId.value, draftContent.value);
  await loadSession(currentSession.value.id, false);
  draftWorkbenchState.value = draftContent.value.trim() ? "save_ready" : "idle";
  statusText.value = "草稿已保存";
  saveSuccessVisible.value = true;
  if (saveSuccessTimer) {
    window.clearTimeout(saveSuccessTimer);
  }
  saveSuccessTimer = window.setTimeout(() => {
    saveSuccessVisible.value = false;
  }, 1800);
}

async function applyDraftProposalAction(hunkId: string, action: "accept" | "reject") {
  if (!currentSession.value || !draftProposal.value) {
    return;
  }
  const updated = await applyDraftProposalActions(currentSession.value.id, draftProposal.value.id, [
    { hunk_id: hunkId, action },
  ]);
  draftProposal.value = updated.status === "pending" ? updated : null;
  await loadSession(currentSession.value.id, false, true);
  await refreshDraftProposal();
}

async function applyAllDraftProposalActions(action: "accept" | "reject") {
  if (!currentSession.value || !draftProposal.value) {
    return;
  }
  const actions = visibleDraftSegments.value
    .filter((segment) => segment.status === "pending")
    .map((segment) => ({ hunk_id: segment.id, action }));
  if (!actions.length) {
    return;
  }
  const updated = await applyDraftProposalActions(currentSession.value.id, draftProposal.value.id, actions);
  draftProposal.value = updated.status === "pending" ? updated : null;
  await loadSession(currentSession.value.id, false, true);
  await refreshDraftProposal();
}

async function sendChat() {
  if (isStreaming.value) {
    return;
  }
  const text = chatInput.value.trim();
  if (!text) {
    statusText.value = "请输入要发送的内容";
    return;
  }
  if (!currentSession.value) {
    await createWorkspaceSession();
  }
  if (!currentSession.value) {
    return;
  }

  const requestMode = currentSession.value.draft_mode_enabled ? "draft" : chatMode.value;
  const draftRequestKind = requestMode === "draft" ? (draftContent.value.trim() ? "edit" : "generate") : undefined;
  const selectionPayload = attachedChatSelection.value?.selected_text?.trim() ? attachedChatSelection.value : null;
  const draftContentBeforeRequest = draftContent.value;
  const shouldStreamDraftIntoEditor =
    requestMode === "draft" && draftRequestKind === "generate" && !draftContentBeforeRequest.trim();

  if (requestMode === "draft" && draftRequestKind === "edit" && !selectionPayload) {
    statusText.value = "请先在右侧选中要修改的草案内容，再发送给草案编辑 Agent。";
    return;
  }

  const sessionId = currentSession.value.id;
  const stageId = currentSession.value.current_stage?.id || "";
  const userMessage: MessageItem = {
    stage_id: stageId,
    role: "user",
    content: text,
    agent_id: null,
    message_type: "chat",
  };
  messages.value = [...messages.value, userMessage];
  chatInput.value = "";
  isStreaming.value = true;
  streamWarning.value = "";
  draftStreamingContent.value = "";
  if (requestMode === "draft") {
    draftProposal.value = null;
  }
  clearAttachedChatSelection(false);
  statusText.value =
    requestMode === "draft"
      ? selectionPayload
        ? "正在围绕您选中的内容与草案Agent协作..."
        : "正在与草案Agent交互..."
      : requestMode === "subagent"
        ? selectionPayload
          ? "正在请阶段专家围绕您选中的内容做点评..."
          : "正在等待Agent分析..."
        : selectionPayload
          ? "正在请主流程围绕您选中的内容做引导..."
          : "正在等待主流程分析...";
  updateWorkflowStatus(requestMode === "draft" ? "draft" : requestMode === "subagent" ? "expert" : "guide", statusText.value, "start");
  const streamMessages = new Map<string, MessageItem>();
  const placeholderTexts = new Map<string, string>();
  const pendingAssistant = createPendingAssistantMessage(requestMode, stageId, statusText.value);
  streamMessages.set(pendingAssistant.key, pendingAssistant.message);
  placeholderTexts.set(pendingAssistant.key, statusText.value);
  messages.value = [...messages.value, pendingAssistant.message];
  scrollFeedToBottom();

  try {
    await streamChat(
      sessionId,
      {
        type: "chat",
        message: text,
        draft_request_kind: draftRequestKind,
        selection: selectionPayload,
      },
      {
        stage: () => {
          selectedStageId.value = currentSession.value?.current_stage?.id || selectedStageId.value;
        },
        agent: (data) => {
          const targetKey =
            requestMode === "draft"
              ? "draft_status"
              : requestMode === "subagent"
                ? "stage_expert"
                : "main_tutor";
          const pendingMessage = streamMessages.get(targetKey);
          if (pendingMessage) {
            pendingMessage.agent_id = data.agent_id || pendingMessage.agent_id || null;
            pendingMessage.agent_name = data.agent_name || pendingMessage.agent_name || null;
            messages.value = [...messages.value];
          }
          if (requestMode === "draft") {
            statusText.value = `${data.agent_name || data.agent_id || "流程引导Agent"} 正在陪您一起整理草案`;
          } else if (requestMode === "subagent") {
            statusText.value = `${data.agent_name || data.agent_id || "Agent"} 正在回答`;
          } else {
            statusText.value = `${data.agent_name || data.agent_id || "主流程"} 正在回答`;
          }
        },
        delta: (data) => {
          const messageType = data.message_type || "main_tutor";
          let assistantMessage = streamMessages.get(messageType);
          if (!assistantMessage) {
            assistantMessage = {
              stage_id: stageId,
              role: "assistant",
              content: "",
              agent_id: data.agent_id || null,
              agent_name: data.agent_name || null,
              message_type: messageType,
            };
            streamMessages.set(messageType, assistantMessage);
            messages.value = [...messages.value, assistantMessage];
          }
          const chunkText = data.text || "";
          if (placeholderTexts.has(messageType)) {
            assistantMessage.content = chunkText;
            placeholderTexts.delete(messageType);
          } else {
            assistantMessage.content += chunkText;
          }
          assistantMessage.agent_id = data.agent_id || assistantMessage.agent_id || null;
          assistantMessage.agent_name = data.agent_name || assistantMessage.agent_name || null;
          messages.value = [...messages.value];
          scrollFeedToBottom();
        },
        draft: (data) => {
          if (data.message_type === "draft_tutor" || data.agent_id === "draft_agent") {
            draftStreamingContent.value = data.content || data.text || draftStreamingContent.value;
            draftWorkbenchState.value = draftRequestKind === "edit" ? "edit_streaming" : "generate_streaming";
            if (shouldStreamDraftIntoEditor) {
              draftContent.value = data.content || draftStreamingContent.value;
            }
          }
        },
        proposal: (data) => {
          draftProposal.value = data.proposal || null;
          draftStreamingContent.value = "";
          if (draftProposal.value) {
            draftWorkbenchState.value = "proposal_review";
          }
        },
        status: (data) => {
          const phase = data.phase === "draft" ? "draft" : data.phase === "guide" ? "guide" : "idle";
          const state = data.state === "error" ? "error" : data.state === "done" ? "done" : "start";
          const text =
            data.text ||
            (phase === "draft" ? "正在生成草案..." : phase === "guide" ? "正在生成流程引导..." : "准备就绪");
          updateWorkflowStatus(phase, text, state);
          if (requestMode === "draft") {
            if (state === "error") {
              draftStreamingContent.value = "";
              if (shouldStreamDraftIntoEditor) {
                draftContent.value = draftContentBeforeRequest;
              }
              draftWorkbenchState.value = draftContent.value.trim() ? "save_ready" : "idle";
            }
            let assistantMessage = streamMessages.get("draft_status");
            if (!assistantMessage) {
              assistantMessage = {
                stage_id: stageId,
                role: "assistant",
                content: "",
                agent_id: "main_agent",
                agent_name: "流程引导Agent",
                message_type: "main_tutor",
              };
              streamMessages.set("draft_status", assistantMessage);
              messages.value = [...messages.value, assistantMessage];
            }
            assistantMessage.content = text;
            placeholderTexts.delete("draft_status");
            messages.value = [...messages.value];
            scrollFeedToBottom();
          }
        },
        warning: (data) => {
          streamWarning.value = `${data.agent_name || "阶段专家"}暂时不可用：${data.message || "本轮由主导师继续指导"}`;
          statusText.value = "阶段专家降级，主导师继续回答";
        },
        done: async (data) => {
          await loadSession(sessionId, true, true);
          await refreshDraftProposal();
          if (requestMode === "draft") {
            if (data.draft_proposal) {
              draftWorkbenchState.value = "proposal_review";
            } else {
              draftWorkbenchState.value = draftContent.value.trim() ? "save_ready" : "idle";
            }
            statusText.value = data.draft_failed
              ? "这次草案整理没有成功"
              : data.draft_updated
                ? "右侧草案已经整理好了"
                : data.draft_status_text || "右侧草案暂时不需要调整";
          } else if (requestMode === "subagent") {
            statusText.value = "Agent回复完成";
            updateWorkflowStatus("expert", statusText.value, "done");
          } else {
            statusText.value = data.degraded ? "主导师已在降级模式下完成回复" : "主流程回复完成";
            updateWorkflowStatus("guide", statusText.value, "done");
          }
        },
      },
    );
  } catch (err: any) {
    if (shouldStreamDraftIntoEditor) {
      draftContent.value = draftContentBeforeRequest;
      draftStreamingContent.value = "";
      draftWorkbenchState.value = draftContentBeforeRequest.trim() ? "save_ready" : "idle";
    }
    statusText.value = `对话失败：${err.message || err}`;
    updateWorkflowStatus(requestMode === "draft" ? "draft" : requestMode === "subagent" ? "expert" : "guide", statusText.value, "error");
  } finally {
    isStreaming.value = false;
    scrollFeedToBottom();
  }
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter") {
    return;
  }
  if (event.shiftKey) {
    return;
  }
  event.preventDefault();
  void sendChat();
}

async function goNextStage() {
  if (!currentSession.value) {
    return;
  }
  isStreaming.value = true;
  statusText.value = "正在推进到下一阶段...";
  try {
    await streamChat(
      currentSession.value.id,
      {
        type: "sys_action",
        action: "next_stage",
        final_content: draftContent.value,
      },
      {
        stage: () => undefined,
        delta: () => undefined,
        done: async () => {
          await loadSession(currentSession.value!.id, true);
          statusText.value = "已进入下一阶段";
        },
      },
    );
  } finally {
    isStreaming.value = false;
  }
}

async function goPreviousStage() {
  if (!currentSession.value) {
    return;
  }
  statusText.value = "正在回退到上一阶段...";
  isStreaming.value = true;
  try {
    await rollbackSession(currentSession.value.id, { steps: 1, stage_back: true });
    await loadSession(currentSession.value.id, true);
    statusText.value = "已回到上一阶段";
  } finally {
    isStreaming.value = false;
  }
}

async function rollbackRecent() {
  if (!currentSession.value) {
    return;
  }
  statusText.value = "正在回滚最近一轮对话...";
  await rollbackSession(currentSession.value.id, { steps: 1, stage_back: false });
  await loadSession(currentSession.value.id, true);
  statusText.value = "最近一轮对话已回滚";
}

async function exportCurrentPlan() {
  if (!currentSession.value) {
    return;
  }
  const blob = await exportSession(currentSession.value.id);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${currentSession.value.topic}-探究式教案.md`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  statusText.value = "教案已导出";
}

function scrollFeedToBottom() {
  requestAnimationFrame(() => {
    const feed = feedRef.value;
    if (feed) {
      feed.scrollTop = feed.scrollHeight;
    }
  });
}

watch(
  () => [selectedStageId.value, currentSession.value?.id],
  () => syncDraftFromSelection(),
);

watch(
  () => draftContent.value,
  () => {
    const editor = draftEditorRef.value;
    if (!editor || document.activeElement === editor) {
      return;
    }
    syncDraftEditor();
    updateDraftCursorLine();
    nextTick(() => syncDraftEditorMetrics());
  },
);

watch(
  () => showDraftReviewOverlay.value,
  (visible) => {
    document.body.style.overflow = visible ? "hidden" : "";
    if (visible) {
      nextTick(() => scrollActiveReviewBlockIntoView());
    }
  },
);

watch(
  () => activeReviewSegmentId.value,
  () => {
    if (showDraftReviewOverlay.value) {
      nextTick(() => scrollActiveReviewBlockIntoView());
    }
  },
);

watch(
  () => [workflowPhase.value, workflowStatusText.value],
  () => {
    if (workflowPhase.value !== "idle") {
      nextTick(() => scrollFeedToBottom());
    }
  },
);

watch(
  () => currentSession.value?.current_stage?.id,
  (value) => {
    if (value) {
      selectedStageId.value = value;
      syncDraftFromSelection();
      clearAttachedChatSelection(false);
      lastDraftSelection.value = null;
    }
  },
);

onMounted(async () => {
  const savedTheme = window.localStorage.getItem("inquiry-theme");
  if (savedTheme === "light" || savedTheme === "dark") {
    themeMode.value = savedTheme;
  }
  applyTheme(themeMode.value);
  updateWorkflowStatus("idle", "准备就绪", "done");
  await refreshWorkspace();
  if (sessions.value[0]) {
    await loadSession(sessions.value[0].id, true);
  }
  syncDraftEditor();
  updateDraftCursorLine();
  nextTick(() => {
    syncDraftEditorMetrics();
    attachDraftEditorObserver();
  });
  window.addEventListener("resize", syncDraftEditorMetrics);
  window.addEventListener("keydown", handleGlobalKeydown);
});

onBeforeUnmount(() => {
  draftEditorResizeObserver?.disconnect();
  draftEditorResizeObserver = null;
  window.removeEventListener("resize", syncDraftEditorMetrics);
  window.removeEventListener("keydown", handleGlobalKeydown);
});

watch(themeMode, (mode) => {
  window.localStorage.setItem("inquiry-theme", mode);
  applyTheme(mode);
});

watch(
  () => draftEditorRef.value,
  (editor) => {
    if (!editor) {
      return;
    }
    nextTick(() => {
      syncDraftEditorMetrics();
      attachDraftEditorObserver();
    });
  },
);

watch(saveSuccessVisible, (visible) => {
  if (!visible && saveSuccessTimer) {
    window.clearTimeout(saveSuccessTimer);
    saveSuccessTimer = undefined;
  }
});
</script>
