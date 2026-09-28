<template>
  <AuthPanel v-if="!authLoading && !currentUser" @authenticated="handleAuthenticated" />
  <div v-else-if="authLoading" class="auth-loading">正在验证登录状态…</div>
  <div v-else class="workspace-page">
  <AppHeader
    v-model="selectedExpertId"
    :experts="experts"
    :user="currentUser"
    :session="currentSession"
    :stage="currentStage"
    :stage-progress="currentSession?.status === 'completed' ? '已完成' : `阶段 ${currentStageIndex + 1} / ${activeStages.length}`"
    :streaming="isStreaming"
    :sidebar-collapsed="!leftSidebarVisible"
    :theme-mode="themeMode"
    @toggle-sidebar="toggleLeftSidebar"
    @toggle-theme="toggleTheme"
    @logout="logout"
    @open-graph-admin="openGraphAdmin"
  />
  <div
    class="workspace-grid"
    :class="{
      'left-sidebar-collapsed': !leftSidebarVisible,
      'right-sidebar-collapsed': !rightSidebarVisible,
    }"
  >
    <WorkspaceSidebar
      :collapsed="!leftSidebarVisible"
      :session="currentSession"
      :sessions="sessions"
      :selected-session-id="selectedSessionId"
      :stages="activeStages"
      :selected-stage-id="selectedStageId"
      :current-stage-id="currentStageId"
      :progress="currentSession?.status === 'completed' ? '已完成' : `${currentStageIndex + 1}/${activeStages.length}`"
      :uploading="isUploadingFile"
      :search="sessionSearchQuery"
      :output="activeStageOutput"
      @update:search="sessionSearchQuery = $event"
      @new-session="showNewSessionModal = true"
      @delete-session="handleDeleteSession"
      @select-session="selectSession"
      @select-stage="inspectStage"
    />

    <!-- CENTER COLUMN: Main Conversation -->
    <section class="chat-column">
      <ConversationPanel
        :session="currentSession"
        :stage="currentStage"
        :messages="messages"
        :stage-names="stageNameMap"
        :warning="streamWarning"
        :streaming="isStreaming"
        :render="renderMarkdown"
        :message-role-label="messageRoleLabel"
        @rollback="rollbackRecent"
        @feed-ready="feedRef = $event"
      >
        <ChatComposer
          v-model="chatInput"
          :expert="selectedExpert"
          :selection-label="attachedChatSelectionLabel"
          :files="sessionFiles"
          :deleting-ids="deletingFileIds"
          :streaming="isStreaming"
          :uploading="isUploadingFile"
          :session="currentSession"
          :draft-mode="isDraftMode"
          :request-id="activeStreamRequestId"
          :file-error="fileOperationError"
          :send-disabled="isStreaming ? !activeStreamRequestId : (!selectedExpertId && isDraftMode && !!draftContent.trim() && !attachedChatSelection?.selected_text?.trim())"
          :file-status-label="fileStatusLabel"
          @input-ready="chatInputRef = $event"
          @resize="resizeChatInput"
          @keydown="handleComposerKeydown"
          @clear-expert="selectedExpertId = ''"
          @clear-selection="clearAttachedChatSelection()"
          @remove-file="removeReferenceFile"
          @open-file="openFilePicker"
          @open-curriculum="openCurriculumPanel"
          @toggle-draft="toggleDraftMode"
          @send="sendChat"
          @stop="interruptChat"
        >
          <template #file-input><input ref="fileInputRef" class="visually-hidden" type="file" multiple accept=".pdf,.docx,.txt,.md" @change="handleFileSelection" /></template>
        </ChatComposer>
      </ConversationPanel>
    </section>

    <!-- RIGHT COLUMN: Document Display & Editor -->
    <div class="right-panel-container">
      <div v-if="hasKnowledgeGraphContext" class="right-panel-toggle">
        <button
          type="button"
          class="toggle-button"
          :class="{ active: showGraphInRightPanel }"
          @click="openKnowledgeGraphPanel"
        >
          局部图谱
        </button>
        <button
          type="button"
          class="toggle-button"
          :class="{ active: !showGraphInRightPanel }"
          @click="showGraphInRightPanel = false"
        >
          编辑器
        </button>
      </div>
      <DocumentWorkbench
        v-if="!hasKnowledgeGraphContext || !showGraphInRightPanel"
        v-model="draftContent"
        :session="currentSession"
        :stage="activeStages.find(stage => stage.id === selectedStageId) || currentStage"
        :selected-stage-id="selectedStageId"
        :current-stage-id="currentStageId"
        :stage-index="currentStageIndex"
        :streaming="isStreaming"
        :drafting="workflowPhase === 'draft'"
        :proposal="draftProposal"
        :proposal-label="draftProposal ? proposalStatusLabel(draftProposal.status) : draftWorkbenchEmptyText"
        :visual-lines="draftVisualLines"
        :scroll-top="draftEditorScrollTop"
        :line-height="draftEditorLineHeight"
        :cursor-line="currentDraftCursorLine"
        :selection-label="currentSelectionReferenceLabel"
        :attached-label="attachedChatSelectionLabel"
        @previous="goPreviousStage"
        @next="goNextStage"
        @save="saveDraftToServer"
        @export="exportCurrentPlan"
        @preview="openDraftReviewOverlay"
        @editor-ready="draftEditorRef = $event"
        @editor-input="onDraftEditorInput"
        @editor-scroll="syncDraftEditorScroll"
        @capture-selection="captureDraftSelection"
        @add-selection="addSelectionToChat"
        @clear-selection="clearDraftSelection"
      />
      <KnowledgeGraphPanel
        v-if="hasKnowledgeGraphContext && showGraphInRightPanel"
        :graph="knowledgeGraph"
        :selected-entity-ids="selectedGraphEntityIds"
        :selected-relation-ids="selectedGraphRelationIds"
        :loading="isLoadingKnowledgeGraph"
        :streaming="isStreaming"
        :agent-name="activeGraphExpert?.name || ''"
        :query="lastGraphQuery"
        :error="knowledgeGraphError"
        :progress="knowledgeGraphProgress"
        @close="showGraphInRightPanel = false"
        @refresh="openKnowledgeGraphPanel"
        @toggle-node="toggleGraphEntity"
        @toggle-relation="toggleGraphRelation"
        @select-path="selectGraphPath"
        @answer="sendGraphSelectedChat"
      />
    </div>

    <DraftReviewOverlay
      :visible="showDraftReviewOverlay"
      :proposal="draftProposal"
      :description="draftProposalDescription || '这里展示当前草案解析后的 Markdown 效果。'"
      :segments="visibleDraftSegments"
      :active-segment-id="activeReviewSegmentId"
      :blocks="reviewPreviewBlocks"
      :active-block-id="activePreviewBlockId"
      :render="renderMarkdown"
      :proposal-status-label="proposalStatusLabel"
      :segment-status-label="segmentStatusLabel"
      :segment-label="draftSegmentLabel"
      :segment-summary="reviewSegmentSummary"
      @close="closeDraftReviewOverlay"
      @apply-all="applyAllDraftProposalActions"
      @apply="(id, action) => applyDraftProposalAction(id, action)"
      @select-segment="selectReviewSegment"
      @preview-ready="reviewPreviewRef = $event"
    />
    <div
      v-if="showDraftReviewOverlay"
      class="draft-review-overlay legacy-hidden"
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

    <CurriculumModal
      ref="curriculumModalRef"
      :visible="showCurriculumModal"
      :admin="Boolean(currentUser?.is_admin)"
      :files="curriculumFiles"
      :total-chunks="curriculumTotalChunks"
      :status="curriculumStatus"
      :status-label="curriculumStatusLabel"
      :operation="curriculumAdminOperation"
      :loading="isLoadingCurriculum"
      :loading-admin="isLoadingCurriculumAdmin"
      :uploading="isUploadingCurriculum"
      :upload-category="knowledgeUploadCategory"
      :error="curriculumError"
      :upload-results="curriculumUploadResults"
      :experts="experts"
      :editing-source="permissionEditingSource"
      :permission-draft="permissionDraftExpertIds"
      :saving-source="savingPermissionSource"
      :deleting-sources="deletingCurriculumSources"
      :retrievals="curriculumRetrievals"
      :format-date="formatCurriculumDate"
      :vector-label="curriculumFileVectorLabel"
      :expert-name="expertName"
      :mode-label="retrievalModeLabel"
      :score="formatScore"
      @close="showCurriculumModal = false"
      @rebuild="handleRebuildCurriculumVectors"
      @export="handleExportCurriculum"
      @import="openCurriculumBundlePicker"
      @bundle-selected="handleCurriculumBundleSelection"
      @pick-files="openCurriculumFilePicker"
      @drop-files="handleCurriculumDrop"
      @files-selected="handleCurriculumFileSelection"
      @update:upload-category="knowledgeUploadCategory = $event"
      @toggle-permission="togglePermissionExpert"
      @save-permissions="saveCurriculumPermissions"
      @cancel-permissions="closePermissionEditor"
      @edit-permissions="openPermissionEditor"
      @delete-file="removeCurriculumSource"
      @refresh-admin="refreshCurriculumAdminData"
      @save-metadata="saveKnowledgeMetadata"
      @review-source="handleKnowledgeReview"
      @refresh-files="refreshCurriculumFiles"
    />
    <KnowledgeGraphAdminModal
      v-if="showGraphAdminModal"
      :graph="graphAdminData"
      :files="curriculumFiles"
      @close="showGraphAdminModal = false"
      @refresh="refreshGraphAdmin"
    />
    <div v-if="showCurriculumModal" class="modal-overlay legacy-hidden" @click.self="showCurriculumModal = false">
      <section class="modal-content curriculum-modal glass" role="dialog" aria-modal="true" aria-labelledby="curriculum-title">
        <div class="curriculum-modal-head">
          <div>
            <h3 id="curriculum-title">课标知识库</h3>
            <p>{{ currentUser?.is_admin ? "管理员管理" : "只读查看" }} · {{ curriculumFiles.length }} 个文件 · {{ curriculumTotalChunks }} 个片段</p>
          </div>
          <button class="icon-button compact" type="button" title="关闭" aria-label="关闭课标知识库" @click="showCurriculumModal = false">
            <X :size="18" />
          </button>
        </div>

        <div v-if="currentUser?.is_admin" class="curriculum-vector-panel">
          <div class="curriculum-vector-summary">
            <Database :size="20" />
            <div>
              <strong>{{ curriculumStatusLabel }}</strong>
              <span v-if="curriculumStatus">
                {{ curriculumStatus.model }} · {{ curriculumStatus.vector_count }}/{{ curriculumStatus.database_chunk_count }} 个向量
              </span>
              <span v-else>正在读取向量服务状态</span>
              <small v-if="curriculumStatus?.error" :title="curriculumStatus.error">{{ curriculumStatus.error }}</small>
            </div>
          </div>
          <div class="curriculum-admin-actions">
            <button
              class="ghost-button compact"
              type="button"
              :disabled="Boolean(curriculumAdminOperation) || isLoadingCurriculumAdmin"
              @click="handleRebuildCurriculumVectors"
            >
              <LoaderCircle v-if="curriculumAdminOperation === 'rebuild'" class="spin-icon" :size="15" />
              <RefreshCw v-else :size="15" />
              重建索引
            </button>
            <button
              class="ghost-button compact"
              type="button"
              :disabled="Boolean(curriculumAdminOperation)"
              @click="() => handleExportCurriculum()"
            >
              <LoaderCircle v-if="curriculumAdminOperation === 'export'" class="spin-icon" :size="15" />
              <Download v-else :size="15" />
              导出知识库
            </button>
            <button
              class="ghost-button compact"
              type="button"
              :disabled="Boolean(curriculumAdminOperation)"
              @click="curriculumBundleInputRef?.click()"
            >
              <LoaderCircle v-if="curriculumAdminOperation === 'import'" class="spin-icon" :size="15" />
              <Upload v-else :size="15" />
              导入知识库
            </button>
          </div>
          <input
            ref="curriculumBundleInputRef"
            class="visually-hidden"
            type="file"
            accept=".zip,application/zip"
            @change="handleCurriculumBundleSelection"
          />
        </div>

        <button
          v-if="currentUser?.is_admin"
          class="curriculum-dropzone"
          type="button"
          :disabled="isUploadingCurriculum"
          @click="openCurriculumFilePicker"
          @dragover.prevent
          @drop.prevent="handleCurriculumDrop"
        >
          <LoaderCircle v-if="isUploadingCurriculum" class="spin-icon" :size="22" />
          <Upload v-else :size="22" />
          <strong>{{ isUploadingCurriculum ? "正在导入课标" : "上传课标" }}</strong>
          <span>PDF / DOCX / TXT / MD，单文件最大 20 MB</span>
        </button>
        <input
          v-if="currentUser?.is_admin"
          ref="curriculumFileInputRef"
          class="visually-hidden"
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
          @change="handleCurriculumFileSelection"
        />

        <div v-if="curriculumUploadResults.length" class="curriculum-upload-results" aria-live="polite">
          <span
            v-for="result in curriculumUploadResults"
            :key="result.name"
            :class="`status-${result.status}`"
            :title="result.message"
          >
            {{ result.name }} · {{ result.status === "pending" ? "等待" : result.status === "success" ? "完成" : "失败" }}
          </span>
        </div>
        <p v-if="curriculumError" class="curriculum-error" role="alert">{{ curriculumError }}</p>

        <div v-if="isLoadingCurriculum" class="curriculum-empty">
          <LoaderCircle class="spin-icon" :size="20" />
          <span>正在读取课标列表</span>
        </div>
        <div v-else-if="curriculumFiles.length" class="curriculum-file-list">
          <div v-for="item in curriculumFiles" :key="item.source" class="curriculum-file-row">
            <div class="curriculum-file-icon" aria-hidden="true"><FileText :size="20" /></div>
            <div class="curriculum-file-copy">
              <strong :title="item.source">{{ item.source }}</strong>
              <span>{{ item.extension.replace('.', '').toUpperCase() }} · {{ item.chunk_count }} 个片段 · {{ formatCurriculumDate(item.updated_at) }}</span>
              <small :class="`vector-status-${item.vector_status}`" :title="item.last_error">
                {{ curriculumFileVectorLabel(item) }}
              </small>
              <div class="curriculum-permission-tags">
                <span v-if="!item.allowed_expert_ids.length" class="permission-unassigned">尚未授权专家</span>
                <span v-for="expertId in item.allowed_expert_ids" :key="expertId" class="permission-tag">
                  {{ expertName(expertId) }}
                </span>
              </div>
              <div v-if="permissionEditingSource === item.source" class="curriculum-permission-editor">
                <label v-for="expert in experts" :key="expert.id">
                  <input v-model="permissionDraftExpertIds" type="checkbox" :value="expert.id" />
                  <span>{{ expert.name }} · {{ expert.role }}</span>
                </label>
                <div class="curriculum-permission-actions">
                  <button class="primary-button compact" type="button" :disabled="savingPermissionSource === item.source" @click="saveCurriculumPermissions(item)">
                    {{ savingPermissionSource === item.source ? "保存中" : "保存权限" }}
                  </button>
                  <button class="ghost-button compact" type="button" :disabled="savingPermissionSource === item.source" @click="closePermissionEditor">取消</button>
                </div>
              </div>
            </div>
            <button
              v-if="currentUser?.is_admin"
              class="ghost-button compact"
              type="button"
              :disabled="isUploadingCurriculum"
              @click="openPermissionEditor(item)"
            >
              配置权限
            </button>
            <button
              v-if="currentUser?.is_admin"
              class="reference-delete-button"
              type="button"
              :disabled="deletingCurriculumSources.includes(item.source) || isUploadingCurriculum"
              :title="`删除 ${item.source}`"
              :aria-label="`删除 ${item.source}`"
              @click="removeCurriculumSource(item)"
            >
              <LoaderCircle v-if="deletingCurriculumSources.includes(item.source)" class="spin-icon" :size="14" />
              <X v-else :size="18" />
            </button>
          </div>
        </div>
        <div v-else class="curriculum-empty">
          <BookOpen :size="24" />
          <span>当前还没有导入课标</span>
        </div>

        <section v-if="currentUser?.is_admin" class="curriculum-retrieval-section">
          <div class="curriculum-section-head">
            <div>
              <History :size="18" />
              <strong>最近召回</strong>
            </div>
            <button
              class="icon-button compact"
              type="button"
              title="刷新召回记录"
              aria-label="刷新召回记录"
              :disabled="isLoadingCurriculumAdmin"
              @click="refreshCurriculumAdminData"
            >
              <RefreshCw :size="15" />
            </button>
          </div>
          <div v-if="curriculumRetrievals.length" class="curriculum-retrieval-list">
            <details v-for="record in curriculumRetrievals" :key="record.id" class="curriculum-retrieval-row">
              <summary>
                <span>{{ record.query || '空查询' }}</span>
                <small>{{ retrievalModeLabel(record.mode) }} · {{ formatCurriculumDate(record.created_at) }}</small>
              </summary>
              <p v-if="record.vector_error" class="curriculum-retrieval-warning">{{ record.vector_error }}</p>
              <div v-if="record.records.length" class="curriculum-hit-list">
                <article v-for="hit in record.records" :key="`${record.id}-${hit.chunk_id}`">
                  <strong>{{ hit.source }} · 片段 {{ hit.source_index }}</strong>
                  <span>综合 {{ formatScore(hit.score) }} · 余弦相似度 {{ formatScore(hit.vector_score) }} · BM25 原始分 {{ formatScore(hit.bm25_score) }}</span>
                  <p>{{ hit.content }}</p>
                </article>
              </div>
              <p v-else class="curriculum-retrieval-warning">本次没有命中课标片段。</p>
            </details>
          </div>
          <div v-else class="curriculum-retrieval-empty">当前还没有课标召回记录</div>
        </section>
      </section>
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
          <select v-model="newSessionFlowName" class="input">
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
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import AuthPanel from "@/components/AuthPanel.vue";
import AppHeader from "@/components/AppHeader.vue";
import ChatComposer from "@/components/ChatComposer.vue";
import ConversationPanel from "@/components/ConversationPanel.vue";
import CurriculumModal from "@/components/CurriculumModal.vue";
import DocumentWorkbench from "@/components/DocumentWorkbench.vue";
import DraftReviewOverlay from "@/components/DraftReviewOverlay.vue";
import KnowledgeGraphPanel from "@/components/KnowledgeGraphPanel.vue";
import KnowledgeGraphAdminModal from "@/components/KnowledgeGraphAdminModal.vue";
import WorkspaceSidebar from "@/components/WorkspaceSidebar.vue";
import { BookOpen, Database, Download, FileText, History, LoaderCircle, RefreshCw, Upload, X } from "lucide-vue-next";
import {
  createSession,
  deleteKnowledgeSource,
  downloadKnowledgeBundle,
  deleteSession,
  deleteSessionFile,
  applyDraftProposalActions,
  cancelChat,
  getDraftProposal,
  getExperts,
  getCurrentUser,
  getKnowledgeSources,
  getCurriculumRetrievals,
  getCurriculumStatus,
  streamKnowledgeGraphCandidates,
  getKnowledgeGraphAdmin,
  exportSession,
  getFlows,
  getMessages,
  getSession,
  getSessionFiles,
  getSessions,
  logoutUser,
  importKnowledgeBundle,
  rebuildCurriculumVectors,
  rollbackSession,
  saveDraft,
  setDraftMode,
  streamChat,
  updateCurriculumPermissions,
  updateKnowledgeSource,
  reviewKnowledgeSource,
  uploadKnowledgeSource,
  uploadSessionFile,
} from "@/api";
import type {
  AuthUser,
  CurriculumFileItem,
  CurriculumRetrievalRecord,
  CurriculumVectorStatus,
  DraftProposal,
  DraftSelection,
  DraftProposalSegment,
  ExpertAgentItem,
  FlowInfo,
  FlowStage,
  GraphSelectionPayload,
  GraphProgressState,
  KnowledgeGraphPayload,
  MessageItem,
  SessionDetail,
  SessionFileItem,
  SessionListItem,
} from "@/types";
import { renderMarkdown } from "@/utils/markdown";

