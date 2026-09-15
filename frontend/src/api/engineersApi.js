import { apiRequest } from './httpClient.js'

export function listEngineers() {
  return apiRequest('GET', '/engineers')
}

export function createEngineer(fields) {
  return apiRequest('POST', '/engineers', { json: fields })
}

export function updateEngineer(engineerId, fields) {
  return apiRequest('PUT', `/engineers/${engineerId}`, { json: fields })
}

export function deleteEngineer(engineerId) {
  return apiRequest('DELETE', `/engineers/${engineerId}`)
}
