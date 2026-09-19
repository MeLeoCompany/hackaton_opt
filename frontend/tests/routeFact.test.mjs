import test from 'node:test'
import assert from 'node:assert/strict'

import { brigadeNow, routeProgress, visitFactState } from '../src/utils/routeFact.js'

const REFERENCES = {
  request_statuses: [
    { id: 2, code: 'planned' },
    { id: 3, code: 'done' },
    { id: 4, code: 'cancelled' },
    { id: 5, code: 'in_progress' },
    { id: 6, code: 'en_route' },
  ],
}
const visit = (id, status_id, extra = {}) => ({ request_id: id, status_id, approved_plan_id: 22, ...extra })

test('состояние визита по статусу и отметкам бригады', () => {
  assert.equal(visitFactState(visit(1, 3), REFERENCES, 22), 'done')
  assert.equal(visitFactState(visit(1, 6, { departed_at: '2026-08-17T10:00:00Z' }), REFERENCES, 22), 'moving')
  assert.equal(visitFactState(visit(1, 5, { arrived_at: '2026-08-17T10:20:00Z' }), REFERENCES, 22), 'onsite')
  assert.equal(visitFactState(visit(1, 2, { approved_plan_id: null }), REFERENCES, 22), 'removed')
})

test('где бригада: в пути к следующей, на месте, ещё не выехала', () => {
  const moving = { visits: [visit(1, 3), visit(2, 6, { departed_at: '2026-08-17T11:05:00Z' }), visit(3, 2)] }
  const now = brigadeNow(moving, REFERENCES, 22)
  assert.equal(now.kind, 'moving')
  assert.equal(now.previous.request_id, 1)
  assert.equal(now.text, 'в пути к №2 с 14:05')

  assert.equal(brigadeNow({ visits: [visit(1, 2), visit(2, 2)] }, REFERENCES, 22).kind, 'start')
  assert.equal(brigadeNow({ visits: [visit(1, 3), visit(2, 2)] }, REFERENCES, 22).text, 'закрыла №1, ждёт выезда')
  assert.equal(brigadeNow({ visits: [visit(1, 3), visit(2, 4)] }, REFERENCES, 22).kind, 'finished')
})

test('прогресс маршрута: закрытые из всех, снятые с плана не считаются', () => {
  const route = { visits: [visit(1, 3), visit(2, 4), visit(3, 2), visit(4, 2, { approved_plan_id: null })] }
  assert.deepEqual(routeProgress(route, REFERENCES, 22), { done: 2, total: 3 })
})
