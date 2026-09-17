import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

// composable поднимается без Vue и без сети: ref, computed, watch и запрос подменяются заглушками
function harness() {
  const file = fs.readFileSync(new URL('../src/composables/usePlanComparison.js', import.meta.url), 'utf8')
  const source = file
    .slice(file.indexOf('export const COMPARED_METRICS'))
    .replace('export const COMPARED_METRICS', 'const COMPARED_METRICS')
    .replace('export function', 'function')
  const lists = {}
  const make = new Function(
    'ref',
    'computed',
    'watch',
    'listPlans',
    'useMessages',
    'useSelectedDay',
    source + '; return usePlanComparison()',
  )
  const view = make(
    (value) => ({ value }),
    (getter) => ({
      get value() {
        return getter()
      },
    }),
    () => {},
    (day) => new Promise((resolve) => { lists[day] = resolve }),
    () => ({ showError() {}, clearMessages() {} }),
    () => ({ selectedDay: { value: '2026-08-17' } }),
  )
  return { view, lists }
}

const PLANS = [
  { id: 29, solver: 'baseline', assigned_count: 8, urgent_assigned_count: 3, unassigned_count: 2, engineers_used: 5, total_distance_km: 111.3, solve_duration_ms: 0.1 },
  { id: 28, solver: 'cuopt', assigned_count: 9, urgent_assigned_count: 3, unassigned_count: 1, engineers_used: 4, total_distance_km: 122.7, solve_duration_ms: 1914.4 },
]

async function loadedView() {
  const { view, lists } = harness()
  const loaded = view.load()
  lists['2026-08-17'](PLANS)
  await loaded
  return view
}

test('по умолчанию сравниваются два последних плана дня', async () => {
  const view = await loadedView()

  assert.equal(view.loading.value, false)
  assert.deepEqual(view.selectedIds.value, [28, 29])
})

test('сравниваются ровно два плана: третий отметить нельзя', async () => {
  const view = await loadedView()

  assert.equal(view.first.value.solver, 'cuopt')
  assert.equal(view.second.value.solver, 'baseline')
  assert.equal(view.selectionIsFull.value, true)

  view.togglePlan(99) // лишний план не добавляется
  assert.deepEqual(view.selectedIds.value, [28, 29])

  view.togglePlan(28) // сняли отметку — место освободилось
  assert.deepEqual(view.selectedIds.value, [29])
  assert.equal(view.selectionIsFull.value, false)
  assert.equal(view.second.value, null)
})

test('разница считается со стороны второго плана', async () => {
  const view = await loadedView()
  const byKey = Object.fromEntries(view.metrics.value.map((metric) => [metric.key, metric]))

  // план Б — baseline: на одну заявку меньше и на одного исполнителя больше
  assert.equal(byKey.assigned_count.difference, -1)
  assert.equal(byKey.engineers_used.difference, 1)
  assert.equal(byKey.unassigned_count.difference, 1)
})