const flows = ref<FlowInfo[]>([]);
const currentUser = ref<AuthUser | null>(null);
const authLoading = ref(true);
const sessions = ref<SessionListItem[]>([]);
const currentSession = ref<SessionDetail | null>(null);
const messages = ref<MessageItem[]>([]);
const newSessionFlowName = ref("inquiry_7_stage");
const sessionFiles = ref<SessionFileItem[]>([]);
const curriculumFiles = ref<CurriculumFileItem[]>([]);
const curriculumStatus = ref<CurriculumVectorStatus | null>(null);
const curriculumRetrievals = ref<CurriculumRetrievalRecord[]>([]);
const experts = ref<ExpertAgentItem[]>([]);
const selectedExpertId = ref("");
const permissionEditingSource = ref("");
const permissionDraftExpertIds = ref<string[]>([]);
const savingPermissionSource = ref("");
const selectedSessionId = ref("");
const sessionSearchQuery = ref("");
const selectedStageId = ref("");
const topicInput = ref("光的反射");
const chatInput = ref("");
const draftContent = ref("");
const draftProposal = ref<DraftProposal | null>(null);
const draftStreamingContent = ref("");
const statusText = ref("准备就绪");
const streamWarning = ref("");
const isStreaming = ref(false);
const activeStreamRequestId = ref<string | null>(null);
const activeStreamAbortController = ref<AbortController | null>(null);
const interruptRequested = ref(false);
const themeMode = ref<"dark" | "light">("light");
const saveSuccessVisible = ref(false);
const workflowPhase = ref<"idle" | "guide" | "draft" | "expert">("idle");
const workflowStatusText = ref("准备就绪");
const leftSidebarVisible = ref(true);
const rightSidebarVisible = ref(true);
const feedRef = ref<HTMLElement | null>(null);
const chatInputRef = ref<HTMLTextAreaElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const curriculumFileInputRef = ref<HTMLInputElement | null>(null);
const curriculumBundleInputRef = ref<HTMLInputElement | null>(null);
const curriculumModalRef = ref<any>(null);
const draftEditorRef = ref<HTMLTextAreaElement | null>(null);
const reviewPreviewRef = ref<HTMLElement | null>(null);
const showDraftReviewOverlay = ref(false);
const activeReviewSegmentId = ref<string | null>(null);
const expandedReviewSegmentIds = ref<string[]>([]);
const draftWorkbenchState = ref<"idle" | "generate_streaming" | "edit_streaming" | "proposal_review" | "save_ready">("idle");
const lastDraftSelection = ref<DraftSelection | null>(null);
const attachedChatSelection = ref<DraftSelection | null>(null);
const attachedChatSelectionLabel = ref("");
const isUploadingFile = ref(false);
const deletingFileIds = ref<string[]>([]);
const fileOperationError = ref("");
const showCurriculumModal = ref(false);
const isLoadingCurriculum = ref(false);
const isUploadingCurriculum = ref(false);
const knowledgeUploadCategory = ref<"curriculum" | "ecology" | "rural_revitalization">("curriculum");
const isLoadingCurriculumAdmin = ref(false);
const curriculumAdminOperation = ref<
  "" | "rebuild" | "export" | "import" | `metadata:${string}` | `review:${string}`
