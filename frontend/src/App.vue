<template>
  <div class="app-shell">
    <!-- LEFT COLUMN: Chat & Progress -->
    <aside class="chat-column">
      <!-- Platform Name / Header -->
      <section class="brand-card glass">
        <div class="brand-main">
          <div>
            <p class="eyebrow">AI 教师探究式教学指导平台</p>
            <h1>探究式教案工作台</h1>
          </div>
          <div class="status-pill" :class="{ live: isStreaming }">
            <span class="status-dot"></span>
            {{ isStreaming ? "SSE 流式中" : "已连接" }}
          </div>
        </div>
      </section>

      <!-- Dynamic Progress Bar (读条) -->
      <section class="glass progress-panel" v-if="currentSession">
        <div class="progress-container">
          <div class="progress-header">
            <span class="progress-title">探究进度 ({{ currentSession.flow_display_name }})</span>
            <span class="progress-percentage">
              {{ currentSession.status === 'completed' ? '已完成' : `第 ${currentStageIndex + 1}/${activeStages.length} 阶段` }}
            </span>
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
          <div class="progress-current-info" v-if="currentStage">
            <strong>当前角色：{{ currentStage.expert }}</strong>
          </div>
        </div>
      </section>

      <!-- Chat Dialogue Box -->
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
              :title="chatMode === 'subagent' ? '当前为子Agent模式，点击切回主流程' : '当前为主流程模式，点击切到子Agent'"
            >
              {{ chatMode === 'subagent' ? '子Agent对话' : '主流程对话' }}
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
              <span>{{ messageRoleLabel(message) }}</span>
              <small>{{ stageNameMap[message.stage_id] || message.stage_id }}</small>
              <small v-if="message.agent_id">{{ message.agent_id }}</small>
            </div>
            <div class="message-content markdown-content" v-html="renderMarkdown(message.content)"></div>
          </article>

          <div v-if="!messages.length" class="empty-state">
            在右侧选择会话并开始对话，系统将引导您完成教学设计。
          </div>
        </div>

        <div class="composer">
          <div class="composer-box">
            <textarea
              v-model="chatInput"
              class="chat-input"
              rows="3"
              placeholder="输入课堂切入点、问题追问、实验思路或阶段补充内容，按 Ctrl/⌘ + Enter 发送"
              @keydown.ctrl.enter.prevent="sendChat"
              @keydown.meta.enter.prevent="sendChat"
            />
            <button class="primary-button send-btn" :disabled="isStreaming" @click="sendChat">
              发送对话
            </button>
          </div>
        </div>
      </section>
    </aside>

    <!-- MIDDLE COLUMN: Document List (Stages) -->
    <section class="glass panel middle-column">
      <div class="panel-head">
        <h2>教案文档列表</h2>
        <div class="panel-actions">
          <button class="icon-button compact danger" @click="handleDeleteSession" :disabled="!currentSession" title="删除当前会话">🗑 删除</button>
          <button class="icon-button compact" @click="showNewSessionModal = true" title="新建会话">＋ 新建</button>
        </div>
      </div>

      <!-- Session & Flow Selector -->
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

      <!-- Document List (Stages) -->
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

    <!-- RIGHT COLUMN: Document Display & Editor -->
    <section class="glass panel document-column">
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
        <div class="stage-card">
          <strong>{{ stageNameMap[selectedStageId] || selectedStageId }}</strong>
          <span class="muted">负责专家：{{ activeStages.find(s => s.id === selectedStageId)?.expert || '主导师' }}</span>
        </div>
        <div
          ref="draftEditorRef"
          class="document-preview markdown-preview editable"
          contenteditable="true"
          spellcheck="false"
          data-placeholder="这里可以直接编辑 Markdown 草稿"
          @input="onDraftEditorInput"
          @blur="syncDraftEditor"
        ></div>
      </div>
      <div v-else class="empty-state">
        请从中间列表选择一个阶段文档进行查看或编辑。
      </div>
    </section>

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
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import {
  createSession,
  deleteSession,
  getChatMode,
  exportSession,
  getFlows,
  getMessages,
  getSession,
  getSessions,
  rollbackSession,
  saveDraft,
  selectFlow,
  setChatMode,
  streamChat,
} from "@/api";
import type { ChatMode, FlowInfo, FlowStage, MessageItem, SessionDetail, SessionListItem } from "@/types";
import { htmlToMarkdown, renderMarkdown } from "@/utils/markdown";

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
const statusText = ref("准备就绪");
const streamWarning = ref("");
const isStreaming = ref(false);
const chatMode = ref<ChatMode>("main");
const feedRef = ref<HTMLElement | null>(null);
const draftEditorRef = ref<HTMLElement | null>(null);

