<script setup>
// Почему визит стоит здесь: факты этого визита, а не пересказ правил планирования.
// Открывается по клику на визит в маршруте.
import { computed } from 'vue'

import { formatDuration } from '../utils/duration.js'
import { moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'

const props = defineProps({
  visit: { type: Object, required: true },
  route: { type: Object, required: true },
  references: { type: Object, required: true },
})
defineEmits(['close'])

const minutesBetween = (from, to) => Math.round((new Date(to) - new Date(from)) / 60000)

// от освобождения до начала работ: дорога и ожидание открытия окна
const beforeWork = computed(() => minutesBetween(props.visit.available_from, props.visit.planned_arrival_time))

const workEnd = computed(() =>
  new Date(new Date(props.visit.planned_arrival_time).getTime() + props.visit.duration_minutes * 60000),
)

const isFirst = computed(() => props.visit.visit_order === 1)
</script>

<template>
  <div class="dialog-backdrop" @click.self="$emit('close')">
    <div class="dialog" role="dialog" :aria-label="`Заявка №${visit.request_id} в маршруте`">
      <header>
        <strong>Заявка №{{ visit.request_id }} · {{ visit.address }}</strong>
        <button class="close" title="Закрыть" @click="$emit('close')">×</button>
      </header>

      <dl>
        <div>
          <dt>Кто едет</dt>
          <dd>
            {{ route.engineer_name }} · {{ referenceName(references, 'transports', route.transport_id) }},
            визит {{ visit.visit_order }} из {{ route.visits.length }}
          </dd>
        </div>
        <div>
          <dt>{{ isFirst ? 'Смена началась' : 'Освободился' }}</dt>
          <dd>
            {{ moscowTimeOf(visit.available_from) }}
            <span class="muted">
              · {{ isFirst ? 'выезд со старта бригады' : 'после предыдущей заявки' }},
              дорога и ожидание {{ formatDuration(beforeWork) }}
            </span>
          </dd>
        </div>
        <div>
          <dt>Работа</dt>
          <dd>
            {{ moscowTimeOf(visit.planned_arrival_time) }}–{{ moscowTimeOf(workEnd) }}
            <span class="muted">· {{ formatDuration(visit.duration_minutes) }}</span>
          </dd>
        </div>
        <div>
          <dt>Окно заявки</dt>
          <dd>
            {{ moscowTimeOf(visit.window_start) }}–{{ moscowTimeOf(visit.window_end) }}
            <span class="muted">· начать позже нельзя, запас {{ formatDuration(visit.window_slack_minutes) }}</span>
          </dd>
        </div>
        <div>
          <dt>Смена</dt>
          <dd>
            до {{ moscowTimeOf(route.shift_end) }}
            <span class="muted">· после работы остаётся {{ formatDuration(visit.shift_slack_minutes) }}</span>
          </dd>
        </div>
        <div v-if="visit.candidate_engineers !== null">
          <dt>Кто ещё мог</dt>
          <dd>
            <template v-if="visit.candidate_engineers > 1">
              подходящих бригад в этот день: {{ visit.candidate_engineers }}
            </template>
            <template v-else>только эта бригада: навык и транспорт больше ни у кого не совпали</template>
          </dd>
        </div>
      </dl>
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
  width: min(560px, 92vw);
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
  font-size: 13px;
}

.dialog header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.close {
  padding: 0 8px;
  font-size: 18px;
  line-height: 26px;
}

dl {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
}

dl > div {
  display: flex;
  gap: 12px;
}

dt {
  flex-shrink: 0;
  width: 140px;
  color: #64748b;
}

dd {
  margin: 0;
}
</style>
