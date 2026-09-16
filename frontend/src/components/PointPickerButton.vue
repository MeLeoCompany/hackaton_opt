<script setup>
// Кнопка-значок карты рядом с парой координат: открывает карту выбора точки.
// Значок, а не подпись, чтобы ячейка таблицы не меняла ширину и строка не прыгала.
import { ref } from 'vue'

import PointPickerDialog from './PointPickerDialog.vue'

defineProps({
  // title — заголовок окна с картой, hint — подсказка при наведении на кнопку
  title: { type: String, required: true },
  hint: { type: String, required: true },
  latitude: { type: [Number, String], default: '' },
  longitude: { type: [Number, String], default: '' },
  contextPoints: { type: Array, default: () => [] },
})
const emit = defineEmits(['pick'])

const open = ref(false)

function pick(latitude, longitude) {
  emit('pick', latitude, longitude)
  open.value = false
}
</script>

<template>
  <button type="button" class="map-button" :title="hint" :aria-label="hint" @click="open = true">
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        d="M12 2c3.9 0 7 3.1 7 7 0 5.2-7 13-7 13S5 14.2 5 9c0-3.9 3.1-7 7-7z"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
      />
      <circle cx="12" cy="9" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8" />
    </svg>
  </button>

  <PointPickerDialog
    v-if="open"
    :title="title"
    :latitude="latitude"
    :longitude="longitude"
    :context-points="contextPoints"
    @pick="pick"
    @close="open = false"
  />
</template>

<style scoped>
.map-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  color: #2563eb;
}
</style>
