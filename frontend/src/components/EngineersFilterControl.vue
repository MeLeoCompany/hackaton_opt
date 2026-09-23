<script setup>
// Фильтр одной колонки исполнителей. Один и тот же компонент стоит в шапке таблицы и в панели
// над картой — поэтому фильтры в обоих видах выглядят и работают одинаково.
import TimeInput from './TimeInput.vue'

defineProps({
  column: { type: String, required: true }, // key колонки из ENGINEER_COLUMNS
  filters: { type: Object, required: true }, // объект из useEngineersView, меняется напрямую
  references: { type: Object, required: true },
  activeFilterCount: { type: Number, required: true },
  // есть что сбрасывать помимо фильтров: отмеченные галочками строки
  checkedCount: { type: Number, default: 0 },
})
defineEmits(['reset'])
</script>

<template>
  <input
    v-if="column === 'id'"
    v-model="filters.idText"
    inputmode="numeric"
    placeholder="номер"
    aria-label="фильтр по номеру исполнителя"
  />

  <input
    v-else-if="column === 'name'"
    v-model="filters.text"
    placeholder="бригада"
    aria-label="фильтр по бригаде"
  />

  <select v-else-if="column === 'transport'" v-model="filters.transportId" aria-label="фильтр по транспорту">
    <option value="">любой</option>
    <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
  </select>

  <select v-else-if="column === 'skills'" v-model="filters.skillId" aria-label="фильтр по навыку">
    <option value="">любой навык</option>
    <option v-for="item in references.skills" :key="item.id" :value="item.id">{{ item.name }}</option>
  </select>

  <select v-else-if="column === 'equipment'" v-model="filters.equipmentId" aria-label="фильтр по оборудованию">
    <option value="">любое</option>
    <option v-for="item in references.equipment ?? []" :key="item.id" :value="item.id">{{ item.name }}</option>
  </select>

  <select v-else-if="column === 'start'" v-model="filters.startKind" aria-label="фильтр по старту">
    <option value="">все</option>
    <option value="office">офис</option>
    <option value="own">своя</option>
  </select>

  <div v-else-if="column === 'shift'" class="time-range">
    <TimeInput v-model="filters.shiftFrom" aria-label="смена начинается не раньше" />
    <span>–</span>
    <TimeInput v-model="filters.shiftTo" aria-label="смена начинается не позже" />
  </div>


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
