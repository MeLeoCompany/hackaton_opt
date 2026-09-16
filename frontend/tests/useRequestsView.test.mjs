import test from 'node:test'
import assert from 'node:assert/strict'

// Во Vue computed и watch реактивны; для проверки порядка строк достаточно простых заглушек:
// computed пересчитывается при каждом чтении, watch ничего не делает.
async function harness(requests) {
  const vue = {
    ref: (value) => ({ value }),
    reactive: (value) => value,
    computed: (getter) => ({
      get value() {
        return getter()
      },
    }),
    watch: () => {},
  }
  globalThis.__vueStub = vue
  const moduleUrl = new URL('../src/composables/useRequestsView.js', import.meta.url)
  const fs = await import('node:fs')
  const source = fs
    .readFileSync(moduleUrl, 'utf8')
    .replace("import { computed, reactive, ref, watch } from 'vue'", 'const { computed, reactive, ref, watch } = globalThis.__vueStub')
    .replace("from '../utils/", `from '${new URL('../src/utils/', import.meta.url).href}`)
    .replace("from '../utils/", `from '${new URL('../src/utils/', import.meta.url).href}`)
  const dataUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
  const { useRequestsView } = await import(dataUrl)
  return useRequestsView({ value: requests }, { value: { priorities: [], transports: [], work_types: [] } })
}

const REQUESTS = [
  { id: 3, address: 'В', duration_minutes: 30, window_start: '2026-08-17T07:00:00Z', is_active: true },
  { id: 1, address: 'Б', duration_minutes: 90, window_start: '2026-08-17T08:00:00Z', is_active: true },
  { id: 2, address: 'А', duration_minutes: 60, window_start: '2026-08-17T09:00:00Z', is_active: true },
]

const ids = (view) => view.pageRequests.value.map((request) => request.id)

test('по умолчанию строки идут в порядке бэкенда', async () => {
  const view = await harness(REQUESTS)
  assert.equal(view.sortKey.value, '')
  assert.deepEqual(ids(view), [3, 1, 2])
})

test('клики по колонке: по возрастанию, по убыванию, обратно как по умолчанию', async () => {
  const view = await harness(REQUESTS)

  view.toggleSort('duration_minutes')
  assert.deepEqual(ids(view), [3, 2, 1])

  view.toggleSort('duration_minutes')
  assert.deepEqual(ids(view), [1, 2, 3])

  view.toggleSort('duration_minutes')
  assert.equal(view.sortKey.value, '')
  assert.deepEqual(ids(view), [3, 1, 2])
})

test('другая колонка всегда начинает с возрастания', async () => {
  const view = await harness(REQUESTS)
  view.toggleSort('duration_minutes')
  view.toggleSort('duration_minutes')
  view.toggleSort('address')
  assert.equal(view.sortDirection.value, 'asc')
  assert.deepEqual(ids(view), [2, 1, 3])
})