>("");
const deletingCurriculumSources = ref<string[]>([]);
const curriculumError = ref("");
const curriculumUploadResults = ref<Array<{
  name: string;
  status: "pending" | "success" | "failed";
  message: string;
}>>([]);
const showKnowledgeGraphPanel = ref(false);
const showGraphInRightPanel = ref(false);
const showGraphAdminModal = ref(false);
const graphAdminData = ref<KnowledgeGraphPayload>({
  entities: [],
  relations: [],
  paths: [],
  recommended_path_ids: [],
});
const isLoadingKnowledgeGraph = ref(false);
const knowledgeGraphError = ref("");
const knowledgeGraphProgress = ref<GraphProgressState>({
  phase: "idle",
  percent: 0,
  message: "等待查询",
});
const knowledgeGraph = ref<KnowledgeGraphPayload>({
  entities: [],
  relations: [],
  paths: [],
  recommended_path_ids: [],
});
const selectedGraphEntityIds = ref<string[]>([]);
const selectedGraphRelationIds = ref<string[]>([]);
const lastGraphQuery = ref("");
const lastGraphExpertId = ref("");
const graphContextSessionId = ref("");
let knowledgeGraphRequestSequence = 0;
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

function isKnowledgeGraphExpert(expertId: string): boolean {
  return expertId === "insect_agent" || expertId === "nature_agent";
}

