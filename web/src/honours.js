export function podiumSlots(entries = []) {
  const byPosition = new Map(entries.map((entry) => [Number(entry.position), entry]))
  return [1, 2, 3].map((position) => ({
    position,
    entry: byPosition.get(position) || null,
  }))
}

export function groupHonours(categories = [], awards = []) {
  return categories.map((category) => ({
    ...category,
    awards: awards.filter((award) => award.category === category.key),
  }))
}

export function honourAnchor(value) {
  return `honour-${String(value || '').replace(/[^a-z0-9-]/gi, '-')}`
}

export function honourSharePath(cup, awardKey) {
  return `/${encodeURIComponent(cup)}/honours#${honourAnchor(awardKey)}`
}

export function honourFilename(cupAlias, title) {
  const safe = `${cupAlias}-${title}`
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
  return `${safe || 'season-honour'}.png`
}

export function honourStatus(status) {
  return status === 'final'
    ? { label: '最终荣誉榜', note: '赛季数据已封存' }
    : { label: '实时预展', note: '随新比赛持续更新' }
}

export function carouselIndex(index, total) {
  if (!total) return 0
  return ((Number(index) % total) + total) % total
}

export function honourIndexByHash(awards = [], hash = '') {
  const anchor = String(hash || '').replace(/^#/, '')
  const index = awards.findIndex((award) => honourAnchor(award.key) === anchor)
  return index < 0 ? 0 : index
}
