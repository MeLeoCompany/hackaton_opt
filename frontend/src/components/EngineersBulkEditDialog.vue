<script setup>
// Групповая правка смен: меняем только то, что оператор отметил галочкой слева.
// Что не отмечено — у каждой смены остаётся своим: бригаду и стартовую точку группой
// не меняют, это про каждую смену отдельно.
import { computed, ref } from 'vue'

import { formatDay } from '../utils/moscowTime.js'

const props = defineProps({
  count: { type: Number, required: true },
  references: { type: Object, required: true },
  saving: { type: Boolean, default: false },
  planDate: { type: String, default: '' },
})
const emit = defineEmits(['apply', 'close'])

const change = ref({ day: false, shift: false, transport: false, skills: false, start: false })
const value = ref({
  day: props.planDate,
  shiftStart: '09:00',
  shiftEnd: '18:00',
  transportId: '',
  skillIds: [],
  startAtOffice: true,
})

const transports = computed(() => props.references.transports ?? [])
const skills = computed(() => props.references.skills ?? [])

function toggleSkill(skillId) {
  const chosen = value.value.skillIds
  value.value.skillIds = chosen.includes(skillId)
    ? chosen.filter((id) => id !== skillId)
    : [...chosen, skillId].slice(0, 3) // по ТЗ у исполнителя не больше трёх навыков
}

const brokenShift = computed(() => change.value.shift && value.value.shiftEnd <= value.value.shiftStart)
const nothingChosen = computed(() => !Object.values(change.value).some(Boolean))
const blocked = computed(
  () =>
    nothingChosen.value ||
    brokenShift.value ||
    (change.value.day && !value.value.day) ||
    (change.value.transport && value.value.transportId === '') ||
    (change.value.skills && value.value.skillIds.length === 0),
)

function moment(day, time) {
  return `${day}T${time}:00+03:00`
}

function apply() {
  const day = change.value.day ? value.value.day : props.planDate
  const fields = {}
  if (change.value.day) fields.move_to_day = value.value.day
  if (change.value.shift) {
    fields.shift_start = moment(day, value.value.shiftStart)
    fields.shift_end = moment(day, value.value.shiftEnd)
  }
  if (change.value.transport) fields.transport_id = Number(value.value.transportId)
  if (change.value.skills) fields.skill_ids = value.value.skillIds
  if (change.value.start) fields.start_at_office = value.value.startAtOffice
  emit('apply', fields)
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" aria-label="Изменить отмеченные смены">
      <header>
        <strong>Изменить смены: {{ count }}</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <p class="hint">
        Отметьте поля, которые нужно поменять у всех выбранных смен. Остальные останутся у каждой
        своими. Бригада и её точка старта правятся по одной — группой их не меняют.
      </p>

      <div class="fields">
        <label class="field">
          <input v-model="change.day" type="checkbox" />
          <span class="name">Перенести на день</span>
          <input v-model="value.day" type="date" :disabled="!change.day" />
          <span v-if="change.day && value.day" class="note">
            время смены то же, день — {{ formatDay(value.day) }}
          </span>
        </label>

        <label class="field">
          <input v-model="change.shift" type="checkbox" />
          <span class="name">Смена (МСК)</span>
          <span class="range">
            <input v-model="value.shiftStart" type="time" :disabled="!change.shift" />
            <span class="dash">–</span>
            <input v-model="value.shiftEnd" type="time" :disabled="!change.shift" />
          </span>
          <span v-if="brokenShift" class="warn">конец смены должен быть позже начала</span>
        </label>

        <label class="field">
          <input v-model="change.transport" type="checkbox" />
          <span class="name">Транспорт</span>
          <select v-model="value.transportId" :disabled="!change.transport">
            <option value="" disabled>выберите</option>
            <option v-for="transport in transports" :key="transport.id" :value="transport.id">
              {{ transport.name }}
            </option>
          </select>
        </label>

        <div class="field">
          <input v-model="change.skills" type="checkbox" aria-label="менять навыки" />
          <span class="name">Навыки</span>
          <div class="chips">
            <button
              v-for="skill in skills"
              :key="skill.id"
              type="button"
              :class="['chip', { chosen: value.skillIds.includes(skill.id) }]"
              :disabled="!change.skills"
              @click="toggleSkill(skill.id)"
            >
              {{ skill.name }}
            </button>
          </div>
          <span v-if="change.skills" class="note">от одного до трёх; заменят прежние навыки</span>
        </div>

        <label class="field">
          <input v-model="change.start" type="checkbox" />
          <span class="name">Откуда выезжают</span>
          <select v-model="value.startAtOffice" :disabled="!change.start">
            <option :value="true">из офиса</option>
            <option :value="false">со своей точки</option>
          </select>
          <span v-if="change.start && !value.startAtOffice" class="note">
            у каждой смены останутся её прежние координаты
          </span>
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

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* навык выбирается плашкой: их немного, а выпадающий список с множественным выбором неудобен */
.chip {
  padding: 3px 10px;
  border: 1px solid #cbd5f5;
  border-radius: 999px;
  background: #fff;
  color: #334155;
  font-size: 13px;
  cursor: pointer;
}

.chip.chosen {
  border-color: #2563eb;
  background: #dbeafe;
  color: #1e3a8a;
  font-weight: 600;
}

.chip:disabled {
  opacity: 0.5;
  cursor: default;
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
