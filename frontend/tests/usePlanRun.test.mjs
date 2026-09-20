import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function harness(crypto) {
  const file = fs.readFileSync(new URL('../src/composables/usePlanRun.js', import.meta.url), 'utf8')
  const source = file.slice(file.indexOf('export function')).replace('export function', 'function')
  const make = new Function('ref', 'fetchPlanRun', 'window', `${source}; return usePlanRun()`)
  return make((value) => ({ value }), async () => ({}), { crypto })
}

test('номер запуска — настоящий UUID v4, даже без crypto.randomUUID', () => {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

  // стенд открывают по IP: там есть только getRandomValues
  const withValues = harness({ getRandomValues: (bytes) => bytes.fill(7) })
  assert.match(withValues.newRunId(), uuid)

  // и совсем без crypto — на всякий случай
  const without = harness(undefined)
  assert.match(without.newRunId(), uuid)
})
