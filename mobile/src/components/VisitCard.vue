<script setup>
// Заявка маршрута. У текущей (current) — крупные кнопки следующего шага: выехали → на месте →
// выполнено, и «Не выполнить». У остальных кнопок нет: бригада идёт по маршруту по порядку.
import { computed, ref } from 'vue'

import { isClosed, mapsLink, moscowTime, nextAction } from '../route.js'

const props = defineProps({
  visit: { type: Object, required: true },
  // откуда бригада едет на эту заявку: прошлый визит маршрута или старт смены
  from: { type: Object, default: null },
  current: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['mark', 'fail'])

// подробности раскрываются по нажатию; у текущей — сразу
const expanded = ref(false)
const open = computed(() => props.current || expanded.value)
const action = computed(() => (props.current ? nextAction(props.visit) : null))
const closed = computed(() => isClosed(props.visit))
// выезд закрыт: бригада выбилась из плана или идёт пересчёт (docs/algoV2.md, шаги 7-9)
const blocked = computed(() => action.value?.action === 'depart' && props.visit.can_depart === false)

const stateText = computed(() => {
  const visit = props.visit
  if (visit.removed) return 'Снята с плана'
  if (visit.status_code === 'done') return `Выполнена${visit.finished_at ? ` в ${moscowTime(visit.finished_at)}` : ''}`
  if (visit.status_code === 'cancelled') return 'Не выполнена'
  if (visit.status_code === 'in_progress') {
    return `На месте${visit.arrived_at ? ` с ${moscowTime(visit.arrived_at)}` : ''}`
  }
  if (visit.status_code === 'en_route') {
    return `В пути${visit.departed_at ? ` с ${moscowTime(visit.departed_at)}` : ''}`
  }
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
      <!-- аварийный и высокий уровень приоритета видны сразу; обычный не отмечаем -->
      <span v-if="visit.priority_level < 3 && !closed" :class="['priority', `level-${visit.priority_level}`]">
        {{ visit.priority }}
      </span>
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
        <!-- почему заявки больше нет в работе: чтобы не выяснять это звонком диспетчеру -->
        <div v-if="visit.status_code === 'cancelled'">
          <dt>Отменена</dt>
          <dd>
            {{ visit.cancelled_by ?? 'диспетчером' }}<template v-if="visit.cancelled_at">
              в {{ moscowTime(visit.cancelled_at) }}</template>
            <template v-if="visit.cancel_reason"> · {{ visit.cancel_reason }}</template>
          </dd>
        </div>
        <div v-else-if="visit.removed">
          <dt>Снята с плана</dt>
          <dd>снята при пересчёте — бригада к ней не едет</dd>
        </div>
      </dl>

      <a v-if="!closed" class="maps" :href="mapsLink(visit, from)" target="_blank" rel="noopener" @click.stop>
        {{ from ? 'Маршрут в Яндекс Картах ↗' : 'Показать в Яндекс Картах ↗' }}
      </a>

      <div v-if="action" class="actions" @click.stop>
        <p v-if="blocked" class="blocked">{{ visit.blocked_reason ?? 'Ждите нового плана' }}</p>
        <button class="primary big" :disabled="busy || blocked" @click="emit('mark', visit, action.action)">
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

.order.state-en_route,
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

.priority {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.priority.level-1 {
  background: #fee2e2;
  color: #b91c1c;
}

.priority.level-2 {
  background: #ffedd5;
  color: #c2410c;
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

/* выезд закрыт: бригада ждёт нового плана или разрешения диспетчера */
.blocked {
  margin: 0;
  padding: 8px 10px;
  border-radius: 10px;
  background: #fef3c7;
  color: #92400e;
  font-size: 14px;
  font-weight: 600;
}
</style>
