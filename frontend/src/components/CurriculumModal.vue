<template>
  <div v-if="visible" class="knowledge-admin-overlay" @click.self="$emit('close')">
    <section v-if="admin" class="knowledge-admin-workbench" :class="{ 'has-error': Boolean(error) }" role="dialog" aria-modal="true" aria-labelledby="knowledge-admin-title" tabindex="-1" @keydown.esc="handleEscape">
      <header class="knowledge-admin-header">
        <div class="knowledge-admin-heading">
          <p class="section-kicker">统一知识基础设施</p>
          <h1 id="knowledge-admin-title">知识库管理</h1>
          <span>{{ files.length }} 个来源 · {{ totalChunks }} 个片段</span>
        </div>
        <label class="knowledge-admin-global-search">
          <Search :size="17" /><input v-model.trim="searchQuery" aria-label="搜索知识资料" placeholder="搜索标题、文件名、发文机关或文号" @keyup.enter="activeView = 'sources'" />
          <button v-if="searchQuery" type="button" aria-label="清除搜索" @click="searchQuery = ''"><X :size="14" /></button>
        </label>
        <div class="knowledge-admin-header-actions">
          <button class="primary" type="button" :disabled="uploading" @click="openUploadPanel"><Plus :size="16" />上传资料</button>
          <details class="knowledge-admin-transfer-menu">
            <summary><PackageOpen :size="16" />导入与导出<ChevronDown :size="14" /></summary>
            <div>
              <button type="button" :disabled="Boolean(operation)" @click="$emit('import')"><Upload :size="15" />导入知识包</button>
              <strong>导出知识包</strong>
              <button v-for="option in exportOptions" :key="option.value" type="button" :disabled="Boolean(operation)" @click="$emit('export', option.value)"><Download :size="15" />{{ option.label }}</button>
            </div>
          </details>
          <button class="icon" type="button" aria-label="关闭知识库" title="关闭" @click="$emit('close')"><X :size="19" /></button>
        </div>
        <input ref="bundleInput" class="visually-hidden" type="file" accept=".zip,application/zip" @change="$emit('bundle-selected', $event)" />
        <input ref="fileInput" class="visually-hidden" type="file" multiple accept=".pdf,.docx,.txt,.md" @change="$emit('files-selected', $event)" />
      </header>

      <nav class="knowledge-admin-nav" aria-label="知识库管理栏目">
        <button v-for="view in views" :key="view.value" type="button" :class="{ active: activeView === view.value }" @click="activeView = view.value">
          <component :is="view.icon" :size="16" />{{ view.label }}
          <span v-if="view.value === 'sources'">{{ filteredFiles.length }}</span>
          <span v-if="view.value === 'retrievals'">{{ retrievals.length }}</span>
        </button>
        <button class="refresh" type="button" :disabled="loadingAdmin" aria-label="刷新管理数据" title="刷新管理数据" @click="$emit('refresh-admin')"><RefreshCw :size="16" :class="{ 'spin-icon': loadingAdmin }" /></button>
      </nav>

      <div v-if="error" class="knowledge-admin-error-banner"><AlertCircle :size="17" /><span>{{ error }}</span><button type="button" @click="$emit('refresh-admin')">重试</button></div>

      <main class="knowledge-admin-main">
        <KnowledgeHealthOverview
          v-if="activeView === 'health'"
          :files="files" :total-chunks="totalChunks" :status="status" :status-label="statusLabel"
          :loading="loadingAdmin" :operation="operation"
          @rebuild="$emit('rebuild')" @refresh="$emit('refresh-admin')" @filter="applyHealthFilter" @open-source="openHealthSource"
        />

        <section v-else-if="activeView === 'sources'" class="knowledge-admin-sources">
          <div class="knowledge-admin-filter-bar">
            <div class="role-category-tabs">
              <button
                :class="{ active: selectedRoleCategory === 'teacher' }"
                @click="selectedRoleCategory = 'teacher'"
              >
                教师类知识库
              </button>
              <button
                :class="{ active: selectedRoleCategory === 'study_travel' }"
                @click="selectedRoleCategory = 'study_travel'"
              >
                研学类知识库
              </button>
            </div>
            <label><span>资料分类</span><select v-model="viewCategory"><option value="all">全部资料</option><option value="curriculum">课程与课标</option><option value="ecology">昆虫与植物生态</option><option value="rural_revitalization">乡村振兴</option></select></label>
            <label><span>审核状态</span><select v-model="reviewStatus"><option value="">全部状态</option><option value="draft">草稿</option><option value="in_review">审核中</option><option value="published">已发布</option><option value="archived">已归档</option></select></label>
            <button type="button" :class="{ active: advancedFilters }" @click="advancedFilters = !advancedFilters"><SlidersHorizontal :size="15" />高级筛选<span v-if="advancedFilterCount">{{ advancedFilterCount }}</span></button>
            <span class="knowledge-admin-result-count">显示 {{ filteredFiles.length }} / {{ files.length }}</span>
          </div>
          <div v-if="advancedFilters" class="knowledge-admin-advanced-filters">
            <label><span>四层归属</span><select v-model="policyLayer"><option value="">全部</option><option v-for="option in layerOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <label><span>地域</span><select v-model="authorityScope"><option value="">全部</option><option value="national">国家</option><option value="beijing">北京市</option><option value="district">区级</option></select></label>
            <label><span>效力</span><select v-model="validityStatus"><option value="">全部</option><option value="current">现行</option><option value="expired">已过期</option><option value="repealed">已废止</option><option value="unknown">待核验</option><option value="not_applicable">非规范性材料</option></select></label>
            <label><span>资料性质</span><select v-model="documentTypeFilter"><option value="">全部</option><option v-for="option in documentTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <label><span>主题</span><select v-model="topicFilter"><option value="">全部</option><option v-for="option in topicOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
          </div>
          <div v-if="activeFilterChips.length" class="knowledge-admin-filter-chips">
            <button v-for="chip in activeFilterChips" :key="chip.key" type="button" @click="clearFilter(chip.key)">{{ chip.label }}<X :size="12" /></button>
            <button class="clear" type="button" @click="resetFilters">清除全部</button>
          </div>
          <div class="knowledge-admin-source-layout" :class="{ 'drawer-open': drawerMode !== 'none' }">
            <KnowledgeSourceTable
              :files="filteredFiles" :selected-id="selectedId" :loading="loading" :format-date="formatDate" :vector-label="vectorLabel"
              :category-label="categoryLabel" :layer-label="layerLabel" :scope-label="scopeLabel" :validity-label="validityLabel" :review-label="reviewLabel"
              @select="openSource"
            />
            <KnowledgeSourceDetail
              v-if="drawerMode === 'source' && selectedFile" ref="detailRef" :item="selectedFile" :operation="operation" :experts="experts"
              :editing-source="editingSource" :permission-draft="permissionDraft" :saving-source="savingSource" :deleting-sources="deletingSources"
              :uploading="uploading" :format-date="formatDate" :vector-label="vectorLabel" :expert-name="expertName" :category-label="categoryLabel"
              :layer-label="layerLabel" :scope-label="scopeLabel" :validity-label="validityLabel" :review-label="reviewLabel"
              @close="closeDrawer" @save-metadata="(item, metadata) => $emit('save-metadata', item, metadata)"
              @review-source="(item, action, note) => $emit('review-source', item, action, note)" @edit-permissions="(item) => $emit('edit-permissions', item)"
              @toggle-permission="(id) => $emit('toggle-permission', id)" @save-permissions="(item) => $emit('save-permissions', item)"
              @cancel-permissions="$emit('cancel-permissions')" @delete-file="(item) => $emit('delete-file', item)"
            />
            <aside v-else-if="drawerMode === 'upload'" class="knowledge-admin-upload-drawer">
              <header><div><p>新增知识来源</p><h2>上传资料</h2></div><button type="button" aria-label="关闭上传面板" @click="closeDrawer"><X :size="18" /></button></header>
              <div class="knowledge-admin-upload-body">
                <label><span>资料类型</span><select :value="uploadCategory" :disabled="uploading" @change="onUploadCategoryChange"><option value="curriculum">课程与课标</option><option value="ecology">昆虫与植物生态</option><option value="rural_revitalization">乡村振兴</option></select></label>
                <button class="knowledge-admin-dropzone" type="button" :disabled="uploading" @click="$emit('pick-files')" @dragover.prevent @drop.prevent="$emit('drop-files', $event)"><UploadCloud :size="30" /><strong>{{ uploading ? '正在导入资料' : `上传${uploadCategoryLabel}` }}</strong><span>点击选择或拖放文件到这里</span><small>PDF / DOCX / TXT / MD，单文件最大 20 MB</small></button>
                <div v-if="uploadResults.length" class="knowledge-admin-upload-results"><article v-for="result in uploadResults" :key="result.name" :class="`status-${result.status}`"><LoaderCircle v-if="result.status === 'pending'" class="spin-icon" :size="15" /><CheckCircle2 v-else-if="result.status === 'success'" :size="15" /><AlertCircle v-else :size="15" /><span><strong>{{ result.name }}</strong><small>{{ result.message || (result.status === 'pending' ? '等待处理' : '导入完成') }}</small></span></article></div>
                <p v-if="uploadCategory === 'rural_revitalization'" class="knowledge-admin-upload-note"><Info :size="16" />乡村振兴资料上传后进入草稿，并自动打开元数据编辑页。</p>
              </div>
            </aside>
          </div>
        </section>

        <section v-else class="knowledge-admin-retrievals">
          <header><div><p class="section-kicker">检索质量</p><h2>最近召回记录</h2><span>查看混合检索命中和降级情况</span></div><button type="button" :disabled="loadingAdmin" @click="$emit('refresh-admin')"><RefreshCw :size="15" />刷新</button></header>
          <div v-if="retrievals.length" class="knowledge-admin-retrieval-list">
            <details v-for="record in retrievals" :key="record.id"><summary><span><strong>{{ record.query || '空查询' }}</strong><small>{{ modeLabel(record.mode) }} · {{ formatDate(record.created_at) }}</small></span><span>{{ record.records.length }} 条命中<ChevronDown :size="15" /></span></summary><p v-if="record.vector_error" class="knowledge-admin-retrieval-error">{{ record.vector_error }}</p><article v-for="hit in record.records" :key="`${record.id}-${hit.chunk_id}`"><header><strong>{{ hit.source }} · 片段 {{ hit.source_index }}</strong><span>综合 {{ score(hit.score) }} · 向量 {{ score(hit.vector_score) }} · BM25 {{ score(hit.bm25_score) }}</span></header><p>{{ hit.content }}</p></article><p v-if="!record.records.length" class="knowledge-admin-retrieval-empty">本次没有命中知识片段</p></details>
          </div>
          <div v-else class="knowledge-admin-retrieval-empty"><History :size="24" />当前还没有知识召回记录</div>
        </section>
      </main>
    </section>

    <section v-else class="curriculum-modal" role="dialog" aria-modal="true" aria-labelledby="knowledge-title">
      <header class="curriculum-modal-head"><div><p class="section-kicker">统一知识基础设施</p><h2 id="knowledge-title">知识库</h2><span>只读查看 · {{ files.length }} 个文件 · {{ totalChunks }} 个片段</span></div><button class="close-button" type="button" @click="$emit('close')"><X :size="18" />关闭</button></header>
      <div v-if="loading" class="curriculum-empty"><LoaderCircle class="spin-icon" :size="20" />正在读取知识文件</div>
      <div v-else-if="files.length" class="curriculum-file-list"><article v-for="item in files" :key="item.id || item.source" class="curriculum-file-row"><FileText :size="19" /><div class="curriculum-file-copy"><strong>{{ item.title || item.source }}</strong><span><em :class="`knowledge-category ${item.category}`">{{ categoryLabel(item.category) }}</em>{{ item.extension.replace('.', '').toUpperCase() }} · {{ item.chunk_count }} 个片段 · {{ formatDate(item.updated_at) }}</span><small :class="`vector-status-${item.vector_status}`">{{ vectorLabel(item) }}</small><div class="curriculum-permission-tags"><span v-if="!item.allowed_expert_ids.length" class="permission-unassigned">尚未授权专家</span><span v-for="id in item.allowed_expert_ids" :key="id" class="permission-tag">{{ expertName(id) }}</span></div></div></article></div>
      <div v-else class="curriculum-empty"><BookOpen :size="24" />当前还没有知识文件</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { Activity, AlertCircle, BookOpen, CheckCircle2, ChevronDown, Download, FileText, History, Info, Library, LoaderCircle, PackageOpen, Plus, RefreshCw, Search, SlidersHorizontal, Upload, UploadCloud, X } from "lucide-vue-next";
