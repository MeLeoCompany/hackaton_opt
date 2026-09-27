import test from 'node:test'
import assert from 'node:assert/strict'

import { SOLVER_FIELDS, SOLVER_ROWS, limitFor, limitHint, numericParams, paramText } from '../src/utils/solverParams.js'

const params = {
  time_limit_seconds: 2,
  seconds_per_location: 0.2,
  free_locations: 20,
  max_time_limit_seconds: 20,
  distance_weight: 1,
  transit_attempts: 4,
  equipment_reserve: 2,
}

test('время поиска растёт с размером дня и упирается в максимум', () => {
  assert.equal(limitFor(params, 7), 2) // маленькому дню хватает базового времени
  assert.equal(limitFor(params, 50), 6) // 30 точек сверх бесплатных по 0.2 с
  assert.equal(limitFor(params, 1000), 20) // выше максимума не поднимаемся
})

test('значения формы приводятся к числам перед отправкой', () => {
  const typed = Object.fromEntries(SOLVER_FIELDS.map((field) => [field.key, `${params[field.key]}`]))

  assert.deepEqual(numericParams({ ...typed, verbose_log: undefined }), {
    ...params,
    verbose_log: false,
  })
})

test('в таблице параметров — все числовые поля и подробный лог', () => {
  assert.deepEqual(
    SOLVER_ROWS.map((row) => row.key),
    [...SOLVER_FIELDS.map((field) => field.key), 'verbose_log'],
  )
  assert.equal(paramText('verbose_log', true), 'включён')
  assert.equal(paramText('verbose_log', false), 'выключен')
  assert.equal(paramText('time_limit_seconds', 1), '1')
})

test('подсказка считает время поиска по набранным значениям', () => {
  assert.equal(limitHint(params), 'День из 20 точек будет искаться 2 с, из 200 точек — 20 с')
  assert.equal(limitHint({ ...params, time_limit_seconds: 'abc' }), '')
})
