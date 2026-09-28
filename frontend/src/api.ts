import type {
  AuthUser,
  CurriculumFileItem,
  CurriculumRetrievalRecord,
  CurriculumVectorStatus,
  DraftProposal,
  DraftSelection,
  ExpertAgentItem,
  EcologyGraphSyncStatus,
  FlowInfo,
  GlobiImportPreview,
  GlobiImportRun,
  GraphSelectionPayload,
  KnowledgeEntity,
  KnowledgeEntityInput,
  KnowledgeEvidence,
  KnowledgeCategory,
  KnowledgeGraphPayload,
  KnowledgeRelation,
  KnowledgeRelationInput,
  KnowledgeSourceChunk,
  KnowledgeSourceDetail,
  MessageItem,
  SessionDetail,
  SessionFileItem,
  SessionListItem,
} from "@/types";

const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/$/, "") ||
  `${window.location.protocol}//${window.location.hostname}:8010`;

type ApiEnvelope<T> = {
  code?: number;
  message?: string;
  data: T;
};

async function readJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    credentials: "include",
  });
  if (!response.ok) {
    const body = await response.text();
    let detail = body || response.statusText;
    try {
      const parsed = JSON.parse(body);
      detail = parsed.detail || parsed.message || detail;
    } catch {
      // Keep the original response body when it is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function getFlows(): Promise<FlowInfo[]> {
  const payload = await readJson<ApiEnvelope<FlowInfo[]>>(`${API_BASE}/api/flows`);
  return payload.data || [];
}

export async function getSessions(): Promise<SessionListItem[]> {
  const payload = await readJson<ApiEnvelope<SessionListItem[]>>(`${API_BASE}/api/sessions`);
  return payload.data || [];
}

export async function createSession(topic: string, flowName: string): Promise<SessionDetail> {
  const payload = await readJson<ApiEnvelope<SessionDetail>>(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, flow_name: flowName }),
  });
  return payload.data;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const payload = await readJson<ApiEnvelope<SessionDetail>>(`${API_BASE}/api/sessions/${sessionId}`);
  return payload.data;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await readJson<ApiEnvelope<null>>(`${API_BASE}/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function getMessages(sessionId: string): Promise<MessageItem[]> {
  const payload = await readJson<ApiEnvelope<MessageItem[]>>(`${API_BASE}/api/sessions/${sessionId}/messages`);
  return payload.data || [];
}

export async function getExperts(): Promise<ExpertAgentItem[]> {
  const payload = await readJson<ApiEnvelope<ExpertAgentItem[]>>(`${API_BASE}/api/experts`);
  return payload.data || [];
}

export async function getSessionFiles(sessionId: string): Promise<SessionFileItem[]> {
  const payload = await readJson<ApiEnvelope<SessionFileItem[]>>(
    `${API_BASE}/api/sessions/${sessionId}/files`,
  );
  return payload.data || [];
}

export async function uploadSessionFile(sessionId: string, file: File): Promise<SessionFileItem> {
  const formData = new FormData();
  formData.append("file", file);
  const payload = await readJson<ApiEnvelope<SessionFileItem>>(
    `${API_BASE}/api/sessions/${sessionId}/files`,
    {
      method: "POST",
      body: formData,
    },
  );
  return payload.data;
}

export async function deleteSessionFile(sessionId: string, fileId: string): Promise<void> {
  await readJson<ApiEnvelope<null>>(
    `${API_BASE}/api/sessions/${sessionId}/files/${fileId}`,
    { method: "DELETE" },
  );
}

export async function registerUser(username: string, password: string): Promise<AuthUser> {
  const payload = await readJson<ApiEnvelope<AuthUser>>(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return payload.data;
}

export async function loginUser(username: string, password: string): Promise<AuthUser> {
  const payload = await readJson<ApiEnvelope<AuthUser>>(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return payload.data;
}

export async function registerAdmin(username: string, password: string): Promise<AuthUser> {
  const payload = await readJson<ApiEnvelope<AuthUser>>(`${API_BASE}/api/auth/admin/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return payload.data;
}