import KnowledgeHealthOverview from "@/components/knowledge/KnowledgeHealthOverview.vue";
import KnowledgeSourceDetail from "@/components/knowledge/KnowledgeSourceDetail.vue";
import KnowledgeSourceTable from "@/components/knowledge/KnowledgeSourceTable.vue";
import type { CurriculumFileItem, CurriculumRetrievalRecord, CurriculumVectorStatus, ExpertAgentItem, KnowledgeCategory, PolicyLayer } from "@/types";

type AdminView = "health" | "sources" | "retrievals";
type DrawerMode = "none" | "source" | "upload";
const props = defineProps<{ visible: boolean; admin: boolean; files: CurriculumFileItem[]; totalChunks: number; status: CurriculumVectorStatus | null; statusLabel: string; operation: string; loading: boolean; loadingAdmin: boolean; uploading: boolean; uploadCategory: KnowledgeCategory; error: string; uploadResults: { name: string; status: "pending" | "success" | "failed"; message: string }[]; experts: ExpertAgentItem[]; editingSource: string; permissionDraft: string[]; savingSource: string; deletingSources: string[]; retrievals: CurriculumRetrievalRecord[]; formatDate: (value: string) => string; vectorLabel: (item: CurriculumFileItem) => string; expertName: (id: string) => string; modeLabel: (mode: string) => string; score: (value: number) => string; }>();
const emit = defineEmits(["close", "rebuild", "export", "import", "bundle-selected", "pick-files", "drop-files", "files-selected", "toggle-permission", "save-permissions", "cancel-permissions", "edit-permissions", "delete-file", "refresh-admin", "update:upload-category", "save-metadata", "review-source", "refresh-files"]);

