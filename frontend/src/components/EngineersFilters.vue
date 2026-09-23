<script setup>
// Фильтры над картой исполнителей — это шапка таблицы исполнителей без строк: та же сетка
// колонок (colgroup), те же подписи и те же поля. При переключении «Таблица ↔ Карта» каждое
// поле остаётся на своём месте и своей ширины.
import { ref, watch } from 'vue'

import { useColumnWidths } from '../composables/useColumnWidths.js'
import { ENGINEER_COLUMNS as COLUMNS } from '../composables/useEngineersView.js'

import EngineersFilterControl from './EngineersFilterControl.vue'

defineProps({
  filters: { type: Object, required: true }, // объект из useEngineersView, меняется напрямую
  references: { type: Object, required: true },
  activeCount: { type: Number, required: true },
  // отмеченные галочками строки: «Сбросить» снимает и их
  checkedCount: { type: Number, default: 0 },
})
const emit = defineEmits(['reset', 'widths'])

// те же ширины, что у таблицы; карточке справа от карты нужны ровно эти числа
const root = ref(null)
const { widths } = useColumnWidths(COLUMNS, root)
watch(widths, (value) => emit('widths', value), { immediate: true })
</script>

<template>
  <div ref="root" class="table-scroll filters-head">
    <table class="data-table fixed-columns fluid">
      <colgroup>
        <col v-for="column in COLUMNS" :key="column.key" :style="{ width: `${widths[column.key]}px` }" />
      </colgroup>
      <thead>
        <tr>
          <th v-for="column in COLUMNS" :key="column.key">{{ column.label }}</th>
        </tr>
        <tr class="filter-row filter-controls">
          <th v-for="column in COLUMNS" :key="column.key" :class="{ 'actions-cell': column.key === 'actions' }">
            <EngineersFilterControl
              :column="column.key"
              :filters="filters"
              :references="references"
              :active-filter-count="activeCount"
              :checked-count="checkedCount"
              @reset="$emit('reset')"
            />
          </th>
        </tr>
      </thead>
    </table>
  </div>
</template>
