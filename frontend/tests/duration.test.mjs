import test from 'node:test'
import assert from 'node:assert/strict'

import { formatDuration, parseDuration } from '../src/utils/duration.js'

test('длительность показывается часами и минутами', () => {
  assert.equal(formatDuration(185.4), '3 ч 5 мин')
  assert.equal(formatDuration(45), '45 мин')
  assert.equal(formatDuration(120), '2 ч')
  assert.equal(formatDuration(0), '0 мин')
})

test('длительность набирается как удобно', () => {
  assert.equal(parseDuration('1 ч 30 мин'), 90)
  assert.equal(parseDuration('1ч30м'), 90)
  assert.equal(parseDuration('2 ч'), 120)
  assert.equal(parseDuration('45 мин'), 45)
  assert.equal(parseDuration('1:30'), 90)
  assert.equal(parseDuration('90'), 90)
})

test('непонятная длительность не принимается', () => {
  assert.equal(parseDuration(''), null)
  assert.equal(parseDuration('1:75'), null)
  assert.equal(parseDuration('1 ч 75 мин'), null)
  assert.equal(parseDuration('999999999999999999999999'), null)
  assert.equal(parseDuration('долго'), null)
})
