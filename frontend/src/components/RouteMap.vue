<script setup>
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { TRAVEL_MODES } from '../api/travelApi.js'
import { decodePolyline } from '../utils/polyline.js'

const props = defineProps({
  points: { type: Array, required: true },
  route: { type: Object, default: null },
})
const emit = defineEmits(['add-point'])

const container = ref(null)
let map = null
let markerLayer = null
let routeLayer = null

// цвета чередуются по участкам, чтобы было видно, где кончается одно плечо и начинается другое.
// у общественного транспорта цвет вместо этого говорит, чем человек едет: метро, пешком, наземным
const LEG_COLORS = ['#2563eb', '#db2777', '#059669', '#d97706', '#7c3aed']

function numberedIcon(index, total) {
  const isStart = index === 0
  const isEnd = index === total - 1 && total > 1
  const color = isStart ? '#059669' : isEnd ? '#dc2626' : '#2563eb'
  return L.divIcon({
    className: 'point-marker',
    html: `<span style="background:${color}">${index + 1}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
}

function drawMarkers() {
  markerLayer.clearLayers()
  props.points.forEach((point, index) => {
    L.marker([point.latitude, point.longitude], {
      icon: numberedIcon(index, props.points.length),
    })
      .bindTooltip(`Точка ${index + 1}: ${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)}`)
      .addTo(markerLayer)
  })
}

function drawRoute() {
  routeLayer.clearLayers()
  if (!props.route) return

  if (props.route.geometry.length > 0) {
    props.route.geometry.forEach((leg, index) => {
      const mode = props.route.legs?.[index]?.mode
      const routeId = props.route.legs?.[index]?.route_short_name || props.route.legs?.[index]?.route_id
      const routeColor = props.route.legs?.[index]?.route_color
      const style = mode && mode !== 'road' ? TRAVEL_MODES[mode] : null
      L.polyline(decodePolyline(leg), {
        color: routeColor || (style ? style.color : LEG_COLORS[index % LEG_COLORS.length]),
        weight: 5,
        opacity: 0.8,
        // пеший кусок пунктиром: это не поездка
        // своим ходом — пунктиром: пешком мелким, на велосипеде крупнее
        dashArray: mode === 'walk' ? '6 6' : mode === 'bike' ? '10 6' : undefined,
      })
        .bindTooltip(
          style
            ? `Участок ${index + 1}: ${style.label}${routeId ? ` · ${routeId}` : ''}`
            : `Участок ${index + 1}`,
        )
        .addTo(routeLayer)
    })
  } else {
    // haversine-провайдер геометрии не даёт — рисуем прямые, чтобы это было видно глазом
    const straight = props.points.map((p) => [p.latitude, p.longitude])
    L.polyline(straight, { color: '#94a3b8', weight: 4, dashArray: '8 8' }).addTo(routeLayer)
  }

  const bounds = routeLayer.getBounds()
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40] })
}

onMounted(() => {
  map = L.map(container.value).setView([55.751244, 37.618423], 10)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map)

  markerLayer = L.layerGroup().addTo(map)
  // featureGroup, а не layerGroup: только у него есть getBounds для подгонки масштаба
  routeLayer = L.featureGroup().addTo(map)

  map.on('click', (event) => emit('add-point', event.latlng.lat, event.latlng.lng))
})

onBeforeUnmount(() => map?.remove())

watch(() => props.points, drawMarkers, { deep: true })
watch(() => props.route, drawRoute)
</script>

<template>
  <!-- карта тянется на всю высоту блока, ползунок покрытия — поверх неё в углу -->
  <div class="map-frame">
    <div ref="container" class="map"></div>
    <!-- часы демонстрации висят ровно над этим углом карты: опускаем ползунок под них -->
  </div>
</template>

<style>
.map-frame {
  position: relative;
  width: 100%;
  height: 100%;
}

.map {
  width: 100%;
  height: 100%;
}

.point-marker span {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  color: #fff;
  font:
    600 13px/1 system-ui,
    sans-serif;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgb(0 0 0 / 40%);
}
</style>
