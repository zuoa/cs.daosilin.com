import test from 'node:test'
import assert from 'node:assert/strict'

import {
  chronologicalDraftSessions,
  draftGroupPlayerCount,
  draftRoute,
  formatDraftClock,
  formatDraftDay,
} from './draft.js'

test('draft date and time labels are stable', () => {
  assert.equal(formatDraftDay('20260903'), '2026.09.03')
  assert.equal(formatDraftClock('2026-09-03T19:57:44'), '19:57')
  assert.equal(formatDraftClock('2026-09-03T19:57:44', true), '19:57:44')
})

test('same-day sessions are ordered chronologically without mutating input', () => {
  const sessions = [
    { id: 2, completed_at: '2026-09-03T20:10:00' },
    { id: 1, completed_at: '2026-09-03T19:00:00' },
  ]
  assert.deepEqual(chronologicalDraftSessions(sessions).map((row) => row.id), [1, 2])
  assert.deepEqual(sessions.map((row) => row.id), [2, 1])
})

test('dynamic matchup counts and routes do not assume five-player teams', () => {
  const group = { teams: [{ roster_size: 4 }, { roster_size: 7 }] }
  assert.equal(draftGroupPlayerCount(group), 11)
  assert.deepEqual(draftRoute('20260903', 8), {
    path: '/draft', query: { day: '20260903', session_id: 8 },
  })
})