function initialView(): AdminView { try { const value = sessionStorage.getItem("knowledge-admin-view"); return value === "sources" || value === "retrievals" ? value : "health"; } catch { return "health"; } }
const activeView = ref<AdminView>(initialView());
const drawerMode = ref<DrawerMode>("none");
const selectedId = ref("");
const searchQuery = ref("");
const selectedRoleCategory = ref<"teacher" | "study_travel">("teacher");
const viewCategory = ref<"all" | KnowledgeCategory>("all");
const reviewStatus = ref("");
const policyLayer = ref<"" | PolicyLayer>("");
const authorityScope = ref("");
const validityStatus = ref("");
const documentTypeFilter = ref("");
const topicFilter = ref("");
const advancedFilters = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const bundleInput = ref<HTMLInputElement | null>(null);
const detailRef = ref<InstanceType<typeof KnowledgeSourceDetail> | null>(null);
const views = [{ value: "health" as const, label: "运行健康", icon: Activity }, { value: "sources" as const, label: "资料管理", icon: Library }, { value: "retrievals" as const, label: "召回记录", icon: History }];
const exportOptions: { value: "" | KnowledgeCategory; label: string }[] = [{ value: "", label: "全部资料" }, { value: "curriculum", label: "课程与课标" }, { value: "ecology", label: "昆虫与植物生态" }, { value: "rural_revitalization", label: "乡村振兴" }];
const layerOptions: { value: PolicyLayer; label: string }[] = [{ value: "foundation", label: "基础法规" }, { value: "annual_action", label: "年度任务" }, { value: "ceo_talent", label: "CEO与人才" }, { value: "grassroots_compliance", label: "基层合规" }];
const documentTypeOptions = [["law", "法律"], ["local_regulation", "地方性法规"], ["policy_plan", "政策方案"], ["administrative_measure", "管理办法"], ["notice", "通知"], ["training_program", "培训活动"], ["case_material", "案例材料"], ["official_information", "官方信息"], ["guide", "办事指南"], ["reference", "参考资料"]].map(([value, label]) => ({ value, label }));
const topicOptions = [["organization_governance", "组织治理"], ["land_homestead", "土地宅基地"], ["collective_assets", "集体三资"], ["industry_development", "产业发展"], ["agritourism", "农文旅"], ["project_finance", "项目资金"], ["talent_development", "人才培养"], ["public_services", "公共服务"], ["ecology_environment", "生态环境"], ["safety_emergency", "安全应急"], ["digital_rural", "数字乡村"]].map(([value, label]) => ({ value, label }));

