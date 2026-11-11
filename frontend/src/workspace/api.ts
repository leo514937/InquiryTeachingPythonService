export interface Artifact {
  id: string;
  type: string;
  version: number;
  content: Record<string, any>;
  locked?: boolean;
  review_status?: string;
  source_refs?: Array<{expert_id: string; source: string}>;
  order_index?: number;
  status?: string;
}

export interface Workspace {
  id: string;
  title: string;
  revision: number;
  artifacts: Artifact[];
  latest_run?: {id: string; status: string; error: string; mode: string; teaching_context?: TeachingContextInput; review_approvable?: boolean; warnings: string[]; nodes: Array<{id: string; capability: string; status: string}>} | null;
}

export interface Dependency {
  upstream_id: string;
  upstream_version: number;
  upstream_field: string;
  downstream_id: string;
  downstream_field: string;
}

const base = (import.meta.env.VITE_API_BASE?.replace(/\/$/, '') || `${window.location.protocol}//${window.location.hostname}:8010`) + '/api/inquiry-workspaces';

export class WorkspaceRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function workspaceRequest<T>(path = '', options: RequestInit = {}): Promise<T> {
  const response = await fetch(base + path, { credentials: 'include', ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 403) window.dispatchEvent(new CustomEvent('inquiry-workspace:access-denied', {detail: {path, message: body.detail}}));
    throw new WorkspaceRequestError(body.detail || `请求失败（${response.status}）`, response.status);
  }
  return (await response.json()).data as T;
}

export function jsonRequest(method: string, data: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) };
}


export interface DagRunSummary {
  id: string; mode: string; status: string; created_at: string; updated_at: string;
}
export interface DagNodeData {
  id: string; capability: string; depends_on: string[]; status: string; attempts: number;
  started_at: string | null; finished_at: string | null; error_code: string | null;
  error_message: string | null; input_summary: string; output_summary: string;
  result_refs: Array<{id: string; version: number; operation: string}>;
  change_kind: string | null; source_refs?: Array<{expert_id:string; source:string}>;
}
export interface DagSnapshot extends DagRunSummary {
  error: string | null; nodes: DagNodeData[];
  edges: Array<{id: string; source: string; target: string}>;
  incomplete: boolean; empty_reason: string | null; event_cursor: number;
}
export function workspaceEventsUrl(workspaceId: string, runId: string, after: number): string {
  return base + '/' + encodeURIComponent(workspaceId) + '/runs/' + encodeURIComponent(runId) +
    '/events?follow=true&after=' + encodeURIComponent(String(after));
}
export interface TeachingContextInput {
  subject?: string; stage?: string; grade?: string; duration_minutes?: number;
  learning_goals?: string[]; prior_knowledge?: string; language_level?: string;
  real_life_context?: string; resources?: string[]; activity_formats?: string[];
  safety_constraints?: string; teacher_requirements?: string;
}
