export function artifactDraftDirty(artifact: {type: string; content: Record<string, unknown>} | null, title: string, description: string) {
  if (!artifact) return false;
  const existing = artifact.type === 'InquiryQuestion' ? artifact.content.question : artifact.content.description;
  return title !== String(artifact.content.title || '') || description !== String(existing || '');
}
