// Цвет типа транспорта на карте исполнителей. Номера — из справочника transport.

const COLOR_BY_TRANSPORT_ID = {
  1: '#2563eb', // автомобиль
  2: '#16a34a', // пешеход
  3: '#d97706', // велосипед
  4: '#7c3aed', // общественный транспорт
}

export function transportColor(transportId) {
  return COLOR_BY_TRANSPORT_ID[transportId] ?? '#64748b'
}
