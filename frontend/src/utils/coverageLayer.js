// Зона покрытия на карте: где выгружены дороги и расписания и где расчёт честный.
// Для демонстрации готовы не вся страна, а районы Москвы, в которых лежат наши адреса,
// и города области — Домодедово, Ступино, Кашира. Между ними нарисован коридор вдоль
// шоссе (рядом с ним идёт и железная дорога) — иначе зоны выглядели бы оторванными.
// Данные готовит scripts/build_coverage.py по границам OpenStreetMap.

import L from 'leaflet'

import coverage from '../assets/coverage.json'

const COLOR = '#16a34a'
const AREA_STYLE = {
  color: COLOR,
  weight: 1,
  opacity: 0.5,
  fillColor: COLOR,
  fillOpacity: 0.12,
  interactive: false,
}
// коридор — эвристика, а не выгруженный район: рисуем его бледнее и пунктиром
const CORRIDOR_STYLE = { ...AREA_STYLE, opacity: 0.35, fillOpacity: 0.07, dashArray: '6 6' }

export const COVERAGE_HINT =
  'Зона покрытия: районы и города, для которых выгружены дороги и расписания. ' +
  'Между ними — коридор вдоль шоссе и железной дороги'

export function createCoverageLayer() {
  const layer = L.layerGroup()
  for (const area of coverage.areas) {
    L.polygon(area.rings, AREA_STYLE).addTo(layer)
  }
  for (const corridor of coverage.corridors) {
    L.polygon(corridor.polygon, CORRIDOR_STYLE).addTo(layer)
  }
  return layer
}

// сколько всего зон — показываем в подсказке ползунка
export const COVERAGE_AREAS = coverage.areas.length
