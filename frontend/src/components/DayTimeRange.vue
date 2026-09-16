<script setup>
// День и два времени вместо двух «прокручиваемых» полей даты-времени:
// дата задаётся один раз, время набирается руками.
// Если время окончания не позже времени начала, конец считается следующим днём:
// ночная смена и ночное окно.
import { computed, ref, watch } from 'vue'

import { formatDay, joinMoscowInputValue, nextDay, splitMoscowInputValue } from '../utils/moscowTime.js'

import TimeInput from './TimeInput.vue'

const props = defineProps({
  start: { type: String, default: '' },
  end: { type: String, default: '' },
})
const emit = defineEmits(['update:start', 'update:end'])

const date = ref('')
const startTime = ref('')
const endTime = ref('')

watch(
  () => [props.start, props.end],
  ([start, end]) => {
    const startParts = splitMoscowInputValue(start)
    const endParts = splitMoscowInputValue(end)
    date.value = startParts.date || endParts.date
    startTime.value = startParts.time
    endTime.value = endParts.time
  },
  { immediate: true },
)

const endDate = computed(() => {
  if (!date.value || !startTime.value || !endTime.value) return date.value
  return endTime.value <= startTime.value ? nextDay(date.value) : date.value
})

function apply() {
  emit('update:start', joinMoscowInputValue(date.value, startTime.value))
  emit('update:end', joinMoscowInputValue(endDate.value, endTime.value))
}
</script>

<template>
  <div class="day-time-range">
    <input v-model="date" type="date" aria-label="день" @change="apply" />
    <div class="times">
      <TimeInput v-model="startTime" aria-label="время начала" @update:model-value="apply" />
      <span>—</span>
      <TimeInput v-model="endTime" aria-label="время окончания" @update:model-value="apply" />
      <span v-if="endDate && endDate !== date" class="next-day" :title="`Окончание — ${formatDay(endDate)}`">
        +1 день
      </span>
    </div>
  </div>
</template>

<style scoped>
.day-time-range {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.times {
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.times span {
  color: #64748b;
  font-size: 12px;
}

.next-day {
  color: #b45309;
}
</style>
