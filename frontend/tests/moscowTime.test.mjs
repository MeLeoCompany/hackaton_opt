import test from 'node:test'
import assert from 'node:assert/strict'

import {
  completeTime,
  joinMoscowInputValue,
  maskTimeInput,
  nextDay,
  splitMoscowInputValue,
} from '../src/utils/moscowTime.js'

test('маска сама расставляет двоеточие и ведущий ноль', () => {
  assert.equal(maskTimeInput('1'), '1')
  assert.equal(maskTimeInput('18'), '18:')
  assert.equal(maskTimeInput('1845'), '18:45')
  assert.equal(maskTimeInput('9'), '09:')
  assert.equal(maskTimeInput('930'), '09:30')
  assert.equal(maskTimeInput('08:05'), '08:05')
})

test('несуществующее время набрать нельзя: лишние цифры просто не вводятся', () => {
  assert.equal(maskTimeInput('1890'), '18:0') // девятка в минутах не принимается
  assert.equal(maskTimeInput('24'), '2') // после двойки час не уходит за 23
  assert.equal(maskTimeInput('1061'), '10:1') // шестёрка в минутах не принимается
  assert.equal(maskTimeInput('вечером'), '')
  assert.equal(maskTimeInput(''), '')
})

test('недобранное время дополняется нулями', () => {
  assert.equal(completeTime('18:'), '18:00')
  assert.equal(completeTime('9'), '09:00')
  assert.equal(completeTime('09:3'), '09:30')
  assert.equal(completeTime('09:30'), '09:30')
  assert.equal(completeTime(''), '')
})

test('день и время собираются в значение формы и разбираются обратно', () => {
  assert.deepEqual(splitMoscowInputValue('2026-08-17T18:00'), { date: '2026-08-17', time: '18:00' })
  assert.deepEqual(splitMoscowInputValue(''), { date: '', time: '' })
  assert.equal(joinMoscowInputValue('2026-08-17', '09:30'), '2026-08-17T09:30')
  assert.equal(joinMoscowInputValue('2026-08-17', ''), '')
  assert.equal(joinMoscowInputValue('', '09:30'), '')
})

test('через полночь окончание переносится на следующий день', () => {
  assert.equal(nextDay('2026-08-17'), '2026-08-18')
  assert.equal(nextDay('2026-08-31'), '2026-09-01')
  assert.equal(nextDay('2026-12-31'), '2027-01-01')
})