export async function loginAdmin(username: string, password: string): Promise<AuthUser> {
  const payload = await readJson<ApiEnvelope<AuthUser>>(`${API_BASE}/api/auth/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return payload.data;
}

export async function getCurrentUser(): Promise<AuthUser> {
  const payload = await readJson<ApiEnvelope<AuthUser>>(`${API_BASE}/api/auth/me`);
  return payload.data;
}

export async function logoutUser(): Promise<void> {
  await readJson<ApiEnvelope<null>>(`${API_BASE}/api/auth/logout`, { method: "POST" });
}

export async function setDraftMode(sessionId: string, enabled: boolean): Promise<SessionDetail> {
  const payload = await readJson<ApiEnvelope<SessionDetail>>(`${API_BASE}/api/sessions/${sessionId}/draft-mode`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return payload.data;
}

export async function getDraftProposal(sessionId: string, stageId: string): Promise<DraftProposal | null> {
  const payload = await readJson<ApiEnvelope<DraftProposal | null>>(
    `${API_BASE}/api/sessions/${sessionId}/draft-proposal?stage_id=${encodeURIComponent(stageId)}`,
  );
  return payload.data || null;
}

export async function applyDraftProposalActions(
  sessionId: string,
  proposalId: string,
  actions: { hunk_id: string; action: "accept" | "reject" }[],
): Promise<DraftProposal> {
  const payload = await readJson<ApiEnvelope<DraftProposal>>(
    `${API_BASE}/api/sessions/${sessionId}/draft-proposals/${proposalId}/actions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actions }),
    },
  );
  return payload.data;
}

