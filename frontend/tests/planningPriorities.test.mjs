import test from 'node:test'
import assert from 'node:assert/strict'

import {
  DEFAULT_OBJECTIVE_ORDER,
  objectiveOrder,
  objectivePolicyLabel,
} from '../src/utils/planningPriorities.js'

test('default policy keeps urgent work and minimum crews first', () => {
  assert.deepEqual(objectiveOrder('urgent_requests', 'engineers_used'), DEFAULT_OBJECTIVE_ORDER)
  assert.equal(objectivePolicyLabel(DEFAULT_OBJECTIVE_ORDER), 'Срочность · минимум бригад')
})

test('dispatcher choices produce a complete safe objective order', () => {
  const order = objectiveOrder('assigned_requests', 'travel_distance')

  assert.deepEqual(order, [
    'assigned_requests',
    'urgent_requests',
    'travel_distance',
    'engineers_used',
  ])
  assert.equal(objectivePolicyLabel(order), 'Максимум заявок · минимум пробега')
})

test('plans without a stored policy have an explicit placeholder', () => {
  assert.equal(objectivePolicyLabel(null), '—')
})
