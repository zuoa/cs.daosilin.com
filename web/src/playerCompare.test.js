import test from 'node:test'
import assert from 'node:assert/strict'

import {
  PLAYER_COMPARE_LIMIT,
  addComparedPlayer,
  clearComparedPlayers,
  compareRoute,
  getComparedPlayers,
  hydrateComparedPlayers,
  parseCompareIds,
  replaceComparedPlayers,
} from './playerCompare.js'
import {
  formatPlayerMetric,
  leadingPlayerIds,
  metricHasDifference,
  signedPercent,
} from './playerMetrics.js'

test('compare ids are de-duplicated and capped at four', () => {
  assert.deepEqual(parseCompareIds('p1,p2,p1,p3,p4,p5'), ['p1', 'p2', 'p3', 'p4'])
  assert.equal(PLAYER_COMPARE_LIMIT, 4)
})

test('selection is isolated by season and day', () => {
  clearComparedPlayers('cup-a', '')
  clearComparedPlayers('cup-a', 'day-1')
  addComparedPlayer('cup-a', '', { player_id: 'p1', alias_name: 'One' })
  addComparedPlayer('cup-a', 'day-1', { player_id: 'p2', alias_name: 'Two' })
  assert.deepEqual(getComparedPlayers('cup-a', '').map((item) => item.player_id), ['p1'])
  assert.deepEqual(getComparedPlayers('cup-a', 'day-1').map((item) => item.player_id), ['p2'])
})

test('selection rejects a fifth player and keeps first four', () => {
  clearComparedPlayers('limit-cup', '')
  replaceComparedPlayers('limit-cup', '', ['p1', 'p2', 'p3', 'p4'])
  const result = addComparedPlayer('limit-cup', '', 'p5')
  assert.deepEqual(result, { ok: false, reason: 'limit' })
  assert.deepEqual(getComparedPlayers('limit-cup', '').map((item) => item.player_id), ['p1', 'p2', 'p3', 'p4'])
})

test('hydration restores full comparison metrics from current scope data', () => {
  replaceComparedPlayers('hydrate-cup', '', [
    { player_id: 'p1', nickname: 'Stored summary' },
    { player_id: 'stale', nickname: 'No longer in scope' },
  ])
  hydrateComparedPlayers('hydrate-cup', '', [{ player_id: 'p1', nickname: 'Current player', avg_pw_rating: 1.57 }])
  assert.equal(getComparedPlayers('hydrate-cup', '')[0].avg_pw_rating, 1.57)
  assert.equal(getComparedPlayers('hydrate-cup', '').length, 1)
})

test('share route keeps season, day and selected ids', () => {
  assert.deepEqual(compareRoute('major-1', '20260101', ['p1', 'p2']), {
    path: '/compare/major-1/20260101',
    query: { ids: 'p1,p2' },
  })
})

test('higher and lower metrics mark ties without treating missing as zero', () => {
  const players = [
    { player_id: 'p1', rating: 1.2, deaths: 0.6 },
    { player_id: 'p2', rating: 1.2, deaths: 0.7 },
    { player_id: 'p3', rating: null, deaths: null },
  ]
  const higher = { key: 'rating', direction: 'higher', format: (value) => value == null ? '—' : value.toFixed(2) }
  const lower = { key: 'deaths', direction: 'lower', format: (value) => value == null ? '—' : value.toFixed(2) }
  assert.deepEqual(leadingPlayerIds(higher, players), ['p1', 'p2'])
  assert.deepEqual(leadingPlayerIds(lower, players), ['p1'])
  assert.equal(formatPlayerMetric(higher, players[2]), '—')
  assert.equal(metricHasDifference(higher, players), true)
})

test('round swing percentage keeps its sign and percentage-point scale', () => {
  assert.equal(signedPercent(4.0056), '+4.01%')
  assert.equal(signedPercent(-0.5), '-0.50%')
  assert.equal(signedPercent(0), '0.00%')
  assert.equal(signedPercent(null), '—')
})
