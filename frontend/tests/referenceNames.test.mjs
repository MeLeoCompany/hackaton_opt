import test from 'node:test'
import assert from 'node:assert/strict'

import { isUrgent, priorityBadgeClass, priorityLevel } from '../src/utils/referenceNames.js'

const REFERENCES = {
  priorities: [
    { id: 2, name: 'Аварийный', level: 1 },
    { id: 3, name: 'Высокий', level: 2 },
    { id: 1, name: 'Обычный', level: 3 },
  ],
}

test('срочность — по уровню приоритета, а не по названию', () => {
  assert.equal(priorityLevel(REFERENCES, 3), 2)
  assert.equal(isUrgent(REFERENCES, { priority_id: 2 }), true)
  assert.equal(isUrgent(REFERENCES, { priority_id: 3 }), false)
})

test('плашка приоритета окрашивается по уровню', () => {
  assert.deepEqual(priorityBadgeClass(REFERENCES, 2), ['badge', 'priority-1'])
  assert.deepEqual(priorityBadgeClass(REFERENCES, 99), ['badge', 'priority-none'])
})
