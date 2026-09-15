import { apiRequest } from './httpClient.js'

export const TRANSPORTS = [
  { id: 1, label: 'Автомобиль' },
  { id: 2, label: 'Пешеход' },
  { id: 3, label: 'Велосипед' },
  { id: 4, label: 'Общественный транспорт' },
]

export function fetchRoute(points, transport) {
  return apiRequest('POST', '/travel/route', { json: { points, transport } })
}

export function fetchMatrix(points, transport) {
  return apiRequest('POST', '/travel/matrix', { json: { points, transport } })
}
