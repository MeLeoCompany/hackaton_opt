import { apiRequest } from './httpClient.js'

// { skills: [{id, name}], priorities: [...], transports: [...],
//   work_types: [{id, name, skill_id, travel_minutes, work_minutes, baseline_minutes}] }
export function fetchReferences() {
  return apiRequest('GET', '/references')
}

// уровень приоритета по умолчанию для типа работ (только администратор): { priority_id }
export function updateWorkTypePriority(workTypeId, priorityId) {
  return apiRequest('PUT', `/references/work-types/${workTypeId}/priority`, { json: { priority_id: priorityId } })
}

// правка нормативов типа работ (только администратор): { travel_minutes, work_minutes }
export function updateWorkTypeNorms(workTypeId, norms) {
  return apiRequest('PUT', `/references/work-types/${workTypeId}`, { json: norms })
}
