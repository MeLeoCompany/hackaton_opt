<script setup>
// Карта исполнителей: стартовая точка каждого исполнителя, прошедшего фильтры.
// Цвет — тип транспорта, выбранный — крупнее с тёмной обводкой.

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { formatMoscowWindow } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { transportColor } from '../utils/transportColors.js'

const props = defineProps({
  engineers: { type: Array, required: true },
  references: { type: Object, required: true },
  selectedId: { type: Number, default: null },
})
const emit = defineEmits(['select'])

const container = ref(null)
let map = null
let markerLayer = null
const markerByEngineerId = new Map()
// номера исполнителей, под которых последний раз подгонялся масштаб
let fittedEngineerIds = ''

function markerStyle(engineer) {
  const isSelected = engineer.id === props.selectedId
  return {
    radius: isSelected ? 11 : 8,
    color: isSelected ? '#0f172a' : '#ffffff',
    weight: isSelected ? 3 : 2,
    fillColor: transportColor(engineer.transport_id),
    fillOpacity: 0.9,
  }
}

// имя вводит человек — экранируем, прежде чем вставлять в HTML подсказки
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (symbol) => `&#${symbol.charCodeAt(0)};`)
}

function tooltipHtml(engineer) {
  const transport = referenceName(props.references, 'transports', engineer.transport_id)
  const skills = engineer.skill_ids.map((skillId) => referenceName(props.references, 'skills', skillId)).join(', ')
  return (
    `<b>${escapeHtml(engineer.name)}</b> · ${escapeHtml(transport)}<br>` +
    `смена ${formatMoscowWindow(engineer.shift_start, engineer.shift_end)}<br>` +
    `<span style="color:#64748b">${escapeHtml(skills)}</span>`
  )
}

function drawMarkers() {
  markerLayer.clearLayers()
  markerByEngineerId.clear()

  for (const engineer of props.engineers) {
    const marker = L.circleMarker([engineer.start_latitude, engineer.start_longitude], markerStyle(engineer))
      .bindTooltip(tooltipHtml(engineer), { direction: 'top', offset: [0, -6] })
      .on('click', () => emit('select', engineer.id))
    marker.addTo(markerLayer)
    markerByEngineerId.set(engineer.id, marker)
  }

  const engineerIds = props.engineers.map((engineer) => engineer.id).join(',')
  if (engineerIds === fittedEngineerIds) return
  fittedEngineerIds = engineerIds

  const bounds = L.latLngBounds(props.engineers.map((engineer) => [engineer.start_latitude, engineer.start_longitude]))
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 })
}

function highlightSelected() {
  for (const engineer of props.engineers) {
    markerByEngineerId.get(engineer.id)?.setStyle(markerStyle(engineer))
  }
  const selectedMarker = markerByEngineerId.get(props.selectedId)
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
  highlightSelected()
})

onBeforeUnmount(() => map?.remove())

watch(() => props.engineers, drawMarkers)
watch(() => props.references, drawMarkers)
watch(() => props.selectedId, highlightSelected)
</script>

<template>
  <div class="map-frame">
    <div ref="container" class="map"></div>
    <div class="map-legend">
      <span v-for="transport in references.transports" :key="transport.id">
        <i class="legend-dot" :style="{ background: transportColor(transport.id) }"></i>{{ transport.name }}
      </span>
      <span class="muted">на карте: {{ engineers.length }}</span>
    </div>
  </div>
</template>
