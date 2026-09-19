<script setup>
// Карта плана: маршрут каждого исполнителя своим цветом — линия по дорогам, старт (белый кружок
// с цветной обводкой) и пронумерованные визиты по порядку. Неназначенные заявки — серые точки.
// Если выбран исполнитель, остальные маршруты приглушаются.

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { TRAVEL_MODES } from '../api/travelApi.js'
import { moscowTimeOf } from '../utils/moscowTime.js'
import { decodePolyline } from '../utils/polyline.js'
import { routeColor } from '../utils/routeColors.js'

const props = defineProps({
  plan: { type: Object, required: true },
  selectedEngineerId: { type: Number, default: null },
})
const emit = defineEmits(['select-engineer'])

const UNASSIGNED_COLOR = '#94a3b8'

const container = ref(null)
let map = null
let planLayer = null
// план, под который последний раз подгонялся масштаб
let fittedPlanId = null

// имена и адреса вводит человек — экранируем, прежде чем вставлять в HTML подсказки
function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (symbol) => `&#${symbol.charCodeAt(0)};`)
}

function visitIcon(visitOrder, color) {
  return L.divIcon({
    className: '',
    html:
      `<span style="display:flex;align-items:center;justify-content:center;width:22px;height:22px;` +
      `border-radius:50%;background:${color};color:#fff;font:600 11px/1 system-ui,sans-serif;` +
      `border:2px solid #fff;box-shadow:0 1px 3px rgb(0 0 0 / 40%)">` +
      `${visitOrder}</span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  })
}

function routePoints(route) {
  return [[route.start_latitude, route.start_longitude], ...route.visits.map((visit) => [visit.latitude, visit.longitude])]
}

function drawPlan() {
  planLayer.clearLayers()

  // выбран исполнитель — рисуем только его маршрут: с десятком маршрутов карта иначе тормозит
  props.plan.routes.forEach((route, routeIndex) => {
    if (props.selectedEngineerId !== null && props.selectedEngineerId !== route.engineer_id) return

    const color = routeColor(routeIndex)
    const lineStyle = { color, weight: 5, opacity: 0.85 }
    const selectThisRoute = () => emit('select-engineer', route.engineer_id)

    if (route.geometry.length > 0) {
      for (const [legIndex, leg] of route.geometry.entries()) {
        const details = route.legs?.[legIndex]
        const modeStyle = details?.mode && details.mode !== 'road' ? TRAVEL_MODES[details.mode] : null
        const style = {
          ...lineStyle,
          color: modeStyle?.color ?? color,
          dashArray: details?.mode === 'walk' ? '6 6' : undefined,
        }
        const label = modeStyle
          ? `${modeStyle.label}${details.route_id ? ` · ${escapeHtml(details.route_id)}` : ''}`
          : escapeHtml(route.engineer_name)
        L.polyline(decodePolyline(leg), style)
          .bindTooltip(label)
          .on('click', selectThisRoute)
          .addTo(planLayer)
      }
    } else {
      // маршрутизатор был недоступен — рисуем прямые пунктиром, чтобы было видно, что это оценка
      L.polyline(routePoints(route), { ...lineStyle, dashArray: '8 8' }).on('click', selectThisRoute).addTo(planLayer)
    }

    L.circleMarker([route.start_latitude, route.start_longitude], {
      radius: 7,
      color,
      weight: 3,
      fillColor: '#ffffff',
      fillOpacity: 1,
    })
      .bindTooltip(`Старт: <b>${escapeHtml(route.engineer_name)}</b>`, { direction: 'top' })
      .on('click', selectThisRoute)
      .addTo(planLayer)

    for (const visit of route.visits) {
      L.marker([visit.latitude, visit.longitude], { icon: visitIcon(visit.visit_order, color) })
        .bindTooltip(
          `<b>${visit.visit_order}. ${moscowTimeOf(visit.planned_arrival_time)}</b> · заявка №${visit.request_id}<br>` +
            `${escapeHtml(visit.address)}<br>` +
            `<span style="color:#64748b">${escapeHtml(route.engineer_name)}</span>`,
          { direction: 'top', offset: [0, -8] },
        )
        .on('click', selectThisRoute)
        .addTo(planLayer)
    }
  })

  for (const request of props.plan.unassigned) {
    L.circleMarker([request.latitude, request.longitude], {
      radius: 7,
      color: '#ffffff',
      weight: 1.5,
      fillColor: UNASSIGNED_COLOR,
      fillOpacity: 0.9,
    })
      .bindTooltip(
        `<b>Не назначена</b> · заявка №${request.request_id}<br>${escapeHtml(request.address)}<br>` +
          `<span style="color:#64748b">${escapeHtml(request.reason)}</span>`,
        { direction: 'top' },
      )
      .addTo(planLayer)
  }

  // масштаб подгоняем только при смене плана — при выборе исполнителя карта не прыгает
  if (fittedPlanId !== props.plan.id) {
    fittedPlanId = props.plan.id
    fitTo([
      ...props.plan.routes.flatMap(routePoints),
      ...props.plan.unassigned.map((request) => [request.latitude, request.longitude]),
    ])
  }
}

function fitTo(points) {
  const bounds = L.latLngBounds(points)
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 })
}

// выбрали исполнителя — остаётся только его маршрут; сняли выбор — возвращаются все
function showSelectedRoute() {
  drawPlan()
  const selectedRoute = props.plan.routes.find((route) => route.engineer_id === props.selectedEngineerId)
  fitTo(
    selectedRoute
      ? routePoints(selectedRoute)
      : [
          ...props.plan.routes.flatMap(routePoints),
          ...props.plan.unassigned.map((request) => [request.latitude, request.longitude]),
        ],
  )
}

onMounted(async () => {
  map = L.map(container.value).setView([55.751244, 37.618423], 10)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map)
  planLayer = L.layerGroup().addTo(map)

  await nextTick()
  map.invalidateSize()
  drawPlan()
})

onBeforeUnmount(() => map?.remove())

watch(() => props.plan, drawPlan)
watch(() => props.selectedEngineerId, showSelectedRoute)
</script>

<template>
  <div class="map-frame">
    <div ref="container" class="map"></div>
    <div class="map-legend">
      <span><i class="legend-dot start-dot"></i>старт исполнителя</span>
      <span><i class="legend-dot" :style="{ background: UNASSIGNED_COLOR }"></i>не назначена</span>
      <span class="muted">цифра — порядок визита</span>
    </div>
  </div>
</template>

<style scoped>
.start-dot {
  background: #fff;
  box-shadow: 0 0 0 2px #334155;
}
</style>
