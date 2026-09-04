async function request(path, options = {}) {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const json = await res.json().catch(() => ({}))
  if (res.status === 401) {
    if (!path.startsWith('/api/admin/login') && location.pathname.startsWith('/admin') && location.pathname !== '/admin/login') {
      location.href = '/admin/login'
    }
    const err = new Error(json.message || '未登录')
    err.status = 401
    throw err
  }
  if (!res.ok || json.success === false) {
    const err = new Error(json.message || '请求失败')
    err.status = res.status
    err.data = json.data
    throw err
  }
  return json.data
}

export const api = {
  meta: () => request('/api/v1/meta'),
  seasons: () => request('/api/v1/seasons'),
  draft: (day, sessionId) => {
    const q = new URLSearchParams()
    if (day) q.set('day', day)
    if (sessionId) q.set('session_id', sessionId)
    const query = q.toString()
    return request(`/api/v1/draft${query ? `?${query}` : ''}`)
  },
  cup: (cup, day) => request(`/api/v1/cup/${encodeURIComponent(cup)}${day ? `?day=${encodeURIComponent(day)}` : ''}`),
  liveStatuses: (playerIds) => request(
    `/api/v1/live-status?${new URLSearchParams({ player_ids: playerIds.join(',') })}`,
  ),
  player: (id, cup, day) => {
    const q = new URLSearchParams()
    if (cup) q.set('cup', cup)
    if (day) q.set('day', day)
    const qs = q.toString()
    return request(`/api/v1/player/${encodeURIComponent(id)}${qs ? `?${qs}` : ''}`)
  },
  playerCommunityRating: (id, cup) => request(
    `/api/v1/player/${encodeURIComponent(id)}/community-rating?${new URLSearchParams({ cup })}`,
  ),
  ratePlayer: (id, cup, score) => request(
    `/api/v1/player/${encodeURIComponent(id)}/community-rating?${new URLSearchParams({ cup })}`,
    { method: 'POST', body: JSON.stringify({ score }) },
  ),
  match: (matchId, cup) => request(`/api/v1/match?${new URLSearchParams({ match_id: matchId, cup })}`),
  login: (body) => request('/api/admin/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request('/api/admin/logout', { method: 'POST' }),
  me: () => request('/api/admin/me'),
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
  form: (path, body) => request(path, { method: 'POST', body, headers: {} }),
  send: (path, params) => request(path + (path.includes('?') ? '&' : '?') + new URLSearchParams(params)),
}

export function avatarUrl(url) {
  if (!url) return ''
  return `https://wsrv.nl/?url=${encodeURIComponent(url)}`
}
