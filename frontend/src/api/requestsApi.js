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

// копия отменённой заявки: новая заявка с теми же данными (отменённую в «Новая» не возвращают)
// planDate — перенести копию на другой день: время суток окна то же, дата новая
export function duplicateRequest(requestId, planDate) {
  const path = `/requests/${requestId}/duplicate${planDate ? `?plan_date=${encodeURIComponent(planDate)}` : ''}`
  return apiRequest('POST', path)
}

export function deleteRequest(requestId) {
  return apiRequest('DELETE', `/requests/${requestId}`)
}

// перевести заявки в статус — только ручным переходом из таблицы переходов; все или ни одной
export function setRequestsStatus(requestIds, statusId) {
  return apiRequest('PATCH', '/requests/status', { json: { request_ids: requestIds, status_id: statusId } })
}

// история смен статуса заявки по порядку
export function getRequestHistory(requestId) {
  return apiRequest('GET', `/requests/${requestId}/history`)
}

// слепок дня: выгрузка заявок выбранного дня
export function exportRequestsCsv(planDate) {
  return apiDownload(`/requests/export?plan_date=${encodeURIComponent(planDate)}`)
}

// planDate — перенести файл в этот день копией: время суток то же, номера новые
export function importRequestsCsv(file, planDate, cancelled) {
  const formData = new FormData()
  formData.append('file', file)
  // cancelled — что делать с отменёнными заявками из файла при переносе дня
  const query = planDate
    ? `?plan_date=${encodeURIComponent(planDate)}&cancelled=${encodeURIComponent(cancelled ?? 'skip')}`
    : ''
  const path = `/requests/import${query}`
  return apiRequest('POST', path, { formData })
}

export function downloadCsvTemplate() {
  return apiDownload('/requests/csv-template')
}
