<script setup>
// Фильтры над картой заявок — это шапка таблицы заявок без строк: та же сетка колонок
// (colgroup), те же подписи и те же поля. При переключении «Таблица ↔ Карта» каждое поле
// остаётся на своём месте и своей ширины.
import { REQUEST_COLUMNS as COLUMNS } from '../composables/useRequestsView.js'

import RequestsFilterControl from './RequestsFilterControl.vue'

defineProps({
  filters: { type: Object, required: true }, // объект из useRequestsView, меняется напрямую
  references: { type: Object, required: true },
  activeCount: { type: Number, required: true },
})
defineEmits(['reset'])
</script>

<template>
  <div class="table-scroll filters-head">
    <table class="data-table fixed-columns">
      <colgroup>
        <col v-for="column in COLUMNS" :key="column.key" :style="column.width ? { width: column.width } : null" />
      </colgroup>
      <thead>
        <tr>
          <th v-for="column in COLUMNS" :key="column.key">{{ column.label }}</th>
        </tr>
        <tr class="filter-row filter-controls">
          <th v-for="column in COLUMNS" :key="column.key" :class="{ 'actions-cell': column.key === 'actions' }">
            <RequestsFilterControl
              :column="column.key"
              :filters="filters"
              :references="references"
              :active-filter-count="activeCount"
              @reset="$emit('reset')"
            />
          </th>
        </tr>
      </thead>
    </table>
  </div>
</template>
