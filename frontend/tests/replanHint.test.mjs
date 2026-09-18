import test from 'node:test'
import assert from 'node:assert/strict'

import { replanHint } from '../src/utils/replanHint.js'

const APPROVED = '2026-08-16T18:00:00Z'

test('утверждённый план без изменений пересчитывать незачем', () => {
  assert.equal(replanHint({ approved_at: APPROVED, withdrawn_requests: [], new_request_ids: [] }), '')
})

test('в подсказке — номера снятых и новых заявок', () => {
  const hint = replanHint({
    approved_at: APPROVED,
    withdrawn_requests: [{ request_id: 50104, status_id: 4 }],
    new_request_ids: [16, 17],
  })
  assert.match(hint, /сняты с плана: №50104/)
  assert.match(hint, /новые заявки дня: №16, №17/)
})

test('неутверждённый план знак не получает', () => {
  assert.equal(replanHint({ approved_at: null, withdrawn_requests: [{ request_id: 1, status_id: 4 }] }), '')
})
