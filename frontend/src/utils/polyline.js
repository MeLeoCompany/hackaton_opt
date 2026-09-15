// Valhalla отдаёт геометрию encoded polyline с точностью 6 знаков
// (у Google/Leaflet по умолчанию 5 — отсюда отдельный параметр precision).
export function decodePolyline(encoded, precision = 6) {
  const factor = 10 ** precision
  const coordinates = []
  let index = 0
  let lat = 0
  let lon = 0

  while (index < encoded.length) {
    let shift = 0
    let result = 0
    let byte
    do {
      byte = encoded.charCodeAt(index++) - 63
      result |= (byte & 0x1f) << shift
      shift += 5
    } while (byte >= 0x20)
    lat += result & 1 ? ~(result >> 1) : result >> 1

    shift = 0
    result = 0
    do {
      byte = encoded.charCodeAt(index++) - 63
      result |= (byte & 0x1f) << shift
      shift += 5
    } while (byte >= 0x20)
    lon += result & 1 ? ~(result >> 1) : result >> 1

    coordinates.push([lat / factor, lon / factor])
  }

  return coordinates
}
