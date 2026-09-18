<script setup>
// Два поля времени: день отдельно не выбирается — он и так выбран на форме.
// У новой записи берётся выбранный день, у существующей — её собственная дата.
// Если время окончания не позже начала, конец уходит на следующие сутки (ночная смена,
// ночное окно). Про это говорит значок «!»; на ровно 00:00 он не нужен — это конец
// того же дня по часам диспетчера.
import { computed, ref, watch } from 'vue'

import { useSelectedDay } from '../composables/useSelectedDay.js'
import { formatDay, joinMoscowInputValue, nextDay, splitMoscowInputValue } from '../utils/moscowTime.js'

import TimeInput from './TimeInput.vue'

const MIDNIGHT = '00:00'

const props = defineProps({
  start: { type: String, default: '' },
  end: { type: String, default: '' },
})
const emit = defineEmits(['update:start', 'update:end'])

const { selectedDay } = useSelectedDay()

const date = ref('')
const startTime = ref('')
const endTime = ref('')

watch(
  () => [props.start, props.end],
  ([start, end]) => {
    const startParts = splitMoscowInputValue(start)
    const endParts = splitMoscowInputValue(end)
    date.value = startParts.date || endParts.date || selectedDay.value
    startTime.value = startParts.time
    endTime.value = endParts.time
  },
  { immediate: true },
)

const endDate = computed(() => {
  if (!date.value || !startTime.value || !endTime.value) return date.value
  return endTime.value <= startTime.value ? nextDay(date.value) : date.value
})

// 00:00 — это полночь того же дня для диспетчера, предупреждать не о чем
const endsNextDay = computed(() => endDate.value !== date.value && endTime.value !== MIDNIGHT)

function apply() {
  emit('update:start', joinMoscowInputValue(date.value, startTime.value))
  emit('update:end', joinMoscowInputValue(endDate.value, endTime.value))
}
</script>

<template>
  <div class="day-time-range">
    <div class="times">
      <TimeInput v-model="startTime" aria-label="время начала" @update:model-value="apply" />
      <span>–</span>
      <TimeInput v-model="endTime" aria-label="время окончания" @update:model-value="apply" />
      <!-- окончание на следующих сутках: компактный значок, пояснение — при наведении -->
      <span
        v-if="endsNextDay"
        class="next-day"
        role="img"
        :title="`Окончание на следующие сутки — ${formatDay(endDate)}`"
        :aria-label="`Окончание на следующие сутки — ${formatDay(endDate)}`"
      >
        !
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

/* два поля времени делят строку поровну и вместе занимают ту же ширину, что и дата */
.times :deep(.time-input) {
  flex: 1;
  width: auto;
  min-width: 0;
}

.times .next-day {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #f59e0b;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  cursor: help;
}
</style>