export async function saveDraft(sessionId: string, stageId: string, draftContent: string): Promise<void> {
  await readJson(`${API_BASE}/api/sessions/${sessionId}/stages/${stageId}/draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft_content: draftContent }),
  });
}

export async function rollbackSession(
  sessionId: string,
  payload: { steps: number; stage_back: boolean },
): Promise<SessionDetail> {
  const response = await readJson<ApiEnvelope<{ session: SessionDetail }>>(
    `${API_BASE}/api/sessions/${sessionId}/rollback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return response.data.session;
}

export async function exportSession(sessionId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/export`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.blob();
}

type StreamHandlers = {
  stage?: (data: any) => void | Promise<void>;
  graph?: (data: any) => void | Promise<void>;
  graph_progress?: (data: any) => void | Promise<void>;
  agent?: (data: any) => void | Promise<void>;
  delta?: (data: any) => void | Promise<void>;
  draft?: (data: any) => void | Promise<void>;
  proposal?: (data: any) => void | Promise<void>;
  status?: (data: any) => void | Promise<void>;
  warning?: (data: any) => void | Promise<void>;
  interrupted?: (data: any) => void | Promise<void>;
  done?: (data: any) => void | Promise<void>;
};

export type StreamChatPayload = {
  type: "chat" | "sys_action";
  request_id?: string;
  message?: string;
  action?: "next_stage" | "prev_stage" | "intro" | "confirm_stage";
  final_content?: string;
  expert_id?: string;
  draft_request_kind?: "generate" | "edit";
  selection?: DraftSelection | null;
  graph_selection?: GraphSelectionPayload | null;
};

export async function streamChat(
  sessionId: string,
  payload: StreamChatPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/chat`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const dispatch = async (eventName: string, rawData: string) => {
    if (!rawData) {
      return;
    }
    try {
      const data = JSON.parse(rawData);
      await handlers[eventName as keyof StreamHandlers]?.(data);
    } catch {
      await handlers[eventName as keyof StreamHandlers]?.({ text: rawData });
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    while (true) {
      const splitIndex = buffer.indexOf("\n\n");
      if (splitIndex < 0) {
        break;
      }

      const chunk = buffer.slice(0, splitIndex);
      buffer = buffer.slice(splitIndex + 2);
      const lines = chunk.split(/\r?\n/);
      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      await dispatch(eventName, dataLines.join("\n"));
    }
  }
}

export async function getCurriculumFiles(category?: KnowledgeCategory): Promise<CurriculumFileItem[]> {
  const suffix = category ? `?category=${encodeURIComponent(category)}` : "";
  const payload = await readJson<ApiEnvelope<CurriculumFileItem[]>>(`${API_BASE}/api/curriculum/files${suffix}`);
  return payload.data || [];
}

export async function getKnowledgeSources(category?: KnowledgeCategory): Promise<CurriculumFileItem[]> {
  const suffix = category ? `?category=${encodeURIComponent(category)}` : "";
  const payload = await readJson<ApiEnvelope<CurriculumFileItem[]>>(`${API_BASE}/api/knowledge/sources${suffix}`);
  return payload.data || [];
}

export async function getKnowledgeSource(sourceId: string): Promise<KnowledgeSourceDetail> {
  const payload = await readJson<ApiEnvelope<KnowledgeSourceDetail>>(
    `${API_BASE}/api/knowledge/sources/${encodeURIComponent(sourceId)}`,
  );
  return payload.data;
}

export async function getKnowledgeSourceChunks(sourceId: string): Promise<KnowledgeSourceChunk[]> {
  const payload = await readJson<ApiEnvelope<KnowledgeSourceChunk[]>>(
    `${API_BASE}/api/knowledge/sources/${encodeURIComponent(sourceId)}/chunks`,
  );
  return payload.data || [];
}

export async function uploadKnowledgeSource(
  file: File,
  category: KnowledgeCategory = "curriculum",
  metadata: Record<string, unknown> = {},
): Promise<CurriculumFileItem> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("category", category);
  formData.append("metadata_json", JSON.stringify(metadata));
  const payload = await readJson<ApiEnvelope<CurriculumFileItem>>(`${API_BASE}/api/knowledge/sources`, {
    method: "POST",
    body: formData,
  });
  return payload.data;
}

export async function updateKnowledgeSource(
  sourceId: string,
  metadata: Record<string, unknown>,
  file?: File,
): Promise<CurriculumFileItem> {
  const formData = new FormData();
  formData.append("metadata_json", JSON.stringify(metadata));
  if (file) formData.append("file", file);
  const payload = await readJson<ApiEnvelope<CurriculumFileItem>>(
    `${API_BASE}/api/knowledge/sources/${encodeURIComponent(sourceId)}`,
    { method: "PATCH", body: formData },
  );
  return payload.data;
}

export async function reviewKnowledgeSource(
  sourceId: string,
  action: "submit" | "return" | "publish" | "archive",
  note = "",
): Promise<CurriculumFileItem> {
  const payload = await readJson<ApiEnvelope<CurriculumFileItem>>(
    `${API_BASE}/api/knowledge/sources/${encodeURIComponent(sourceId)}/review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note }),
    },
  );
  return payload.data;
}

export async function deleteKnowledgeSource(sourceId: string): Promise<void> {
  await readJson<ApiEnvelope<null>>(
    `${API_BASE}/api/knowledge/sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" },
  );
}

export async function downloadKnowledgeBundle(category?: KnowledgeCategory): Promise<Blob> {
  const suffix = category ? `?category=${encodeURIComponent(category)}` : "";
  const response = await fetch(`${API_BASE}/api/knowledge/sources/export${suffix}`, {
    credentials: "include",
  });
  if (!response.ok) throw new Error(await response.text());
  return response.blob();
}

export async function importKnowledgeBundle(file: File): Promise<{ source_count: number; chunk_count: number }> {
  const formData = new FormData();
  formData.append("file", file);
  const payload = await readJson<ApiEnvelope<{ source_count: number; chunk_count: number }>>(
    `${API_BASE}/api/knowledge/sources/import`,
    { method: "POST", body: formData },
  );
  return payload.data;
}

export async function uploadCurriculumFile(
  file: File,
  category: KnowledgeCategory = "curriculum",
): Promise<CurriculumFileItem> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("category", category);
  const payload = await readJson<ApiEnvelope<CurriculumFileItem>>(`${API_BASE}/api/curriculum/files`, {
    method: "POST",
    body: formData,
  });
  return payload.data;
}

