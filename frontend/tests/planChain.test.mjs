import test from 'node:test'
import assert from 'node:assert/strict'

import { planChain } from '../src/utils/planChain.js'

const plans = [
  { id: 41, parent_plan_id: 22 },
  { id: 22, parent_plan_id: 19, replaced_by_plan_id: 41, superseded_at: '2026-08-17T15:42:00+03:00' },
  { id: 19, replaced_by_plan_id: 22, superseded_at: '2026-08-17T12:05:00+03:00' },
  { id: 20 },
]

test('цепочка планов дня строится от исходного к действующему', () => {
  const ids = (planId) => planChain(plans, planId).map((plan) => plan.id)
  assert.deepEqual(ids(22), [19, 22, 41])
  assert.deepEqual(ids(19), [19, 22, 41])
  assert.deepEqual(ids(41), [19, 22, 41])
})

test('одиночный план и неизвестный номер цепочки не дают', () => {
  assert.deepEqual(planChain(plans, 20), [])
  assert.deepEqual(planChain(plans, 99), [])
})

test('неутверждённый пересчёт виден в конце цепочки', () => {
  const pending = [{ id: 22, replaced_by_plan_id: null }, { id: 50, parent_plan_id: 22 }]
  assert.deepEqual(planChain(pending, 50).map((plan) => plan.id), [22, 50])
})
