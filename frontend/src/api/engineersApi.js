import { apiRequest } from './httpClient.js'

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
