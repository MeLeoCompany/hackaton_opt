import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

// composable поднимается без Vue и без сети: ref, запросы и сообщения подменяются заглушками
function harness({ confirm = true } = {}) {
  const file = fs.readFileSync(new URL('../src/composables/useOffices.js', import.meta.url), 'utf8')
  const source = file
    .slice(file.indexOf('export const NEW_OFFICE'))
    .replace('export const NEW_OFFICE', 'const NEW_OFFICE')
    .replace('export function', 'function')
  const calls = []
  const notices = []
  const errors = []
  let offices = [
    { id: 1, name: 'Восток', address: 'ул Юных Ленинцев, 83', latitude: 55.6998, longitude: 37.7726, engineer_count: 2 },
  ]
  const make = new Function(
    'ref', 'window', 'createOffice', 'deleteOffice', 'listOffices', 'updateOffice',
    'useMessages',
    source + '; return useOffices()',
  )
  const officesState = make(
    (value) => ({ value }),
    { confirm: () => confirm },
    async (payload) => { calls.push(['create', payload]); return { id: 4, ...payload, engineer_count: 0 } },
    async (officeId) => { calls.push(['delete', officeId]) },
    async () => offices,
    async (officeId, payload) => {
      calls.push(['update', officeId, payload])
      offices = offices.map((office) => (office.id === officeId ? { ...office, ...payload } : office))
      return offices.find((office) => office.id === officeId)
    },
    () => ({
      errorMessage: { value: '' },
      errorDetails: { value: [] },
      noticeMessage: { value: '' },
      showError: (error) => errors.push(error),
      showNotice: (text) => notices.push(text),
      clearMessages() {},
    }),
  )
  return { officesState, calls, notices, errors }
}

test('новый офис уходит на бэкенд числами, пустые координаты — null', async () => {
  const { officesState, calls } = harness()
  officesState.startCreate()
  Object.assign(officesState.form.value, { name: ' Север ', address: 'ул Лётчика, 1', latitude: '55.9', longitude: '' })

  await officesState.saveForm()

  assert.deepEqual(calls[0], ['create', { name: 'Север', address: 'ул Лётчика, 1', latitude: 55.9, longitude: null }])
})

test('сдвинули офис с бригадами — диспетчер узнаёт, что их старт переехал', async () => {
  const { officesState, notices } = harness()
  await officesState.load()
  officesState.startEdit(officesState.offices.value[0])
  officesState.form.value.latitude = 55.71

  await officesState.saveForm()

  assert.match(notices.at(-1), /старт его исполнителей \(2\) перенесён/)
  assert.equal(officesState.editingId.value, null)
})

test('переименовали без переноса — про старт не говорим', async () => {
  const { officesState, notices } = harness()
  await officesState.load()
  officesState.startEdit(officesState.offices.value[0])
  officesState.form.value.name = 'Восток-1'

  await officesState.saveForm()

  assert.doesNotMatch(notices.at(-1), /перенесён/)
})

test('удаление офиса без подтверждения не уходит на бэкенд', async () => {
  const { officesState, calls } = harness({ confirm: false })
  await officesState.load()

  await officesState.remove(officesState.offices.value[0])

  assert.equal(calls.length, 0)
})
