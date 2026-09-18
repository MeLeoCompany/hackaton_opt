import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

// composable поднимается без Vue, сети и браузера: ref, computed, запросы и хранилище — заглушки
function harness({ hasToken = false, me = null, offices = [] } = {}) {
  const file = fs.readFileSync(new URL('../src/composables/useAuth.js', import.meta.url), 'utf8')
  // всё до «const USER_KEY» — импорты; состояние модуля ниже нужно сохранить
  const source = file.slice(file.indexOf('const USER_KEY')).replace('export function', 'function')
  const storage = {}
  const session = { token: hasToken ? 'old' : null, officeId: null, expired: [] }
  const make = new Function(
    'computed', 'ref', 'fetchMe', 'requestLogin', 'hasToken', 'onSessionExpired', 'saveOfficeId',
    'saveToken', 'storedOfficeId', 'listOffices', 'window',
    source + '; return { useAuth }',
  )
  const module = make(
    (getter) => ({ get value() { return getter() } }),
    (value) => ({ value }),
    async () => me,
    async (loginName, password) => {
      if (password !== 'верный') throw new Error('Неверный логин или пароль')
      return { token: 't', user: me }
    },
    () => Boolean(session.token),
    (listener) => session.expired.push(listener),
    (value) => { session.officeId = value },
    (value) => { session.token = value },
    () => session.officeId,
    async () => offices,
    { localStorage: {
      getItem: (key) => storage[key] ?? null,
      setItem: (key, value) => { storage[key] = value },
      removeItem: (key) => { delete storage[key] },
    } },
  )
  const expire = () => session.expired.forEach((listener) => listener())
  return { auth: module.useAuth(), expire, session }
}

const DISPATCHER = { id: 2, login: 'yug', name: 'Диспетчер', role: 'dispatcher', office_id: 3, office_name: 'Югоцентр' }
const ADMIN = { id: 1, login: 'admin', name: 'Администратор', role: 'admin', office_id: null, office_name: null }
const OFFICES = [{ id: 1, name: 'Восток' }, { id: 3, name: 'Югоцентр' }]

test('диспетчер после входа работает в офисе своей учётки', async () => {
  const { auth, session } = harness({ me: DISPATCHER })

  await auth.login('yug', 'верный')

  assert.equal(auth.currentOfficeId.value, 3)
  assert.equal(auth.currentOfficeName.value, 'Югоцентр')
  assert.equal(session.token, 't')
  // заголовок офиса диспетчеру не нужен: сервер берёт офис из учётки
  assert.equal(session.officeId, null)
})

test('администратор после входа получает первый офис и может сменить его', async () => {
  const { auth, session } = harness({ me: ADMIN, offices: OFFICES })

  await auth.login('admin', 'верный')
  assert.equal(auth.currentOfficeId.value, 1)

  auth.chooseOffice(3)
  assert.equal(auth.currentOfficeName.value, 'Югоцентр')
  assert.equal(session.officeId, 3)
})

test('неверный пароль не открывает сессию', async () => {
  const { auth, session } = harness({ me: DISPATCHER })

  await assert.rejects(auth.login('yug', 'не тот'), /Неверный логин/)
  assert.equal(auth.user.value, null)
  assert.equal(session.token, null)
})

test('истёкшая сессия возвращает ко входу', async () => {
  const { auth, expire } = harness({ me: DISPATCHER })
  await auth.login('yug', 'верный')

  expire()

  assert.equal(auth.user.value, null)
})

test('выход забывает токен и учётку', async () => {
  const { auth, session } = harness({ me: ADMIN, offices: OFFICES })
  await auth.login('admin', 'верный')

  auth.logout()

  assert.equal(auth.user.value, null)
  assert.equal(session.token, null)
})
