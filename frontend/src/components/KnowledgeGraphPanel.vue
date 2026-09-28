<template>
  <section class="knowledge-graph-panel">
    <header>
      <div>
        <strong>{{ agentName ? `${agentName} 局部知识图谱` : "局部知识图谱" }}</strong>
        <span v-if="query" :title="query">问题：{{ query }}</span>
        <span v-else>本地知识与 GloBI 全球数据分开展示</span>
      </div>
      <div class="graph-panel-actions">
        <button type="button" :disabled="loading || !query" @click="$emit('refresh')"><RefreshCw :size="14" />刷新</button>
        <button type="button" @click="$emit('close')"><X :size="15" />关闭</button>
      </div>
    </header>

    <div v-if="loading" class="knowledge-graph-progress" aria-live="polite">
      <div class="graph-progress-heading">
        <LoaderCircle class="spin-icon" :size="18" />
        <div><strong>{{ progress.message }}</strong><span>{{ normalizedPercent }}%</span></div>
      </div>
      <div class="graph-progress-track"><i :style="{ width: `${normalizedPercent}%` }" /></div>
      <ol>
        <li v-for="step in progressSteps" :key="step.label" :class="step.state">
          <span>{{ step.state === "done" ? "✓" : step.state === "active" ? "●" : "○" }}</span>{{ step.label }}
        </li>
      </ol>
    </div>
    <div v-else-if="error" class="knowledge-graph-empty graph-error">图谱加载失败：{{ error }}</div>
    <div v-else-if="!query" class="knowledge-graph-empty">请先向昆虫或自然生态专家发送问题</div>
    <div v-else-if="!graph.entities.length" class="knowledge-graph-empty">
      {{ graph.globi_runtime?.warning || "当前问题没有匹配到可展示的图谱关系" }}
    </div>
    <div v-else class="knowledge-graph-body">
      <div v-if="graph.globi_runtime" class="knowledge-graph-runtime-status">
        <strong>GloBI 实时查询</strong>
        <span v-if="graph.globi_runtime.queried_entities.length">
          查询实体：{{ graph.globi_runtime.queried_entities.map((item) => `${item.mention}（${item.scientific_name}）`).join("、") }}
        </span>
        <span>{{ graph.globi_runtime.relation_count }} 条全球关系{{ graph.globi_runtime.cache_hit ? " · 已命中缓存" : "" }}</span>
        <small v-if="graph.globi_runtime.warning">{{ graph.globi_runtime.warning }}</small>
      </div>

      <div class="knowledge-graph-sections">
        <section v-for="view in graphViews" :key="view.key" class="knowledge-graph-section" :class="view.key">
          <div class="knowledge-graph-section-head">
            <div><strong>{{ view.title }}</strong><span>{{ view.subtitle }}</span></div>
            <em>{{ view.entities.length }} 节点 · {{ view.relations.length }} 关系</em>
          </div>
          <div v-if="!view.entities.length" class="knowledge-graph-section-empty">{{ view.emptyText }}</div>
          <svg v-else class="knowledge-graph-svg" viewBox="0 0 520 320" role="img" :aria-label="view.title">
            <defs>
              <marker :id="`knowledge-arrow-${view.key}`" viewBox="0 0 10 10" refX="26" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>
              <marker :id="`knowledge-arrow-selected-${view.key}`" viewBox="0 0 10 10" refX="26" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>
            </defs>
            <line v-for="edge in view.edges" :key="`${edge.id}-hit`" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" class="knowledge-edge-hit" @click.stop="emit('toggle-relation', edge.id)" />
            <line v-for="edge in view.edges" :key="edge.id" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" class="knowledge-edge" :class="[{ selected: isEdgeSelected(edge.id) }, edge.evidenceStatus]" :marker-end="isEdgeSelected(edge.id) ? `url(#knowledge-arrow-selected-${view.key})` : `url(#knowledge-arrow-${view.key})`" />
            <text v-for="edge in view.edges" :key="`${edge.id}-label`" :x="(edge.x1 + edge.x2) / 2" :y="(edge.y1 + edge.y2) / 2 - 5" class="knowledge-edge-label" :class="[{ selected: isEdgeSelected(edge.id) }, edge.evidenceStatus]">{{ edge.predicateLabel }}{{ edge.evidenceStatus === "unverified" ? " · 待补证" : "" }}</text>
            <g v-for="node in view.nodes" :key="node.id" class="knowledge-node" :class="[node.entity.entity_type, { selected: isNodeSelected(node.id) }]" @click.stop="emit('toggle-node', node.id)">
              <circle :cx="node.x" :cy="node.y" r="26" />
              <text :x="node.x" :y="node.y + 4">{{ shortName(node.entity.name) }}</text>
            </g>
          </svg>

          <section v-if="view.recommendedPaths.length" class="knowledge-recommendations">
            <strong>推荐链路</strong>
            <button v-for="path in view.recommendedPaths" :key="path.id" type="button" :class="{ active: isPathSelected(path.id) }" @click="emit('select-path', path.id)">
              <span>{{ pathLabel(path, view) }}</span>
              <small :class="path.evidence_status">{{ evidenceLabel(path.evidence_status) }} · {{ path.reason }}</small>
            </button>
          </section>
        </section>
      </div>
      <p class="knowledge-graph-scope-note">本地图谱用于本地资料依据；GloBI 图谱是全球数据库参考，两者不在同一画布叠加。共享植物关系不能证明两种昆虫之间存在直接作用。</p>
    </div>
    <footer>
      <span>{{ selectedEntityIds.length ? `已选择 ${selectedEntityIds.length} 个节点、${selectedRelationIds.length} 条关系` : "可分别在两张图中选择回答依据" }}</span>
      <button type="button" :disabled="!selectedEntityIds.length || streaming" @click="$emit('answer')"><GitBranch :size="15" />按选中链路重新回答</button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { GitBranch, LoaderCircle, RefreshCw, X } from "lucide-vue-next";
