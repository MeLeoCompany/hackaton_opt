import test from 'node:test'
import assert from 'node:assert/strict'

import { durationText, eventTree, worstLevel } from '../src/utils/runEvents.js'

const events = [
  { id: 1, parent_id: null, level: 'info', message: 'Матрицы', duration_ms: 6167 },
  { id: 2, parent_id: 1, level: 'info', message: 'Valhalla' },
  { id: 3, parent_id: 1, level: 'warning', message: 'R5 не ответил' },
  { id: 4, parent_id: null, level: 'info', message: 'Решатель', duration_ms: 312 },
]

test('плоский журнал превращается в дерево шагов', () => {
  const roots = eventTree(events)

  assert.deepEqual(roots.map((node) => node.id), [1, 4])
  assert.deepEqual(roots[0].children.map((node) => node.id), [2, 3])
  assert.deepEqual(roots[1].children, [])
})

test('у свёрнутого шага виден худший статус внутри', () => {
  const [matrices, solver] = eventTree(events)

  assert.equal(worstLevel(matrices), 'warning')
  assert.equal(worstLevel(solver), 'info')
})

test('длительность шага читается в миллисекундах и секундах', () => {
  assert.equal(durationText({ duration_ms: 312 }), '312 мс')
  assert.equal(durationText({ duration_ms: 6167 }), '6.2 с')
  assert.equal(durationText({ duration_ms: null }), '')
})
