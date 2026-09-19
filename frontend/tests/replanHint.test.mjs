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

test('отставание бригад — тоже повод: номера заявок, к которым не успеть', () => {
  const hint = replanHint({ approved_at: APPROVED, withdrawn_requests: [], new_request_ids: [], at_risk_request_ids: [32840] })
  assert.match(hint, /бригады не успевают к окну: №32840/)
})

test('новые аварийные заявки — первым пунктом и без повтора среди новых', () => {
  const hint = replanHint({
    approved_at: APPROVED,
    withdrawn_requests: [],
    new_request_ids: [16, 17],
    urgent_request_ids: [17],
  })
  assert.match(hint, /— новые аварийные заявки: №17; новые заявки дня: №16$/)
})
