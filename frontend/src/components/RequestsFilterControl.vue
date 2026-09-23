<script setup>
// Фильтр одной колонки заявок. Один и тот же компонент стоит в шапке таблицы и в панели
// над картой — поэтому фильтры в обоих видах выглядят и работают одинаково.
import { computed } from 'vue'

import { EQUIPMENT_ANY, NO_TRANSPORT } from '../composables/useRequestsView.js'
import { OVERDUE_FILTER } from '../utils/requestMarks.js'
import { orderedStatuses } from '../utils/requestStatuses.js'

import TimeInput from './TimeInput.vue'

const props = defineProps({
  column: { type: String, required: true }, // key колонки из REQUEST_COLUMNS
  filters: { type: Object, required: true }, // объект из useRequestsView, меняется напрямую
  references: { type: Object, required: true },
  activeFilterCount: { type: Number, required: true },
  // есть что сбрасывать помимо фильтров: отмеченные галочками строки
  checkedCount: { type: Number, default: 0 },
})
defineEmits(['reset'])

// колонка «Тип работ» фильтрует или по типу, или по нужному оборудованию: одно значение
// списка -> одно из двух полей фильтра, второе сбрасывается
const workTypeOrEquipment = computed({
  get() {
    if (props.filters.equipmentId !== '') return `equipment:${props.filters.equipmentId}`
    if (props.filters.workTypeId !== '') return `work:${props.filters.workTypeId}`
    return ''
  },
  set(value) {
    const [kind, id] = value ? value.split(':') : ['', '']
    props.filters.workTypeId = kind === 'work' ? Number(id) : ''
    props.filters.equipmentId = kind === 'equipment' ? (id === EQUIPMENT_ANY ? EQUIPMENT_ANY : Number(id)) : ''
  },
})
</script>

<template>
  <input
    v-if="column === 'id'"
    v-model="filters.idText"
    inputmode="numeric"
    placeholder="номер"
    aria-label="фильтр по номеру заявки"
  />

  <select v-else-if="column === 'status'" v-model="filters.statusId" aria-label="фильтр по статусу">
    <option value="">любой</option>
    <option v-for="status in orderedStatuses(references)" :key="status.id" :value="status.id">{{ status.name }}</option>
    <!-- не статус, а хвост: «Новая» с уже закрытым окном -->
    <option :value="OVERDUE_FILTER">Просроченные</option>
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

  <!-- один список на колонку: тип работ или нужное оборудование — вторая строка фильтров
       сделала бы шапку выше у всей таблицы -->
  <select
    v-else-if="column === 'work_type'"
    v-model="workTypeOrEquipment"
    aria-label="фильтр по типу работ или оборудованию"
  >
    <option value="">любой</option>
    <optgroup label="Тип работ">
      <option v-for="item in references.work_types" :key="item.id" :value="`work:${item.id}`">{{ item.name }}</option>
    </optgroup>
    <optgroup v-if="references.equipment?.length" label="Нужно оборудование">
      <option :value="`equipment:${EQUIPMENT_ANY}`">любое</option>
      <option v-for="item in references.equipment" :key="item.id" :value="`equipment:${item.id}`">
        {{ item.name }}
      </option>
    </optgroup>
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
    :disabled="activeFilterCount === 0 && checkedCount === 0"
    :title="
      checkedCount
        ? 'Сбросить фильтры и снять отметки со строк'
        : 'Сбросить фильтры'
    "
    @click="$emit('reset')"
  >
    Сбросить{{ activeFilterCount ? ` (${activeFilterCount})` : '' }}
  </button>
</template>
