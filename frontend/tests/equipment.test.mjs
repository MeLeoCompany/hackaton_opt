import test from 'node:test'
import assert from 'node:assert/strict'

import { equipmentPayload } from '../src/utils/equipment.js'

test('отмеченное оборудование уходит в API списком с количеством', () => {
  assert.deepEqual(equipmentPayload({ 1: 3, 2: 1 }), [
    { equipment_id: 1, quantity: 3 },
    { equipment_id: 2, quantity: 1 },
  ])
})

test('пустое или неверное количество у отмеченного типа — одна штука', () => {
  assert.deepEqual(equipmentPayload({ 1: '', 2: 0, 3: 2.7 }), [
    { equipment_id: 1, quantity: 1 },
    { equipment_id: 2, quantity: 1 },
    { equipment_id: 3, quantity: 2 },
  ])
})

test('ничего не отмечено — пустой список', () => {
  assert.deepEqual(equipmentPayload({}), [])
  assert.deepEqual(equipmentPayload(), [])
})
