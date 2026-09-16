import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const WORK_TYPES = [
  { id: 1, name: 'Подключение клиентов, базовая', skill_id: 2, travel_minutes: 20, work_minutes: 70 },
  { id: 2, name: 'Авария на ТКД', skill_id: 3, travel_minutes: 20, work_minutes: 80 },
]

// composable поднимается без Vue и без сети: ref и всё, что он импортирует, подменяется заглушками
function harness() {
  const file = fs.readFileSync(new URL('../src/composables/useRequestsTable.js', import.meta.url), 'utf8')
  // всё до первого объявления — импорты, они заменяются аргументами new Function
  const source = file
    .slice(file.indexOf('export const NEW_REQUEST'))
    .replace('export const NEW_REQUEST', 'const NEW_REQUEST')
    .replace('export function', 'function')
  const lists = {}
  const selectedDay = { value: '2026-08-17' }
  const make = new Function(
    'ref',
    'watch',
    'useMessages',
    'useSelectedDay',
    'toMoscowInputValue',
    'fetchReferences',
    'listRequests',
    source + '; return useRequestsTable()',
  )
  const table = make(
    (value) => ({ value }),
    () => {},
    () => ({ showError() {}, showNotice() {}, clearMessages() {} }),
    () => ({ selectedDay }),
    (value) => value,
    async () => ({ skills: [], priorities: [], transports: [], work_types: WORK_TYPES }),
    (day) => new Promise((resolve) => { lists[day] = resolve }),
  )
  table.references.value = { skills: [], priorities: [{ id: 1 }], transports: [], work_types: WORK_TYPES }
  return { table, lists, selectedDay }
}

test('новая заявка заполняется нормативами первого типа работ', () => {
  const { table } = harness()
  table.startCreate()

  assert.equal(table.form.value.work_type_id, 1)
  assert.equal(table.form.value.duration_minutes, 70)
  assert.equal(table.form.value.skill_id, 2)
})

test('смена типа работ подставляет его норматив и навык', () => {
  const { table } = harness()
  table.startCreate()
  table.applyWorkTypeNorms(2)

  assert.equal(table.form.value.duration_minutes, 80)
  assert.equal(table.form.value.skill_id, 3)
})

test('свою длительность после автозаполнения ничто не перетирает', () => {
  const { table } = harness()
  table.startCreate()
  table.applyWorkTypeNorms(2)
  table.form.value.duration_minutes = 45

  assert.equal(table.form.value.duration_minutes, 45)
  assert.equal(table.form.value.skill_id, 3)
})

test('поздний ответ старого дня не заменяет заявки нового дня', async () => {
  const { table, lists, selectedDay } = harness()
  const first = table.load()
  selectedDay.value = '2026-08-18'
  const second = table.load()

  lists['2026-08-18']([{ id: 18 }]); await second
  lists['2026-08-17']([{ id: 17 }]); await first

  assert.deepEqual(table.requests.value, [{ id: 18 }])
  assert.equal(table.loading.value, false)
})
