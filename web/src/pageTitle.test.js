import test from 'node:test'
import assert from 'node:assert/strict'

import { nextDocumentTitle } from './pageTitle.js'

test('first navigation keeps the server-rendered title', () => {
  const serverTitle = '哈哈明｜鲨鱼MAJOR S2 赛季数据、Rating 与 K/D｜熊掌CS Major'
  assert.equal(
    nextDocumentTitle({ meta: {} }, serverTitle, true),
    serverTitle,
  )
  assert.equal(
    nextDocumentTitle({ meta: { title: '从夯到拉排名' } }, serverTitle, true),
    serverTitle,
  )
})

test('player routes do not fall back to the site name', () => {
  const current = '哈哈明｜鲨鱼MAJOR S2 赛季数据、Rating 与 K/D｜熊掌CS Major'
  assert.equal(nextDocumentTitle({ meta: {} }, current, false), current)
})

test('static meta titles apply after the first navigation', () => {
  assert.equal(
    nextDocumentTitle({ meta: { title: '管理登录' } }, '哈哈明｜赛季', false),
    '管理登录 · 熊掌CS Major',
  )
})
