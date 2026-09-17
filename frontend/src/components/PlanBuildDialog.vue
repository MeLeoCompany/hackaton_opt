<script setup>
// Параметры расчёта плана: окно открывается по кнопке «Построить план», поля заполнены
// значениями по умолчанию — можно сразу нажать «Рассчитать».
import { computed, reactive } from 'vue'

import { formatDay } from '../utils/moscowTime.js'
import { objectiveOrder } from '../utils/planningPriorities.js'

const props = defineProps({
  planDate: { type: String, required: true },
  building: { type: Boolean, required: true },
  // ответ /plans/day-check: заявки дня, уже закреплённые за утверждёнными планами других дней
  dayCheck: { type: Object, default: null },
})
const emit = defineEmits(['build', 'close'])

const SOLVERS = [
  {
    value: 'cuopt',
    label: 'cuOpt — глобальная оптимизация',
    hint: 'Считает на видеокарте NVIDIA: максимум срочных заявок, затем всех заявок, меньше исполнителей и пробега',
  },
  {
    value: 'baseline',
    label: 'Базовый — первый подходящий исполнитель',
    hint: 'Контрольный алгоритм ТЗ: заявки по порядку поступления, без перестановок. Считается мгновенно',
  },
]

// значения по умолчанию: ими же расчёт и запускается, если ничего не менять
const params = reactive({
  solver: 'cuopt',
  servicePriority: 'urgent_requests',
  resourcePriority: 'engineers_used',
})

// заявки с окном через полночь мог забрать утверждённый план соседнего дня — предупреждаем до расчёта
const heldRequests = computed(() => props.dayCheck?.held_requests ?? [])
const heldHolders = computed(() =>
  [...new Set(heldRequests.value.map((held) => `№${held.plan_id} от ${formatDay(held.plan_date)}`))].join(', ')
)
const heldNumbers = computed(() => heldRequests.value.map((held) => `№${held.request_id}`).join(', '))

function solverHint() {
  return SOLVERS.find((solver) => solver.value === params.solver)?.hint ?? ''
}

function submit() {
  const payload = { solver: params.solver }
  if (params.solver === 'cuopt') {
    payload.objective_order = objectiveOrder(params.servicePriority, params.resourcePriority)
  }
  emit('build', payload)
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" aria-label="Параметры расчёта плана">
      <header>
        <strong>Параметры расчёта · {{ formatDay(planDate) }}</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <label class="field">
        <span>Алгоритм</span>
        <select v-model="params.solver" :disabled="building">
          <option v-for="solver in SOLVERS" :key="solver.value" :value="solver.value">
            {{ solver.label }}
          </option>
        </select>
      </label>
      <p class="hint">{{ solverHint() }}</p>

      <fieldset v-if="params.solver === 'cuopt'" class="priority-settings" :disabled="building">
        <legend>Порядок целей</legend>
        <label class="field">
          <span>Сначала выполнить</span>
          <select v-model="params.servicePriority">
            <option value="urgent_requests">Максимум срочных заявок</option>
            <option value="assigned_requests">Максимум всех заявок</option>
          </select>
        </label>
        <label class="field">
          <span>После этого сократить</span>
          <select v-model="params.resourcePriority">
            <option value="engineers_used">Количество задействованных бригад</option>
            <option value="travel_distance">Общий пробег</option>
          </select>
        </label>
        <p class="hint">
          Все четыре цели остаются в расчёте. Выбор определяет строгий порядок: более важная
          цель всегда сильнее любых улучшений нижних уровней.
        </p>
      </fieldset>

      <p v-if="heldRequests.length" class="warning">
        <span class="mark">!</span>
        <span>
          Заявок этого дня закреплено за утверждёнными планами других дней:
          {{ heldRequests.length }} ({{ heldNumbers }}). Забрали: {{ heldHolders }}.
          В расчёт они не пойдут — иначе одну заявку выполнят дважды.
          Нужны здесь — снимите утверждение с того плана.
        </span>
      </p>

      <footer>
        <span class="hint">Заявки и смены берутся на {{ formatDay(planDate) }}</span>
        <div class="dialog-actions">
          <button class="primary" :disabled="building" @click="submit">
            {{ building ? 'Считаю…' : 'Рассчитать' }}
          </button>
          <button :disabled="building" @click="emit('close')">Отмена</button>
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
  width: min(520px, 92vw);
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

.close {
  padding: 0 8px;
  font-size: 18px;
  line-height: 26px;
}

.hint {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

.warning {
  display: flex;
  gap: 8px;
  margin: 0;
  padding: 8px 10px;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
  font-size: 12px;
  line-height: 1.4;
}

.warning .mark {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #f59e0b;
  color: #fff;
  font-weight: 700;
}

.dialog-actions {
  display: flex;
  gap: 8px;
}

.priority-settings {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.priority-settings legend {
  padding: 0 5px;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}
</style>
