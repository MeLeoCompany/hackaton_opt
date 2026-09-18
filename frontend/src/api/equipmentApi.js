import { apiRequest } from './httpClient.js'

// тип оборудования: { id, name, description, request_count }
export function listEquipment() {
  return apiRequest('GET', '/equipment')
}

export function createEquipment(equipment) {
  return apiRequest('POST', '/equipment', { json: equipment })
}

export function updateEquipment(equipmentId, equipment) {
  return apiRequest('PUT', `/equipment/${equipmentId}`, { json: equipment })
}

export function deleteEquipment(equipmentId) {
  return apiRequest('DELETE', `/equipment/${equipmentId}`)
}