function clearKnowledgeGraphPayload() {
  knowledgeGraph.value = {
    entities: [],
    relations: [],
    paths: [],
    recommended_path_ids: [],
  };
  selectedGraphEntityIds.value = [];
  selectedGraphRelationIds.value = [];
}

function resetKnowledgeGraphState() {
  knowledgeGraphRequestSequence += 1;
  showKnowledgeGraphPanel.value = false;
  isLoadingKnowledgeGraph.value = false;
  knowledgeGraphError.value = "";
  knowledgeGraphProgress.value = { phase: "idle", percent: 0, message: "等待查询" };
  clearKnowledgeGraphPayload();
  lastGraphQuery.value = "";
  lastGraphExpertId.value = "";
  graphContextSessionId.value = "";
}

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
    return flows.value.find((item) => item.name === newSessionFlowName.value)?.stages || [];
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
const selectedExpert = computed(() =>
  experts.value.find((expert) => expert.id === selectedExpertId.value) || null,
);
const isSelectedGraphExpert = computed(() =>
  isKnowledgeGraphExpert(selectedExpertId.value),
);
const activeGraphExpert = computed(() =>
  experts.value.find((expert) => expert.id === lastGraphExpertId.value) || null,
);
const hasKnowledgeGraphContext = computed(() =>
  Boolean(
    currentSession.value
    && graphContextSessionId.value === currentSession.value.id
    && (lastGraphExpertId.value || isSelectedGraphExpert.value),
  ),
);
const curriculumTotalChunks = computed(() =>
  curriculumFiles.value.reduce((total, item) => total + item.chunk_count, 0),
);
const curriculumStatusLabel = computed(() => {
  const status = curriculumStatus.value;
  if (!status) return "正在检查向量检索";
  if (!status.enabled) return "仅使用 BM25 检索";
  if (status.rebuild_required) return "向量索引需要重建";
  if (status.available) return "混合检索可用";
  return "向量不可用，已降级 BM25";
});

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
  const [flowList, sessionList, expertList] = await Promise.all([
    getFlows(),
    getSessions(),
    getExperts(),
  ]);
  flows.value = flowList;
  sessions.value = sessionList;
  experts.value = expertList;
  if (!newSessionFlowName.value && flowList[0]) {
    newSessionFlowName.value = flowList[0].name;
  }
  statusText.value = "工作区已刷新";
}

async function handleAuthenticated(user: AuthUser) {
  currentUser.value = user;
  await Promise.all([refreshWorkspace(), refreshCurriculumFiles()]);
  if (sessions.value[0]) {
    await loadSession(sessions.value[0].id, true);
  }
}

async function logout() {
  if (isStreaming.value) {
    return;
  }
  try {
    await logoutUser();
  } finally {
    currentUser.value = null;
    sessions.value = [];
    currentSession.value = null;
    selectedSessionId.value = "";
    selectedStageId.value = "";
    messages.value = [];
    curriculumFiles.value = [];
    curriculumStatus.value = null;
    curriculumRetrievals.value = [];
    experts.value = [];
    selectedExpertId.value = "";
    showCurriculumModal.value = false;
    resetKnowledgeGraphState();
    draftContent.value = "";
    draftProposal.value = null;
    draftStreamingContent.value = "";
    statusText.value = "已退出登录";
  }
}

function restoreKnowledgeGraphContextFromMessages(sessionId: string, history: MessageItem[]): boolean {
  for (let assistantIndex = history.length - 1; assistantIndex >= 0; assistantIndex -= 1) {
    const assistant = history[assistantIndex];
    if (assistant.role !== "assistant" || !isKnowledgeGraphExpert(assistant.agent_id || "")) continue;
    for (let userIndex = assistantIndex - 1; userIndex >= 0; userIndex -= 1) {
      const userMessage = history[userIndex];
      if (userMessage.role !== "user" || !userMessage.content.trim()) continue;
      graphContextSessionId.value = sessionId;
      lastGraphExpertId.value = assistant.agent_id || "";
      lastGraphQuery.value = userMessage.content.trim();
      showGraphInRightPanel.value = true;
      return true;
    }
  }
  return false;
}

async function loadSession(
  sessionId: string,
  loadMessages = true,
  preserveWarning = false,
  preserveGraphContext = false,
) {
  const keepGraphContext = graphContextSessionId.value === sessionId
    && (preserveGraphContext || !loadMessages);
  const [session, files] = await Promise.all([
    getSession(sessionId),
    getSessionFiles(sessionId),
  ]);
  if (!preserveWarning) {
    streamWarning.value = "";
  }
  currentSession.value = session;
  sessionFiles.value = files;
  fileOperationError.value = "";
  selectedSessionId.value = session.id;
  selectedExpertId.value = "";
  selectedStageId.value = pickStageIdFromSession(session);
  if (!keepGraphContext) resetKnowledgeGraphState();
  if (loadMessages) {
    messages.value = await getMessages(sessionId);
  }
  const restoredGraphContext = !keepGraphContext
    && loadMessages
    && restoreKnowledgeGraphContextFromMessages(sessionId, messages.value);
  clearAttachedChatSelection(true);
  syncDraftFromSelection();
  draftStreamingContent.value = "";
  await nextTick();
  syncDraftEditor();
  updateDraftCursorLine();
  await refreshDraftProposal();
  if (restoredGraphContext) {
    await refreshKnowledgeGraph(lastGraphQuery.value, lastGraphExpertId.value, sessionId);
  }
  statusText.value = `已切换到 ${session.topic}`;
}

async function selectSession(sessionId: string) {
  await loadSession(sessionId, true);
}

function openFilePicker() {
  if (isStreaming.value || isUploadingFile.value || !currentSession.value) {
    return;
  }
  fileInputRef.value?.click();
}

async function refreshCurriculumFiles() {
  isLoadingCurriculum.value = true;
  curriculumError.value = "";
  try {
    curriculumFiles.value = await getKnowledgeSources();
  } catch (error: any) {
    curriculumError.value = error.message || String(error);
  } finally {
    isLoadingCurriculum.value = false;
  }
}

function expertName(expertId: string): string {
  return experts.value.find((expert) => expert.id === expertId)?.name || expertId;
}

