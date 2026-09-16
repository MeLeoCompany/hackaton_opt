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
    text.value = value === '' ? '' : formatDuration(value)
    invalid.value = false
  },
)

function finish() {
  if (text.value.trim() === '') {
    invalid.value = false
    emit('update:modelValue', '')
    return
  }

  const minutes = parseDuration(text.value)
  invalid.value = minutes === null
  if (minutes === null) return

  text.value = formatDuration(minutes)
  emit('update:modelValue', minutes)
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
