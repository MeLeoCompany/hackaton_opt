import test from 'node:test'
import assert from 'node:assert/strict'

import { manualTransitions, orderedStatuses, statusIdByCode } from '../src/utils/requestStatuses.js'

const REFERENCES = {
  request_statuses: [
    { id: 4, code: 'cancelled', name: 'Отменена', plannable: false },
    { id: 3, code: 'done', name: 'Выполнена', plannable: false },
    { id: 1, code: 'new', name: 'Новая', plannable: true },
    { id: 5, code: 'in_progress', name: 'В работе', plannable: false },
    { id: 2, code: 'planned', name: 'В плане', plannable: true },
  ],
  request_status_transitions: [
    { from_status_id: 2, to_status_id: 4, manual: true, description: 'Отмена' },
    { from_status_id: 2, to_status_id: 1, manual: false, description: 'Утверждение снято' },
    { from_status_id: 2, to_status_id: 3, manual: true, description: 'Выполнена' },
    { from_status_id: 2, to_status_id: 5, manual: true, description: 'Выехала' },
    { from_status_id: 1, to_status_id: 4, manual: true, description: 'Отмена' },
    { from_status_id: 4, to_status_id: 2, manual: true, description: 'В план' },
    { from_status_id: 4, to_status_id: 1, manual: true, description: 'Новая' },
  ],
}

test('оператору предлагаются только ручные переходы, в порядке работы с заявкой', () => {
  const targets = manualTransitions(REFERENCES, 2).map((transition) => transition.name)
  assert.deepEqual(targets, ['В работе', 'Выполнена', 'Отменена'])
})

test('статусы идут в порядке работы, а не в порядке номеров', () => {
  assert.deepEqual(
    orderedStatuses(REFERENCES).map((status) => status.code),
    ['new', 'planned', 'in_progress', 'done', 'cancelled'],
  )
  assert.equal(statusIdByCode(REFERENCES, 'new'), 1)
})

test('вернуть «В план» предлагается только заявке, у которой есть утверждённый план', () => {
  assert.deepEqual(manualTransitions(REFERENCES, 4).map((item) => item.name), ['Новая'])
  assert.deepEqual(manualTransitions(REFERENCES, 4, 22).map((item) => item.name), ['Новая', 'В плане'])
})
