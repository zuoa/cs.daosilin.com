export const FEEDBACK_STORAGE_KEY = 'cs-feedback-references-v1'

export function feedbackPayload({
  type,
  subject,
  content,
  submitterName = '',
  context = {},
  details = {},
  sourcePath = '',
  website = '',
}) {
  return {
    type,
    subject: String(subject || '').trim(),
    content: String(content || '').trim(),
    submitter_name: String(submitterName || '').trim(),
    context,
    details: Object.fromEntries(
      Object.entries(details).filter(([, value]) => String(value || '').trim()),
    ),
    source_path: sourcePath,
    _website: website,
  }
}

export function mergeFeedbackReference(entries = [], entry) {
  if (!entry?.reference) return entries
  return [entry, ...entries.filter((item) => item.reference !== entry.reference)].slice(0, 20)
}

export function relevantFeedbackReferences(entries = [], type, contextId) {
  return entries.filter((item) => item.type === type && item.context_id === contextId).slice(0, 8)
}
