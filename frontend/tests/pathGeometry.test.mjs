import test from 'node:test'
import assert from 'node:assert/strict'

import { cumulativeLengths, pointAlong, travelledShare } from '../src/utils/pathGeometry.js'

const PATH = [
  [0, 0],
  [10, 0],
  [10, 10],
]

test('точка вдоль ломаной и направление на её звене', () => {
  const lengths = cumulativeLengths(PATH)
  assert.deepEqual(lengths, [0, 10, 20])
  assert.deepEqual(pointAlong(PATH, lengths, 5), { point: [5, 0], angle: 0 })
  assert.deepEqual(pointAlong(PATH, lengths, 15), { point: [10, 5], angle: 90 })
  // за концом линии — её конец
  assert.deepEqual(pointAlong(PATH, lengths, 99).point, [10, 10])
})

test('пройденная доля участка — по времени в пути, не доезжая до конца', () => {
  const departed = '2026-08-20T10:00:00Z'
  assert.equal(travelledShare(departed, 20, new Date('2026-08-20T10:05:00Z')), 0.25)
  assert.equal(travelledShare(departed, 20, new Date('2026-08-20T11:00:00Z')), 0.9)
  assert.equal(travelledShare(null, 20), 0.5)
})

test('сдвиг линии вбок: параллельно, на изломе — по биссектрисе', async () => {
  const { offsetPath } = await import('../src/utils/pathGeometry.js')
  // на восток по экрану (y вниз): вправо по ходу — это вниз
  assert.deepEqual(offsetPath([[0, 0], [10, 0]], 4), [[0, 4], [10, 4]])
  const bent = offsetPath([[0, 0], [10, 0], [10, 10]], 2)
  assert.deepEqual(bent[0], [0, 2])
  assert.deepEqual(bent[2], [8, 10])
  assert.ok(Math.abs(bent[1][0] - 8) < 1e-9 && Math.abs(bent[1][1] - 2) < 1e-9)
  // повторяющиеся точки не ломают сдвиг
  assert.deepEqual(offsetPath([[0, 0], [0, 0], [10, 0]], 4), [[0, 4], [10, 4]])
})

test('длина линии в километрах', async () => {
  const { lengthKm } = await import('../src/utils/pathGeometry.js')
  // градус широты — около 111 км
  assert.ok(Math.abs(lengthKm([[55, 37], [56, 37]]) - 111.2) < 0.2)
  assert.equal(lengthKm([[55, 37]]), 0)
})
