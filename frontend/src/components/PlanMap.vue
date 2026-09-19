<script setup>
// Карта плана: маршрут каждого исполнителя своим цветом — линия по дорогам, старт (белый кружок
// с цветной обводкой) и пронумерованные визиты по порядку. Неназначенные заявки — серые точки.
// Если выбран исполнитель, остальные маршруты приглушаются.
// Режим «Факт» (fact) — по отметкам бригад из мобильного приложения: пройденные участки и
// выполненные точки — зелёным, участок, по которому бригада едет сейчас, — бегущим пунктиром,
// впереди — бледным цветом маршрута; значок бригады стоит там, где она сейчас.

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { moscowTimeOf } from '../utils/moscowTime.js'
import { decodePolyline } from '../utils/polyline.js'
import { routeColor } from '../utils/routeColors.js'
import { brigadeNow, visitFactState } from '../utils/routeFact.js'

const props = defineProps({
  plan: { type: Object, required: true },
  selectedEngineerId: { type: Number, default: null },
  // заявка, к которой перешли из «Заявок»: её точка крупнее, с обводкой и подписью
  focusedRequestId: { type: Number, default: null },
  references: { type: Object, default: () => ({}) },
  fact: { type: Boolean, default: false }, // показать факт по отметкам бригад
})
const emit = defineEmits(['select-engineer', 'focus-request'])

const UNASSIGNED_COLOR = '#94a3b8'
const DONE_COLOR = '#16a34a'
const ACTIVE_COLOR = '#f59e0b'
const LATE_COLOR = '#dc2626'

// участок к визиту в режиме факта: пройден, едут сейчас, впереди или к нему уже не поедут
function factLegStyle(state, color) {
  if (state === 'done' || state === 'onsite') return { color: DONE_COLOR, weight: 6, opacity: 0.9 }
  if (state === 'moving') return { color: ACTIVE_COLOR, weight: 6, opacity: 1, dashArray: '10 8', className: 'leg-moving' }
  if (state === 'cancelled' || state === 'removed') return { color: UNASSIGNED_COLOR, weight: 4, opacity: 0.7, dashArray: '3 7' }
  return { color, weight: 5, opacity: 0.3 }
}

// точка визита в режиме факта: ✓ выполнена, × не выполнена, номер — впереди
function factVisitIcon(visit, state, color, focused, atRisk) {
  // бригада отстаёт так, что к этой заявке до конца окна не успеть — красная точка
  if (atRisk) return visitIcon(visit.visit_order, LATE_COLOR, focused, true)
  if (state === 'done') return visitIcon('✓', DONE_COLOR, focused)
  if (state === 'cancelled') return visitIcon('×', UNASSIGNED_COLOR, focused)
  if (state === 'removed') return visitIcon(visit.visit_order, UNASSIGNED_COLOR, focused)
  if (state === 'moving' || state === 'onsite') return visitIcon(visit.visit_order, ACTIVE_COLOR, focused, true)
  return visitIcon(visit.visit_order, color, focused, false, 0.55)
}

// фургон бригады — рисунком, не эмодзи: эмодзи есть не во всех шрифтах
const VAN_SVG =
  '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" ' +
  'stroke-linecap="round" stroke-linejoin="round"><path d="M14 17V6H3v11h2M9 17h6M14 9h4l3 4v4h-2"/>' +
  '<circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/></svg>'

