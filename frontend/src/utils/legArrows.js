// Бегущие стрелки вдоль участка, по которому бригада едет сейчас: белые шевроны на линии цвета
// маршрута плывут к заявке. Позиции считаются в пикселях карты; стрелки ставятся только на
// видимый кусок участка (вблизи он длиннее экрана в сотни раз) и пересчитываются при сдвиге
// и смене масштаба. Если в системе просили меньше движения — стрелки стоят на месте.

import L from 'leaflet'

import { cumulativeLengths, pointAlong } from './pathGeometry.js'

const SPACING_PX = 44 // расстояние между стрелками на экране
const SPEED_PX = 26 // скорость бега, пикселей в секунду
const MAX_ARROWS = 120

const CHEVRON =
  '<svg viewBox="0 0 12 12" width="14" height="14" fill="none" stroke="#fff" stroke-width="2.6" ' +
  'stroke-linecap="round" stroke-linejoin="round"><path d="M4 2l4 4-4 4"/></svg>'

function arrowIcon() {
  return L.divIcon({
    className: 'leg-arrow',
    html: `<span style="display:block;width:14px;height:14px">${CHEVRON}</span>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
}

// запускает стрелки на слое layer; возвращает функцию остановки
export function runArrows(map, layer, latlngs) {
  const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  let points = []
  let lengths = [0]
  let markers = []
  let frame = null
  // видимый кусок участка: с какого расстояния от начала ставить стрелки
  let firstDistance = 0

  function place(offset) {
    const total = lengths.at(-1)
    markers.forEach((marker, index) => {
      const distance = firstDistance + offset + index * SPACING_PX
      const element = marker.getElement()
      if (distance > total) {
        if (element) element.style.visibility = 'hidden'
        return
      }
      const { point, angle } = pointAlong(points, lengths, distance)
      marker.setLatLng(map.layerPointToLatLng(L.point(point[0], point[1])))
      if (element) {
        element.style.visibility = ''
        element.firstChild.style.transform = `rotate(${angle}deg)`
      }
    })
  }

  // масштаб или вид сменился — пиксели линии другие, и видна другая её часть
  function project() {
    points = latlngs.map((latlng) => {
      const point = map.latLngToLayerPoint(latlng)
      return [point.x, point.y]
    })
    lengths = cumulativeLengths(points)
    // какие вершины линии на экране (с запасом): от первой до последней из них и ставим стрелки
    const view = map.getPixelBounds()
    const origin = map.getPixelOrigin()
    const pad = SPACING_PX * 2
    const visible = points
      .map(([x, y], index) => ({ x: x + origin.x, y: y + origin.y, index }))
      .filter(({ x, y }) => x >= view.min.x - pad && x <= view.max.x + pad && y >= view.min.y - pad && y <= view.max.y + pad)
    // на экране может не оказаться ни одной вершины, хотя сам отрезок его пересекает —
    // тогда берём соседние с ним вершины
    const from = visible.length ? Math.max(visible[0].index - 1, 0) : 0
    const to = visible.length ? Math.min(visible.at(-1).index + 1, points.length - 1) : points.length - 1
    firstDistance = Math.floor(lengths[from] / SPACING_PX) * SPACING_PX
    markers.forEach((marker) => layer.removeLayer(marker))
    const count = Math.min(Math.floor((lengths[to] - firstDistance) / SPACING_PX) + 2, MAX_ARROWS)
    markers = Array.from({ length: count }, () =>
      L.marker(latlngs[0], { icon: arrowIcon(), interactive: false, keyboard: false, zIndexOffset: -1000 }).addTo(layer),
    )
    place(SPACING_PX / 2)
  }

  function tick(time) {
    place(((time / 1000) * SPEED_PX) % SPACING_PX)
    frame = requestAnimationFrame(tick)
  }

  project()
  map.on('zoomend viewreset moveend', project)
  if (!still && latlngs.length > 1) frame = requestAnimationFrame(tick)

  return () => {
    if (frame !== null) cancelAnimationFrame(frame)
    map.off('zoomend viewreset moveend', project)
    markers.forEach((marker) => layer.removeLayer(marker))
  }
}
