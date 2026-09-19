import { apiRequest } from './httpClient.js'

// { token, user: { id, login, name, role, office_id, office_name } }
export function login(loginName, password) {
  return apiRequest('POST', '/auth/login', { json: { login: loginName, password } })
}

export function fetchMe() {
  return apiRequest('GET', '/auth/me')
}
