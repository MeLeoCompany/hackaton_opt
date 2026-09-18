import { apiRequest } from './httpClient.js'

// { skills: [{id, name}], priorities: [...], transports: [...],
//   work_types: [{id, name, skill_id, travel_minutes, work_minutes, baseline_minutes}] }
export function fetchReferences() {
  return apiRequest('GET', '/references')
}

// правка нормативов типа работ (только администратор): { travel_minutes, work_minutes }
export function updateWorkTypeNorms(workTypeId, norms) {
  return apiRequest('PUT', `/references/work-types/${workTypeId}`, { json: norms })
}
