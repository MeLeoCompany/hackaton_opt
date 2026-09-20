import test from 'node:test'
import assert from 'node:assert/strict'

import { movedAway, requestMarks } from '../src/utils/requestMarks.js'

test('отметки заявки: обещание, перенос, «требует уточнения» и причина отмены', () => {
  assert.deepEqual(
    requestMarks({
      promised_from: '2026-08-17T17:40:00+03:00',
      promised_to: '2026-08-17T18:10:00+03:00',
      moved_from: '2026-08-16',
      needs_followup: true,
      cancel_reason: 'не дозвонились',
    }).map((mark) => [mark.kind, mark.text]),
    [
      ['promised', 'согласовано 17:40–18:10'],
      ['moved', 'перенесена с 16.08.2026'],
      ['followup', 'требует уточнения — перезвонить'],
      ['cancelled', 'причина: не дозвонились'],
    ],
  )
  assert.deepEqual(requestMarks({ needs_followup: false }), [])
})

test('в дне, откуда заявку перенесли, видно, куда она ушла', () => {
  const request = {
    moved_from: '2026-08-19',
    window_start: '2026-08-20T11:30:00Z',
    window_end: '2026-08-20T16:00:00Z',
    needs_followup: false,
  }

  assert.equal(movedAway(request, '2026-08-19'), true)
  assert.deepEqual(requestMarks(request, '2026-08-19').map((mark) => mark.text), [
    'перенесена на 20.08.2026',
  ])
  // в своём новом дне та же заявка показывает, откуда пришла
  assert.equal(movedAway(request, '2026-08-20'), false)
  assert.deepEqual(requestMarks(request, '2026-08-20').map((mark) => mark.text), [
    'перенесена с 19.08.2026',
  ])
})