const uploadCategoryLabel = computed(() => ({ curriculum: "课标资料", ecology: "生态资料", rural_revitalization: "乡村振兴资料" })[props.uploadCategory]);
const filteredFiles = computed(() => { const query = searchQuery.value.toLowerCase(); return props.files.filter((item) => (!query || `${item.title} ${item.source} ${item.issuing_authority} ${item.document_number}`.toLowerCase().includes(query)) && (viewCategory.value === "all" || item.category === viewCategory.value) && (!reviewStatus.value || item.review_status === reviewStatus.value) && (!policyLayer.value || item.policy_layer === policyLayer.value) && (!authorityScope.value || item.authority_scope === authorityScope.value) && (!validityStatus.value || item.validity_status === validityStatus.value) && (!documentTypeFilter.value || item.document_type === documentTypeFilter.value) && (!topicFilter.value || item.topics.includes(topicFilter.value))); });
const selectedFile = computed(() => props.files.find((item) => item.id === selectedId.value) || null);
const advancedFilterCount = computed(() => [policyLayer.value, authorityScope.value, validityStatus.value, documentTypeFilter.value, topicFilter.value].filter(Boolean).length);
const activeFilterChips = computed(() => { const chips: { key: string; label: string }[] = []; if (searchQuery.value) chips.push({ key: "search", label: `搜索：${searchQuery.value}` }); if (viewCategory.value !== "all") chips.push({ key: "category", label: categoryLabel(viewCategory.value) }); if (reviewStatus.value) chips.push({ key: "review", label: reviewLabel(reviewStatus.value) }); if (policyLayer.value) chips.push({ key: "layer", label: layerLabel(policyLayer.value) }); if (authorityScope.value) chips.push({ key: "scope", label: scopeLabel(authorityScope.value) }); if (validityStatus.value) chips.push({ key: "validity", label: validityLabel(validityStatus.value) }); const document = documentTypeOptions.find((item) => item.value === documentTypeFilter.value); if (document) chips.push({ key: "document", label: document.label }); const topic = topicOptions.find((item) => item.value === topicFilter.value); if (topic) chips.push({ key: "topic", label: topic.label }); return chips; });

