<script setup>
// Выбор координаты: клик по карте ставит точку, её можно перетащить, а можно вписать
// широту и долготу в поля внизу — метка переедет туда же. Нужен, чтобы адрес заявки и старт
// бригады не приходилось набирать числами вслепую.
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  latitude: { type: [Number, String], default: '' },
  longitude: { type: [Number, String], default: '' },
  // уже известные точки — чтобы было видно, куда ставить новую
  contextPoints: { type: Array, default: () => [] },
  // заметные ориентиры (офисы): клик по такому значку ставит точку прямо в него
  landmarks: { type: Array, default: () => [] },
  // точка «по умолчанию»: кнопка в окне сразу выбирает её — { latitude, longitude, label }
  home: { type: Object, default: null },
})
const emit = defineEmits(['pick', 'close'])

const MOSCOW_CENTER = [55.751244, 37.618423]
const COORDINATE_DIGITS = 6
import { useCoverage } from '../composables/useCoverage.js'
import { createCoverageLayer } from '../utils/coverageLayer.js'
import CoverageToggle from './CoverageToggle.vue'

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
const picked = ref(validCoordinates(props.latitude, props.longitude))
// поля ввода живут своим текстом: пока координата набирается, метка стоит на месте
const latitudeText = ref(picked.value ? String(picked.value.latitude) : '')
const longitudeText = ref(picked.value ? String(picked.value.longitude) : '')
let map = null
let marker = null

function validCoordinates(latitude, longitude) {
  const lat = Number(String(latitude).replace(',', '.'))
  const lon = Number(String(longitude).replace(',', '.'))
  if (latitude === '' || longitude === '' || Number.isNaN(lat) || Number.isNaN(lon)) return null
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null
  return { latitude: lat, longitude: lon }
}

function round(value) {
  return Number(value.toFixed(COORDINATE_DIGITS))
}

function placeMarker(latlng) {
  if (marker) {
    marker.setLatLng(latlng)
    return
  }
  marker = L.marker(latlng, { draggable: true }).addTo(map)
  marker.on('dragend', () => movePoint(marker.getLatLng()))
}

// точку поставили мышью — поля показывают её координаты
function movePoint(latlng) {
  picked.value = { latitude: round(latlng.lat), longitude: round(latlng.lng) }
  latitudeText.value = String(picked.value.latitude)
  longitudeText.value = String(picked.value.longitude)
  placeMarker(latlng)
}

// координаты вписали руками — метка переезжает, карта подвигается к ней
function typePoint() {
  const typed = validCoordinates(latitudeText.value, longitudeText.value)
  if (!typed) {
    picked.value = null
    return
  }
  picked.value = typed
  const latlng = L.latLng(typed.latitude, typed.longitude)
  placeMarker(latlng)
  map.panTo(latlng)
}

// значок офиса: квадрат, чтобы не путать с кружками других точек
const LANDMARK_ICON = L.divIcon({
  className: 'landmark-marker',
  html: '<span></span>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

function drawLandmarks() {
  for (const point of props.landmarks) {
    L.marker([point.latitude, point.longitude], { icon: LANDMARK_ICON })
      .bindTooltip(point.label ?? '')
      .on('click', () => movePoint(L.latLng(point.latitude, point.longitude)))
      .addTo(map)
  }
}

function drawContext() {
  for (const point of props.contextPoints) {
    L.circleMarker([point.latitude, point.longitude], {
      radius: 4,
      color: '#94a3b8',
      weight: 1,
      fillColor: '#cbd5e1',
      fillOpacity: 0.9,
    })
      .bindTooltip(point.label ?? '')
      .addTo(map)
  }
}

onMounted(async () => {
  await nextTick()
  map = L.map(container.value).setView(MOSCOW_CENTER, 10)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map)

  syncCoverage()
  drawContext()
  drawLandmarks()

  const knownPoints = [...props.contextPoints, ...props.landmarks]
  if (picked.value) {
    movePoint(L.latLng(picked.value.latitude, picked.value.longitude))
    map.setView([picked.value.latitude, picked.value.longitude], 15)
  } else if (knownPoints.length) {
    map.fitBounds(
      L.latLngBounds(knownPoints.map((point) => [point.latitude, point.longitude])),
      { padding: [40, 40] },
    )
  }

  map.on('click', (event) => movePoint(event.latlng))
  // карта появляется в уже открытом окне — без этого плитки встают неровно
  setTimeout(() => map.invalidateSize(), 0)
})

onBeforeUnmount(() => map?.remove())

watch(coverageShown, syncCoverage)

function confirm() {
  if (picked.value) emit('pick', picked.value.latitude, picked.value.longitude)
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')" @keyup.esc="emit('close')">
    <div class="dialog" role="dialog" :aria-label="title">
      <header>
        <strong>{{ title }}</strong>
        <span class="hint">
          Кликните по карте, перетащите метку или впишите координаты<template v-if="landmarks.length">;
            ■ — офисы, клик ставит точку в офис</template>
        </span>
      </header>

      <div class="picker-frame">
        <div ref="container" class="picker-map"></div>
        <CoverageToggle />
      </div>

      <footer>
        <div class="coordinate-fields">
          <label>
            <span>Широта</span>
            <input v-model="latitudeText" inputmode="decimal" placeholder="55.751244" @input="typePoint" />
          </label>
          <label>
            <span>Долгота</span>
            <input v-model="longitudeText" inputmode="decimal" placeholder="37.618423" @input="typePoint" />
          </label>
          <span v-if="!picked" class="hint">
            {{ latitudeText || longitudeText ? 'Координаты вне допустимых границ' : 'Точка не выбрана' }}
          </span>
        </div>
        <div class="dialog-actions">
          <button v-if="home" @click="emit('pick', home.latitude, home.longitude)">{{ home.label }}</button>
          <button class="primary" :disabled="!picked" @click="confirm">Готово</button>
          <button @click="emit('close')">Отмена</button>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(15 23 42 / 45%);
}

.dialog {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(820px, 92vw);
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
}

.dialog header,
.dialog footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.picker-frame {
  position: relative;
}

.picker-map {
  height: min(60vh, 460px);
  border-radius: 8px;
}

.hint {
  color: #64748b;
  font-size: 13px;
}

.coordinate-fields {
  display: flex;
  align-items: center;
  gap: 10px;
}

.coordinate-fields label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: 13px;
}

.coordinate-fields input {
  width: 110px;
  font-variant-numeric: tabular-nums;
}

/* значок офиса: синий квадрат с белой рамкой, заметнее серых кружков */
:deep(.landmark-marker span) {
  display: block;
  width: 12px;
  height: 12px;
  border: 2px solid #fff;
  border-radius: 3px;
  background: #1d4ed8;
  box-shadow: 0 0 0 1px #1d4ed8;
  cursor: pointer;
}

.dialog-actions {
  display: flex;
  gap: 8px;
}
</style>
