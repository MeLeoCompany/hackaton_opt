import test from 'node:test'
import assert from 'node:assert/strict'

import { toApiError } from '../src/api/httpClient.js'

test('ошибки проверки полей переводятся на человеческий язык', () => {
  const error = toApiError(422, {
    detail: [
      { loc: ['body', 'skill_ids'], type: 'too_short', ctx: { min_length: 1 } },
      { loc: ['body', 'address'], type: 'missing' },
    ],
  })

  assert.deepEqual(error.details, ['Навыки: выберите хотя бы 1', 'Адрес: не заполнено'])
})
