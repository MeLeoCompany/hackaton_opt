import test from 'node:test'
import assert from 'node:assert/strict'

import { formatSyncMoment, syncSummary } from '../src/utils/daySync.js'

test('время синхронизации того же дня — без даты, другого — с датой', () => {
  assert.equal(formatSyncMoment('2026-08-17T11:30:00Z', '2026-08-17'), '14:30')
  assert.equal(formatSyncMoment('2026-09-18T21:40:00Z', '2026-08-17'), '19.09.2026 00:40')
})

test('итог синхронизации — сколько заявок в какой статус', () => {
  const codes = { 3: 'done', 5: 'in_progress', 4: 'cancelled' }
  const transitions = [{ to_status_id: 3 }, { to_status_id: 3 }, { to_status_id: 4 }]
  assert.equal(syncSummary(transitions, (id) => codes[id]), 'выполнено 2, отменено 1')
  assert.equal(syncSummary([], (id) => codes[id]), 'статусы менять не пришлось')
})
