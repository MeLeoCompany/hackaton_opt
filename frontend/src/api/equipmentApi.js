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

// ёмкость: сколько штук оборудования увозит бригада на каждом транспорте
// [{ transport_id, transport_name, equipment_id, equipment_name, max_quantity }]
export function listCapacity() {
  return apiRequest('GET', '/equipment/capacity')
}

// сохраняем только изменившиеся пары; править может администратор
export function saveCapacity(rows) {
  return apiRequest('PUT', '/equipment/capacity', { json: { rows } })
}