function openPermissionEditor(item: CurriculumFileItem) {
  permissionEditingSource.value = item.source;
  permissionDraftExpertIds.value = [...item.allowed_expert_ids];
  curriculumError.value = "";
}

function togglePermissionExpert(expertId: string) {
  permissionDraftExpertIds.value = permissionDraftExpertIds.value.includes(expertId)
    ? permissionDraftExpertIds.value.filter((item) => item !== expertId)
    : [...permissionDraftExpertIds.value, expertId];
}

function closePermissionEditor() {
  if (savingPermissionSource.value) return;
  permissionEditingSource.value = "";
  permissionDraftExpertIds.value = [];
}

async function saveCurriculumPermissions(item: CurriculumFileItem) {
  if (!currentUser.value?.is_admin || savingPermissionSource.value) return;
  savingPermissionSource.value = item.source;
  curriculumError.value = "";
  try {
    const updated = await updateCurriculumPermissions(
      item.source,
      permissionDraftExpertIds.value,
    );
    item.allowed_expert_ids = [...updated.allowed_expert_ids];
    closePermissionEditor();
    statusText.value = updated.allowed_expert_ids.length
      ? `已更新 ${item.source} 的专家权限`
      : `${item.source} 已设为未授权`;
  } catch (error: any) {
    curriculumError.value = error.message || String(error);
  } finally {
    savingPermissionSource.value = "";
    permissionEditingSource.value = "";
    permissionDraftExpertIds.value = [];
  }
}

async function refreshCurriculumAdminData() {
  if (!currentUser.value?.is_admin) return;
  isLoadingCurriculumAdmin.value = true;
  const [statusResult, retrievalResult] = await Promise.allSettled([
    getCurriculumStatus(),
    getCurriculumRetrievals(20),
  ]);
  if (statusResult.status === "fulfilled") {
    curriculumStatus.value = statusResult.value;
  } else {
    curriculumError.value = statusResult.reason?.message || String(statusResult.reason);
  }
  if (retrievalResult.status === "fulfilled") {
    curriculumRetrievals.value = retrievalResult.value;
  } else if (!curriculumError.value) {
    curriculumError.value = retrievalResult.reason?.message || String(retrievalResult.reason);
  }
  isLoadingCurriculumAdmin.value = false;
}

async function openCurriculumPanel() {
  showCurriculumModal.value = true;
  curriculumUploadResults.value = [];
  await Promise.all([refreshCurriculumFiles(), refreshCurriculumAdminData()]);
}

function openCurriculumFilePicker() {
  if (!currentUser.value?.is_admin || isUploadingCurriculum.value) {
    return;
  }
  if (curriculumModalRef.value?.openFilePicker) {
    curriculumModalRef.value.openFilePicker();
    return;
  }
  curriculumFileInputRef.value?.click();
}

function openCurriculumBundlePicker() {
  if (!currentUser.value?.is_admin || curriculumAdminOperation.value) return;
  if (curriculumModalRef.value?.openBundlePicker) {
    curriculumModalRef.value.openBundlePicker();
    return;
  }
  curriculumBundleInputRef.value?.click();
}

async function importCurriculumFiles(files: File[]) {
  if (!currentUser.value?.is_admin || !files.length || isUploadingCurriculum.value) {
    return;
  }
  isUploadingCurriculum.value = true;
  curriculumError.value = "";
  curriculumUploadResults.value = files.map((file) => ({
    name: file.name,
    status: "pending",
    message: "",
  }));
  const errors: string[] = [];
  try {
    for (const file of files) {
      try {
        const uploaded = await uploadKnowledgeSource(file, knowledgeUploadCategory.value);
        curriculumFiles.value = [
          uploaded,
          ...curriculumFiles.value.filter((item) => item.source !== uploaded.source),
        ];
        if (knowledgeUploadCategory.value === "rural_revitalization") {
          await nextTick();
          curriculumModalRef.value?.openMetadataEditor?.(uploaded);
        }
        curriculumUploadResults.value = curriculumUploadResults.value.map((item) =>
          item.name === file.name ? { ...item, status: "success", message: "导入完成" } : item,
        );
      } catch (error: any) {
        const message = error.message || String(error);
        errors.push(`${file.name}：${message}`);
        curriculumUploadResults.value = curriculumUploadResults.value.map((item) =>
          item.name === file.name ? { ...item, status: "failed", message } : item,
        );
      }
    }
  } finally {
    isUploadingCurriculum.value = false;
  }
  curriculumError.value = errors.join("；");
  const categoryLabel = knowledgeUploadCategory.value === "ecology"
    ? "生态资料"
    : knowledgeUploadCategory.value === "rural_revitalization"
      ? "乡村振兴资料"
      : "课标文件";
  statusText.value = errors.length ? "部分知识资料导入失败" : `已导入 ${files.length} 个${categoryLabel}`;
  await refreshCurriculumAdminData();
}

async function handleCurriculumFileSelection(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = "";
  await importCurriculumFiles(files);
}

async function handleCurriculumDrop(event: DragEvent) {
  await importCurriculumFiles(Array.from(event.dataTransfer?.files || []));
}

async function removeCurriculumSource(item: CurriculumFileItem) {
  if (!currentUser.value?.is_admin || isUploadingCurriculum.value) {
    return;
  }
  if (!confirm(`确认删除知识文件《${item.source}》吗？删除后将不再参与检索。`)) {
    return;
  }
  deletingCurriculumSources.value = [...deletingCurriculumSources.value, item.source];
  curriculumError.value = "";
  try {
    await deleteKnowledgeSource(item.id);
    curriculumFiles.value = curriculumFiles.value.filter((file) => file.source !== item.source);
    statusText.value = `已删除知识文件：${item.source}`;
    await refreshCurriculumAdminData();
  } catch (error: any) {
    curriculumError.value = error.message || String(error);
  } finally {
    deletingCurriculumSources.value = deletingCurriculumSources.value.filter(
      (source) => source !== item.source,
    );
  }
}

async function handleRebuildCurriculumVectors() {
  if (!currentUser.value?.is_admin || curriculumAdminOperation.value) return;
  curriculumAdminOperation.value = "rebuild";
  curriculumError.value = "";
  try {
    curriculumStatus.value = await rebuildCurriculumVectors();
    await refreshCurriculumFiles();
    statusText.value = "知识库向量索引已重建";
  } catch (error: any) {
    curriculumError.value = error.message || String(error);
  } finally {
    curriculumAdminOperation.value = "";
  }
}

async function handleExportCurriculum(category?: string) {
  if (!currentUser.value?.is_admin || curriculumAdminOperation.value) return;
  const exportCategory = category === "curriculum"
    || category === "ecology"
    || category === "rural_revitalization"
    ? category
    : undefined;
  curriculumAdminOperation.value = "export";
  curriculumError.value = "";
  try {
    const blob = await downloadKnowledgeBundle(exportCategory);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = exportCategory
      ? `${exportCategory}-knowledge-v4.zip`
      : "all-knowledge-v4.zip";
    anchor.click();
    URL.revokeObjectURL(url);
    statusText.value = exportCategory === "ecology"
      ? "生态知识库已导出"
      : exportCategory === "curriculum"
        ? "课标知识库已导出"
        : exportCategory === "rural_revitalization"
          ? "乡村振兴知识库已导出"
          : "全部知识库已导出";
  } catch (error: any) {
    curriculumError.value = error.message || String(error);
  } finally {
    curriculumAdminOperation.value = "";
  }
}