export async function deleteCurriculumFile(source: string): Promise<void> {
  await readJson<ApiEnvelope<null>>(
    `${API_BASE}/api/curriculum/files?source=${encodeURIComponent(source)}`,
    { method: "DELETE" },
  );
}

export async function updateCurriculumPermissions(
  source: string,
  expertIds: string[],
): Promise<{ source: string; allowed_expert_ids: string[] }> {
  const payload = await readJson<
    ApiEnvelope<{ source: string; allowed_expert_ids: string[] }>
  >(`${API_BASE}/api/curriculum/files/permissions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, expert_ids: expertIds }),
  });
  return payload.data;
}

export async function getCurriculumStatus(): Promise<CurriculumVectorStatus> {
  const payload = await readJson<ApiEnvelope<CurriculumVectorStatus>>(`${API_BASE}/api/curriculum/status`);
  return payload.data;
}

export async function rebuildCurriculumVectors(): Promise<CurriculumVectorStatus> {
  const payload = await readJson<ApiEnvelope<{ status: CurriculumVectorStatus }>>(
    `${API_BASE}/api/curriculum/vector/rebuild`,
    { method: "POST" },
  );
  return payload.data.status;
}

export async function getCurriculumRetrievals(limit = 20): Promise<CurriculumRetrievalRecord[]> {
  const payload = await readJson<ApiEnvelope<CurriculumRetrievalRecord[]>>(
    `${API_BASE}/api/curriculum/retrievals?limit=${limit}`,
  );
  return payload.data || [];
}

export async function downloadCurriculumBundle(
  category?: KnowledgeCategory,
): Promise<Blob> {
  const suffix = category ? `?category=${encodeURIComponent(category)}` : "";
  const response = await fetch(`${API_BASE}/api/curriculum/export${suffix}`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.blob();
}

export async function importCurriculumBundle(file: File): Promise<{ source_count: number; chunk_count: number }> {
  const formData = new FormData();
  formData.append("file", file);
  const payload = await readJson<ApiEnvelope<{ source_count: number; chunk_count: number }>>(
    `${API_BASE}/api/curriculum/import`,
    { method: "POST", body: formData },
  );
  return payload.data;
}

export async function cancelChat(sessionId: string, requestId: string): Promise<boolean> {
  const payload = await readJson<ApiEnvelope<{ cancelled: boolean }>>(
    `${API_BASE}/api/sessions/${sessionId}/chat/${encodeURIComponent(requestId)}/cancel`,
    { method: "POST" },
  );
  return Boolean(payload.data?.cancelled);
}

export async function getKnowledgeGraphCandidates(
  sessionId: string,
  message: string,
  expertId?: string,
): Promise<KnowledgeGraphPayload> {
  const payload = await readJson<ApiEnvelope<KnowledgeGraphPayload>>(`${API_BASE}/api/knowledge/graph/candidates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      expert_id: expertId || undefined,
    }),
  });
  return payload.data;
}

