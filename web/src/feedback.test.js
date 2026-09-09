import test from 'node:test'
import assert from 'node:assert/strict'

import { feedbackPayload, mergeFeedbackReference, relevantFeedbackReferences } from './feedback.js'

test('feedback payload trims public fields and omits empty details', () => {
  const result = feedbackPayload({
    type: 'award_suggestion', subject: '  烟雾大师  ', content: '  看封烟质量  ',
    submitterName: '  秋梨膏  ', context: { type: 'season', id: 'cup' },
    details: { method: '  每回合有效烟  ', empty: '  ' }, sourcePath: '/cup/honours',
  })
  assert.equal(result.subject, '烟雾大师')
  assert.equal(result.content, '看封烟质量')
  assert.equal(result.submitter_name, '秋梨膏')
  assert.deepEqual(result.details, { method: '  每回合有效烟  ' })
})

test('feedback references are de-duplicated, bounded and scoped', () => {
  const entries = Array.from({ length: 20 }, (_, index) => ({
    reference: `old-${index}`, type: 'award_suggestion', context_id: index % 2 ? 'a' : 'b',
  }))
  const merged = mergeFeedbackReference(entries, {
    reference: 'old-4', type: 'award_suggestion', context_id: 'a',
  })
  assert.equal(merged.length, 20)
  assert.equal(merged[0].reference, 'old-4')
  assert.equal(new Set(merged.map((item) => item.reference)).size, 20)
  assert.ok(relevantFeedbackReferences(merged, 'award_suggestion', 'a').every((item) => item.context_id === 'a'))
})
