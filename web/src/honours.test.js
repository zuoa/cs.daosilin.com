import test from 'node:test'
import assert from 'node:assert/strict'

import {
  DEFAULT_HONOURS_VIEW,
  carouselIndex,
  groupHonours,
  honourAnchor,
  honourFilename,
  honourIndexByHash,
  honourPosterOptions,
  honourSharePath,
  honourStatus,
  podiumSlots,
} from './honours.js'

test('honours open in the item-by-item carousel by default', () => {
  assert.equal(DEFAULT_HONOURS_VIEW, 'carousel')
})

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

test('poster export keeps avatar proxy query strings in the image cache key', () => {
  const options = honourPosterOptions()

  assert.equal(options.width, 768)
  assert.equal(options.height, 1024)
  assert.equal(options.includeQueryParams, true)
  assert.equal(options.cacheBust, true)
})

test('status copy distinguishes provisional and final boards', () => {
  assert.equal(honourStatus('provisional').label, '实时预展')
  assert.equal(honourStatus('final').label, '最终荣誉榜')
})

test('carousel navigation wraps and resolves an award hash', () => {
  const awards = [{ key: 'gold' }, { key: 'duo-slump' }, { key: 'best-ct' }]

  assert.equal(carouselIndex(-1, awards.length), 2)
  assert.equal(carouselIndex(3, awards.length), 0)
  assert.equal(honourIndexByHash(awards, '#honour-duo-slump'), 1)
  assert.equal(honourIndexByHash(awards, '#missing'), 0)
})