import type { GraphProgressState, KnowledgeEntity, KnowledgeGraphPayload, KnowledgePath, KnowledgeRelation } from "@/types";

const props = defineProps<{
  graph: KnowledgeGraphPayload;
  selectedEntityIds: string[];
  selectedRelationIds: string[];
  loading: boolean;
  streaming: boolean;
  agentName: string;
  query: string;
  error: string;
  progress: GraphProgressState;
}>();

const emit = defineEmits<{
  close: []; refresh: []; answer: [];
  "toggle-node": [entityId: string];
  "toggle-relation": [relationId: string];
  "select-path": [pathId: string];
}>();

const normalizedPercent = computed(() => Math.max(0, Math.min(100, Math.round(props.progress.percent || 0))));
const progressSteps = computed(() => [
  { label: "匹配本地知识图谱", threshold: 8 },
  { label: "识别并规范化物种名称", threshold: 30 },
  { label: "双向查询 GloBI 全球关系", threshold: 80 },
  { label: "去重、筛选并生成图谱", threshold: 100 },
].map((step) => ({
  ...step,
  state: normalizedPercent.value >= step.threshold ? "done" : normalizedPercent.value >= step.threshold - 18 ? "active" : "pending",
})));

function isRuntimeEntity(entity: KnowledgeEntity): boolean {
  return entity.id.startsWith("globi_runtime_entity_") || entity.origin === "globi_runtime";
}

function buildView(key: "local" | "runtime") {
  const runtime = key === "runtime";
  const entities = props.graph.entities.filter((entity) => isRuntimeEntity(entity) === runtime);
  const entityIds = new Set(entities.map((entity) => entity.id));
  const relations = props.graph.relations.filter((relation) => entityIds.has(relation.subject_entity_id) && entityIds.has(relation.object_entity_id));
  const relationIds = new Set(relations.map((relation) => relation.id));
  const paths = props.graph.paths.filter((path) => path.relation_ids.every((id) => relationIds.has(id)));
  const nodes = layoutNodes(entities);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const edges = relations.flatMap((relation) => {
    const source = nodeById.get(relation.subject_entity_id);
    const target = nodeById.get(relation.object_entity_id);
    if (!source || !target) return [];
    return [{ id: relation.id, predicateLabel: relation.predicate_label || relation.predicate, evidenceStatus: relation.evidence_status, x1: source.x, y1: source.y, x2: target.x, y2: target.y }];
  });
  return {
    key,
    title: runtime ? "GloBI 全球关系图谱" : "本地知识图谱",
    subtitle: runtime ? "本轮 API 临时结果，不代表本地观察" : "来自本地知识库与资料证据",
    emptyText: runtime ? (props.graph.globi_runtime?.warning || "GloBI 未返回可展示关系") : "本地知识库未匹配到关系",
    entities, relations, paths, nodes, edges,
    recommendedPaths: props.graph.recommended_path_ids.map((id) => paths.find((path) => path.id === id)).filter((path): path is KnowledgePath => Boolean(path)).slice(0, 3),
  };
}

const graphViews = computed(() => [buildView("local"), buildView("runtime")]);

function layoutNodes(entities: KnowledgeEntity[]) {
  const count = Math.max(entities.length, 1);
  const radiusX = count > 14 ? 205 : 190;
  const radiusY = count > 14 ? 118 : 105;
  return entities.map((entity, index) => {
    const ring = count > 18 && index % 3 === 0 ? 0.62 : 1;
    const angle = (Math.PI * 2 * index) / count - Math.PI / 2;
    return { id: entity.id, entity, x: 260 + Math.cos(angle) * radiusX * ring, y: 160 + Math.sin(angle) * radiusY * ring };
  });
}

function shortName(name: string): string { return name.length > 12 ? `${name.slice(0, 11)}…` : name; }
function isEdgeSelected(id: string): boolean { return props.selectedRelationIds.includes(id); }
function isNodeSelected(id: string): boolean { return props.selectedEntityIds.includes(id); }
function isPathSelected(id: string): boolean {
  const path = props.graph.paths.find((item) => item.id === id);
  return Boolean(path && path.entity_ids.every((value) => props.selectedEntityIds.includes(value)) && path.relation_ids.every((value) => props.selectedRelationIds.includes(value)));
}
function pathLabel(path: KnowledgePath, view: { entities: KnowledgeEntity[]; relations: KnowledgeRelation[] }): string {
  const entityName = (id: string) => view.entities.find((entity) => entity.id === id)?.name || id;
  let label = entityName(path.entity_ids[0] || "");
  path.relation_ids.forEach((relationId, index) => {
    const relation = view.relations.find((item) => item.id === relationId);
    const nextId = path.entity_ids[index + 1];
    label += relation ? ` —${relation.predicate_label || relation.predicate}→ ${entityName(nextId)}` : ` — ${entityName(nextId)}`;
  });
  return label;
}
function evidenceLabel(status: KnowledgePath["evidence_status"]): string { return status === "verified" ? "证据完整" : status === "partial" ? "部分有证据" : "待补证"; }
</script>
