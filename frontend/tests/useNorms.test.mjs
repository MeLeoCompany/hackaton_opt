import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

// composable поднимается без Vue и без сети: ref, запросы и сообщения — заглушки
function harness({ failSave = null } = {}) {
  const file = fs.readFileSync(new URL('../src/composables/useNorms.js', import.meta.url), 'utf8')
  const source = file.slice(file.indexOf('export function')).replace('export function', 'function')
  const calls = []
  const notices = []
  const errors = []
  const make = new Function('ref', 'fetchReferences', 'updateWorkTypeNorms', 'useMessages', source + '; return useNorms()')
  const norms = make(
    (value) => ({ value }),
    async () => ({
      skills: [{ id: 1, name: 'Локальные работы' }],
      work_types: [{ id: 4, name: 'Локальная заявка', skill_id: 1, travel_minutes: 20, work_minutes: 30, baseline_minutes: 50 }],
    }),
    async (id, payload) => {
      calls.push([id, payload])
      if (failSave) throw failSave
      return { id, name: 'Локальная заявка', skill_id: 1, ...payload, baseline_minutes: payload.travel_minutes + payload.work_minutes }
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
  return { norms, calls, notices, errors }
}

test('сохранённые нормативы сразу видны в таблице вместе с новым базовым', async () => {
  const { norms, calls, notices } = harness()
  await norms.load()
  norms.startEdit(norms.references.value.work_types[0])
  norms.form.value.work_minutes = '45'

  await norms.saveForm()

  assert.deepEqual(calls[0], [4, { travel_minutes: 20, work_minutes: 45 }])
  assert.equal(norms.references.value.work_types[0].baseline_minutes, 65)
  assert.equal(norms.editingId.value, null)
  assert.match(notices[0], /подставятся в новые заявки/)
})

test('отказ сервера оставляет строку в правке', async () => {
  const refusal = new Error('Проверьте данные')
  const { norms, errors } = harness({ failSave: refusal })
  await norms.load()
  norms.startEdit(norms.references.value.work_types[0])
  norms.form.value.work_minutes = ''

  await norms.saveForm()

  assert.deepEqual(errors, [refusal])
  assert.equal(norms.editingId.value, 4)
  assert.equal(norms.saving.value, false)
})