function categoryLabel(value: CurriculumFileItem["category"]) { return ({ curriculum: "课程与课标", ecology: "生态资料", rural_revitalization: "乡村振兴" })[value]; }
function layerLabel(value: CurriculumFileItem["policy_layer"]) { return layerOptions.find((item) => item.value === value)?.label || "未归层"; }
function scopeLabel(value: string) { return ({ national: "国家", beijing: "北京市", district: "区级" } as Record<string, string>)[value] || "地域待补"; }
function validityLabel(value: string) { return ({ current: "现行", expired: "已过期", repealed: "已废止", unknown: "待核验", not_applicable: "非规范性材料" } as Record<string, string>)[value] || "待核验"; }
function reviewLabel(value: string) { return ({ draft: "草稿", in_review: "审核中", published: "已发布", archived: "已归档" } as Record<string, string>)[value] || value; }
function onUploadCategoryChange(event: Event) { emit("update:upload-category", (event.target as HTMLSelectElement).value); }
function openUploadPanel() { activeView.value = "sources"; selectedId.value = ""; drawerMode.value = "upload"; emit("cancel-permissions"); }
function openSource(item: CurriculumFileItem) { activeView.value = "sources"; selectedId.value = item.id; drawerMode.value = "source"; if (props.editingSource && props.editingSource !== item.source) emit("cancel-permissions"); }
function openHealthSource(item: CurriculumFileItem) { resetFilters(); openSource(item); }
function closeDrawer() { drawerMode.value = "none"; selectedId.value = ""; emit("cancel-permissions"); }
function handleEscape() { if (drawerMode.value !== "none") closeDrawer(); else emit("close"); }
function applyHealthFilter(kind: "category" | "layer", value: string) { resetFilters(); if (kind === "category") viewCategory.value = value as KnowledgeCategory; else { viewCategory.value = "rural_revitalization"; policyLayer.value = value as PolicyLayer; advancedFilters.value = true; } activeView.value = "sources"; }
function clearFilter(key: string) { if (key === "search") searchQuery.value = ""; if (key === "category") viewCategory.value = "all"; if (key === "review") reviewStatus.value = ""; if (key === "layer") policyLayer.value = ""; if (key === "scope") authorityScope.value = ""; if (key === "validity") validityStatus.value = ""; if (key === "document") documentTypeFilter.value = ""; if (key === "topic") topicFilter.value = ""; }
function resetFilters() { searchQuery.value = ""; viewCategory.value = "all"; reviewStatus.value = ""; policyLayer.value = ""; authorityScope.value = ""; validityStatus.value = ""; documentTypeFilter.value = ""; topicFilter.value = ""; }
async function openMetadataEditor(item: CurriculumFileItem) { openSource(item); await nextTick(); await detailRef.value?.openTab("metadata"); }
watch(activeView, (value) => { try { sessionStorage.setItem("knowledge-admin-view", value); } catch { /* session storage may be unavailable */ } });
watch(filteredFiles, (items) => { if (drawerMode.value === "source" && selectedId.value && !items.some((item) => item.id === selectedId.value)) closeDrawer(); });
watch(selectedFile, (item) => { if (drawerMode.value === "source" && !item) closeDrawer(); });
defineExpose({ openFilePicker: () => fileInput.value?.click(), openBundlePicker: () => bundleInput.value?.click(), openMetadataEditor });
</script>

