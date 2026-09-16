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
  const make = new Function('ref', 'watch', 'useMessages', 'useSelectedDay', 'toMoscowInputValue',
    source + '; return useRequestsTable()')
  const table = make(
    (value) => ({ value }),
    () => {},
    () => ({ showError() {}, showNotice() {}, clearMessages() {} }),
    () => ({ selectedDay: { value: '2026-08-17' } }),
    (value) => value,
  )
  table.references.value = { skills: [], priorities: [{ id: 1 }], transports: [], work_types: WORK_TYPES }
  return table
}

test('новая заявка заполняется нормативами первого типа работ', () => {
  const table = harness()
  table.startCreate()

  assert.equal(table.form.value.work_type_id, 1)
  assert.equal(table.form.value.duration_minutes, 70)
  assert.equal(table.form.value.skill_id, 2)
})

test('смена типа работ подставляет его норматив и навык', () => {
  const table = harness()
  table.startCreate()
  table.applyWorkTypeNorms(2)

  assert.equal(table.form.value.duration_minutes, 80)
  assert.equal(table.form.value.skill_id, 3)
})

test('свою длительность после автозаполнения ничто не перетирает', () => {
  const table = harness()
  table.startCreate()
  table.applyWorkTypeNorms(2)
  table.form.value.duration_minutes = 45

  assert.equal(table.form.value.duration_minutes, 45)
  assert.equal(table.form.value.skill_id, 3)
})
