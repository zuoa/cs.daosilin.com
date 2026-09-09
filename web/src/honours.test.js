import test from 'node:test'
import assert from 'node:assert/strict'

import {
  groupHonours,
  honourAnchor,
  honourFilename,
  honourSharePath,
  honourStatus,
  podiumSlots,
} from './honours.js'

test('podium slots retain semantic first-to-third order and fill gaps', () => {
  const slots = podiumSlots([{ position: 2, player_id: 'p2' }])
  assert.deepEqual(slots.map((slot) => slot.position), [1, 2, 3])
  assert.equal(slots[0].entry, null)
  assert.equal(slots[1].entry.player_id, 'p2')
})

test('honours group into the server category order', () => {
  const groups = groupHonours(
    [{ key: 'one', label: '一' }, { key: 'two', label: '二' }],
    [{ key: 'b', category: 'two' }, { key: 'a', category: 'one' }],
  )
  assert.deepEqual(groups.map((group) => group.awards.map((award) => award.key)), [['a'], ['b']])
})

test('share paths, anchors and filenames are safe and stable', () => {
  assert.equal(honourAnchor('first/death'), 'honour-first-death')
  assert.equal(honourSharePath('秋季 杯', 'first-death'), '/%E7%A7%8B%E5%AD%A3%20%E6%9D%AF/honours#honour-first-death')
  assert.equal(honourFilename('秋季杯', 'Rating 心电图'), '秋季杯-Rating-心电图.png')
  assert.equal(honourFilename('', ''), 'season-honour.png')
})

test('status copy distinguishes provisional and final boards', () => {
  assert.equal(honourStatus('provisional').label, '实时预展')
  assert.equal(honourStatus('final').label, '最终荣誉榜')
})