export async function streamKnowledgeGraphCandidates(
  sessionId: string,
  message: string,
  expertId: string,
  handlers: Pick<StreamHandlers, "graph" | "graph_progress">,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/knowledge/graph/candidates/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, expert_id: expertId }),
    signal,
  });
  if (!response.ok || !response.body) throw new Error(await response.text());

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  const dispatch = async (chunk: string) => {
    const lines = chunk.split(/\r?\n/);
    const eventName = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() || "message";
    const rawData = lines.filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart()).join("\n");
    if (!rawData) return;
    const handler = handlers[eventName as keyof typeof handlers];
    if (!handler) return;
    try {
      await handler(JSON.parse(rawData));
    } catch {
      await handler({ text: rawData });
    }
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let splitIndex = buffer.indexOf("\n\n");
    while (splitIndex >= 0) {
      await dispatch(buffer.slice(0, splitIndex));
      buffer = buffer.slice(splitIndex + 2);
      splitIndex = buffer.indexOf("\n\n");
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) await dispatch(buffer);
}

export async function getKnowledgeGraphAdmin(): Promise<KnowledgeGraphPayload> {
  const payload = await readJson<ApiEnvelope<KnowledgeGraphPayload>>(`${API_BASE}/api/knowledge/graph`);
  return payload.data;
}

export async function updateKnowledgeGraphEntityRagSources(entityId: string, sources: string[]): Promise<string[]> {
  const payload = await readJson<ApiEnvelope<{ entity_id: string; sources: string[] }>>(
    `${API_BASE}/api/knowledge/graph/entities/${encodeURIComponent(entityId)}/rag-sources`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sources }),
    },
  );
  return payload.data.sources;
}

