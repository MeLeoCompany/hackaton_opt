<script setup>
import { TRAVEL_MODES } from '../api/travelApi.js'

const props = defineProps({
  route: { type: Object, default: null },
  matrix: { type: Object, default: null },
})

function formatDuration(minutes) {
  const hours = Math.floor(minutes / 60)
  const rest = Math.round(minutes % 60)
  return hours > 0 ? `${hours} ч ${rest} мин` : `${rest} мин`
}

function modeOf(leg) {
  return TRAVEL_MODES[leg.mode] ?? TRAVEL_MODES.road
}

// сумма плеч по матрице пригодится, чтобы своими глазами увидеть расхождение с /route
function matrixLegSum(matrix) {
  return matrix.distances_km
    .slice(0, -1)
    .reduce((total, row, index) => row[index + 1] === null ? Infinity : total + row[index + 1], 0)
}
</script>

<template>
  <div v-if="route" class="summary">
    <h3>Маршрут</h3>
    <dl>
      <div><dt>Пробег</dt><dd>{{ route.distance_km.toFixed(2) }} км</dd></div>
      <div><dt>Время</dt><dd>{{ formatDuration(route.duration_min) }}</dd></div>
      <div><dt>Участков</dt><dd>{{ route.geometry.length || '—' }}</dd></div>
      <div>
        <dt>Провайдер</dt>
        <dd :class="{ fallback: route.provider !== 'valhalla' }">{{ route.provider }}</dd>
      </div>
    </dl>
    <ol v-if="route.legs?.length" class="legs">
      <li v-for="(leg, index) in route.legs" :key="index">
        <span class="leg-points">{{ index + 1 }} → {{ index + 2 }}</span>
        <span class="mode" :style="{ background: modeOf(leg).color }">{{ modeOf(leg).label }}</span>
        <span class="leg-numbers">{{ formatDuration(leg.duration_min) }} · {{ leg.distance_km.toFixed(2) }} км</span>
      </li>
    </ol>

    <p v-if="route.provider !== 'valhalla'" class="warn">
      Valhalla недоступна, посчитано по прямой линии — цифры оценочные, геометрии нет.
    </p>
  </div>

  <div v-if="matrix" class="summary">
    <h3>Матрица</h3>
    <dl>
      <div><dt>Размер</dt><dd>{{ matrix.points.length }} × {{ matrix.points.length }}</dd></div>
      <div><dt>Сумма плеч</dt><dd>{{ Number.isFinite(matrixLegSum(matrix)) ? `${matrixLegSum(matrix).toFixed(2)} км` : "Нет пути между точками" }}</dd></div>
      <div v-if="props.route && Number.isFinite(matrixLegSum(matrix))">
        <dt>Расхождение с /route</dt>
        <dd>{{ Math.abs(matrixLegSum(matrix) - props.route.distance_km).toFixed(2) }} км</dd>
      </div>
    </dl>
    <p class="warn">
      Матрица — приближённый алгоритм и занижает длинные плечи. Она нужна планировщику,
      а итоговый пробег считается по /route.
    </p>
  </div>
</template>

<style scoped>
.summary {
  border-top: 1px solid #e2e8f0;
  padding-top: 12px;
}

h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

dl {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

dl > div {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

dt {
  color: #64748b;
}

dd {
  margin: 0;
  font-weight: 600;
}

dd.fallback {
  color: #d97706;
}

.legs {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.legs li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.leg-points {
  color: #64748b;
}

.mode {
  padding: 1px 6px;
  border-radius: 999px;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.leg-numbers {
  margin-left: auto;
  color: #334155;
}

.warn {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.4;
  color: #94a3b8;
}
</style>
