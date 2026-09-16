<script setup>
// Фильтр одной колонки заявок. Один и тот же компонент стоит в шапке таблицы и в панели
// над картой — поэтому фильтры в обоих видах выглядят и работают одинаково.
import { NO_TRANSPORT } from '../composables/useRequestsView.js'

import TimeInput from './TimeInput.vue'

defineProps({
  column: { type: String, required: true }, // key колонки из REQUEST_COLUMNS
  filters: { type: Object, required: true }, // объект из useRequestsView, меняется напрямую
  references: { type: Object, required: true },
  activeFilterCount: { type: Number, required: true },
})
defineEmits(['reset'])
</script>

<template>
  <input
    v-if="column === 'id'"
    v-model="filters.idText"
    inputmode="numeric"
    placeholder="номер"
    aria-label="фильтр по номеру заявки"
  />

  <select v-else-if="column === 'is_active'" v-model="filters.activity" aria-label="фильтр по планированию">
    <option value="">все</option>
    <option value="active">активные</option>
    <option value="inactive">выключенные</option>
  </select>

  <input
    v-else-if="column === 'address'"
    v-model="filters.text"
    placeholder="адрес"
    aria-label="фильтр по адресу"
  />

  <input
    v-else-if="column === 'coordinates'"
    v-model="filters.coordinates"
    placeholder="55.74"
    aria-label="фильтр по координатам"
  />

  <select v-else-if="column === 'work_type'" v-model="filters.workTypeId" aria-label="фильтр по типу работ">
    <option value="">любой</option>
    <option v-for="item in references.work_types" :key="item.id" :value="item.id">{{ item.name }}</option>
  </select>

  <div v-else-if="column === 'duration'" class="range-pair">
    <input
      v-model="filters.durationFrom"
      type="number"
      min="0"
      placeholder="от"
      aria-label="работа на месте не меньше"
    />
    <span>–</span>
    <input
      v-model="filters.durationTo"
      type="number"
      min="0"
      placeholder="до"
      aria-label="работа на месте не больше"
    />
  </div>

  <div v-else-if="column === 'window'" class="time-range">
    <TimeInput v-model="filters.timeFrom" aria-label="окно начинается не раньше" />
    <span>–</span>
    <TimeInput v-model="filters.timeTo" aria-label="окно начинается не позже" />
  </div>

  <select v-else-if="column === 'priority'" v-model="filters.priorityId" aria-label="фильтр по приоритету">
    <option value="">любой</option>
    <option v-for="item in references.priorities" :key="item.id" :value="item.id">{{ item.name }}</option>
  </select>

  <select v-else-if="column === 'transport'" v-model="filters.transportId" aria-label="фильтр по транспорту">
    <option value="">любой</option>
    <option :value="NO_TRANSPORT">не важен</option>
    <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
  </select>

  <button
    v-else-if="column === 'actions'"
    class="link"
    :disabled="activeFilterCount === 0"
    @click="$emit('reset')"
  >
    Сбросить{{ activeFilterCount ? ` (${activeFilterCount})` : '' }}
  </button>
</template>
