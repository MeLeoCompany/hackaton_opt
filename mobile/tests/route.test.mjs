import test from 'node:test'
import assert from 'node:assert/strict'

import { currentVisit, formatDay, moscowTime, nextAction, progress } from '../src/route.js'

const visit = (id, status_code, extra = {}) => ({ request_id: id, status_code, removed: false, ...extra })

test('время по Москве и день по-русски', () => {
  assert.equal(moscowTime('2026-08-17T15:00:00Z'), '18:00')
  assert.equal(formatDay('2026-08-17'), '17 августа, пн')
})

test('текущая — первая незакрытая: выполненные, отменённые и снятые пропускаются', () => {
  const route = {
    visits: [visit(1, 'done'), visit(2, 'planned', { removed: true }), visit(3, 'cancelled'), visit(4, 'planned'), visit(5, 'planned')],
  }
  assert.equal(currentVisit(route).request_id, 4)
  assert.deepEqual(progress(route), { done: 2, total: 4 })
})

test('кнопка у текущей заявки идёт по шагам: выехали → на месте → выполнено', () => {
  assert.equal(nextAction(visit(1, 'planned')).action, 'depart')
  assert.equal(nextAction(visit(1, 'in_progress', { departed_at: 'x' })).action, 'arrive')
  assert.equal(nextAction(visit(1, 'in_progress', { departed_at: 'x', arrived_at: 'y' })).action, 'done')
  assert.equal(nextAction(visit(1, 'done')), null)
})
