import { apiDownload, apiRequest } from './httpClient.js'

// день не указан — вернутся все исполнители; указан — только те, чья смена попадает в этот день
export function listEngineers(planDate) {
  return apiRequest('GET', planDate ? `/engineers?plan_date=${encodeURIComponent(planDate)}` : '/engineers')
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

// групповая правка смен: в fields только отмеченные поля — меняются все или ни одна
export function updateEngineers(engineerIds, fields) {
  return apiRequest('PATCH', '/engineers', { json: { engineer_ids: engineerIds, ...fields } })
}

// групповое удаление: удаляется всё, что можно, остальное вернётся с причинами
export function deleteEngineers(engineerIds) {
  return apiRequest('DELETE', '/engineers', { json: { ids: engineerIds } })
}

// слепок дня: выгрузка исполнителей выбранного дня
export function exportEngineersCsv(planDate) {
  return apiDownload(`/engineers/export?plan_date=${encodeURIComponent(planDate)}`)
}

// planDate — перенести смены в этот день копией: время то же, номера новые
export function importEngineersCsv(file, planDate) {
  const formData = new FormData()
  formData.append('file', file)
  const path = planDate ? `/engineers/import?plan_date=${encodeURIComponent(planDate)}` : '/engineers/import'
  return apiRequest('POST', path, { formData })
}
