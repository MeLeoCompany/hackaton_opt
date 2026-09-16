<script setup>
// Поле длительности: набирается как угодно («1 ч 30 мин», «1:30», «90»), при уходе из поля
// приводится к виду «1 ч 30 мин». Наружу отдаёт минуты или '' — если поле пустое.
import { ref, watch } from 'vue'

import { formatDuration, parseDuration } from '../utils/duration.js'

const props = defineProps({
  modelValue: { type: [Number, String], default: '' },
  placeholder: { type: String, default: '' },
  ariaLabel: { type: String, default: 'длительность' },
})
const emit = defineEmits(['update:modelValue'])

const text = ref(props.modelValue === '' ? '' : formatDuration(props.modelValue))
const invalid = ref(false)

// значение сбросили снаружи (кнопка «Сбросить», другой план)
watch(
  () => props.modelValue,
  (value) => {
    if (value === '' && !invalid.value) text.value = ''
  },
)

function finish() {
  const minutes = parseDuration(text.value)
  invalid.value = text.value.trim() !== '' && minutes === null
  if (minutes !== null) text.value = formatDuration(minutes)
  emit('update:modelValue', minutes === null ? '' : minutes)
}
</script>

<template>
  <input
    v-model="text"
    :class="{ invalid }"
    :placeholder="placeholder"
    :aria-label="ariaLabel"
    :title="invalid ? 'Например: 1 ч 30 мин, 1:30 или 90' : ''"
    @blur="finish"
    @keyup.enter="finish"
  />
</template>

<style scoped>
input.invalid {
  border-color: #dc2626;
  color: #dc2626;
}
</style>
