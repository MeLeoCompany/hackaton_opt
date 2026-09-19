import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

import { isAtOffice } from '../src/utils/officePoint.js'

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
    'fetchReferences', 'listEngineers', 'isAtOffice', 'listBrigades',
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
    isAtOffice,
    async () => [{ id: 7, name: 'Бригада Соколов', is_active: true }],
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

test('новая бригада по умолчанию стоит в своём офисе', async () => {
  const { table } = harness()
  table.references.value = {
    skills: [],
    priorities: [],
    transports: [{ id: 1, name: 'Автомобиль' }],
    work_types: [],
    offices: [{ id: 3, name: 'Югоцентр', address: 'проезд Симферопольский, 7', latitude: 55.664757, longitude: 37.615839 }],
  }

  table.startCreate()

  assert.equal(table.form.value.start_latitude, 55.664757)
  assert.equal(table.form.value.start_longitude, 37.615839)
})

test('без офиса в справочнике координаты старта пустые', () => {
  const { table } = harness()
  table.references.value = { skills: [], priorities: [], transports: [], work_types: [] }

  table.startCreate()

  assert.equal(table.form.value.start_latitude, '')
})
