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
    throw err
  }
  return json.data
}

export const api = {
  meta: () => request('/api/v1/meta'),
  seasons: () => request('/api/v1/seasons'),
  cup: (cup, day) => request(`/api/v1/cup/${encodeURIComponent(cup)}${day ? `?day=${encodeURIComponent(day)}` : ''}`),
  player: (id, cup, day) => {
    const q = new URLSearchParams()
    if (cup) q.set('cup', cup)
    if (day) q.set('day', day)
    const qs = q.toString()
    return request(`/api/v1/player/${encodeURIComponent(id)}${qs ? `?${qs}` : ''}`)
  },
  login: (body) => request('/api/admin/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request('/api/admin/logout', { method: 'POST' }),
  me: () => request('/api/admin/me'),
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  send: (path, params) => request(path + (path.includes('?') ? '&' : '?') + new URLSearchParams(params)),
}

export function avatarUrl(url) {
  if (!url) return ''
  return `https://wsrv.nl/?url=${encodeURIComponent(url)}`
}
