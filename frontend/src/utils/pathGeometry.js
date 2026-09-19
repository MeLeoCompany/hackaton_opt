// Геометрия линии на экране: точки [x, y] в пикселях карты. Из неё карта плана ставит
// бегущие стрелки вдоль участка и значок бригады на её пути.

// накопленная длина до каждой точки линии
export function cumulativeLengths(points) {
  const lengths = [0]
  for (let index = 1; index < points.length; index += 1) {
    const [x1, y1] = points[index - 1]
    const [x2, y2] = points[index]
    lengths.push(lengths[index - 1] + Math.hypot(x2 - x1, y2 - y1))
  }
  return lengths
}

// точка на расстоянии distance от начала линии и направление линии там (градусы, 0 — вправо,
// по часовой стрелке, как у поворота в CSS)
export function pointAlong(points, lengths, distance) {
  const total = lengths.at(-1)
  const target = Math.min(Math.max(distance, 0), total)
  let index = 1
  while (index < points.length - 1 && lengths[index] < target) index += 1
  const [x1, y1] = points[index - 1]
  const [x2, y2] = points[index]
  const segment = lengths[index] - lengths[index - 1]
  const share = segment > 0 ? (target - lengths[index - 1]) / segment : 0
  return {
    point: [x1 + (x2 - x1) * share, y1 + (y2 - y1) * share],
    angle: (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI,
  }
}

// какая доля участка уже пройдена: сколько минут едут из запланированных; не доезжая до конца,
// пока нет отметки «на месте»
export function travelledShare(departedAt, durationMinutes, now = new Date()) {
  if (!departedAt || !durationMinutes) return 0.5
  const minutes = (now.getTime() - new Date(departedAt).getTime()) / 60000
  return Math.min(Math.max(minutes / durationMinutes, 0), 0.9)
}

// линия, сдвинутая вбок на distance пикселей — как параллельные линии на схеме метро:
// плюс — вправо по ходу движения, минус — влево. На изломах сдвиг по биссектрисе,
// острые углы ограничены, чтобы линия не улетала
export function offsetPath(points, distance) {
  // одинаковые соседние точки направления не задают
  const clean = points.filter(
    (point, index) => index === 0 || point[0] !== points[index - 1][0] || point[1] !== points[index - 1][1],
  )
  if (clean.length < 2 || distance === 0) return clean
  const normals = []
  for (let index = 1; index < clean.length; index += 1) {
    const dx = clean[index][0] - clean[index - 1][0]
    const dy = clean[index][1] - clean[index - 1][1]
    const length = Math.hypot(dx, dy)
    normals.push([-dy / length, dx / length])
  }
  return clean.map(([x, y], index) => {
    const before = normals[Math.max(index - 1, 0)]
    const after = normals[Math.min(index, normals.length - 1)]
    const sum = [before[0] + after[0], before[1] + after[1]]
    const length = Math.hypot(sum[0], sum[1]) || 1
    const normal = [sum[0] / length, sum[1] / length]
    const scale = distance / Math.max(normal[0] * after[0] + normal[1] * after[1], 0.5)
    return [x + normal[0] * scale, y + normal[1] * scale]
  })
}

// длина линии [[широта, долгота], …] в километрах — по большому кругу
export function lengthKm(latlngs) {
  const radians = (degrees) => (degrees * Math.PI) / 180
  let total = 0
  for (let index = 1; index < latlngs.length; index += 1) {
    const [lat1, lng1] = latlngs[index - 1]
    const [lat2, lng2] = latlngs[index]
    const a =
      Math.sin(radians(lat2 - lat1) / 2) ** 2 +
      Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(radians(lng2 - lng1) / 2) ** 2
    total += 2 * 6371 * Math.asin(Math.sqrt(a))
  }
  return total
}