// New ref for modal
const showNewSessionModal = ref(false);

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
  if (!editor) {
    return;
  }
  editor.innerHTML = draftContent.value ? renderMarkdown(draftContent.value) : "";
}

function onDraftEditorInput() {
  const editor = draftEditorRef.value;
  if (!editor) {
    return;
  }
  draftContent.value = htmlToMarkdown(editor.innerHTML);
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
  syncDraftFromSelection();
  await nextTick();
  syncDraftEditor();
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
    statusText.value = savedMode === "subagent" ? "已切换到子Agent模式" : "已切换到主流程模式";
  } catch (err: any) {
    statusText.value = `切换失败：${err.message || err}`;
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
      draftContent.value = "";
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
  void nextTick(() => syncDraftEditor());
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
    return "主教学导师";
  }
  return "导师";
}

async function saveDraftToServer() {
  if (!currentSession.value || !selectedStageId.value) {
    return;
  }
  await saveDraft(currentSession.value.id, selectedStageId.value, draftContent.value);
  await loadSession(currentSession.value.id, false);
  statusText.value = "草稿已保存";
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
  const requestMode = chatMode.value;
  statusText.value = requestMode === "subagent" ? "正在等待子Agent分析..." : "正在等待主流程分析...";
  const streamMessages = new Map<string, MessageItem>();

  try {
    await streamChat(
      sessionId,
      {
        type: "chat",
        message: text,
      },
      {
        stage: () => {
          selectedStageId.value = currentSession.value?.current_stage?.id || selectedStageId.value;
        },
        agent: (data) => {
          if (requestMode === "subagent") {
            statusText.value = `${data.agent_name || data.agent_id || "子Agent"} 正在回答`;
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
          assistantMessage.content += data.text || "";
          messages.value = [...messages.value];
          scrollFeedToBottom();
        },
        draft: (data) => {
          if (data.message_type === "main_tutor" || data.agent_id === "main_agent") {
            draftContent.value = data.content || "";
          }
        },
        warning: (data) => {
          streamWarning.value = `${data.agent_name || "阶段专家"}暂时不可用：${data.message || "本轮由主导师继续指导"}`;
          statusText.value = "阶段专家降级，主导师继续回答";
        },
        done: async (data) => {
          await loadSession(sessionId, true, true);
          if (requestMode === "subagent") {
            statusText.value = "子Agent回复完成";
          } else {
            statusText.value = data.degraded ? "主导师已在降级模式下完成回复" : "主流程回复完成";
          }
        },
      },
    );
  } catch (err: any) {
    statusText.value = `对话失败：${err.message || err}`;
  } finally {
    isStreaming.value = false;
    scrollFeedToBottom();
  }
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
  },
);

watch(
  () => currentSession.value?.current_stage?.id,
  (value) => {
    if (value) {
      selectedStageId.value = value;
      syncDraftFromSelection();
    }
  },
);

onMounted(async () => {
  await refreshWorkspace();
  if (sessions.value[0]) {
    await loadSession(sessions.value[0].id, true);
  }
  syncDraftEditor();
});
</script>
