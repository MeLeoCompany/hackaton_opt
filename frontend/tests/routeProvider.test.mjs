import test from 'node:test'
import assert from 'node:assert/strict'

import { estimateNote, isApproximate, providerTitle } from '../src/utils/routeProvider.js'

test('маршрут по расписанию R5 — настоящий расчёт, а не оценка по прямой', () => {
  assert.equal(isApproximate('r5'), false)
  assert.equal(estimateNote('r5'), '')
  assert.match(providerTitle('r5'), /расписанию/)
})

test('Valhalla и R5 вместе — тоже не приближённо', () => {
  assert.equal(isApproximate('valhalla'), false)
  assert.equal(isApproximate('routed'), false)
})

test('оценка — только когда маршрутизатор не ответил', () => {
  assert.equal(isApproximate('haversine'), true)
  assert.equal(estimateNote('haversine'), 'оценка по прямой')
  assert.equal(isApproximate('transit_estimate'), true)
  assert.equal(isApproximate('mixed'), true)
})
