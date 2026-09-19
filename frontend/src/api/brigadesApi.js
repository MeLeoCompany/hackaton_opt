import { apiRequest } from './httpClient.js'

// бригада офиса: { id, office_id, name, is_active, login, shift_count }; login — вход в
// мобильное приложение (null — входа нет). Офис — выбранный в интерфейсе (httpClient)
export function listBrigades() {
  return apiRequest('GET', '/brigades')
}

export function createBrigade(brigade) {
  return apiRequest('POST', '/brigades', { json: brigade })
}

export function updateBrigade(brigadeId, brigade) {
  return apiRequest('PUT', `/brigades/${brigadeId}`, { json: brigade })
}

export function deleteBrigade(brigadeId) {
  return apiRequest('DELETE', `/brigades/${brigadeId}`)
}
