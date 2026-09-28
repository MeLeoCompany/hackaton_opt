<script setup>
// Карта исполнителей: стартовая точка каждого исполнителя, прошедшего фильтры.
// Цвет — тип транспорта, выбранный — крупнее с тёмной обводкой. Офисы из справочника —
// синие квадраты под точками: видно, кто выезжает из офиса, а кто из своей точки.

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { formatMoscowWindow } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { transportColor } from '../utils/transportColors.js'

const props = defineProps({
  engineers: { type: Array, required: true },
  references: { type: Object, required: true },
  selectedId: { type: Number, default: null },
  // отмеченные галочками строки таблицы: на карте они в синем кольце, остальные приглушены
  checkedIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['select'])

// отмеченные приходят списком номеров — для отрисовки удобнее множество
const checked = computed(() => new Set(props.checkedIds))
// сколько отмеченных смен реально видно на карте: часть могла уйти под фильтры
const checkedOnMap = computed(() => props.engineers.filter((engineer) => checked.value.has(engineer.id)).length)

const container = ref(null)
let map = null
let markerLayer = null
let haloLayer = null
let officeLayer = null
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

// кольцо вокруг отмеченной смены: отдельным слоем под точками, кликам не мешает
function drawHalos() {
  haloLayer.clearLayers()
  for (const engineer of props.engineers) {
    if (!checked.value.has(engineer.id)) continue
    L.circleMarker([engineer.start_latitude, engineer.start_longitude], {
      radius: 14,
      color: '#2563eb',
      weight: 3,
      opacity: 1,
      fill: false,
      interactive: false,
    }).addTo(haloLayer)
  }
}

// отметки поменялись: перерисовываем кольца и приглушение, не трогая масштаб
function redrawChecked() {
  drawHalos()
  for (const engineer of props.engineers) {
    markerByEngineerId.get(engineer.id)?.setStyle(markerStyle(engineer))
  }
}

// имя вводит человек — экранируем, прежде чем вставлять в HTML подсказки
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (symbol) => `&#${symbol.charCodeAt(0)};`)
}

const OFFICE_ICON = L.divIcon({
  className: 'office-marker',
  html: '<span></span>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

function drawOffices() {
  officeLayer.clearLayers()
  for (const office of props.references.offices ?? []) {
    L.marker([office.latitude, office.longitude], { icon: OFFICE_ICON, zIndexOffset: -1000 })
      .bindTooltip(`<b>Офис «${escapeHtml(office.name)}»</b><br>${escapeHtml(office.address)}`, {
        direction: 'top',
        offset: [0, -6],
      })
      .addTo(officeLayer)
  }
}

function tooltipHtml(engineer) {
  const transport = referenceName(props.references, 'transports', engineer.transport_id)
  const skills = engineer.skill_ids.map((skillId) => referenceName(props.references, 'skills', skillId)).join(', ')
  const start = engineer.start_at_office
    ? `выезд из офиса «${escapeHtml(referenceName(props.references, 'offices', engineer.office_id))}»<br>`
    : ''
  return (
    `<b>${escapeHtml(engineer.name)}</b> · ${escapeHtml(transport)}<br>` +
    start +
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
  // офисы ниже точек исполнителей: кружок бригады, стоящей в офисе, лежит поверх квадрата
  officeLayer = L.layerGroup().addTo(map)
  // кольца отмеченных смен ложатся под точки
  haloLayer = L.layerGroup().addTo(map)
  markerLayer = L.layerGroup().addTo(map)

  // карта появляется по кнопке — даём раскладке досчитать размер контейнера
  await nextTick()
  map.invalidateSize()
  drawOffices()
  drawMarkers()
  drawHalos()
  highlightSelected()
})

onBeforeUnmount(() => map?.remove())

watch(() => props.engineers, () => {
  drawMarkers()
  drawHalos()
})
watch(
  () => props.references,
  () => {
    drawOffices()
    drawMarkers()
  },
)
watch(() => props.selectedId, highlightSelected)
watch(() => props.checkedIds, redrawChecked)
</script>

<template>
  <div class="map-frame">
    <div ref="container" class="map"></div>
    <div class="map-legend">
      <span v-for="transport in references.transports" :key="transport.id">
        <i class="legend-dot" :style="{ background: transportColor(transport.id) }"></i>{{ transport.name }}
      </span>
      <span v-if="references.offices?.length"><i class="office-legend"></i>офис</span>
      <span v-if="checkedIds.length" class="checked-note">
        <i class="legend-ring"></i>отмечено: {{ checkedOnMap }}<template v-if="checkedOnMap < checkedIds.length">
          из {{ checkedIds.length }} — остальные скрыты фильтрами</template
        >
      </span>
      <span class="muted">на карте: {{ engineers.length }}</span>
    </div>
  </div>
</template>

<style scoped>
:deep(.office-marker span) {
  display: block;
  width: 12px;
  height: 12px;
  border: 2px solid #fff;
  border-radius: 3px;
  background: #1d4ed8;
  box-shadow: 0 0 0 1px #1d4ed8;
}

.office-legend {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 4px;
  border-radius: 2px;
  background: #1d4ed8;
  vertical-align: -1px;
}
</style>
