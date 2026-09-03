export function formatDraftDay(value) {
  const day = String(value || '')
  return day.length === 8 ? `${day.slice(0, 4)}.${day.slice(4, 6)}.${day.slice(6)}` : day
}

export function formatDraftClock(value, includeSeconds = false) {
  const text = String(value || '').replace('T', ' ')
  return text.slice(11, includeSeconds ? 19 : 16) || '-'
}

export function chronologicalDraftSessions(sessions) {
  return [...(sessions || [])].sort((left, right) => (
    String(left.completed_at || '').localeCompare(String(right.completed_at || ''))
  ))
}

export function draftGroupPlayerCount(group) {
  return (group?.teams || []).reduce(
    (sum, team) => sum + Number(team.roster_size || 0), 0,
  )
}

export function draftRoute(day, sessionId) {
  const query = {}
  if (day) query.day = day
  if (sessionId) query.session_id = sessionId
  return { path: '/draft', query }
}
