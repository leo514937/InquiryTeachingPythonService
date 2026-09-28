export type FlowStage = {
  id: string;
  name: string;
  direction: string;
  display_direction?: string;
};

export type AuthUser = {
  id: string;
  username: string;
  is_admin: boolean;
  user_role: UserRole;
};

export type UserRole = "teacher" | "study_travel";
export type RoleCategory = "teacher" | "study_travel" | "shared";

export type ExpertAgentItem = {
  id: string;
  name: string;
  role: string;
  description: string;
  capabilities: string[];
  role_category: RoleCategory;
};

export type KnowledgeCategory = "curriculum" | "ecology" | "rural_revitalization";
export type PolicyLayer = "foundation" | "annual_action" | "ceo_talent" | "grassroots_compliance";
export type KnowledgeReviewStatus = "draft" | "in_review" | "published" | "archived";
export type KnowledgeValidityStatus = "current" | "expired" | "repealed" | "unknown" | "not_applicable";

export type CurriculumFileItem = {
  id: string;
  source: string;
  category: KnowledgeCategory;
  extension: string;
  title: string;
  policy_layer: PolicyLayer | null;
  document_type: string;
  authority_scope: "" | "national" | "beijing" | "district";
  region_code: string;
  issuing_authority: string;
  document_number: string;
  source_url: string;
  publish_date: string;
  effective_date: string;
  expiry_date: string;
  validity_status: KnowledgeValidityStatus;
  review_status: KnowledgeReviewStatus;
  review_note: string;
  reviewed_by_user_id: string;
  reviewed_at: string;
  last_verified_at: string;
  replaces_source_id: string;
  topics: string[];
  publish_errors: string[];
  checksum: string;
  chunk_count: number;
  vector_chunk_count: number;
  vector_status: "ready" | "pending" | "error" | "disabled";
  embedding_model: string;
  last_error: string;
  updated_at: string;
  allowed_expert_ids: string[];
};

export type KnowledgeSourceChunk = {
  id: number;
  source_index: number;
  content: string;
  heading_path: string;
  article_number: string;
  chunk_type: string;
};

export type KnowledgeReviewEvent = {
  id: string;
  action: string;
  from_status: string;
  to_status: string;
  note: string;
  actor_user_id: string;
  created_at: string;
};

export type KnowledgeSourceDetail = CurriculumFileItem & {
  review_events: KnowledgeReviewEvent[];
  replaces_source: { id: string; title: string; source: string } | null;
  replaced_by: { id: string; title: string; source: string }[];
};

export type CurriculumVectorStatus = {
  enabled: boolean;
  required: boolean;
  available: boolean;
  dependency_ready: boolean;
  model: string;
  model_dir: string;
  device: string;
  vector_dir: string;
  collection: string;
  vector_count: number;
  database_chunk_count: number;
  source_count: number;
  rebuild_required: boolean;
  error: string;
  candidate_k: number;
  top_k: number;
  vector_weight: number;
  bm25_weight: number;
};

export type CurriculumRetrievalHit = {
  chunk_id: number;
  chunk_ids: number[];
  source: string;
  source_index: number;
  content: string;
  score: number;
  bm25_score: number;
  vector_score: number;
  fusion_score: number;
  retrieval_mode: string;
};

export type CurriculumRetrievalRecord = {
  id: string;
  session_id: string;
  stage_id: string;
  query: string;
  mode: string;
  expert_id: string;
  allowed_sources: string[];
  hit_sources: string[];
  vector_error: string;
  records: CurriculumRetrievalHit[];
  created_at: string;
};

export type KnowledgeEntity = {
  id: string;
  name: string;
  entity_type: "insect" | "plant" | "habitat" | "season" | "behavior" | "concept" | string;
  aliases: string[];
  description: string;
  source: string;
  rag_sources: string[];
  mention_count: number;
  origin: "manual" | "lightrag" | "globi" | string;
  management_mode: "manual" | "auto" | "manual_override" | string;
  extractor_model: string;
  extractor_version: string;
  last_auto_sync_at: string;
  taxa: KnowledgeEntityTaxon[];
};

export type KnowledgeEntityTaxon = {
  authority: string;
  external_id: string;
  scientific_name: string;
  taxon_rank: string;
  common_names: string[];
  match_method: string;
  match_confidence: string;
};

export type KnowledgeEvidence = {
  chunk_id: number;
  source: string;
  source_index: number;
  content: string;
};

export type KnowledgeRelation = {
  id: string;
  subject_entity_id: string;
  predicate: string;
  predicate_label?: string;
  object_entity_id: string;
  description: string;
  evidence_source: string;
  confidence: "high" | "medium" | "low" | string;
  evidence_status: "verified" | "unverified";
  evidence: KnowledgeEvidence[];
  evidence_types: Array<"local_document" | "globi" | "manual" | string>;
  geographic_scope: "local" | "global" | "mixed" | "unknown" | string;
  global_only: boolean;
  globi_evidence_count: number;
  globi_evidence: GlobiEvidence[];
  origin: "manual" | "lightrag" | "globi" | string;
  management_mode: "manual" | "auto" | "manual_override" | string;
  status: "active" | "suppressed" | string;
  extractor_model: string;
  extractor_version: string;
  last_auto_sync_at: string;
};

export type GlobiEvidence = {
  id: string;
  raw_interaction_type: string;
  study_source_id: string;
  study_source_citation: string;
  study_url: string;
  study_doi: string;
  study_source_archive_uri: string;
  locality: string;
  latitude: string;
  longitude: string;
  event_date: string;
  region_status: "located" | "global" | string;
};

