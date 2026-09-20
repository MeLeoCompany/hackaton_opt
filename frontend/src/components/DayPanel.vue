<script setup>
// Выбор дня — общий для всех вкладок, поэтому стоит на каждой форме одинаковым блоком.
// Календарь, шаг на день назад и вперёд, сводка по дню и слепок дня в CSV.
import { ref } from 'vue'

import { useSelectedDay } from '../composables/useSelectedDay.js'
import { nextDay, previousDay } from '../utils/moscowTime.js'

import IconButton from './IconButton.vue'

defineProps({
  // что показываем справа: «активных заявок 10», «исполнителей в смене 7» и т.п.
  summary: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  // слепок дня: выгрузить день в CSV и загрузить файл копией в выбранный день.
  // '' — кнопок нет (например, на вкладке планов); иначе текст для подсказок: «заявки», «смены»
  transfer: { type: String, default: '' },
  // кнопка «обновить» нужна там, где данные меняются снаружи: заявки, планы, отметки бригад.
  // Смены исполнителей так не меняются — там её нет
  refreshable: { type: Boolean, default: false },
})
const emit = defineEmits(['refresh', 'export-day', 'import-day'])

const fileInput = ref(null)

function pickFile(event) {
  const file = event.target.files[0]
  if (file) emit('import-day', file)
  event.target.value = '' // тот же файл можно выбрать снова
}

const { selectedDay, selectDay } = useSelectedDay()
</script>

<template>
  <section class="day-panel" title="Заявки, смены исполнителей и план берутся на этот день">
    <span class="day-label">День</span>
    <button :disabled="disabled" title="Предыдущий день" @click="selectDay(previousDay(selectedDay))">‹</button>
    <input
      :value="selectedDay"
      type="date"
      :disabled="disabled"
      aria-label="день планирования"
      @change="selectDay($event.target.value)"
    />
    <button :disabled="disabled" title="Следующий день" @click="selectDay(nextDay(selectedDay))">›</button>

    <IconButton
      v-if="refreshable"
      icon="refresh"
      class="refresh"
      label="Обновить данные дня: заявки, планы и отметки бригад"
      :disabled="disabled"
      @click="emit('refresh')"
    />

    <span v-if="summary" class="muted">{{ summary }}</span>

    <!-- слепок дня: всегда у правого края, чтобы кнопки не ездили за длиной сводки -->
    <div v-if="transfer" class="day-transfer">
      <IconButton
        icon="export"
        class="export"
        :label="`Выгрузить ${transfer} этого дня в CSV: файл можно загрузить в другой день`"
        :disabled="disabled"
        @click="emit('export-day')"
      />
      <IconButton
        icon="import"
        class="import"
        :label="`Загрузить CSV в этот день: ${transfer} добавятся копией с новыми номерами`"
        :disabled="disabled"
        @click="fileInput.click()"
      />
      <input ref="fileInput" type="file" accept=".csv,text/csv" hidden @change="pickFile" />
    </div>
  </section>
</template>

<style scoped>
.day-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  font-size: 13px;
}

.day-label {
  font-weight: 600;
}

/* кнопка «обновить» — того же размера, что стрелки дня рядом с календарём */
.day-panel :deep(.refresh) {
  width: 30px;
  height: 32px;
  padding: 0;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}

/* Слепок дня прижат к правому краю и стоит ровно над кнопками последней колонки таблицы.
   Ячейка колонки шириной 130 с отступами по 6 оставляет под содержимое 118 пикселей,
   а его правый край — в 7 пикселях от края блока таблицы (рамка 1 + отступ ячейки 6).
   Поэтому у панели отступ справа 6 (её собственная рамка добавляет седьмой). */
.day-panel:has(.day-transfer) {
  padding-right: 6px;
}

.day-transfer {
  display: flex;
  align-items: center;
  gap: 6px;
  /* 118 под кнопки + отступ 6 и рамка-разделитель слева: ровно как в ячейке таблицы,
     где от линии колонки до кнопки правки те же 6 пикселей */
  width: 125px;
  padding-left: 6px;
  margin-left: auto;
  border-left: 1px solid #e2e8f0;
}

/* тот же размер, что у кнопок правки и удаления в строках таблицы */
.day-transfer :deep(.icon-button) {
  flex: 1;
  width: auto;
}

/* выгрузка — синим, загрузка — зелёным: видно, что кнопка делает, до наведения подсказки */
.day-transfer :deep(.export:hover:not(:disabled)) {
  border-color: #2563eb;
  background: #eff6ff;
  color: #2563eb;
}

.day-transfer :deep(.import:hover:not(:disabled)) {
  border-color: #16a34a;
  background: #f0fdf4;
  color: #16a34a;
}

.day-panel input[type='date'] {
  width: 160px;
}
</style>
