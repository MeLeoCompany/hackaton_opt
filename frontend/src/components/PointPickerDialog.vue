<script setup>
// Выбор координаты мышью: клик по карте ставит точку, её же можно перетащить.
// Нужен, чтобы адрес заявки и старт бригады не приходилось набирать числами.
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  latitude: { type: [Number, String], default: '' },
  longitude: { type: [Number, String], default: '' },
  // уже известные точки — чтобы было видно, куда ставить новую
  contextPoints: { type: Array, default: () => [] },
})
const emit = defineEmits(['pick', 'close'])

const MOSCOW_CENTER = [55.751244, 37.618423]
const COORDINATE_DIGITS = 6

const container = ref(null)
const picked = ref(validCoordinates(props.latitude, props.longitude))
let map = null
let marker = null

function validCoordinates(latitude, longitude) {
  const lat = Number(latitude)
  const lon = Number(longitude)
  if (latitude === '' || longitude === '' || Number.isNaN(lat) || Number.isNaN(lon)) return null
  return { latitude: lat, longitude: lon }
}

function round(value) {
  return Number(value.toFixed(COORDINATE_DIGITS))
}

function movePoint(latlng) {
  picked.value = { latitude: round(latlng.lat), longitude: round(latlng.lng) }
  if (marker) {
    marker.setLatLng(latlng)
    return
  }
  marker = L.marker(latlng, { draggable: true }).addTo(map)
  marker.on('dragend', () => movePoint(marker.getLatLng()))
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

  drawContext()

  if (picked.value) {
    movePoint(L.latLng(picked.value.latitude, picked.value.longitude))
    map.setView([picked.value.latitude, picked.value.longitude], 15)
  } else if (props.contextPoints.length) {
    map.fitBounds(
      L.latLngBounds(props.contextPoints.map((point) => [point.latitude, point.longitude])),
      { padding: [40, 40] },
    )
  }

  map.on('click', (event) => movePoint(event.latlng))
  // карта появляется в уже открытом окне — без этого плитки встают неровно
  setTimeout(() => map.invalidateSize(), 0)
})

onBeforeUnmount(() => map?.remove())

function confirm() {
  if (picked.value) emit('pick', picked.value.latitude, picked.value.longitude)
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')" @keyup.esc="emit('close')">
    <div class="dialog" role="dialog" :aria-label="title">
      <header>
        <strong>{{ title }}</strong>
        <span class="hint">Кликните по карте или перетащите метку</span>
      </header>

      <div ref="container" class="picker-map"></div>

      <footer>
        <span v-if="picked" class="coordinates">
          {{ picked.latitude.toFixed(6) }}, {{ picked.longitude.toFixed(6) }}
        </span>
        <span v-else class="hint">Точка не выбрана</span>
        <div class="dialog-actions">
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

.picker-map {
  height: min(60vh, 460px);
  border-radius: 8px;
}

.hint {
  color: #64748b;
  font-size: 13px;
}

.coordinates {
  font-variant-numeric: tabular-nums;
}

.dialog-actions {
  display: flex;
  gap: 8px;
}
</style>