// значок бригады там, где она сейчас: на заявке, на полпути к ней или на последней выполненной
function brigadeIcon(color) {
  return L.divIcon({
    className: '',
    html:
      `<span style="display:flex;align-items:center;justify-content:center;width:30px;height:30px;` +
      `border-radius:50%;background:#fff;border:3px solid ${color};color:${color};` +
      `box-shadow:0 2px 6px rgb(0 0 0 / 35%)">${VAN_SVG}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  })
}

function brigadePosition(route, now) {
  if (now.kind === 'onsite') return [now.visit.latitude, now.visit.longitude]
  if (now.kind === 'moving') {
    const from = now.previous ? [now.previous.latitude, now.previous.longitude] : [route.start_latitude, route.start_longitude]
    return [(from[0] + now.visit.latitude) / 2, (from[1] + now.visit.longitude) / 2]
  }
  if (now.visit) return [now.visit.latitude, now.visit.longitude]
  return [route.start_latitude, route.start_longitude]
}

const container = ref(null)
let map = null
let planLayer = null
// план, под который последний раз подгонялся масштаб
let fittedPlanId = null

// имена и адреса вводит человек — экранируем, прежде чем вставлять в HTML подсказки
function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (symbol) => `&#${symbol.charCodeAt(0)};`)
}

function visitIcon(visitOrder, color, focused = false, pulse = false, opacity = 1) {
  const size = focused ? 32 : 22
  const ring = focused ? '0 0 0 4px #0f172a, 0 0 0 9px rgb(250 204 21 / 70%)' : '0 1px 3px rgb(0 0 0 / 40%)'
  return L.divIcon({
    className: pulse ? 'visit-pulse' : '',
    html:
      `<span style="display:flex;align-items:center;justify-content:center;width:${size}px;height:${size}px;` +
      `border-radius:50%;background:${color};color:#fff;font:600 ${focused ? 14 : 11}px/1 system-ui,sans-serif;` +
      `border:2px solid #fff;box-shadow:${ring};opacity:${opacity}">` +
      `${visitOrder}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

function routePoints(route) {
  return [[route.start_latitude, route.start_longitude], ...route.visits.map((visit) => [visit.latitude, visit.longitude])]
}

// маркер выделенной заявки: после подгонки масштаба у него открывается подпись
let focusedMarker = null

function drawPlan() {
  planLayer.clearLayers()
  focusedMarker = null

  // выбран исполнитель — рисуем только его маршрут: с десятком маршрутов карта иначе тормозит
  props.plan.routes.forEach((route, routeIndex) => {
    if (props.selectedEngineerId !== null && props.selectedEngineerId !== route.engineer_id) return

    const color = routeColor(routeIndex)
    const lineStyle = { color, weight: 5, opacity: 0.85 }
    const selectThisRoute = () => emit('select-engineer', route.engineer_id)

    // состояние каждого визита по отметкам бригады — только в режиме факта
    const states = route.visits.map((visit) => (props.fact ? visitFactState(visit, props.references, props.plan.id) : null))

    if (props.fact) {
      // участок i ведёт к визиту i: красим его по состоянию этого визита
      const points = routePoints(route)
      route.visits.forEach((visit, index) => {
        const leg = route.geometry[index]
        const line = leg ? decodePolyline(leg) : [points[index], points[index + 1]]
        L.polyline(line, factLegStyle(states[index], color)).on('click', selectThisRoute).addTo(planLayer)
      })
    } else if (route.geometry.length > 0) {
      for (const leg of route.geometry) {
        L.polyline(decodePolyline(leg), lineStyle).on('click', selectThisRoute).addTo(planLayer)
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

    route.visits.forEach((visit, index) => {
      const focused = visit.request_id === props.focusedRequestId
      // заявку сняли с утверждённого плана — точка серая: бригада к ней больше не едет
      const removed = Boolean(props.plan.approved_at) && visit.approved_plan_id !== props.plan.id
      const icon = props.fact
        ? factVisitIcon(visit, states[index], color, focused, (route.at_risk_request_ids ?? []).includes(visit.request_id))
        : visitIcon(visit.visit_order, removed ? UNASSIGNED_COLOR : color, focused)
      const marker = L.marker([visit.latitude, visit.longitude], { icon, zIndexOffset: focused ? 1000 : 0 })
      marker
        .bindTooltip(
          `<b>${visit.visit_order}. ${moscowTimeOf(visit.planned_arrival_time)}</b> · заявка №${visit.request_id}<br>` +
            `${escapeHtml(visit.address)}<br>` +
            `<span style="color:#64748b">${escapeHtml(route.engineer_name)}</span>`,
          { direction: 'top', offset: [0, -8] },
        )
        // клик по точке — подсветка переходит на эту заявку; маршрут не снимается
        .on('click', () => {
          emit('focus-request', visit.request_id)
          if (props.selectedEngineerId === null) selectThisRoute()
        })
        .addTo(planLayer)
      if (focused) focusedMarker = marker
    })

    // где бригада сейчас — по её отметкам
    if (props.fact) {
      const now = brigadeNow(route, props.references, props.plan.id)
      L.marker(brigadePosition(route, now), { icon: brigadeIcon(color), zIndexOffset: 2000 })
        .bindTooltip(`<b>${escapeHtml(route.engineer_name)}</b><br>${escapeHtml(now.text)}`, { direction: 'top', offset: [0, -12] })
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
    // открыли план сразу на маршруте бригады (переход из заявки) — масштаб по этому маршруту
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
  focusedMarker?.openTooltip()
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
  // клик по пустому месту карты снимает подсветку заявки: точки её сами не пропускают к карте
  map.on('click', () => {
    if (props.focusedRequestId !== null) emit('focus-request', null)
  })

  await nextTick()
  map.invalidateSize()
  drawPlan()
})

onBeforeUnmount(() => map?.remove())

watch(() => props.plan, drawPlan)
watch(() => props.selectedEngineerId, showSelectedRoute)
// подсветку перенесли кликом в карточке маршрута — точка могла оказаться за краем карты
function showFocused() {
  drawPlan()
  if (focusedMarker && !map.getBounds().contains(focusedMarker.getLatLng())) map.panTo(focusedMarker.getLatLng())
}

watch(() => props.focusedRequestId, showFocused)
watch(() => props.fact, drawPlan)
</script>

<template>
  <div class="map-frame">
    <div ref="container" class="map"></div>
    <div v-if="fact" class="map-legend">
      <span><i class="legend-dot" :style="{ background: DONE_COLOR }"></i>пройдено, выполнено</span>
      <span><i class="legend-dot" :style="{ background: ACTIVE_COLOR }"></i>едет / на месте</span>
      <span><i class="legend-dot" :style="{ background: UNASSIGNED_COLOR }"></i>не выполнена, снята</span>
      <span><i class="legend-dot" :style="{ background: LATE_COLOR }"></i>не успевает к окну</span>
      <span><span class="legend-van" v-html="VAN_SVG"></span>где бригада</span>
    </div>
    <div v-else class="map-legend">
      <span><i class="legend-dot start-dot"></i>старт исполнителя</span>
      <span><i class="legend-dot" :style="{ background: UNASSIGNED_COLOR }"></i>не назначена</span>
      <span class="muted">цифра — порядок визита</span>
    </div>
  </div>
</template>

<!-- анимации факта: Leaflet рисует линии и значки вне компонента, поэтому стили не scoped -->
<style>
/* участок, по которому бригада едет сейчас, — бегущий пунктир */
.leg-moving {
  animation: leg-moving 0.9s linear infinite;
}

@keyframes leg-moving {
  to {
    stroke-dashoffset: -18;
  }
}

/* заявка, где бригада сейчас (едет к ней или на месте), — пульсирующее кольцо */
.visit-pulse > span {
  animation: visit-pulse 1.6s ease-out infinite;
}

@keyframes visit-pulse {
  0% {
    box-shadow: 0 0 0 0 rgb(245 158 11 / 70%);
  }
  100% {
    box-shadow: 0 0 0 12px rgb(245 158 11 / 0%);
  }
}
</style>

<style scoped>
.legend-van {
  display: inline-flex;
  margin-right: 4px;
  vertical-align: middle;
  color: #334155;
}

.start-dot {
  background: #fff;
  box-shadow: 0 0 0 2px #334155;
}
</style>
