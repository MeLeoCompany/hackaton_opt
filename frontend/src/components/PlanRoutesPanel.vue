<script setup>
// Маршруты исполнителей: кто, куда и во сколько едет (ТЗ 2.4.2), и неназначенные заявки
// с причинами. Характеристики плана показываются только рядом со списком: на карте
// те же цифры повторять незачем.
import { formatDay, moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { routeColor } from '../utils/routeColors.js'

defineProps({
  plan: { type: Object, required: true },
  references: { type: Object, required: true },
  selectedEngineerId: { type: Number, default: null },
  withCharacteristics: { type: Boolean, default: true },
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
    <header v-if="withCharacteristics" class="plan-title">
      <h2>План №{{ plan.id }} на {{ formatDay(plan.plan_date) }}</h2>
      <p class="muted">рассчитан в {{ moscowTimeOf(plan.created_at) }} · решатель {{ plan.solver ?? '—' }}</p>
    </header>

    <section v-if="withCharacteristics" class="plan-block">
      <h3>Характеристики плана №{{ plan.id }}</h3>
      <div class="plan-metrics">
        <div>
          <strong>{{ plan.engineers_used }}</strong><span>исполнителей задействовано</span>
        </div>
        <div>
          <strong>{{ plan.assigned_count }}</strong><span>заявок назначено</span>
        </div>
        <div>
          <strong>{{ plan.unassigned_count }}</strong><span>заявок не назначено</span>
        </div>
        <div>
          <strong>{{ plan.total_distance_km.toFixed(1) }}</strong><span>км общий пробег</span>
        </div>
      </div>
    </section>

    <section class="plan-block">
      <h3>Маршруты исполнителей</h3>
      <p v-if="selectedEngineerId !== null" class="muted">
        На карте показан один маршрут — кликните по нему ещё раз, чтобы вернуть все
      </p>
      <div class="route-cards">
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
      </div>
    </section>

    <section v-if="plan.unassigned.length" class="plan-block">
      <h3>Не назначены в этом плане</h3>
      <ul class="unassigned">
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
  gap: 12px;
  font-size: 13px;
}

.plan-title h2 {
  margin: 0;
  font-size: 16px;
}

.plan-title p {
  margin: 2px 0 0;
}

.plan-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* у абзацев-пояснений браузерные отступы складываются с gap — получается дыра в строку */
.plan-block > p {
  margin: 0;
}

.plan-block h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.plan-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
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

/* в узкой колонке рядом с картой карточки встают в один столбец сами */
.route-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
  align-items: start;
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

.unassigned {
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
