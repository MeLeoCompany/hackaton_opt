import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function harness() {
  const file = fs.readFileSync(new URL('../src/composables/useDayPlanWarning.js', import.meta.url), 'utf8')
  const source = file.slice(file.indexOf('export function')).replace('export function', 'function')
  const day = { value: '2026-09-20' }
  const pending = new Map()
  const make = new Function(
    'computed', 'ref', 'listPlans', 'replanHint', 'useSelectedDay',
    `${source}; return useDayPlanWarning()`,
  )
  const warning = make(
    getter => ({ get value() { return getter() } }),
    value => ({ value }),
    planDate => new Promise((resolve, reject) => { pending.set(planDate, { resolve, reject }) }),
    plan => plan?.new_request_ids?.length ? 'Есть новые заявки' : '',
    () => ({ selectedDay: day }),
  )
  return { warning, day, pending }
}

test('поздний ответ предыдущего дня не показывает чужое предупреждение', async () => {
  const { warning, day, pending } = harness()
  const oldLoad = warning.load()
  day.value = '2026-09-21'
  const newLoad = warning.load()
  pending.get('2026-09-21').resolve([{ id: 2, approved_at: 'now', new_request_ids: [] }])
  await newLoad
  pending.get('2026-09-20').resolve([{ id: 1, approved_at: 'now', new_request_ids: [3] }])
  await oldLoad

  assert.equal(warning.planSummary.value.id, 2)
  assert.equal(warning.needsReplan.value, false)
})

test('повторная загрузка очищает старое предупреждение до ответа', async () => {
  const { warning, pending } = harness()
  const first = warning.load()
  pending.get('2026-09-20').resolve([{ id: 1, approved_at: 'now', new_request_ids: [3] }])
  await first
  assert.equal(warning.needsReplan.value, true)

  const refresh = warning.load()
  assert.equal(warning.needsReplan.value, false)
  pending.get('2026-09-20').resolve([])
  await refresh
  assert.equal(warning.planSummary.value, null)
})

test('посчитанный, но не утверждённый пересчёт показывается вместо «пересчитайте»', async () => {
  const { warning, pending } = harness()
  const load = warning.load()
  pending.get('2026-09-20').resolve([
    { id: 54, approved_at: 'now', new_request_ids: [3] },
    { id: 59, parent_plan_id: 54, approved_at: null },
  ])
  await load

  assert.equal(warning.planSummary.value.id, 54)
  assert.equal(warning.pendingReplan.value.id, 59)
  assert.equal(warning.needsReplan.value, true)
})
