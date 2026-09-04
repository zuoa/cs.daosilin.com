export const BROADCAST_PANEL_DURATIONS = [12_000, 10_000, 8_000]

export function clampBroadcastScale(value) {
  if (value == null || value === '') return 1
  const number = Number(value)
  if (!Number.isFinite(number)) return 1
  return Math.min(1.25, Math.max(0.75, number))
}

export function parseBroadcastOptions(search = '') {
  const params = new URLSearchParams(search)
  return {
    anchor: params.get('anchor') === 'left' ? 'left' : 'right',
    scale: clampBroadcastScale(params.get('scale')),
    cycle: params.get('cycle') !== '0',
    debug: params.get('debug') === '1',
  }
}

export function nextBroadcastPanel(current, direction = 1, count = 3) {
  const size = Math.max(1, Number(count) || 1)
  return ((Number(current) + Number(direction)) % size + size) % size
}

export function isNewBroadcastResult(previous, next) {
  const previousId = previous?.latest_match?.match_id
  const nextId = next?.latest_match?.match_id
  return Boolean(previousId && nextId && previousId !== nextId)
}

export function broadcastPlayerName(player) {
  return player?.alias_name || player?.nickname || player?.player_id || '待确认'
}

export function formatBroadcastDay(value) {
  const day = String(value || '').replace(/\D/g, '')
  if (day.length !== 8) return value || '—'
  return `${day.slice(0, 4)}.${day.slice(4, 6)}.${day.slice(6)}`
}

export function formatBroadcastClock(value) {
  const text = String(value || '').replace('T', ' ')
  return text.slice(11, 16) || '—'
}
