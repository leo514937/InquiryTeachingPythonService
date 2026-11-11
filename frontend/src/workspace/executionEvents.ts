export interface ExecutionEvent { sequence: number; kind: string; nodeId: string; }
export function parseExecutionEvents(body: string): ExecutionEvent[] {
  return body.split(/\r?\n\r?\n/).flatMap(block => {
    const fields = block.split(/\r?\n/);
    const sequence = Number(fields.find(line => line.startsWith('id:'))?.slice(3).trim());
    const kind = fields.find(line => line.startsWith('event:'))?.slice(6).trim();
    const raw = fields.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (!Number.isSafeInteger(sequence) || sequence <= 0 || !kind || !raw) return [];
    try { const data: unknown = JSON.parse(raw); if (!data || typeof data !== 'object' || Array.isArray(data)) return []; const nodeId = (data as Record<string,unknown>).node_id; return [{sequence, kind, nodeId: typeof nodeId === 'string' ? nodeId : ''}]; } catch { return []; }
  });
}
export function mergeExecutionEvents(existing: ExecutionEvent[], incoming: ExecutionEvent[]): ExecutionEvent[] {
  const bySequence = new Map(existing.map(event => [event.sequence,event]));
  for (const event of incoming) bySequence.set(event.sequence,event);
  return [...bySequence.values()].sort((a,b) => a.sequence-b.sequence);
}
