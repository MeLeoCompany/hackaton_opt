import { apiDownload, apiRequest } from './httpClient.js'

export function listRequests() {
  return apiRequest('GET', '/requests')
}

export function createRequest(fields) {
  return apiRequest('POST', '/requests', { json: fields })
}

export function updateRequest(requestId, fields) {
  return apiRequest('PUT', `/requests/${requestId}`, { json: fields })
}

export function deleteRequest(requestId) {
  return apiRequest('DELETE', `/requests/${requestId}`)
}

// включить или выключить заявки для планирования
export function setRequestsActive(requestIds, isActive) {
  return apiRequest('PATCH', '/requests/active', { json: { request_ids: requestIds, is_active: isActive } })
}

export function importRequestsCsv(file) {
  const formData = new FormData()
  formData.append('file', file)
  return apiRequest('POST', '/requests/import', { formData })
}

export function downloadCsvTemplate() {
  return apiDownload('/requests/csv-template')
}
