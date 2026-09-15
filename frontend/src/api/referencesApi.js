import { apiRequest } from './httpClient.js'

// { skills: [{id, name}], priorities: [...], transports: [...] }
export function fetchReferences() {
  return apiRequest('GET', '/references')
}
