<script setup>
// Сводка плана и маршруты исполнителей списком: кто, куда и во сколько едет (ТЗ 2.4.2),
// плюс неназначенные заявки с причинами.
import { moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { routeColor } from '../utils/routeColors.js'

defineProps({
  plan: { type: Object, required: true },
  references: { type: Object, required: true },
  selectedEngineerId: { type: Number, default: null },
})
const emit = defineEmits(['select-engineer'])

function formatDuration(minutes) {
  const hours = Math.floor(minutes / 60)
  const rest = Math.round(minutes % 60)
  return hours > 0 ? `${hours} ч ${rest} мин` : `${rest} мин`
}
</script>

<template>
  <section class="routes-panel">
    <div class="plan-metrics">
      <div>
        <strong>{{ plan.engineers_used }}</strong><span>исполнителей</span>
      </div>
      <div>
        <strong>{{ plan.assigned_count }}</strong><span>назначено</span>
      </div>
      <div>
        <strong>{{ plan.unassigned_count }}</strong><span>не назначено</span>
      </div>
      <div>
        <strong>{{ plan.total_distance_km.toFixed(1) }}</strong><span>км пробег</span>
      </div>
    </div>

    <button v-if="selectedEngineerId !== null" class="link" @click="emit('select-engineer', null)">
      Показать все маршруты
    </button>

    <article
      v-for="(route, routeIndex) in plan.routes"
      :key="route.engineer_id"
      :class="['route-card', { selected: route.engineer_id === selectedEngineerId }]"
      @click="emit('select-engineer', route.engineer_id)"
    >
      <header>
        <i class="legend-dot" :style="{ background: routeColor(routeIndex) }"></i>
        <strong>{{ route.engineer_name }}</strong>
        <span class="muted">{{ referenceName(references, 'transports', route.transport_id) }}</span>
      </header>
      <p class="muted">
        {{ route.visits.length }} заявок · {{ route.distance_km.toFixed(1) }} км ·
        {{ formatDuration(route.duration_min) }} в пути
        <template v-if="route.provider !== 'valhalla'"> · оценка по прямой</template>
      </p>
      <ol>
        <li v-for="visit in route.visits" :key="visit.request_id">
          <span class="time">{{ moscowTimeOf(visit.planned_arrival_time) }}</span>
          <span>№{{ visit.request_id }} · {{ visit.address }}</span>
        </li>
      </ol>
    </article>

    <section v-if="plan.unassigned.length" class="unassigned">
      <h3>Не назначены</h3>
      <ul>
        <li v-for="request in plan.unassigned" :key="request.request_id">
          <strong>№{{ request.request_id }}</strong> · {{ request.address }}
          <p class="muted">{{ request.reason }}</p>
        </li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.routes-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
}

.plan-metrics {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.plan-metrics div {
  display: flex;
  flex-direction: column;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.plan-metrics strong {
  font-size: 18px;
}

.plan-metrics span {
  font-size: 12px;
  color: #64748b;
}

.link {
  align-self: flex-start;
}

.route-card {
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
}

.route-card:hover {
  border-color: #93c5fd;
}

.route-card.selected {
  border-color: #2563eb;
  background: #eff6ff;
}

.route-card header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.route-card p {
  margin: 4px 0 6px;
}

.route-card ol {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.time {
  display: inline-block;
  min-width: 42px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.unassigned h3 {
  margin: 6px 0;
  font-size: 14px;
}

.unassigned ul {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.unassigned p {
  margin: 2px 0 0;
}
</style>
