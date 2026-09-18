import { apiRequest } from './httpClient.js'

// учётка: { id, login, name, role: 'admin' | 'dispatcher', office_id, is_active }
export function listUsers() {
  return apiRequest('GET', '/users')
}

export function createUser(user) {
  return apiRequest('POST', '/users', { json: user })
}

export function updateUser(userId, user) {
  return apiRequest('PUT', `/users/${userId}`, { json: user })
}

export function deleteUser(userId) {
  return apiRequest('DELETE', `/users/${userId}`)
}
