import { computed, reactive, unref } from 'vue'

export const PLAYER_COMPARE_LIMIT = 4
export const PLAYER_COMPARE_MINIMUM = 2

const STORAGE_KEY = 'cs-player-compare:v1'
const scopes = reactive(loadStoredScopes())

function storageAvailable() {
  try {
    return typeof window !== 'undefined' && Boolean(window.sessionStorage)
  } catch {
    return false
  }
}

function loadStoredScopes() {
  if (!storageAvailable()) return {}
  try {
    const value = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}')
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  } catch {
    return {}
  }
}

function persist() {
  if (!storageAvailable()) return
  try {
    const snapshots = Object.fromEntries(Object.entries(scopes).map(([key, players]) => [
      key,
      (players || []).map(comparePlayerSnapshot),
    ]))
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshots))
  } catch {
    // The comparison still works in memory when storage is blocked or full.
  }
}

export function compareScopeKey(cup, day = '') {
  return `${String(cup || '')}::${String(day || 'all')}`
}

export function normalizeComparePlayer(player) {
  if (player == null) return null
  const source = typeof player === 'object' ? player : { player_id: player }
  const playerId = String(source.player_id ?? source.id ?? '').trim()
  if (!playerId) return null
  return {
    ...source,
    player_id: playerId,
    alias_name: source.alias_name || '',
    nickname: source.nickname || '',
    avatar: source.avatar || '',
    team_name: source.team_name || '',
  }
}

function comparePlayerSnapshot(player) {
  return {
    player_id: player.player_id,
    alias_name: player.alias_name || '',
    nickname: player.nickname || '',
    avatar: player.avatar || '',
    team_name: player.team_name || '',
  }
}

export function parseCompareIds(value) {
  const raw = Array.isArray(value) ? value.join(',') : String(value || '')
  return [...new Set(raw.split(',').map((item) => item.trim()).filter(Boolean))]
    .slice(0, PLAYER_COMPARE_LIMIT)
}

export function compareRoute(cup, day, ids) {
  const normalized = parseCompareIds(ids)
  return {
    path: `/compare/${encodeURIComponent(String(cup || ''))}${day ? `/${encodeURIComponent(String(day))}` : ''}`,
    query: normalized.length ? { ids: normalized.join(',') } : {},
  }
}

function ensureScope(cup, day) {
  const key = compareScopeKey(cup, day)
  if (!Array.isArray(scopes[key])) scopes[key] = []
  return scopes[key]
}

export function getComparedPlayers(cup, day = '') {
  return ensureScope(cup, day)
}

export function addComparedPlayer(cup, day, player) {
  const normalized = normalizeComparePlayer(player)
  if (!normalized) return { ok: false, reason: 'invalid' }
  const list = ensureScope(cup, day)
  if (list.some((item) => item.player_id === normalized.player_id)) {
    return { ok: true, reason: 'exists' }
  }
  if (list.length >= PLAYER_COMPARE_LIMIT) return { ok: false, reason: 'limit' }
  list.push(normalized)
  persist()
  return { ok: true, reason: 'added' }
}

export function removeComparedPlayer(cup, day, playerId) {
  const list = ensureScope(cup, day)
  const index = list.findIndex((item) => item.player_id === String(playerId))
  if (index < 0) return false
  list.splice(index, 1)
  persist()
  return true
}

export function clearComparedPlayers(cup, day = '') {
  const list = ensureScope(cup, day)
  if (!list.length) return
  list.splice(0)
  persist()
}

export function replaceComparedPlayers(cup, day, players) {
  const key = compareScopeKey(cup, day)
  const normalized = []
  for (const player of players || []) {
    const item = normalizeComparePlayer(player)
    if (!item || normalized.some((entry) => entry.player_id === item.player_id)) continue
    normalized.push(item)
    if (normalized.length === PLAYER_COMPARE_LIMIT) break
  }
  scopes[key] = normalized
  persist()
  return normalized
}

export function hydrateComparedPlayers(cup, day, candidates) {
  const byId = new Map((candidates || []).map((player) => [String(player.player_id), player]))
  const hydrated = ensureScope(cup, day).map((item) => byId.get(item.player_id)).filter(Boolean)
  return replaceComparedPlayers(cup, day, hydrated)
}

export function isPlayerCompared(cup, day, playerId) {
  return ensureScope(cup, day).some((item) => item.player_id === String(playerId))
}

export function usePlayerCompare(cup, day = '') {
  const selected = computed(() => getComparedPlayers(unref(cup), unref(day)))
  const selectedIds = computed(() => selected.value.map((item) => item.player_id))
  return {
    selected,
    selectedIds,
    add: (player) => addComparedPlayer(unref(cup), unref(day), player),
    remove: (playerId) => removeComparedPlayer(unref(cup), unref(day), playerId),
    clear: () => clearComparedPlayers(unref(cup), unref(day)),
    includes: (playerId) => isPlayerCompared(unref(cup), unref(day), playerId),
  }
}
