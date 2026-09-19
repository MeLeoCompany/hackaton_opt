import { apiRequest } from './httpClient.js'

// офис: { id, name, address, latitude, longitude, engineer_count }
export function listOffices() {
  return apiRequest('GET', '/offices')
}

export function createOffice(office) {
  return apiRequest('POST', '/offices', { json: office })
}

export function updateOffice(officeId, office) {
  return apiRequest('PUT', `/offices/${officeId}`, { json: office })
}

export function deleteOffice(officeId) {
  return apiRequest('DELETE', `/offices/${officeId}`)
}