export async function createKnowledgeGraphEntity(input: KnowledgeEntityInput): Promise<KnowledgeEntity> {
  const payload = await readJson<ApiEnvelope<KnowledgeEntity>>(`${API_BASE}/api/knowledge/graph/entities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return payload.data;
}

export async function updateKnowledgeGraphEntity(
  entityId: string,
  input: KnowledgeEntityInput,
): Promise<KnowledgeEntity> {
  const payload = await readJson<ApiEnvelope<KnowledgeEntity>>(
    `${API_BASE}/api/knowledge/graph/entities/${encodeURIComponent(entityId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  return payload.data;
}

export async function deleteKnowledgeGraphEntity(entityId: string): Promise<void> {
  await readJson<ApiEnvelope<null>>(
    `${API_BASE}/api/knowledge/graph/entities/${encodeURIComponent(entityId)}`,
    { method: "DELETE" },
  );
}

export async function createKnowledgeGraphRelation(input: KnowledgeRelationInput): Promise<KnowledgeRelation> {
  const payload = await readJson<ApiEnvelope<KnowledgeRelation>>(`${API_BASE}/api/knowledge/graph/relations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return payload.data;
}

export async function updateKnowledgeGraphRelation(
  relationId: string,
  input: KnowledgeRelationInput,
): Promise<KnowledgeRelation> {
  const payload = await readJson<ApiEnvelope<KnowledgeRelation>>(
    `${API_BASE}/api/knowledge/graph/relations/${encodeURIComponent(relationId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  return payload.data;
}

export async function deleteKnowledgeGraphRelation(relationId: string): Promise<void> {
  await readJson<ApiEnvelope<null>>(
    `${API_BASE}/api/knowledge/graph/relations/${encodeURIComponent(relationId)}`,
    { method: "DELETE" },
  );
}

export async function restoreAutomaticKnowledgeGraphRelation(
  relationId: string,
): Promise<KnowledgeRelation> {
  const payload = await readJson<ApiEnvelope<KnowledgeRelation>>(
    `${API_BASE}/api/knowledge/graph/relations/${encodeURIComponent(relationId)}/restore-auto`,
    { method: "POST" },
  );
  return payload.data;
}

export async function startEcologyGraphSync(source?: string): Promise<number> {
  const payload = await readJson<ApiEnvelope<{ jobs: unknown[]; queued_count: number }>>(
    `${API_BASE}/api/knowledge/ecology-graph/sync`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: source || null, force: true }),
    },
  );
  return payload.data.queued_count;
}

export async function getEcologyGraphSyncStatus(): Promise<EcologyGraphSyncStatus> {
  const payload = await readJson<ApiEnvelope<EcologyGraphSyncStatus>>(
    `${API_BASE}/api/knowledge/ecology-graph/sync`,
  );
  return payload.data;
}

export type GlobiImportRequest = {
  version: string;
  sourceUrl: string;
  file: File | null;
  includeInsectInsect: boolean;
  keepUnknownRegion: boolean;
  batchSize: number;
  interactionTypes: string[];
};

function globiImportForm(input: GlobiImportRequest): FormData {
  const form = new FormData();
  form.set("version", input.version || "stable");
  form.set("source_url", input.sourceUrl || "");
  form.set("include_insect_insect", String(input.includeInsectInsect));
  form.set("keep_unknown_region", String(input.keepUnknownRegion));
  form.set("batch_size", String(input.batchSize || 1000));
  form.set("interaction_types_json", JSON.stringify(input.interactionTypes || []));
  if (input.file) form.set("file", input.file);
  return form;
}

export async function previewGlobiImport(input: GlobiImportRequest): Promise<GlobiImportPreview> {
  const payload = await readJson<ApiEnvelope<GlobiImportPreview>>(
    `${API_BASE}/api/knowledge/globi/import/preview`,
    { method: "POST", body: globiImportForm(input) },
  );
  return payload.data;
}

export async function startGlobiImport(input: GlobiImportRequest): Promise<GlobiImportRun> {
  const payload = await readJson<ApiEnvelope<GlobiImportRun>>(
    `${API_BASE}/api/knowledge/globi/import`,
    { method: "POST", body: globiImportForm(input) },
  );
  return payload.data;
}

export async function getGlobiImports(limit = 50): Promise<GlobiImportRun[]> {
  const payload = await readJson<ApiEnvelope<GlobiImportRun[]>>(
    `${API_BASE}/api/knowledge/globi/import?limit=${limit}`,
  );
  return payload.data || [];
}

export async function rollbackGlobiImport(runId: string): Promise<GlobiImportRun> {
  const payload = await readJson<ApiEnvelope<GlobiImportRun>>(
    `${API_BASE}/api/knowledge/globi/import/${encodeURIComponent(runId)}/rollback`,
    { method: "POST" },
  );
  return payload.data;
}

export async function retryGlobiImport(runId: string): Promise<GlobiImportRun> {
  const payload = await readJson<ApiEnvelope<GlobiImportRun>>(
    `${API_BASE}/api/knowledge/globi/import/${encodeURIComponent(runId)}/retry`,
    { method: "POST" },
  );
  return payload.data;
}

export async function getKnowledgeEvidenceChunks(
  relationId = "",
  source = "",
): Promise<KnowledgeEvidence[]> {
  const params = new URLSearchParams();
  if (relationId) params.set("relation_id", relationId);
  if (source) params.set("source", source);
  const payload = await readJson<ApiEnvelope<KnowledgeEvidence[]>>(
    `${API_BASE}/api/knowledge/graph/evidence-chunks?${params.toString()}`,
  );
  return payload.data || [];
}

export async function rebuildKnowledgeMentions(): Promise<number> {
  const payload = await readJson<ApiEnvelope<{ mention_count: number }>>(
    `${API_BASE}/api/knowledge/graph/rebuild-mentions`,
    { method: "POST" },
  );
  return payload.data.mention_count;
}

export async function getKnowledgeGraphNeighbors(entityId: string, hops = 1): Promise<KnowledgeGraphPayload> {
  const payload = await readJson<ApiEnvelope<KnowledgeGraphPayload>>(
    `${API_BASE}/api/knowledge/graph/entities/${encodeURIComponent(entityId)}/neighbors?hops=${hops}`,
  );
  return payload.data;
}

export function buildFileDownloadUrl(sessionName: string): string {
  return `${API_BASE}/api/sessions/${encodeURIComponent(sessionName)}/export`;
}
