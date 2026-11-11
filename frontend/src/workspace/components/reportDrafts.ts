export function mergeDrafts(drafts: Record<string, string>, baselines: Record<string, string>, incoming: Record<string, string>) {
  const merged: Record<string, string> = {};
  for (const [id, value] of Object.entries(incoming)) {
    merged[id] = id in drafts && drafts[id] !== baselines[id] ? drafts[id] : value;
  }
  return merged;
}
