import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function harness(listPlanningDays) {
  const source = fs.readFileSync(
    new URL('../src/composables/useSelectedDay.js', import.meta.url),
    'utf8',
  ).replace(/^import .*$/mg, '').replaceAll('export function', 'function')
  const storage = new Map()
  const window = {
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    },
  }
  const make = new Function(
    'ref', 'listPlanningDays', 'window',
    source + '; return useSelectedDay()',
  )
  return make((value) => ({ value }), listPlanningDays, window)
}

test('после временной ошибки список дней можно загрузить повторно', async () => {
  let calls = 0
  const selected = harness(async () => {
    calls += 1
    if (calls === 1) throw new Error('network')
    return [{ plan_date: '2026-08-17', active_requests: 1 }]
  })

  await selected.loadDaysWithRequests()
  await selected.loadDaysWithRequests()

  assert.equal(calls, 2)
  assert.deepEqual(selected.daysWithRequests.value, [
    { plan_date: '2026-08-17', active_requests: 1 },
  ])
})

test('явное обновление заменяет закешированный список дней', async () => {
  let days = [{ plan_date: '2026-08-17', active_requests: 1 }]
  const selected = harness(async () => days)
  await selected.loadDaysWithRequests()

  days = [{ plan_date: '2026-08-18', active_requests: 2 }]
  await selected.refreshDaysWithRequests()

  assert.deepEqual(selected.daysWithRequests.value, days)
})