async function handleCurriculumBundleSelection(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !currentUser.value?.is_admin || curriculumAdminOperation.value) return;
  if (!confirm("导入会替换知识包中的同名知识文件，其他文件保持不变。确认继续吗？")) return;
  curriculumAdminOperation.value = "import";
  curriculumError.value = "";
  try {
    const result = await importKnowledgeBundle(file);
    await Promise.all([refreshCurriculumFiles(), refreshCurriculumAdminData()]);
    statusText.value = `已导入 ${result.source_count} 个知识文件、${result.chunk_count} 个片段`;
  } catch (error: any) {
    curriculumError.value = error.message || String(error);
  } finally {
    curriculumAdminOperation.value = "";
  }
}

async function saveKnowledgeMetadata(
  item: CurriculumFileItem,
  metadata: Record<string, unknown>,
) {
  if (!currentUser.value?.is_admin) return;
  curriculumAdminOperation.value = `metadata:${item.id}`;
  curriculumError.value = "";
  try {
    const updated = await updateKnowledgeSource(item.id, metadata);
    curriculumFiles.value = curriculumFiles.value.map((source) =>
      source.id === updated.id ? updated : source,
    );
    statusText.value = `已保存政策元数据：${updated.title}`;
  } catch (error: any) {
    curriculumError.value = error.message || String(error);
  } finally {
    curriculumAdminOperation.value = "";
  }
}

async function handleKnowledgeReview(
  item: CurriculumFileItem,
  action: "submit" | "return" | "publish" | "archive",
  note = "",
) {
  if (!currentUser.value?.is_admin) return;
  curriculumAdminOperation.value = `review:${item.id}`;
  curriculumError.value = "";
  try {
    const updated = await reviewKnowledgeSource(item.id, action, note);
    curriculumFiles.value = curriculumFiles.value.map((source) =>
      source.id === updated.id ? updated : source,
    );
    statusText.value = `《${updated.title}》审核状态已更新`;
  } catch (error: any) {
    curriculumError.value = error.message || String(error);
  } finally {
    curriculumAdminOperation.value = "";
  }
}

function curriculumFileVectorLabel(item: CurriculumFileItem): string {
  if (item.vector_status === "ready") {
    return `已向量化 ${item.vector_chunk_count}/${item.chunk_count}`;
  }
  if (item.vector_status === "disabled") return "仅 BM25";
  if (item.vector_status === "error") return "向量化失败，使用 BM25";
  return "等待重建向量";
}

function retrievalModeLabel(mode: string): string {
  if (mode === "local_hybrid") return "混合检索";
  if (mode === "local_bm25_fallback") return "BM25 降级";
  if (mode.includes("empty")) return "未命中";
  return "BM25";
}

function formatScore(value: number): string {
  return Number.isFinite(value) ? value.toFixed(3) : "0.000";
}

function formatCurriculumDate(value: string) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function fileStatusLabel(item: SessionFileItem): string {
  if (item.status === "processing") return "正在解析";
  if (item.status === "failed") return "解析失败";
  return "文档";
}

async function handleFileSelection(event: Event) {
  const input = event.target as HTMLInputElement;
  const selectedFiles = Array.from(input.files || []);
  input.value = "";
  if (!currentSession.value || !selectedFiles.length || isStreaming.value) {
    return;
  }

  isUploadingFile.value = true;
  fileOperationError.value = "";
  const sessionId = currentSession.value.id;
  const errors: string[] = [];
  try {
    for (const selectedFile of selectedFiles) {
      try {
        const uploaded = await uploadSessionFile(sessionId, selectedFile);
        if (currentSession.value?.id === sessionId) {
          sessionFiles.value = [
            ...sessionFiles.value.filter((item) => item.id !== uploaded.id),
            uploaded,
          ];
        }
        if (uploaded.status === "failed") {
          errors.push(`${uploaded.name}：${uploaded.error_message || "解析失败"}`);
        }
      } catch (error: any) {
        errors.push(`${selectedFile.name}：${error.message || error}`);
      }
    }
  } finally {
    isUploadingFile.value = false;
  }
  fileOperationError.value = errors.join("；");
  statusText.value = errors.length
    ? `资料上传完成，${errors.length} 个文件未能使用`
    : `已上传 ${selectedFiles.length} 个参考资料`;
}

