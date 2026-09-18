import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

// composable поднимается без Vue и без сети: ref, запросы и сообщения подменяются заглушками
function harness({ confirm = true, deleteError = null } = {}) {
  const file = fs.readFileSync(new URL('../src/composables/useEquipment.js', import.meta.url), 'utf8')
  const source = file
    .slice(file.indexOf('export const NEW_EQUIPMENT'))
    .replace('export const NEW_EQUIPMENT', 'const NEW_EQUIPMENT')
    .replace('export function', 'function')
  const calls = []
  const errors = []
  const make = new Function(
    'ref', 'window', 'createEquipment', 'deleteEquipment', 'listEquipment', 'updateEquipment', 'useMessages',
    source + '; return useEquipment()',
  )
  const equipment = make(
    (value) => ({ value }),
    { confirm: () => confirm },
    async (payload) => { calls.push(['create', payload]) },
    async (id) => {
      calls.push(['delete', id])
      if (deleteError) throw deleteError
    },
    async () => [{ id: 1, name: 'Роутер', description: '', request_count: 3 }],
    async (id, payload) => { calls.push(['update', id, payload]) },
    () => ({
      errorMessage: { value: '' },
      errorDetails: { value: [] },
      noticeMessage: { value: '' },
      showError: (error) => errors.push(error),
      showNotice() {},
      clearMessages() {},
    }),
  )
  return { equipment, calls, errors }
}

test('новое оборудование уходит без лишних пробелов', async () => {
  const { equipment, calls } = harness()
  equipment.startCreate()
  Object.assign(equipment.form.value, { name: ' IP-камера ', description: ' видеонаблюдение ' })

  await equipment.saveForm()

  assert.deepEqual(calls[0], ['create', { name: 'IP-камера', description: 'видеонаблюдение' }])
  assert.equal(equipment.editingId.value, null)
})

test('отказ бэкенда удалить нужное заявкам оборудование показывается диспетчеру', async () => {
  const refusal = new Error('«Роутер» нельзя удалить: его требуют заявки (3)')
  const { equipment, errors } = harness({ deleteError: refusal })
  await equipment.load()

  await equipment.remove(equipment.equipment.value[0])

  assert.deepEqual(errors, [refusal])
  assert.equal(equipment.saving.value, false)
})

test('без подтверждения удаление не уходит на бэкенд', async () => {
  const { equipment, calls } = harness({ confirm: false })
  await equipment.load()

  await equipment.remove(equipment.equipment.value[0])

  assert.deepEqual(calls, [])
})
