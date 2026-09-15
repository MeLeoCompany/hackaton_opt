<script setup>
// Карта заявок: точка на каждую заявку, прошедшую фильтры (со всех страниц списка).
// Срочные — красные, обычные — синие, выбранная — крупнее и с тёмной обводкой.
// Клик по точке сообщает наверх, какую заявку выбрали.

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { formatMoscowWindow } from '../utils/moscowTime.js'
import { isUrgent, referenceName } from '../utils/referenceNames.js'

const props = defineProps({
  requests: { type: Array, required: true },
  references: { type: Object, required: true },
  selectedId: { type: Number, default: null },
})
const emit = defineEmits(['select'])

const REGULAR_COLOR = '#2563eb'
const URGENT_COLOR = '#dc2626'
const INACTIVE_COLOR = '#94a3b8'

const container = ref(null)
let map = null
let markerLayer = null
const markerByRequestId = new Map()

function markerColor(request) {
  if (!request.is_active) return INACTIVE_COLOR
  return isUrgent(props.references, request) ? URGENT_COLOR : REGULAR_COLOR
}

function markerStyle(request) {
  const isSelected = request.id === props.selectedId
  return {
    radius: isSelected ? 11 : 7,
    color: isSelected ? '#0f172a' : '#ffffff',
    weight: isSelected ? 3 : 1.5,
    fillColor: markerColor(request),
    fillOpacity: request.is_active ? 0.9 : 0.6,
  }
}

// адрес вводит человек — экранируем, прежде чем вставлять в HTML подсказки
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (symbol) => `&#${symbol.charCodeAt(0)};`)
}

function tooltipHtml(request) {
  const window = formatMoscowWindow(request.window_start, request.window_end)
  const skill = referenceName(props.references, 'skills', request.skill_id)
  const status = request.is_active ? '' : '<br><span style="color:#94a3b8">выключена из планирования</span>'
  return (
    `<b>№${request.id}</b> · ${window}<br>` +
    `${escapeHtml(request.address)}<br>` +
    `<span style="color:#64748b">${escapeHtml(skill)}</span>` +
    status
  )
}

// номера заявок, под которые последний раз подгонялся масштаб
let fittedRequestIds = ''

function drawMarkers() {
  markerLayer.clearLayers()
  markerByRequestId.clear()

  for (const request of props.requests) {
    const marker = L.circleMarker([request.latitude, request.longitude], markerStyle(request))
      .bindTooltip(tooltipHtml(request), { direction: 'top', offset: [0, -6] })
      .on('click', () => emit('select', request.id))
    marker.addTo(markerLayer)
    markerByRequestId.set(request.id, marker)
  }

  // масштаб подгоняем, только когда поменялся сам набор заявок (фильтр, загрузка),
  // а не их свойства — иначе на каждое включение/выключение заявки карта прыгает
  const requestIds = props.requests.map((request) => request.id).join(',')
  if (requestIds === fittedRequestIds) return
  fittedRequestIds = requestIds

  const bounds = L.latLngBounds(props.requests.map((request) => [request.latitude, request.longitude]))
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 })
}

function highlightSelected() {
  for (const request of props.requests) {
    markerByRequestId.get(request.id)?.setStyle(markerStyle(request))
  }
  const selectedMarker = markerByRequestId.get(props.selectedId)
  if (selectedMarker) {
    selectedMarker.bringToFront()
    map.panTo(selectedMarker.getLatLng())
  }
}

onMounted(async () => {
  map = L.map(container.value).setView([55.751244, 37.618423], 10)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map)
  markerLayer = L.layerGroup().addTo(map)

  // карта появляется по кнопке — даём раскладке досчитать размер контейнера
  await nextTick()
  map.invalidateSize()
  drawMarkers()
  // заявку выбрали в таблице до переключения на карту — сразу показываем её
  highlightSelected()
})

onBeforeUnmount(() => map?.remove())

// другой набор заявок (фильтр, загрузка, правка) — перерисовываем и подгоняем масштаб;
// смена сортировки или страницы набор не меняет, поэтому карта не дёргается
watch(() => props.requests, drawMarkers)
watch(() => props.references, drawMarkers)
watch(() => props.selectedId, highlightSelected)
</script>

<template>
  <div class="map-wrap">
    <div ref="container" class="map"></div>
    <div class="legend">
      <span><i class="dot regular"></i>Обычная</span>
      <span><i class="dot urgent"></i>Срочная</span>
      <span><i class="dot inactive"></i>Выключена</span>
      <span class="count">на карте: {{ requests.length }}</span>
    </div>
  </div>
</template>

<style scoped>
.map-wrap {
  position: relative;
  height: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.map {
  width: 100%;
  height: 100%;
}

.legend {
  position: absolute;
  left: 10px;
  bottom: 10px;
  z-index: 1000;
  display: flex;
  gap: 12px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 1px 4px rgb(0 0 0 / 15%);
  font-size: 12px;
  color: #334155;
}

.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 5px;
  border-radius: 50%;
  border: 1.5px solid #fff;
  box-shadow: 0 0 0 1px rgb(0 0 0 / 15%);
  vertical-align: -1px;
}

.dot.regular {
  background: #2563eb;
}

.dot.urgent {
  background: #dc2626;
}

.dot.inactive {
  background: #94a3b8;
}

.count {
  color: #64748b;
}
</style>