async function removeReferenceFile(item: SessionFileItem) {
  if (!currentSession.value || isStreaming.value) {
    return;
  }
  if (!confirm(`确认删除参考资料《${item.name}》吗？`)) {
    return;
  }

  const sessionId = currentSession.value.id;
  deletingFileIds.value = [...deletingFileIds.value, item.id];
  fileOperationError.value = "";
  try {
    await deleteSessionFile(sessionId, item.id);
    if (currentSession.value?.id === sessionId) {
      sessionFiles.value = sessionFiles.value.filter((file) => file.id !== item.id);
    }
    statusText.value = `已删除参考资料：${item.name}`;
  } catch (error: any) {
    fileOperationError.value = error.message || String(error);
    statusText.value = `删除资料失败：${fileOperationError.value}`;
  } finally {
    deletingFileIds.value = deletingFileIds.value.filter((id) => id !== item.id);
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
      sessionFiles.value = [];
      fileOperationError.value = "";
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
  const created = await createSession(topic, newSessionFlowName.value);
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
  if (message.message_type === "expert_advice") {
    return message.agent_name || expertName(message.agent_id || "") || "领域专家";
  }
  if (message.message_type === "stage_expert") {
    return message.agent_name || "历史阶段专家";
  }
  if (message.message_type === "main_tutor" || message.agent_id === "main_tutor" || message.agent_id === "main_agent") {
    return message.agent_name || "主导师 Agent";
  }
  if (message.message_type === "draft_tutor" || message.agent_id === "draft_agent") {
    return message.agent_name || "草案修订Agent";
  }
  return "导师";
}

function createPendingAssistantMessage(
  requestMode: "main" | "expert" | "draft",
  stageId: string,
  initialText: string,
): { key: string; message: MessageItem } {
  if (requestMode === "expert") {
    return {
      key: "expert_advice",
      message: {
        stage_id: stageId,
        role: "assistant",
        content: initialText,
        agent_id: selectedExpert.value?.id || null,
        agent_name: selectedExpert.value?.name || "领域专家",
        message_type: "expert_advice",
      },
    };
  }
  return {
    key: requestMode === "draft" ? "draft_status" : "main_tutor",
    message: {
      stage_id: stageId,
      role: "assistant",
      content: initialText,
      agent_id: "main_tutor",
      agent_name: "主导师 Agent",
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

function createStreamRequestId() {
  const randomId = globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2);
  return `chat_${Date.now()}_${randomId}`;
}

async function refreshKnowledgeGraph(query: string, expertId: string, sessionId: string) {
  const normalizedQuery = query.trim();
  if (!normalizedQuery || !expertId || !sessionId) {
    knowledgeGraphRequestSequence += 1;
    isLoadingKnowledgeGraph.value = false;
    knowledgeGraphError.value = "";
    clearKnowledgeGraphPayload();
    return;
  }
  const requestSequence = ++knowledgeGraphRequestSequence;
  isLoadingKnowledgeGraph.value = true;
  knowledgeGraphError.value = "";
  knowledgeGraphProgress.value = { phase: "starting", percent: 3, message: "正在准备图谱查询" };
  try {
    await streamKnowledgeGraphCandidates(sessionId, normalizedQuery, expertId, {
      graph_progress: (data) => {
        if (requestSequence !== knowledgeGraphRequestSequence) return;
        knowledgeGraphProgress.value = data as GraphProgressState;
      },
      graph: (data) => {
        if (
          requestSequence !== knowledgeGraphRequestSequence
          || graphContextSessionId.value !== sessionId
          || lastGraphQuery.value !== normalizedQuery
          || lastGraphExpertId.value !== expertId
        ) return;
        const graph = data.graph as KnowledgeGraphPayload | undefined;
        if (!graph) return;
        knowledgeGraph.value = graph;
        const recommendedPath = graph.paths.find((path) => graph.recommended_path_ids.includes(path.id));
        selectedGraphEntityIds.value = recommendedPath?.entity_ids?.length ? [...recommendedPath.entity_ids] : [];
        selectedGraphRelationIds.value = recommendedPath?.relation_ids?.length ? [...recommendedPath.relation_ids] : [];
        knowledgeGraphProgress.value = { phase: "complete", percent: 100, message: "图谱加载完成" };
      },
    });
  } catch (error: any) {
    if (requestSequence !== knowledgeGraphRequestSequence) return;
    clearKnowledgeGraphPayload();
    knowledgeGraphError.value = error.message || String(error);
    knowledgeGraphProgress.value = { phase: "failed", percent: 100, message: "图谱查询失败" };
  } finally {
    if (requestSequence === knowledgeGraphRequestSequence) {
      isLoadingKnowledgeGraph.value = false;
    }
  }
}

async function openKnowledgeGraphPanel() {
  if (!currentSession.value) return;
  if (isSelectedGraphExpert.value) {
    lastGraphExpertId.value = selectedExpertId.value;
    graphContextSessionId.value = currentSession.value.id;
  }
  if (!lastGraphExpertId.value) return;
  showGraphInRightPanel.value = true;
  await refreshKnowledgeGraph(
    lastGraphQuery.value,
    lastGraphExpertId.value,
    currentSession.value.id,
  );
}

async function openGraphAdmin() {
  if (!currentUser.value?.is_admin) return;
  try {
    graphAdminData.value = await getKnowledgeGraphAdmin();
    showGraphAdminModal.value = true;
  } catch (error: any) {
    streamWarning.value = error.message || String(error);
  }
}

async function refreshGraphAdmin() {
  if (!currentUser.value?.is_admin) return;
  try {
    graphAdminData.value = await getKnowledgeGraphAdmin();
    statusText.value = "知识图谱已更新";
  } catch (error: any) {
    streamWarning.value = error.message || String(error);
  }
}



function toggleGraphEntity(entityId: string) {
  const current = selectedGraphEntityIds.value;
  if (current.includes(entityId)) {
    selectedGraphEntityIds.value = current.filter((item) => item !== entityId);
    selectedGraphRelationIds.value = selectedGraphRelationIds.value.filter((relationId) => {
      const relation = knowledgeGraph.value.relations.find((item) => item.id === relationId);
      return relation && relation.subject_entity_id !== entityId && relation.object_entity_id !== entityId;
    });
    return;
  }
  selectedGraphEntityIds.value = [...current, entityId];
}

function toggleGraphRelation(relationId: string) {
  if (selectedGraphRelationIds.value.includes(relationId)) {
    selectedGraphRelationIds.value = selectedGraphRelationIds.value.filter((item) => item !== relationId);
    return;
  }
  const relation = knowledgeGraph.value.relations.find((item) => item.id === relationId);
  if (!relation) return;
  selectedGraphRelationIds.value = [...selectedGraphRelationIds.value, relationId];
  selectedGraphEntityIds.value = Array.from(new Set([
    ...selectedGraphEntityIds.value,
    relation.subject_entity_id,
    relation.object_entity_id,
  ]));
}

function selectGraphPath(pathId: string) {
  const path = knowledgeGraph.value.paths.find((item) => item.id === pathId);
  if (!path) return;
  selectedGraphEntityIds.value = [...path.entity_ids];
  selectedGraphRelationIds.value = [...path.relation_ids];
}

function buildGraphSelection(): GraphSelectionPayload {
  const selected = new Set(selectedGraphEntityIds.value);
  const relationIds = selectedGraphRelationIds.value.filter((relationId) => {
    const relation = knowledgeGraph.value.relations.find((item) => item.id === relationId);
    return relation && selected.has(relation.subject_entity_id) && selected.has(relation.object_entity_id);
  });
  const selectedRelations = new Set(relationIds);
  const pathIds = knowledgeGraph.value.paths
    .filter((path) => path.entity_ids.length > 0
      && path.entity_ids.every((entityId) => selected.has(entityId))
      && path.relation_ids.every((relationId) => selectedRelations.has(relationId)))
    .map((path) => path.id);
  return {
    entity_ids: [...selectedGraphEntityIds.value],
    relation_ids: relationIds,
    path_ids: pathIds,
    globi_query_id: knowledgeGraph.value.globi_runtime?.query_id || null,
  };
}

async function sendGraphSelectedChat() {
  if (!selectedGraphEntityIds.value.length) {
    statusText.value = "请先选择至少一个图谱节点";
    return;
  }
  if (!lastGraphQuery.value || !lastGraphExpertId.value) {
    statusText.value = "当前没有可重新回答的图谱问题";
    return;
  }
  await sendChat({
    graphSelection: buildGraphSelection(),
    message: lastGraphQuery.value,
    expertId: lastGraphExpertId.value,
  });
}

async function interruptChat() {
  if (!isStreaming.value || !currentSession.value || !activeStreamRequestId.value) {
    return;
  }
  const sessionId = currentSession.value.id;
  const requestId = activeStreamRequestId.value;
  interruptRequested.value = true;
  statusText.value = "正在停止生成，本轮内容不会保存...";
  activeStreamAbortController.value?.abort();
  try {
    await cancelChat(sessionId, requestId);
  } catch {
    // The browser abort itself also closes the SSE connection and lets the backend clean up.
  }
}

type SendChatOptions = {
  graphSelection?: GraphSelectionPayload | null;
  message?: string;
  expertId?: string;
};

async function sendChat(options: SendChatOptions = {}) {
  if (isStreaming.value) {
    return;
  }
  const text = (options.message ?? chatInput.value).trim();
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

  const requestedExpertId = options.expertId || selectedExpertId.value;
  const requestExpert = experts.value.find((expert) => expert.id === requestedExpertId) || null;
  const requestExpertId = requestExpert?.id || "";
  const graphSelection = options.graphSelection || null;
  const requestMode: "main" | "expert" | "draft" = requestExpertId
    ? "expert"
    : currentSession.value.draft_mode_enabled
      ? "draft"
      : "main";
  const draftRequestKind = requestMode === "draft" ? (draftContent.value.trim() ? "edit" : "generate") : undefined;
  const selectionPayload = attachedChatSelection.value?.selected_text?.trim() ? attachedChatSelection.value : null;
  const draftContentBeforeRequest = draftContent.value;
  const shouldStreamDraftIntoEditor =
    requestMode === "draft" && draftRequestKind === "generate" && !draftContentBeforeRequest.trim();

  if (requestMode === "draft" && draftRequestKind === "edit" && !selectionPayload) {
    statusText.value = "请先在右侧选中要修改的草案内容，再交给主导师编辑。";
    return;
  }

  const sessionId = currentSession.value.id;
  const requestId = createStreamRequestId();
  let graphRequestSequence = 0;
  const abortController = new AbortController();
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
  void nextTick(resizeChatInput);
  if (isKnowledgeGraphExpert(requestExpertId)) {
    graphRequestSequence = ++knowledgeGraphRequestSequence;
    graphContextSessionId.value = sessionId;
    lastGraphQuery.value = text;
    lastGraphExpertId.value = requestExpertId;
    showGraphInRightPanel.value = true;
    isLoadingKnowledgeGraph.value = true;
    knowledgeGraphError.value = "";
    knowledgeGraphProgress.value = { phase: "starting", percent: 3, message: "正在准备图谱查询" };
  }
  isStreaming.value = true;
  activeStreamRequestId.value = requestId;
  activeStreamAbortController.value = abortController;
  interruptRequested.value = false;
  streamWarning.value = "";
  draftStreamingContent.value = "";
  if (requestMode === "draft") {
    draftProposal.value = null;
  }
  clearAttachedChatSelection(false);
  statusText.value =
    requestMode === "draft"
      ? selectionPayload
        ? "主导师正在围绕您选中的内容整理草案..."
        : "主导师正在整理草案..."
      : requestMode === "expert"
        ? selectionPayload
          ? "正在请领域专家围绕您选中的内容提供建议..."
          : "正在等待领域专家分析..."
        : selectionPayload
          ? "正在请主导师围绕您选中的内容做引导..."
          : "正在等待主导师分析...";
  updateWorkflowStatus(requestMode === "draft" ? "draft" : requestMode === "expert" ? "expert" : "guide", statusText.value, "start");
  const streamMessages = new Map<string, MessageItem>();
  const placeholderTexts = new Map<string, string>();
  const markStreamMessagesInterrupted = () => {
    let changed = false;
    for (const message of streamMessages.values()) {
      if (message.role === "assistant" && !message.interrupted) {
        message.interrupted = true;
        changed = true;
      }
    }
    if (changed) {
      messages.value = [...messages.value];
    }
  };
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
        request_id: requestId,
        message: text,
        expert_id: requestExpertId || undefined,
        draft_request_kind: draftRequestKind,
        selection: selectionPayload,
        graph_selection: graphSelection,
      },
      {
        stage: () => {
          selectedStageId.value = currentSession.value?.current_stage?.id || selectedStageId.value;
        },
        graph: (data) => {
          if (
            graphRequestSequence !== knowledgeGraphRequestSequence
            || graphContextSessionId.value !== sessionId
            || lastGraphQuery.value !== text
            || lastGraphExpertId.value !== requestExpertId
          ) return;
          const graph = data.graph as KnowledgeGraphPayload | undefined;
          if (!graph) return;
          knowledgeGraph.value = graph;
          const recommendedPath = graph.paths.find((path) => graph.recommended_path_ids.includes(path.id));
          selectedGraphEntityIds.value = recommendedPath?.entity_ids?.length
            ? [...recommendedPath.entity_ids]
            : [];
          selectedGraphRelationIds.value = recommendedPath?.relation_ids?.length
            ? [...recommendedPath.relation_ids]
            : [];
          knowledgeGraphError.value = graph.entities.length
            ? ""
            : graph.globi_runtime?.status === "failed"
              ? graph.globi_runtime.warning
              : "";
          isLoadingKnowledgeGraph.value = false;
          knowledgeGraphProgress.value = { phase: "complete", percent: 100, message: "图谱加载完成" };
        },
        graph_progress: (data) => {
          if (
            graphRequestSequence !== knowledgeGraphRequestSequence
            || graphContextSessionId.value !== sessionId
            || lastGraphQuery.value !== text
            || lastGraphExpertId.value !== requestExpertId
          ) return;
          knowledgeGraphProgress.value = data as GraphProgressState;
          isLoadingKnowledgeGraph.value = data.phase !== "complete";
        },
        agent: (data) => {
          const targetKey =
            requestMode === "draft"
              ? "draft_status"
              : requestMode === "expert"
                ? "expert_advice"
                : "main_tutor";
          const pendingMessage = streamMessages.get(targetKey);
          if (pendingMessage) {
            pendingMessage.agent_id = data.agent_id || pendingMessage.agent_id || null;
            pendingMessage.agent_name = data.agent_name || pendingMessage.agent_name || null;
            pendingMessage.agent_role = data.agent_role || pendingMessage.agent_role || null;
            messages.value = [...messages.value];
          }
          if (requestMode === "draft") {
            statusText.value = `${data.agent_name || data.agent_id || "主导师 Agent"} 正在陪您一起整理草案`;
          } else if (requestMode === "expert") {
            statusText.value = `${data.agent_name || data.agent_id || "领域专家"} 正在回答`;
          } else {
            statusText.value = `${data.agent_name || data.agent_id || "主导师 Agent"} 正在回答`;
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
          assistantMessage.agent_role = data.agent_role || assistantMessage.agent_role || null;
          messages.value = [...messages.value];
          scrollFeedToBottom();
        },
        draft: (data) => {
          if (data.message_type === "main_tutor" || data.agent_id === "main_tutor") {
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
                agent_id: "main_tutor",
                agent_name: "主导师 Agent",
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
          if (data.warning_type === "graph_selection") {
            streamWarning.value = data.message || "您选择的图谱链路与当前问题关联较弱。";
            statusText.value = "图谱链路需要调整";
            return;
          }
          streamWarning.value = `${data.agent_name || "专家"}暂时不可用：${data.message || "请稍后重试"}`;
          statusText.value = "专家咨询暂时不可用";
        },
        interrupted: () => {
          interruptRequested.value = true;
          markStreamMessagesInterrupted();
          statusText.value = "已停止生成，本轮内容未保存";
          updateWorkflowStatus(requestMode === "draft" ? "draft" : requestMode === "expert" ? "expert" : "guide", statusText.value, "done");
        },
        done: async (data) => {
          if (graphRequestSequence === knowledgeGraphRequestSequence) {
            isLoadingKnowledgeGraph.value = false;
          }
          await loadSession(sessionId, true, true, true);
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
          } else if (requestMode === "expert") {
            statusText.value = `${requestExpert?.name || "专家"}回复完成`;
            updateWorkflowStatus("expert", statusText.value, "done");
          } else {
            statusText.value = data.degraded ? "主导师已在降级模式下完成回复" : "主导师回复完成";
            updateWorkflowStatus("guide", statusText.value, "done");
          }
        },
      },
    );
  } catch (err: any) {
    if (graphRequestSequence && graphRequestSequence === knowledgeGraphRequestSequence) {
      isLoadingKnowledgeGraph.value = false;
      knowledgeGraphError.value = err?.message || String(err);
      knowledgeGraphProgress.value = { phase: "failed", percent: 100, message: "图谱查询失败" };
    }
    if (shouldStreamDraftIntoEditor) {
      draftContent.value = draftContentBeforeRequest;
      draftStreamingContent.value = "";
      draftWorkbenchState.value = draftContentBeforeRequest.trim() ? "save_ready" : "idle";
    }
    if (interruptRequested.value || err?.name === "AbortError") {
      markStreamMessagesInterrupted();
      statusText.value = "已停止生成，本轮内容未保存";
      updateWorkflowStatus(requestMode === "draft" ? "draft" : requestMode === "expert" ? "expert" : "guide", statusText.value, "done");
    } else {
      statusText.value = `对话失败：${err.message || err}`;
      updateWorkflowStatus(requestMode === "draft" ? "draft" : requestMode === "expert" ? "expert" : "guide", statusText.value, "error");
    }
  } finally {
    isStreaming.value = false;
    activeStreamRequestId.value = null;
    activeStreamAbortController.value = null;
    interruptRequested.value = false;
    selectedExpertId.value = "";
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

function resizeChatInput() {
  const input = chatInputRef.value;
  if (!input) {
    return;
  }
  const maxHeight = 200;
  input.style.height = "auto";
  const nextHeight = Math.min(Math.max(input.scrollHeight, 42), maxHeight);
  input.style.height = `${nextHeight}px`;
  input.style.overflowY = input.scrollHeight > maxHeight ? "auto" : "hidden";
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
  try {
    const user = await getCurrentUser();
    await handleAuthenticated(user);
  } catch {
    currentUser.value = null;
  } finally {
    authLoading.value = false;
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
  activeStreamAbortController.value?.abort();
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

watch(selectedExpertId, (newExpertId) => {
  if (isKnowledgeGraphExpert(newExpertId)) {
    if (currentSession.value) {
      graphContextSessionId.value = currentSession.value.id;
      lastGraphExpertId.value = newExpertId;
    }
    showGraphInRightPanel.value = true;
    if (currentSession.value && lastGraphQuery.value) {
      void refreshKnowledgeGraph(lastGraphQuery.value, newExpertId, currentSession.value.id);
    }
  } else if (newExpertId) {
    showGraphInRightPanel.value = false;
  }
});
</script>
