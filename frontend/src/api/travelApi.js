const BASE_URL = '/api/v1/travel'

async function post(path, body) {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `Запрос не прошёл: ${response.status}`)
  }
  return response.json()
}

export const TRANSPORTS = [
  { id: 1, label: 'Автомобиль' },
  { id: 2, label: 'Пешеход' },
  { id: 3, label: 'Велосипед' },
  { id: 4, label: 'Общественный транспорт' },
]

export function fetchRoute(points, transport) {
  return post('/route', { points, transport })
}

export function fetchMatrix(points, transport) {
  return post('/matrix', { points, transport })
}
