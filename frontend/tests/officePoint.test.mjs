import test from 'node:test'
import assert from 'node:assert/strict'

import { isAtOffice } from '../src/utils/officePoint.js'

const OFFICE = { latitude: 55.664757, longitude: 37.615839 }

test('координаты офиса — бригада выезжает из офиса', () => {
  assert.equal(isAtOffice(55.664757, 37.615839, OFFICE), true)
  // из поля ввода координаты приходят строкой
  assert.equal(isAtOffice('55.664757', '37.615839', OFFICE), true)
})

test('сдвинули координаты — своя точка', () => {
  assert.equal(isAtOffice(55.665, 37.615839, OFFICE), false)
})

test('без офиса или без координат — своя точка', () => {
  assert.equal(isAtOffice(55.664757, 37.615839, null), false)
  assert.equal(isAtOffice('', '', OFFICE), false)
})
