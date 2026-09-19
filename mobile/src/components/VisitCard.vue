<script setup>
// Заявка маршрута. У текущей (current) — крупные кнопки следующего шага: выехали → на месте →
// выполнено, и «Не выполнить». У остальных кнопок нет: бригада идёт по маршруту по порядку.
import { computed, ref } from 'vue'

import { isClosed, mapsLink, moscowTime, nextAction } from '../route.js'

const props = defineProps({
  visit: { type: Object, required: true },
  current: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['mark', 'fail'])

// подробности раскрываются по нажатию; у текущей — сразу
const expanded = ref(false)
const open = computed(() => props.current || expanded.value)
const action = computed(() => (props.current ? nextAction(props.visit) : null))
const closed = computed(() => isClosed(props.visit))

const stateText = computed(() => {
  const visit = props.visit
  if (visit.removed) return 'Снята с плана'
  if (visit.status_code === 'done') return `Выполнена${visit.finished_at ? ` в ${moscowTime(visit.finished_at)}` : ''}`
  if (visit.status_code === 'cancelled') return 'Не выполнена'
  if (visit.arrived_at) return `На месте с ${moscowTime(visit.arrived_at)}`
  if (visit.departed_at) return `В пути с ${moscowTime(visit.departed_at)}`
  return `Начало работ по плану в ${moscowTime(visit.planned_arrival_time)}`
})
</script>

<template>
  <article :class="['visit', { current, closed, removed: visit.removed }]" @click="!current && (expanded = !expanded)">
    <header>
      <span :class="['order', `state-${visit.removed ? 'removed' : visit.status_code}`]">
        {{ visit.status_code === 'done' ? '✓' : visit.visit_order }}
      </span>
      <div class="title">
        <strong>{{ visit.address }}</strong>
        <span class="state">{{ stateText }}</span>
      </div>
      <span v-if="visit.urgent && !closed" class="urgent">Срочно</span>
    </header>

    <div v-if="open" class="details">
      <dl>
        <div>
          <dt>Окно клиента</dt>
          <dd>{{ moscowTime(visit.window_start) }}–{{ moscowTime(visit.window_end) }}</dd>
        </div>
        <div>
          <dt>Работы</dt>
          <dd>{{ visit.work_type ?? '—' }} · {{ visit.duration_minutes }} мин</dd>
        </div>
        <div v-if="visit.equipment.length">
          <dt>Взять с собой</dt>
          <dd>
            <span v-for="item in visit.equipment" :key="item.name" class="chip">⚙ {{ item.name }} × {{ item.quantity }}</span>
          </dd>
        </div>
        <div>
          <dt>Заявка</dt>
          <dd>№{{ visit.request_id }}</dd>
        </div>
      </dl>

      <a v-if="!closed" class="maps" :href="mapsLink(visit)" target="_blank" rel="noopener" @click.stop>
        Маршрут в Яндекс Картах ↗
      </a>

      <div v-if="action" class="actions" @click.stop>
        <button class="primary big" :disabled="busy" @click="emit('mark', visit, action.action)">
          {{ action.label }}
        </button>
        <button class="ghost" :disabled="busy" @click="emit('fail', visit)">Не выполнить</button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.visit {
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
}

.visit.current {
  border: 2px solid #fcd535;
  box-shadow: 0 8px 24px rgb(17 24 39 / 10%);
}

.visit.closed {
  background: #f9fafb;
}

.visit.closed .title strong {
  color: #6b7280;
}

.visit.removed .title strong {
  text-decoration: line-through;
}

header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.order {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e5e7eb;
  color: #111827;
  font-size: 13px;
  font-weight: 700;
}

.order.state-in_progress {
  background: #fcd535;
}

.order.state-done {
  background: #16a34a;
  color: #fff;
}

.order.state-cancelled,
.order.state-removed {
  background: #d1d5db;
  color: #6b7280;
}

.title {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.title strong {
  font-size: 15px;
  line-height: 1.3;
}

.state {
  color: #6b7280;
  font-size: 13px;
}

.current .state {
  color: #92400e;
  font-weight: 600;
}

.urgent {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: #fee2e2;
  color: #b91c1c;
  font-size: 12px;
  font-weight: 600;
}

.details {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

dl {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  font-size: 14px;
}

dl > div {
  display: flex;
  gap: 10px;
}

dt {
  flex-shrink: 0;
  width: 108px;
  color: #6b7280;
}

dd {
  margin: 0;
}

.chip {
  display: inline-block;
  margin: 0 6px 4px 0;
  padding: 1px 8px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
  font-size: 13px;
}

.maps {
  color: #1d4ed8;
  font-size: 14px;
  text-decoration: none;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