<style scoped>
.knowledge-admin-overlay{position:fixed;z-index:1200;inset:0;display:grid;place-items:center;padding:12px;background:var(--overlay-backdrop);backdrop-filter:blur(4px)}.knowledge-admin-workbench{display:grid;grid-template-rows:auto auto auto minmax(0,1fr);width:calc(100vw - 24px);height:calc(100vh - 24px);min-width:0;overflow:hidden;border:1px solid var(--border-default);border-radius:15px;outline:0;background:var(--surface);box-shadow:var(--shadow-raised)}.knowledge-admin-header{display:grid;grid-template-columns:minmax(210px,.75fr) minmax(280px,1.1fr) auto;align-items:center;gap:18px;padding:14px 18px;border-bottom:1px solid var(--border-default);background:var(--surface)}.knowledge-admin-heading{min-width:0}.knowledge-admin-heading h1{margin:0;color:var(--text-primary);font-size:19px}.knowledge-admin-heading>span{display:block;margin-top:3px;color:var(--text-secondary);font-size:10px}.knowledge-admin-global-search{display:grid;grid-template-columns:18px minmax(0,1fr) 26px;align-items:center;gap:7px;min-height:38px;padding:0 8px 0 11px;border:1px solid var(--border-default);border-radius:9px;color:var(--text-muted);background:var(--surface-subtle)}.knowledge-admin-global-search:focus-within{border-color:var(--brand);box-shadow:var(--focus-shadow)}.knowledge-admin-global-search input{min-width:0;border:0;outline:0;color:var(--text-primary);background:transparent;font-size:11px}.knowledge-admin-global-search button,.knowledge-admin-header-actions button.icon{display:grid;place-items:center;padding:0;border:0;color:var(--text-muted);background:transparent}.knowledge-admin-header-actions{display:flex;align-items:center;justify-content:flex-end;gap:7px}.knowledge-admin-header-actions>button,.knowledge-admin-transfer-menu>summary{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:36px;padding:7px 10px;border:1px solid var(--border-default);border-radius:8px;color:var(--text-secondary);background:var(--surface);font-size:11px;white-space:nowrap}.knowledge-admin-header-actions>button.primary{color:var(--brand-contrast);border-color:var(--brand);background:var(--brand)}.knowledge-admin-header-actions button.icon{flex:0 0 36px;width:36px;border:1px solid var(--border-default)}.knowledge-admin-transfer-menu{position:relative}.knowledge-admin-transfer-menu>summary{cursor:pointer;list-style:none}.knowledge-admin-transfer-menu>summary::-webkit-details-marker{display:none}.knowledge-admin-transfer-menu>div{position:absolute;z-index:20;top:43px;right:0;display:grid;width:190px;padding:7px;border:1px solid var(--border-default);border-radius:9px;background:var(--surface);box-shadow:var(--shadow-raised)}.knowledge-admin-transfer-menu div button{display:flex;align-items:center;gap:7px;padding:8px;border:0;border-radius:6px;color:var(--text-secondary);background:transparent;font-size:10px;text-align:left}.knowledge-admin-transfer-menu div button:hover{color:var(--brand);background:var(--brand-soft)}.knowledge-admin-transfer-menu div strong{padding:8px 8px 4px;color:var(--text-muted);font-size:9px}.knowledge-admin-nav{display:flex;align-items:center;gap:3px;padding:7px 18px;border-bottom:1px solid var(--border-default);background:var(--surface-subtle)}.knowledge-admin-nav button{display:inline-flex;align-items:center;gap:6px;min-height:34px;padding:6px 10px;border:0;border-radius:7px;color:var(--text-secondary);background:transparent;font-size:11px}.knowledge-admin-nav button.active{color:var(--brand);background:var(--brand-soft);font-weight:700}.knowledge-admin-nav button span{min-width:18px;padding:1px 5px;border-radius:999px;background:var(--surface);font-size:8px;text-align:center}.knowledge-admin-nav button.refresh{margin-left:auto}.knowledge-admin-error-banner{display:grid;grid-template-columns:19px minmax(0,1fr) auto;align-items:center;gap:8px;padding:8px 18px;color:var(--danger);background:var(--danger-soft);font-size:10px}.knowledge-admin-error-banner button{border:0;color:inherit;background:transparent;font-weight:700}.knowledge-admin-main{position:relative;min-width:0;min-height:0;overflow:auto;background:var(--canvas)}.knowledge-admin-sources{display:grid;grid-template-rows:auto auto auto minmax(0,1fr);height:100%;min-height:0;background:var(--surface)}.knowledge-admin-filter-bar{display:flex;align-items:end;gap:9px;padding:11px 16px;border-bottom:1px solid var(--border-default);background:var(--surface)}.knowledge-admin-filter-bar label,.knowledge-admin-advanced-filters label{display:grid;gap:4px;color:var(--text-muted);font-size:9px}.knowledge-admin-filter-bar select,.knowledge-admin-advanced-filters select{min-width:145px;padding:7px 9px;border:1px solid var(--border-default);border-radius:7px;color:var(--text-primary);background:var(--surface);font:inherit;font-size:10px}.knowledge-admin-filter-bar>button{display:flex;align-items:center;gap:6px;min-height:31px;padding:6px 9px;border:1px solid var(--border-default);border-radius:7px;color:var(--text-secondary);background:var(--surface);font-size:10px}.knowledge-admin-filter-bar>button.active{color:var(--brand);border-color:var(--brand);background:var(--brand-soft)}.knowledge-admin-filter-bar>button span{display:grid;place-items:center;min-width:16px;height:16px;border-radius:999px;color:var(--brand-contrast);background:var(--brand);font-size:8px}.knowledge-admin-result-count{margin-left:auto;padding-bottom:7px;color:var(--text-muted);font-size:9px}.knowledge-admin-advanced-filters{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:9px;padding:10px 16px;border-bottom:1px solid var(--border-default);background:var(--surface-subtle)}.knowledge-admin-advanced-filters select{width:100%;min-width:0}.knowledge-admin-filter-chips{display:flex;align-items:center;flex-wrap:wrap;gap:5px;padding:7px 16px;border-bottom:1px solid var(--border-default);background:var(--surface)}.knowledge-admin-filter-chips button{display:flex;align-items:center;gap:4px;padding:3px 6px;border:0;border-radius:999px;color:var(--brand);background:var(--brand-soft);font-size:9px}.knowledge-admin-filter-chips button.clear{color:var(--text-muted);background:transparent}.knowledge-admin-source-layout{position:relative;display:grid;grid-template-columns:minmax(0,1fr);min-width:0;min-height:0;overflow:hidden}.knowledge-admin-source-layout.drawer-open{grid-template-columns:minmax(0,1fr) minmax(390px,31vw)}.knowledge-admin-upload-drawer{display:grid;grid-template-rows:auto minmax(0,1fr);min-width:0;height:100%;border-left:1px solid var(--border-default);background:var(--surface);box-shadow:-8px 0 22px rgba(28,45,35,.06)}.knowledge-admin-upload-drawer>header{display:flex;align-items:flex-start;justify-content:space-between;padding:16px 18px;border-bottom:1px solid var(--border-default)}.knowledge-admin-upload-drawer header p{margin:0 0 3px;color:var(--brand);font-size:9px;font-weight:700}.knowledge-admin-upload-drawer h2{margin:0;font-size:15px}.knowledge-admin-upload-drawer header button{display:grid;place-items:center;width:32px;height:32px;padding:0;border:1px solid var(--border-default);border-radius:7px;color:var(--text-secondary);background:var(--surface)}.knowledge-admin-upload-body{display:grid;align-content:start;gap:14px;padding:18px;overflow:auto}.knowledge-admin-upload-body>label{display:grid;gap:5px;color:var(--text-secondary);font-size:10px}.knowledge-admin-upload-body select{padding:8px;border:1px solid var(--border-default);border-radius:7px;color:var(--text-primary);background:var(--surface)}.knowledge-admin-dropzone{display:grid;place-items:center;gap:7px;min-height:210px;padding:22px;border:1px dashed var(--border-strong);border-radius:10px;color:var(--brand);background:var(--surface-subtle)}.knowledge-admin-dropzone:hover:not(:disabled){border-color:var(--brand);background:var(--brand-soft)}.knowledge-admin-dropzone strong{color:var(--text-primary);font-size:12px}.knowledge-admin-dropzone span{color:var(--text-secondary);font-size:10px}.knowledge-admin-dropzone small{color:var(--text-muted);font-size:9px}.knowledge-admin-upload-results{display:grid;gap:6px}.knowledge-admin-upload-results article{display:grid;grid-template-columns:18px minmax(0,1fr);gap:7px;padding:9px;border:1px solid var(--border-default);border-radius:7px;color:var(--text-muted)}.knowledge-admin-upload-results article.status-success{color:var(--success)}.knowledge-admin-upload-results article.status-failed{color:var(--danger)}.knowledge-admin-upload-results article span{display:grid;gap:2px;min-width:0}.knowledge-admin-upload-results strong,.knowledge-admin-upload-results small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.knowledge-admin-upload-results strong{color:var(--text-primary);font-size:10px}.knowledge-admin-upload-results small{color:var(--text-muted);font-size:8px}.knowledge-admin-upload-note{display:grid;grid-template-columns:18px minmax(0,1fr);gap:7px;margin:0;padding:9px;border-radius:7px;color:#8b611f;background:#f8eddf;font-size:9px;line-height:1.5}.knowledge-admin-retrievals{display:grid;align-content:start;gap:14px;max-width:1200px;margin:0 auto;padding:22px}.knowledge-admin-retrievals>header{display:flex;align-items:flex-start;justify-content:space-between}.knowledge-admin-retrievals h2{margin:0;font-size:17px}.knowledge-admin-retrievals header span{color:var(--text-secondary);font-size:10px}.knowledge-admin-retrievals>header button{display:flex;align-items:center;gap:5px;padding:7px 9px;border:1px solid var(--border-default);border-radius:7px;color:var(--text-secondary);background:var(--surface);font-size:10px}.knowledge-admin-retrieval-list{display:grid;gap:8px}.knowledge-admin-retrieval-list details{border:1px solid var(--border-default);border-radius:9px;background:var(--surface);overflow:hidden}.knowledge-admin-retrieval-list summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;cursor:pointer;list-style:none}.knowledge-admin-retrieval-list summary::-webkit-details-marker{display:none}.knowledge-admin-retrieval-list summary>span{display:flex;align-items:center;gap:7px;min-width:0;color:var(--text-secondary);font-size:9px}.knowledge-admin-retrieval-list summary>span:first-child{display:grid;gap:3px}.knowledge-admin-retrieval-list summary strong{overflow:hidden;color:var(--text-primary);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.knowledge-admin-retrieval-list summary small{color:var(--text-muted);font-size:8px}.knowledge-admin-retrieval-list details>article{margin:0 14px;padding:11px 0;border-top:1px solid var(--border-default)}.knowledge-admin-retrieval-list article header{display:flex;justify-content:space-between;gap:9px}.knowledge-admin-retrieval-list article strong{font-size:10px}.knowledge-admin-retrieval-list article span{color:var(--text-muted);font-size:8px}.knowledge-admin-retrieval-list article p{margin:6px 0 0;color:var(--text-secondary);font-size:10px;line-height:1.6}.knowledge-admin-retrieval-error{margin:0;padding:8px 14px;color:var(--danger);background:var(--danger-soft);font-size:9px}.knowledge-admin-retrieval-empty{display:grid;place-items:center;align-content:center;gap:7px;min-height:180px;color:var(--text-muted);font-size:10px}
@media(max-width:1050px){.knowledge-admin-header{grid-template-columns:minmax(180px,.65fr) minmax(240px,1fr) auto;gap:10px}.knowledge-admin-heading>span{display:none}.knowledge-admin-header-actions>button:not(.primary),.knowledge-admin-transfer-menu>summary{width:36px;padding:0;font-size:0}.knowledge-admin-source-layout.drawer-open{grid-template-columns:minmax(0,1fr) 380px}.knowledge-admin-advanced-filters{grid-template-columns:repeat(3,1fr)}}
@media(max-width:760px){.knowledge-admin-overlay{padding:0}.knowledge-admin-workbench{width:100vw;height:100vh;border:0;border-radius:0}.knowledge-admin-header{grid-template-columns:minmax(0,1fr) auto;padding:10px 12px}.knowledge-admin-heading h1{font-size:16px}.knowledge-admin-global-search{grid-row:2;grid-column:1/-1}.knowledge-admin-transfer-menu{display:none}.knowledge-admin-nav{padding:6px 10px}.knowledge-admin-nav button{flex:1;justify-content:center;padding:5px}.knowledge-admin-nav button.refresh{display:none}.knowledge-admin-filter-bar{align-items:stretch;flex-wrap:wrap;padding:9px 10px}.knowledge-admin-filter-bar label{flex:1;min-width:130px}.knowledge-admin-filter-bar select{width:100%;min-width:0}.knowledge-admin-result-count{width:100%;margin:0;padding:0}.knowledge-admin-advanced-filters{grid-template-columns:1fr 1fr;padding:9px 10px}.knowledge-admin-filter-chips{padding:6px 10px}.knowledge-admin-source-layout.drawer-open{grid-template-columns:1fr}.knowledge-admin-upload-drawer{position:absolute;z-index:10;inset:0;border-left:0}.knowledge-admin-retrievals{padding:14px}.knowledge-admin-retrieval-list article header{display:grid}}
@media(max-width:460px){.knowledge-admin-header-actions .primary{width:36px;padding:0;font-size:0}.knowledge-admin-heading .section-kicker{display:none}.knowledge-admin-nav button{font-size:10px}.knowledge-admin-advanced-filters{grid-template-columns:1fr}}
.knowledge-admin-workbench{grid-template-rows:auto auto minmax(0,1fr)}
.knowledge-admin-workbench.has-error{grid-template-rows:auto auto auto minmax(0,1fr)}
.knowledge-admin-sources{display:flex;flex-direction:column}
.knowledge-admin-filter-bar,.knowledge-admin-advanced-filters,.knowledge-admin-filter-chips{flex:0 0 auto}
.knowledge-admin-main{display:flex;flex-direction:column;overflow:hidden}
.knowledge-admin-main>.knowledge-admin-health,.knowledge-admin-main>.knowledge-admin-retrievals{flex:1 1 0;min-height:0;overflow:auto}
.knowledge-admin-sources{flex:1 1 0;height:auto;min-height:0}
.knowledge-admin-source-layout{flex:1 1 0;height:0;min-height:0;grid-template-rows:minmax(0,1fr)}
.knowledge-admin-retrievals{box-sizing:border-box;width:100%;max-width:none;margin:0}
@media(max-width:760px){.knowledge-admin-transfer-menu{display:block}}
</style>
