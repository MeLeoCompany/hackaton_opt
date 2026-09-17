import { apiDownload, apiRequest } from './httpClient.js'

// день не указан — вернутся все заявки; указан — только те, чьё окно попадает в этот день
export function listRequests(planDate) {
  return apiRequest('GET', planDate ? `/requests?plan_date=${encodeURIComponent(planDate)}` : '/requests')
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

// слепок дня: выгрузка заявок выбранного дня
export function exportRequestsCsv(planDate) {
  return apiDownload(`/requests/export?plan_date=${encodeURIComponent(planDate)}`)
}

// planDate — перенести файл в этот день копией: время суток то же, номера новые
export function importRequestsCsv(file, planDate) {
  const formData = new FormData()
  formData.append('file', file)
  const path = planDate ? `/requests/import?plan_date=${encodeURIComponent(planDate)}` : '/requests/import'
  return apiRequest('POST', path, { formData })
}

export function downloadCsvTemplate() {
  return apiDownload('/requests/csv-template')
}
