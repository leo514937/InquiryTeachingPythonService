<template>
  <div v-if="visible" class="draft-review-overlay">
    <section class="draft-review-canvas" role="dialog" aria-modal="true" aria-label="草案审阅">
      <header class="draft-review-overlay-head">
        <div><p class="section-kicker">{{ labels.reviewLabel }}</p><h2>{{ proposal ? '草案差异审阅' : 'Markdown 预览' }}</h2><span>{{ description }}</span></div>
        <div class="draft-review-overlay-actions">
          <span v-if="proposal" class="draft-proposal-status" :class="proposal.status">{{ proposalStatusLabel(proposal.status) }}</span>
          <button v-if="proposal" type="button" :disabled="!hasPending" @click="$emit('apply-all', 'accept')">全部接受</button>
          <button v-if="proposal" type="button" :disabled="!hasPending" @click="$emit('apply-all', 'reject')">全部拒绝</button>
          <button class="close-button" type="button" @click="$emit('close')"><X :size="17" />关闭</button>
        </div>
      </header>
      <div class="draft-review-overlay-body">
        <section class="draft-review-document-pane">
          <div class="draft-review-document-head"><strong>正文预览</strong><span>{{ activeSegment ? `${segmentLabel(activeSegment)} · ${segmentStatusLabel(activeSegment.status)}` : '查看当前 Markdown 解析结果' }}</span></div>
          <div ref="preview" class="draft-review-document-body">
            <article v-for="block in blocks" :key="block.id" class="draft-review-document-block" :class="{ active: block.id === activeBlockId }" :data-block-id="block.id"><div class="markdown-preview" v-html="render(block.raw)"></div></article>
          </div>
        </section>
        <aside class="draft-review-sidebar">
          <div v-if="proposal?.target_summary" class="draft-target-summary"><strong>本次修改目标</strong><p>{{ proposal.target_summary }}</p></div>
          <template v-if="proposal">
            <article v-for="segment in segments" :key="segment.id" class="review-segment" :class="[segment.kind, segment.status, { active: activeSegmentId === segment.id }]">
              <button class="review-segment-main" type="button" @click="$emit('select-segment', segment.id)"><strong>{{ segmentLabel(segment) }}</strong><span>{{ segmentStatusLabel(segment.status) }}</span><p>{{ segmentSummary(segment) }}</p></button>
              <div class="review-segment-actions"><button type="button" :disabled="segment.status !== 'pending'" @click="$emit('apply', segment.id, 'accept')">接受</button><button type="button" :disabled="segment.status !== 'pending'" @click="$emit('apply', segment.id, 'reject')">拒绝</button></div>
              <div class="review-diff"><div><small>原内容</small><div class="markdown-preview" v-html="render(segment.base_text || '（无原内容）')"></div></div><div><small>候选内容</small><div class="markdown-preview" v-html="render(segment.candidate_text || '（无新增内容）')"></div></div></div>
            </article>
          </template>
          <div v-else class="review-empty">当前没有待审阅修改。您可以查看解析后的 Markdown 效果，关闭后继续编辑。</div>
        </aside>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { X } from "lucide-vue-next";
import type { DraftProposal, DraftProposalSegment } from "@/types";

const props = defineProps<{
  visible: boolean; proposal: DraftProposal | null; description: string; segments: DraftProposalSegment[]; activeSegmentId: string | null; blocks: { id: string; raw: string }[]; activeBlockId: string | null;
  render: (value: string) => string; proposalStatusLabel: (value: DraftProposal['status']) => string; segmentStatusLabel: (value: DraftProposalSegment['status']) => string; segmentLabel: (value: DraftProposalSegment) => string; segmentSummary: (value: DraftProposalSegment) => string;
  role_category?: "teacher" | "study_travel";
}>();
const emit = defineEmits<{ close: []; 'apply-all': [action: 'accept' | 'reject']; apply: [id: string, action: 'accept' | 'reject']; 'select-segment': [id: string]; 'preview-ready': [element: HTMLElement] }>();

const labels = computed(() => ({
  reviewLabel: "草案审阅",
}));

const preview = ref<HTMLElement | null>(null);
const hasPending = computed(() => props.segments.some((segment) => segment.status === 'pending'));
onMounted(() => { if (preview.value) emit('preview-ready', preview.value); });
watch(() => props.visible, () => { if (preview.value) emit('preview-ready', preview.value); });
const activeSegment = computed(() => props.segments.find((segment) => segment.id === props.activeSegmentId) || null);
</script>
