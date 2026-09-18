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
  landmarks: { type: Array, default: () => [] },
  // точка «по умолчанию» (офис): в окне карты кнопка вернуть её одним нажатием
  home: { type: Object, default: null },
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
    <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
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
    :landmarks="landmarks"
    :home="home"
    @pick="pick"
    @close="open = false"
  />
</template>

<style scoped>
/* кнопка стоит в строке правки таблицы — той же высоты, что и поля рядом */
.map-button {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  color: #2563eb;
}

</style>
