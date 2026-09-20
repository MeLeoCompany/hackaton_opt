import test from 'node:test'
import assert from 'node:assert/strict'

import {
  completeTime,
  joinMoscowInputValue,
  maskTimeInput,
  moscowLogTimeOf,
  moscowTimeRangeParts,
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

test('в таблице дня окно показывается без даты', () => {
  // 07:00–09:00 UTC = 10:00–12:00 по Москве
  assert.deepEqual(moscowTimeRangeParts('2026-08-17T07:00:00Z', '2026-08-17T09:00:00Z'), {
    start: '10:00',
    end: '12:00',
    endsNextDay: false,
  })
})

test('окончание ровно в полночь не помечается следующими сутками', () => {
  // 21:00 UTC = 00:00 МСК следующего дня — для диспетчера это конец того же дня
  assert.deepEqual(moscowTimeRangeParts('2026-08-17T07:00:00Z', '2026-08-17T21:00:00Z'), {
    start: '10:00',
    end: '00:00',
    endsNextDay: false,
  })
})

test('окно через полночь помечается следующими сутками', () => {
  // 19:00 UTC = 22:00 МСК, 23:00 UTC = 02:00 МСК следующего дня
  assert.deepEqual(moscowTimeRangeParts('2026-08-17T19:00:00Z', '2026-08-17T23:00:00Z'), {
    start: '22:00',
    end: '02:00',
    endsNextDay: true,
  })
})

test('время можно стереть до конца: двоеточие при стирании не возвращается', () => {
  assert.equal(maskTimeInput('18', { deleting: true }), '18') // стёрли двоеточие у «18:»
  assert.equal(maskTimeInput('1', { deleting: true }), '1')
  assert.equal(maskTimeInput('18:3', { deleting: true }), '18:3')
  assert.equal(maskTimeInput('18'), '18:') // при наборе двоеточие по-прежнему дописывается
})

test('в журнале расчёта время с секундами и долями', () => {
  assert.equal(moscowLogTimeOf('2026-08-17T15:00:00.312Z'), '18:00:00.312')
  assert.equal(moscowLogTimeOf('2026-08-17T23:59:59.000Z'), '02:59:59.000')
})
