import { apiRequest } from './httpClient.js'

export const TRANSPORTS = [
  { id: 1, label: 'Автомобиль' },
  { id: 2, label: 'Пешеход' },
  { id: 3, label: 'Велосипед' },
  { id: 4, label: 'Общественный транспорт' },
]

// чем человек едет на участке: приходит в route.legs[].mode с бэкенда.
// у общественного транспорта участок может оказаться метро или пешим
export const TRAVEL_MODES = {
  road: { label: 'Наземным', color: '#2563eb' },
  metro: { label: 'Метро', color: '#7c3aed' },
  bus: { label: 'Автобус', color: '#dc2626' },
  tram: { label: 'Трамвай', color: '#d97706' },
  rail: { label: 'Поезд', color: '#0891b2' },
  ferry: { label: 'Паром', color: '#0284c7' },
  transit: { label: 'Транспорт', color: '#475569' },
  walk: { label: 'Пешком', color: '#059669' },
}

// departureTime — когда выезжаем: для общественного транспорта от него зависит расписание
export function fetchRoute(points, transport, departureTime) {
  return apiRequest('POST', '/travel/route', { json: { points, transport, departure_time: departureTime } })
}

export function fetchMatrix(points, transport, departureTime) {
  return apiRequest('POST', '/travel/matrix', { json: { points, transport, departure_time: departureTime } })
}
