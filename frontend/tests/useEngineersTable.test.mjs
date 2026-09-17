import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function harness() {
  const file = fs.readFileSync(new URL('../src/composables/useEngineersTable.js', import.meta.url), 'utf8')
  // всё до первого объявления — импорты, они заменяются аргументами new Function
  const source = file
    .slice(file.indexOf('export const NEW_ENGINEER'))
    .replace('export const NEW_ENGINEER', 'const NEW_ENGINEER')
    .replace('export function', 'function')
  const lists = {}
  const selectedDay = { value: '2026-08-17' }
  const make = new Function(
    'ref', 'watch', 'useMessages', 'useSelectedDay', 'toMoscowInputValue',
    'fetchReferences', 'listEngineers',
    source + '; return useEngineersTable()',
  )
  const table = make(
    (value) => ({ value }),
    () => {},
    () => ({ showError() {}, showNotice() {}, clearMessages() {} }),
    () => ({ selectedDay }),
    (value) => value,
    async () => ({ skills: [], priorities: [], transports: [], work_types: [] }),
    (day) => new Promise((resolve) => { lists[day] = resolve }),
  )
  return { table, lists, selectedDay }
}

test('поздний ответ старого дня не заменяет исполнителей нового дня', async () => {
  const { table, lists, selectedDay } = harness()
  const first = table.load()
  selectedDay.value = '2026-08-18'
  const second = table.load()

  lists['2026-08-18']([{ id: 18 }]); await second
  lists['2026-08-17']([{ id: 17 }]); await first

  assert.deepEqual(table.engineers.value, [{ id: 18 }])
  assert.equal(table.loading.value, false)
})
