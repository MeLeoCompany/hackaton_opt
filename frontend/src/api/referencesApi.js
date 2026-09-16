import { apiRequest } from './httpClient.js'

// { skills: [{id, name}], priorities: [...], transports: [...],
//   work_types: [{id, name, skill_id, travel_minutes, work_minutes, baseline_minutes}] }
export function fetchReferences() {
  return apiRequest('GET', '/references')
}
