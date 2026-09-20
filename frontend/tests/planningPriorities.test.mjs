import test from 'node:test'
import assert from 'node:assert/strict'

import {
  DEFAULT_OBJECTIVE_ORDER,
  objectiveGoalLabel,
  objectiveOrder,
  objectivePolicyLabel,
} from '../src/utils/planningPriorities.js'

test('по умолчанию после уровней приоритета идёт максимум заявок', () => {
  assert.deepEqual(objectiveOrder('assigned_requests'), DEFAULT_OBJECTIVE_ORDER)
  assert.equal(objectivePolicyLabel(DEFAULT_OBJECTIVE_ORDER), 'Срочность · максимум заявок')
})

test('диспетчер выбирает, что важнее сразу после уровней приоритета', () => {
  assert.deepEqual(objectiveOrder('engineers_used'), [
    'urgent_requests',
    'engineers_used',
    'assigned_requests',
    'travel_distance',
  ])
  assert.deepEqual(objectiveOrder('travel_distance'), [
    'urgent_requests',
    'travel_distance',
    'assigned_requests',
    'engineers_used',
  ])
  assert.equal(objectivePolicyLabel(objectiveOrder('engineers_used')), 'Срочность · минимум бригад')
  assert.equal(objectivePolicyLabel(objectiveOrder('travel_distance')), 'Срочность · минимум пробега')
})

test('у старых планов заявки могли стоять выше срочности', () => {
  const legacy = ['assigned_requests', 'urgent_requests', 'travel_distance', 'engineers_used']
  assert.equal(objectivePolicyLabel(legacy), 'Максимум заявок · минимум пробега')
})

test('plans without a stored policy have an explicit placeholder', () => {
  assert.equal(objectivePolicyLabel(null), '—')
})

test('в списке планов цель называется коротко', () => {
  assert.equal(objectiveGoalLabel(DEFAULT_OBJECTIVE_ORDER), 'максимум заявок')
  assert.equal(objectiveGoalLabel(objectiveOrder('travel_distance')), 'минимум пробега')
  assert.equal(objectiveGoalLabel(null), '—')
  const legacy = ['assigned_requests', 'urgent_requests', 'travel_distance', 'engineers_used']
  assert.equal(objectiveGoalLabel(legacy), 'максимум заявок (старый порядок)')
})
