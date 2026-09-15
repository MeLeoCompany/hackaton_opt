// Расшифровка линии маршрута из Valhalla.
//
// Valhalla отдаёт линию строкой в формате encoded polyline с точностью 6 знаков после
// запятой (у Google и Leaflet по умолчанию 5 — если перепутать, координаты уедут в десять раз).
//
// Как устроена строка:
//   - каждая точка записана не целиком, а как разница с предыдущей точкой;
//   - каждое число разбито на куски по 5 бит, к каждому куску прибавлено 63,
//     чтобы получился печатный символ;
//   - шестой бит куска означает «за мной есть ещё кусок этого же числа».
export function decodePolyline(encoded, precision = 6) {
  const scale = 10 ** precision
  const coordinates = []
  let position = 0
  let latitude = 0
  let longitude = 0

  function readNextNumber() {
    let accumulated = 0
    let bitOffset = 0
    let chunk
    do {
      chunk = encoded.charCodeAt(position) - 63
      position += 1
      accumulated |= (chunk & 0b11111) << bitOffset // младшие 5 бит — данные
      bitOffset += 5
    } while (chunk >= 0b100000) // шестой бит — у числа есть продолжение

    // младший бит — знак: отрицательные числа хранятся инвертированными
    const isNegative = accumulated & 1
    return isNegative ? ~(accumulated >> 1) : accumulated >> 1
  }

  while (position < encoded.length) {
    latitude += readNextNumber()
    longitude += readNextNumber()
    coordinates.push([latitude / scale, longitude / scale])
  }

  return coordinates
}
