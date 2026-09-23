<script setup>
// Групповая правка заявок: меняем только то, что оператор отметил галочкой слева.
// Что не отмечено — у каждой заявки остаётся своим: список в окне не про «одинаковые
// значения для всех», а про «поменять вот это поле у всех выбранных».
import { computed, ref } from 'vue'

import { formatDay } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { manualTransitions } from '../utils/requestStatuses.js'
import DurationInput from './DurationInput.vue'

const props = defineProps({
  count: { type: Number, required: true },
  references: { type: Object, required: true },
  saving: { type: Boolean, default: false },
  planDate: { type: String, default: '' },
  // статус отмеченных заявок, если он у всех один: только тогда есть общий переход
  statusId: { type: Number, default: null },
})
const emit = defineEmits(['apply', 'close'])

// какие поля меняем; пока галочки нет — поле в запрос не уйдёт
const change = ref({
  status: false,
  day: false,
  window: false,
  duration: false,
  workType: false,
  priority: false,
  transport: false,
})
const value = ref({
  statusId: '',
  day: props.planDate,
  windowStart: '09:00',
  windowEnd: '18:00',
  duration: 60,
  workTypeId: '',
  priorityId: '',
  transportId: '',
})

// куда отмеченные заявки можно перевести руками: переходы своего статуса
const transitions = computed(() =>
  props.statusId === null ? [] : manualTransitions(props.references, props.statusId),
)
// статус меняется переходом, а не правкой полей, поэтому доступен и заявке в плане;
// но общий переход есть только тогда, когда статус у всех отмеченных один
const statusHint = computed(() => {
  if (props.statusId === null) return 'у отмеченных заявок статусы разные — переводить можно только из одного'
  if (!transitions.value.length) {
    return `из статуса «${referenceName(props.references, 'request_statuses', props.statusId)}» перевести нельзя`
  }
  return ''
})

const workTypes = computed(() => props.references.work_types ?? [])
const priorities = computed(() => props.references.priorities ?? [])
const transports = computed(() => props.references.transports ?? [])

// тип работ задаёт навык и норматив длительности — как и в правке одной заявки
const norm = computed(() =>
  workTypes.value.find((type) => String(type.id) === String(value.value.workTypeId)),
)

const nothingChosen = computed(() => !Object.values(change.value).some(Boolean))
const brokenWindow = computed(
  () => change.value.window && value.value.windowEnd <= value.value.windowStart,
)

function moment(day, time) {
  return `${day}T${time}:00+03:00`
}

function apply() {
  const day = change.value.day ? value.value.day : props.planDate
  const fields = {}
  if (change.value.status) fields.status_id = Number(value.value.statusId)
  if (change.value.day) fields.move_to_day = value.value.day
  if (change.value.window) {
    fields.window_start = moment(day, value.value.windowStart)
    fields.window_end = moment(day, value.value.windowEnd)
  }
  if (change.value.duration) fields.duration_minutes = Number(value.value.duration)
  if (change.value.workType) fields.work_type_id = Number(value.value.workTypeId)
  if (change.value.priority) fields.priority_id = Number(value.value.priorityId)
  if (change.value.transport) {
    fields.transport_id = value.value.transportId === '' ? null : Number(value.value.transportId)
  }
  emit('apply', fields)
}

