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
  // что ушло в PATCH /requests/status; statusReply подменяют тесты — ответ или ошибка
  const statusCalls = [], notices = [], errors = []
  const statusReply = { respond: async () => ({ updated: 1 }) }
  const make = new Function(
    'ref',
    'watch',
    'useMessages',
    'useSelectedDay',
    'toMoscowInputValue',
    'fetchReferences',
    'listRequests',
    'setRequestsStatus',
    'referenceName',
    'duplicateRequest',
    'equipmentPayload',
    source + '; return useRequestsTable()',
  )
  const table = make(
    (value) => ({ value }),
    () => {},
    () => ({
      showError: (error) => errors.push(error.message),
      showNotice: (notice) => notices.push(notice),
      clearMessages() {},
    }),
    () => ({ selectedDay, refreshDaysWithRequests: async () => {} }),
    (value) => value,
    async () => ({ skills: [], priorities: [], transports: [], work_types: WORK_TYPES }),
    (day) => new Promise((resolve) => { lists[day] = resolve }),
    (requestIds, statusId) => {
      statusCalls.push([requestIds, statusId])
      return statusReply.respond()
    },
    (references, listName, id) => references[listName].find((item) => item.id === id).name,
    async (requestId) => ({ id: requestId + 1 }),
    (value) => value,
  )
  table.references.value = { skills: [], priorities: [{ id: 1 }], transports: [], work_types: WORK_TYPES }
  return { table, lists, selectedDay, statusCalls, statusReply, notices, errors }
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

const STATUSES = [
  { id: 1, code: 'new', name: 'Новая', plannable: true },
  { id: 2, code: 'planned', name: 'В плане', plannable: true },
  { id: 3, code: 'done', name: 'Выполнена', plannable: false },
]

test('смена статуса меняет заявку в списке и её участие в планировании', async () => {
  const { table, statusCalls, notices } = harness()
  table.references.value.request_statuses = STATUSES
  table.requests.value = [
    { id: 1, status_id: 2, is_active: true },
    { id: 2, status_id: 2, is_active: true },
  ]

  await table.setStatus([1], 3)

  assert.deepEqual(statusCalls, [[[1], 3]])
  assert.deepEqual(table.requests.value, [
    { id: 1, status_id: 3, is_active: false, approved_plan_id: undefined },
    { id: 2, status_id: 2, is_active: true },
  ])
  assert.deepEqual(notices, ['Заявка №1: «Выполнена»'])
})

test('запрет смены статуса (разрыв в маршруте) показывается, заявки не меняются', async () => {
  const { table, statusReply, errors } = harness()
  table.references.value.request_statuses = STATUSES
  table.requests.value = [{ id: 2, status_id: 2, is_active: true }]
  statusReply.respond = async () => {
    throw new Error('Проверьте данные')
  }

  await table.setStatus([2], 3)

  assert.deepEqual(table.requests.value, [{ id: 2, status_id: 2, is_active: true }])
  assert.deepEqual(errors, ['Проверьте данные'])
})

test('возвращённая в «Новая» заявка отвязывается от плана', async () => {
  const { table } = harness()
  table.references.value.request_statuses = STATUSES
  table.requests.value = [{ id: 7, status_id: 4, is_active: false, approved_plan_id: 22 }]

  await table.setStatus([7], 1)

  assert.deepEqual(table.requests.value, [{ id: 7, status_id: 1, is_active: true, approved_plan_id: null }])
})

test('копия отменённой заявки сразу открывается на правку', async () => {
  const { table, lists, notices } = harness()
  const copying = table.duplicate({ id: 7 })
  await Promise.resolve()
  await Promise.resolve()
  lists['2026-08-17']([
    { id: 7, status_id: 4, address: 'Ленина, 1', window_start: 'a', window_end: 'b', equipment: [] },
    { id: 8, status_id: 1, address: 'Ленина, 1', window_start: 'a', window_end: 'b', equipment: [] },
  ])
  assert.equal(await copying, 8)

  assert.equal(table.editingId.value, 8)
  assert.equal(table.form.value.address, 'Ленина, 1')
  assert.match(notices.at(-1), /№8 — копия отменённой №7/)
})
