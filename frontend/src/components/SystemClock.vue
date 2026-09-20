<script setup>
// Часы системного времени в правом верхнем углу, на всех вкладках. Время серверное: от него
// считаются пересчёт плана «с текущего момента», отметки бригад и опоздания.
// Администратор перематывает его для демонстрации: кнопками на час или выбором дня.
import { computed, ref, watch } from 'vue'

import { useAuth } from '../composables/useAuth.js'
import { useSystemTime } from '../composables/useSystemTime.js'
import { formatDay, fromMoscowInputValue, moscowDateOf, moscowTimeOf } from '../utils/moscowTime.js'
import TimeInput from './TimeInput.vue'

const { now, offsetSeconds, updatedBy, loaded, shifted, errorMessage, setMoment, shiftBy, reset } = useSystemTime()
const { isAdmin } = useAuth()

const open = ref(false)
// день и время в панели: пока панель закрыта, идут за часами
const day = ref('')
const time = ref('')

const iso = computed(() => now.value.toISOString())
const clockTime = computed(() => moscowTimeOf(iso.value))
const clockDay = computed(() => moscowDateOf(iso.value))

// «+2 д 3 ч» — насколько перемотано относительно настоящего времени
const shiftText = computed(() => {
  const seconds = Math.abs(offsetSeconds.value)
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const parts = [days && `${days} д`, hours && `${hours} ч`, !days && minutes && `${minutes} мин`]
  return `${offsetSeconds.value > 0 ? '+' : '−'}${parts.filter(Boolean).join(' ') || ' меньше минуты'}`
})

function openPanel() {
  open.value = !open.value
  if (open.value) {
    day.value = clockDay.value
    time.value = clockTime.value
  }
}

// поменяли день или время — часы переводятся сразу, отдельной кнопки не нужно
watch([day, time], ([newDay, newTime]) => {
  if (!open.value || !newDay || !/^\d\d:\d\d$/.test(newTime)) return
  if (newDay === clockDay.value && newTime === clockTime.value) return
  setMoment(fromMoscowInputValue(`${newDay}T${newTime}`))
})

// кнопки ±час двигают время и обновляют поля панели
async function shift(seconds) {
  await shiftBy(seconds)
  day.value = moscowDateOf(now.value.toISOString())
  time.value = moscowTimeOf(now.value.toISOString())
}

async function back() {
  await reset()
  day.value = moscowDateOf(now.value.toISOString())
  time.value = moscowTimeOf(now.value.toISOString())
}
</script>

<template>
  <div v-if="loaded" class="clock-box">
    <button
      :class="['clock', { shifted, plain: !isAdmin }]"
      :disabled="!isAdmin"
      :title="isAdmin ? 'Системное время — нажмите, чтобы перемотать' : 'Системное время сервера'"
      @click="openPanel"
    >
      <span class="time">{{ clockTime }}</span>
      <span class="day">{{ formatDay(clockDay) }}</span>
      <span v-if="shifted" class="shift">{{ shiftText }}</span>
    </button>

    <div v-if="open" class="panel">
      <header>
        <strong>Системное время</strong>
        <button class="close" title="Закрыть" @click="open = false">×</button>
      </header>

      <label class="day-field">
        <span>День</span>
        <input v-model="day" type="date" />
      </label>

      <label class="day-field">
        <span>Время</span>
        <TimeInput v-model="time" aria-label="время системы" />
      </label>

      <div class="quick">
        <button @click="shift(-3600)">−1 час</button>
        <button @click="shift(3600)">+1 час</button>
      </div>

      <button class="wide" :disabled="!shifted" @click="back">Вернуть настоящее время</button>

      <p v-if="shifted" class="hint">
        Перемотано на {{ shiftText }}<template v-if="updatedBy"> ({{ updatedBy }})</template>. От этого времени
        считаются пересчёт плана, отметки бригад и опоздания.
      </p>
      <p v-else class="hint">От него считаются пересчёт плана, отметки бригад и опоздания.</p>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<style scoped>
.clock-box {
  position: relative;
}

.clock {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  color: #0f172a;
  cursor: pointer;
}

.clock.plain {
  cursor: default;
}

.clock:hover:not(.plain) {
  border-color: #93c5fd;
}

/* перемотанное время видно сразу: часы становятся жёлтыми */
.clock.shifted {
  border-color: #fcd34d;
  background: #fffbeb;
}

.time {
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.day {
  color: #64748b;
  font-size: 12px;
}

.shift {
  padding: 1px 6px;
  border-radius: 999px;
  background: #fde68a;
  color: #92400e;
  font-size: 11px;
  font-weight: 600;
}

.panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 1200;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 260px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 28px rgb(15 23 42 / 18%);
}

.panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.quick {
  display: flex;
  gap: 6px;
}

.quick button,
.wide {
  flex: 1;
  width: 100%;
}

.day-field {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.day-field span {
  width: 42px;
  color: #475569;
}

.day-field input,
.day-field :deep(.time-input) {
  flex: 1;
  min-width: 0;
}

.hint {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.error {
  margin: 0;
  color: #b91c1c;
  font-size: 12px;
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
