type Data = Record<string, any>;

/** Merge only local changes over the latest server content, retaining unknown fields. */
export function mergeArtifactDraft(base: Data, local: Data, latest: Data): {content: Data; conflicts: string[]} {
  const conflicts: string[] = [];
  const equal = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);
  const object = (value: unknown): value is Data => !!value && typeof value === 'object' && !Array.isArray(value);
  function merge(original: unknown, ours: unknown, theirs: unknown, path: string): unknown {
    if (equal(ours, original)) return theirs;
    if (equal(theirs, original) || equal(ours, theirs)) return ours;
    if (object(original) && object(ours) && object(theirs)) {
      const result: Data = {};
      for (const key of new Set([...Object.keys(original), ...Object.keys(ours), ...Object.keys(theirs)])) {
        const value = merge(original[key], ours[key], theirs[key], path + '/' + key.replace(/~/g, '~0').replace(/\//g, '~1'));
        if (value !== undefined) result[key] = value;
      }
      return result;
    }
    conflicts.push(path || '/');
    return ours;
  }
  return {content: merge(base, local, latest, '') as Data, conflicts};
}