export type GlobiImportStats = {
  total_rows: number;
  candidate_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  created_entities: number;
  updated_entities: number;
  created_relations: number;
  updated_relations: number;
  rejection_reasons: Record<string, number>;
  rejection_samples: Array<{ reason: string; source: string; interaction: string; target: string }>;
  predicate_counts: Record<string, number>;
  rollback?: { interactions: number; relations: number; entities: number };
};

export type GlobiImportOptions = {
  include_insect_insect: boolean;
  keep_unknown_region: boolean;
  batch_size: number;
  interaction_types: string[];
};

export type GlobiImportRun = {
  id: string;
  version: string;
  source_url: string;
  source_name: string;
  checksum: string;
  filters: GlobiImportOptions;
  status: "preview" | "queued" | "running" | "completed" | "failed" | "rolled_back" | string;
  attempts: number;
  total_rows: number;
  candidate_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  created_entities: number;
  updated_entities: number;
  created_relations: number;
  updated_relations: number;
  stats: GlobiImportStats;
  started_at: string;
  finished_at: string;
  last_error: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type GlobiImportPreview = {
  version: string;
  source_name: string;
  checksum: string;
  filters: GlobiImportOptions;
  stats: GlobiImportStats;
};

export type EcologyGraphSyncJob = {
  id: string;
  source: string;
  source_checksum: string;
  operation: "sync" | "delete" | string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | string;
  attempts: number;
  stats: Record<string, number>;
  last_error: string;
  created_at: string;
  started_at: string;
  finished_at: string;
  updated_at: string;
};

export type EcologyGraphSourceState = {
  source: string;
  source_checksum: string;
  lightrag_doc_id: string;
  status: string;
  last_job_id: string;
  entity_count: number;
  relation_count: number;
  rejected_count: number;
  last_error: string;
  last_synced_at: string;
  updated_at: string;
};

export type EcologyGraphSyncStatus = {
  jobs: EcologyGraphSyncJob[];
  sources: EcologyGraphSourceState[];
};

export type KnowledgePath = {
  id: string;
  entity_ids: string[];
  relation_ids: string[];
  score: number;
  evidence_status: "verified" | "partial" | "unverified";
  reason: string;
};

export type KnowledgeEntityInput = {
  name: string;
  entity_type: "insect" | "plant" | "habitat" | "season" | "concept";
  aliases: string[];
  description: string;
  source: string;
};

export type KnowledgeRelationInput = {
  subject_entity_id: string;
  predicate: string;
  object_entity_id: string;
  description: string;
  confidence: "high" | "medium" | "low";
  evidence_chunk_ids: number[];
};

export type KnowledgeGraphPayload = {
  entities: KnowledgeEntity[];
  relations: KnowledgeRelation[];
  paths: KnowledgePath[];
  recommended_path_ids: string[];
  globi_runtime?: {
    query_id: string;
    status: "success" | "empty" | "failed" | "disabled" | "expired" | "skipped" | string;
    cache_hit: boolean;
    queried_entities: Array<{
      mention: string;
      scientific_name: string;
      entity_type: "insect" | "plant" | string;
    }>;
    relation_count: number;
    warning: string;
  } | null;
};

export type GraphProgressState = {
  phase: string;
  percent: number;
  message: string;
  completed?: number;
  total?: number;
};

export type GraphSelectionPayload = {
  entity_ids: string[];
  relation_ids: string[];
  path_ids: string[];
  globi_query_id?: string | null;
};

export type FlowInfo = {
  name: string;
  display_name: string;
  description: string;
  stage_count: number;
  stages: FlowStage[];
};

export type SessionListItem = {
  id: string;
  title: string;
  topic: string;
  flow_name: string;
  flow_display_name: string;
  current_stage_index: number;
  status: string;
  draft_mode_enabled: boolean;
  updated_at: string;
  created_at: string;
};

export type StageOutput = {
  stage_id: string;
  stage_name: string;
  order_index: number;
  draft_content: string;
  final_content: string;
  confirmed: boolean;
};

export type SessionDetail = SessionListItem & {
  current_stage: FlowStage | null;
  outputs: StageOutput[];
};

export type SessionFileItem = {
  id: string;
  name: string;
  extension: string;
  mime_type: string;
  size_bytes: number;
  extracted_chars: number;
  status: "processing" | "ready" | "failed";
  error_message: string;
  created_at: string;
};

export type DraftProposalSegment = {
  id: string;
  kind: "equal" | "replace" | "delete" | "insert";
  base_start: number;
  base_end: number;
  candidate_start: number;
  candidate_end: number;
  base_text: string;
  candidate_text: string;
  status: "pending" | "accepted" | "rejected";
};

export type DraftSelection = {
  selected_text: string;
  start_offset: number;
  end_offset: number;
  stage_id: string;
  block_id?: string | null;
};

export type DraftProposal = {
  id: string;
  session_id: string;
  stage_id: string;
  base_content: string;
  candidate_content: string;
  segments: DraftProposalSegment[];
  status: "pending" | "accepted" | "rejected";
  proposal_kind: "generate" | "edit";
  target_mode: "selection" | null;
  target_summary: string | null;
  target_range?: {
    start_offset: number;
    end_offset: number;
  } | null;
  highlight_segment_ids: string[];
  created_at: string;
  updated_at: string;
};

export type MessageItem = {
  id?: string;
  stage_id: string;
  role: "user" | "assistant";
  content: string;
  agent_id?: string | null;
  agent_name?: string | null;
  agent_role?: string | null;
  message_type?: string;
  interrupted?: boolean;
  created_at?: string;
};
