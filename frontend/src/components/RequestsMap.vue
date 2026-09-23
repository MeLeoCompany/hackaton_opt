<script setup>
// Карта заявок: точка на каждую заявку, прошедшую фильтры (со всех страниц списка).
// Цвет — статус заявки, теми же цветами, что у плашек статусов в таблице: на карте и в
// списке одна заявка выглядит одинаково. Авария — красная обводка точки, выбранная —
// крупнее с тёмной обводкой, отмеченная галочкой — в синем кольце.
// Клик по точке сообщает наверх, какую заявку выбрали.

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { formatMoscowWindow } from '../utils/moscowTime.js'
import { useCoverage } from '../composables/useCoverage.js'
import { createCoverageLayer } from '../utils/coverageLayer.js'
import CoverageToggle from './CoverageToggle.vue'
import { isUrgent, referenceName } from '../utils/referenceNames.js'
import { orderedStatuses, statusCode, statusPlannable } from '../utils/requestStatuses.js'

const props = defineProps({
  requests: { type: Array, required: true },
  references: { type: Object, required: true },
  selectedId: { type: Number, default: null },
  // отмеченные галочками строки таблицы: на карте они в синем кольце, остальные приглушены
  checkedIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['select'])

// цвет статуса: насыщенная версия цвета плашки из таблицы (styles/common.css, .status-badge)
const STATUS_COLORS = {
  new: '#2563eb',
  planned: '#7c3aed',
  en_route: '#ea580c',
  in_progress: '#d97706',
  done: '#16a34a',
  cancelled: '#94a3b8',
}
const OTHER_STATUS_COLOR = '#64748b'
const URGENT_COLOR = '#dc2626'

// отмеченные приходят списком номеров — для отрисовки удобнее множество
const checked = computed(() => new Set(props.checkedIds))

// сколько отмеченных заявок реально видно на карте: часть могла уйти под фильтры
const checkedOnMap = computed(() => props.requests.filter((request) => checked.value.has(request.id)).length)

// легенда — статусы справочника в порядке работы с заявкой; авария поверх статуса,
// поэтому она отдельным пунктом с красным кольцом
const legend = computed(() => [
  ...orderedStatuses(props.references).map((status) => ({
    label: status.name,
    color: STATUS_COLORS[status.code] ?? OTHER_STATUS_COLOR,
  })),
  { label: 'авария', ring: URGENT_COLOR },
])
// зона покрытия: слой включается ползунком в углу карты
const { shown: coverageShown } = useCoverage()
let coverageLayer = null

function syncCoverage() {
  if (!map) return
  if (coverageShown.value && !coverageLayer) {
    coverageLayer = createCoverageLayer().addTo(map)
    // зона — подложка: маршруты и точки остаются поверх неё
    coverageLayer.eachLayer((shape) => shape.bringToBack())
  } else if (!coverageShown.value && coverageLayer) {
    map.removeLayer(coverageLayer)
    coverageLayer = null
  }
}

const container = ref(null)
let map = null
let markerLayer = null
let haloLayer = null
const markerByRequestId = new Map()
// номера заявок, под которые последний раз подгонялся масштаб
let fittedRequestIds = ''

function markerColor(request) {
  return STATUS_COLORS[statusCode(props.references, request.status_id)] ?? OTHER_STATUS_COLOR
}

function markerStyle(request) {
  const isSelected = request.id === props.selectedId
  // заявка, которая в расчёт уже не идёт (выполнена, отменена), бледнее — как в таблице
  const planned = statusPlannable(props.references, request.status_id)
  return {
    radius: isSelected ? 11 : 7,
    color: isSelected ? '#0f172a' : isUrgent(props.references, request) ? URGENT_COLOR : '#ffffff',
    weight: isSelected || isUrgent(props.references, request) ? 3 : 1.5,
    fillColor: markerColor(request),
    fillOpacity: planned ? 0.9 : 0.55,
  }
}

// кольцо вокруг отмеченной заявки: отдельным слоем под точками, кликам не мешает.
// Остальные точки не приглушаем — по ним видно обстановку вокруг выбранных
function haloStyle() {
  return { radius: 13, color: '#2563eb', weight: 3, opacity: 1, fill: false, interactive: false }
}

function drawHalos() {
  haloLayer.clearLayers()
  for (const request of props.requests) {
    if (!checked.value.has(request.id)) continue
    L.circleMarker([request.latitude, request.longitude], haloStyle()).addTo(haloLayer)
  }
}

// адрес вводит человек — экранируем, прежде чем вставлять в HTML подсказки
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (symbol) => `&#${symbol.charCodeAt(0)};`)
}

function tooltipHtml(request) {
  const window = formatMoscowWindow(request.window_start, request.window_end)
  const workType = referenceName(props.references, 'work_types', request.work_type_id)
  // статус пишем всегда: по точке видно, что с заявкой (Новая, В плане, Выполнена…)
  const statusName = referenceName(props.references, 'request_statuses', request.status_id)
  const status = `<br><span style="color:${markerColor(request)}">${escapeHtml(statusName)}</span>`
  // приоритет цветом больше не показан — называем его словами
  const priorityName = referenceName(props.references, 'priorities', request.priority_id)
  const priority = isUrgent(props.references, request)
    ? `<br><b style="color:${URGENT_COLOR}">${escapeHtml(priorityName)}</b>`
    : `<br><span style="color:#94a3b8">${escapeHtml(priorityName)}</span>`
  return (
    `<b>№${request.id}</b> · ${window}<br>` +
    `${escapeHtml(request.address)}<br>` +
    `<span style="color:#64748b">${escapeHtml(workType)}</span>` +
    status +
    priority
  )
}

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

// отметки поменялись: перерисовываем кольца и приглушение, не трогая масштаб
function redrawChecked() {
  drawHalos()
  for (const request of props.requests) {
    markerByRequestId.get(request.id)?.setStyle(markerStyle(request))
  }
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
  // кольца добавляем первыми: они ложатся под точки
  haloLayer = L.layerGroup().addTo(map)
  markerLayer = L.layerGroup().addTo(map)

  // карта появляется по кнопке — даём раскладке досчитать размер контейнера
  await nextTick()
  map.invalidateSize()
  drawMarkers()
  drawHalos()
  syncCoverage()
  // заявку выбрали в таблице до переключения на карту — сразу показываем её
  highlightSelected()
})

onBeforeUnmount(() => map?.remove())

watch(coverageShown, syncCoverage)

// другой набор заявок (фильтр, загрузка, правка) — перерисовываем;
// смена сортировки или страницы набор не меняет, поэтому карта не дёргается
watch(() => props.requests, () => {
  drawMarkers()
  drawHalos()
})
watch(() => props.references, drawMarkers)
watch(() => props.selectedId, highlightSelected)
watch(() => props.checkedIds, redrawChecked)
</script>

<template>
  <div class="map-frame">
    <div ref="container" class="map"></div>
    <CoverageToggle />
    <div class="map-legend">
      <span v-for="item in legend" :key="item.label">
        <i
          class="legend-dot"
          :style="item.ring ? { background: '#fff', boxShadow: `inset 0 0 0 3px ${item.ring}` } : { background: item.color }"
        ></i
        >{{ item.label }}
      </span>
      <span v-if="checkedIds.length" class="checked-note">
        <i class="legend-ring"></i>отмечено: {{ checkedOnMap }}<template v-if="checkedOnMap < checkedIds.length">
          из {{ checkedIds.length }} — остальные скрыты фильтрами</template
        >
      </span>
      <span class="muted">на карте: {{ requests.length }}</span>
    </div>
  </div>
</template>