// нельзя применить: ничего не отмечено, окно вверх ногами или в отмеченном поле нет значения
const blocked = computed(
  () =>
    nothingChosen.value ||
    brokenWindow.value ||
    (change.value.day && !value.value.day) ||
    (change.value.status && value.value.statusId === '') ||
    (change.value.workType && value.value.workTypeId === '') ||
    (change.value.priority && value.value.priorityId === ''),
)
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" aria-label="Изменить отмеченные заявки">
      <header>
        <strong>Изменить заявки: {{ count }}</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <p class="hint">
        Отметьте, что поменять у всех выбранных заявок; остальное останется у каждой своим.
        Статус меняется переходом — его можно сменить и у заявки, которая уже в плане, а вот
        поля правятся только у «Новых».
      </p>

      <div class="fields">
        <label class="field" :class="{ off: Boolean(statusHint) }">
          <input v-model="change.status" type="checkbox" :disabled="Boolean(statusHint)" />
          <span class="name">Статус</span>
          <select v-model="value.statusId" :disabled="!change.status || Boolean(statusHint)">
            <option value="" disabled>выберите</option>
            <option
              v-for="transition in transitions"
              :key="transition.to_status_id"
              :value="transition.to_status_id"
            >
              {{ transition.name }}
            </option>
          </select>
          <span v-if="statusHint" class="note">{{ statusHint }}</span>
        </label>

        <label class="field">
          <input v-model="change.day" type="checkbox" />
          <span class="name">Перенести на день</span>
          <input v-model="value.day" type="date" :disabled="!change.day" />
          <span v-if="change.day && value.day" class="note">
            время окна то же, день — {{ formatDay(value.day) }}
          </span>
        </label>

        <label class="field">
          <input v-model="change.window" type="checkbox" />
          <span class="name">Окно (МСК)</span>
          <span class="range">
            <input v-model="value.windowStart" type="time" :disabled="!change.window" />
            <span class="dash">–</span>
            <input v-model="value.windowEnd" type="time" :disabled="!change.window" />
          </span>
          <span v-if="brokenWindow" class="warn">конец окна должен быть позже начала</span>
        </label>

        <label class="field">
          <input v-model="change.duration" type="checkbox" />
          <span class="name">Работа на месте</span>
          <DurationInput v-model="value.duration" :disabled="!change.duration" />
        </label>

        <label class="field">
          <input v-model="change.workType" type="checkbox" />
          <span class="name">Тип работ</span>
          <select v-model="value.workTypeId" :disabled="!change.workType">
            <option value="" disabled>выберите</option>
            <option v-for="type in workTypes" :key="type.id" :value="type.id">{{ type.name }}</option>
          </select>
          <span v-if="change.workType && norm" class="note">
            навык — «{{ referenceName(references, 'skills', norm.skill_id) }}»{{
              change.duration ? '' : `, работа на месте — ${norm.work_minutes} мин`
            }}
          </span>
        </label>

        <label class="field">
          <input v-model="change.priority" type="checkbox" />
          <span class="name">Приоритет</span>
          <select v-model="value.priorityId" :disabled="!change.priority">
            <option value="" disabled>выберите</option>
            <option v-for="priority in priorities" :key="priority.id" :value="priority.id">
              {{ priority.name }}
            </option>
          </select>
        </label>

        <label class="field">
          <input v-model="change.transport" type="checkbox" />
          <span class="name">Транспорт</span>
          <select v-model="value.transportId" :disabled="!change.transport">
            <option value="">не важен</option>
            <option v-for="transport in transports" :key="transport.id" :value="transport.id">
              {{ transport.name }}
            </option>
          </select>
        </label>
      </div>

      <footer>
        <button class="primary" :disabled="blocked || saving" @click="apply">
          {{ saving ? 'Меняю…' : `Применить к ${count}` }}
        </button>
        <button :disabled="saving" @click="emit('close')">Отмена</button>
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
  gap: 12px;
  width: min(560px, 94vw);
  padding: 16px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
}

.dialog header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dialog footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.hint {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}

.fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* поле, которое сейчас недоступно: видно, что оно есть, и почему им нельзя воспользоваться */
.field.off .name {
  color: #94a3b8;
}

/* строка поля: галочка, название, значение и поясняющая приписка справа */
.field {
  display: grid;
  grid-template-columns: 18px 150px minmax(140px, 1fr);
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.field .name {
  color: #334155;
  font-size: 14px;
}

.range {
  display: flex;
  align-items: center;
  gap: 6px;
}

.dash {
  color: #94a3b8;
}

.note,
.warn {
  grid-column: 2 / -1;
  font-size: 12px;
}

.note {
  color: #94a3b8;
}

.warn {
  color: #b91c1c;
}

.close {
  border: none;
  background: none;
  color: #64748b;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
</style>
