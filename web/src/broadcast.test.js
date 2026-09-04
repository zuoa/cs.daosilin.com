import test from 'node:test'
import assert from 'node:assert/strict'

import {
  broadcastPlayerName,
  clampBroadcastScale,
  formatBroadcastClock,
  formatBroadcastDay,
  isNewBroadcastResult,
  nextBroadcastPanel,
  parseBroadcastOptions,
} from './broadcast.js'

test('broadcast URL options are bounded and predictable', () => {
  assert.deepEqual(parseBroadcastOptions('?anchor=left&scale=1.4&cycle=0&debug=1'), {
    anchor: 'left', scale: 1.25, cycle: false, debug: true,
  })
  assert.deepEqual(parseBroadcastOptions('?anchor=middle&scale=nope'), {
    anchor: 'right', scale: 1, cycle: true, debug: false,
  })
  assert.equal(parseBroadcastOptions('').scale, 1)
  assert.equal(clampBroadcastScale(0.5), 0.75)
})

test('panel navigation wraps in both directions', () => {
  assert.equal(nextBroadcastPanel(2, 1), 0)
  assert.equal(nextBroadcastPanel(0, -1), 2)
  assert.equal(nextBroadcastPanel(1, 1), 2)
})

test('a new completed map is detected only after initial data exists', () => {
  assert.equal(isNewBroadcastResult(null, { latest_match: { match_id: 'm1' } }), false)
  assert.equal(isNewBroadcastResult(
    { latest_match: { match_id: 'm1' } },
    { latest_match: { match_id: 'm2' } },
  ), true)
  assert.equal(isNewBroadcastResult(
    { latest_match: { match_id: 'm2' } },
    { latest_match: { match_id: 'm2' } },
  ), false)
})

test('broadcast labels use stable fallbacks', () => {
  assert.equal(broadcastPlayerName({ alias_name: 'One', nickname: 'Player' }), 'One')
  assert.equal(broadcastPlayerName({ nickname: 'Player' }), 'Player')
  assert.equal(formatBroadcastDay('20260904'), '2026.09.04')
  assert.equal(formatBroadcastClock('2026-09-04T19:08:22'), '19:08')
})
