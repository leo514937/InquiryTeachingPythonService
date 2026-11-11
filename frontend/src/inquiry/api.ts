const base = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') || `${window.location.protocol}//${window.location.hostname}:8010`;

export type Scene = { id: string; name: string; description: string; version: number; has_configured_sources?: boolean };
export type Source = { id: string; title: string };
export type Artifact = { id: string; type: string; version: number; content: Record<string, unknown>; source_refs: Array<Record<string, string>>; status: string; review_status: string; locked: boolean };
export type Run = { id: string; status: string; error: string; warnings: string[]; nodes: Array<{id: string; capability: string; status: string}> };
export type Workspace = { id: string; title: string; artifacts: Artifact[]; latest_run: Run | null };

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(base + path, { credentials: 'include', ...init });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail; } catch { /* use safe status */ }
    throw new Error(message);
  }
  return (await response.json()).data as T;
}
export function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}
export function eventsUrl(workspaceId: string, runId: string, after = 0): string {
  return `${base}/api/inquiry-workspaces/${encodeURIComponent(workspaceId)}/runs/${encodeURIComponent(runId)}/events?follow=true&after=${after}`;
}
export async function downloadSnapshot(workspaceId: string, snapshotId: string): Promise<void> {
  const url = `${base}/api/inquiry-workspaces/${encodeURIComponent(workspaceId)}/report/snapshots/${encodeURIComponent(snapshotId)}/docx`;
  const response = await fetch(url, { credentials: 'include' });
  if (!response.ok) throw new Error(`下载失败（${response.status}），请检查来源权限和成果状态`);
  const blobUrl = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a'); anchor.href = blobUrl; anchor.download = '教学资源.docx'; anchor.click();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 30000);
}

export async function downloadLesson(workspaceId: string, artifactId: string): Promise<void> {
  const path = `/api/inquiry-workspaces/${encodeURIComponent(workspaceId)}/lesson-document/${encodeURIComponent(artifactId)}/docx`;
  const response = await fetch(base + path, { method: 'POST', credentials: 'include' });
  if (!response.ok) {
    let message = `导出失败（${response.status}）`;
    try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail; } catch { /* retain status */ }
    throw new Error(message);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = '教案.docx'; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
